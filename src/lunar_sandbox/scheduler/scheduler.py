"""Core batch scheduler for task evaluation orchestration.

Provides :class:`BatchScheduler` -- the central orchestration engine that
wires together the sandbox pool (Phase 4), episode runner (Phase 2), and
trajectory collection (Phase 3) into runnable single-task and batch
evaluations.

Single task execution (EVAL-01)::

    scheduler = BatchScheduler(pool)
    result = await scheduler.run_single(task, agent_factory)

Batch execution (EVAL-02)::

    scheduler = BatchScheduler(pool, config)
    batch = await scheduler.run_batch(tasks, agent_factory)

Architecture:
  - ``asyncio.Semaphore`` bounds concurrency to ``min(max_workers, pool_capacity)``
  - ``asyncio.gather(return_exceptions=True)`` handles continue-on-failure
  - ``asyncio.Event`` provides fail-fast cancellation across workers
  - ``asyncio.Lock`` protects JSONL streaming writes
  - ``asyncio.wait_for`` implements per-task and per-batch timeouts
  - Tasks sorted by fingerprint before scheduling to maximize pool cache hits
  - Infrastructure errors retried up to ``max_retries``; agent failures never retried
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

import structlog

from lunar_sandbox.episode.runner import AgentAdapter, EpisodeRunner
from lunar_sandbox.scheduler.config import BatchConfig
from lunar_sandbox.scheduler.result import AggregateMetrics, BatchResult, TaskResult
from lunar_sandbox.scheduler.store import BatchResultStore

if TYPE_CHECKING:
    from lunar_sandbox.pool.pool import SandboxPool
    from lunar_sandbox.task.schema import TaskDefinition
    from lunar_sandbox.telemetry.collector import TelemetryCollector

__all__ = ["BatchScheduler"]


class BatchScheduler:
    """Central orchestration engine for single-task and batch evaluation.

    Wires together the sandbox pool, episode runner, and result collection
    into a complete evaluation pipeline with configurable concurrency,
    failure handling, retry logic, and result streaming.

    Args:
        pool: A :class:`~lunar_sandbox.pool.pool.SandboxPool` instance for
            sandbox acquisition and release.
        config: Batch configuration.  Defaults to :class:`BatchConfig`
            with sensible defaults when ``None``.
    """

    __slots__ = ("_pool", "_config", "_log", "_telemetry")

    def __init__(
        self,
        pool: SandboxPool,
        config: BatchConfig | None = None,
        telemetry_collector: TelemetryCollector | None = None,
    ) -> None:
        self._pool = pool
        self._config = config if config is not None else BatchConfig()
        self._log = structlog.get_logger(__name__).bind(component="scheduler")
        self._telemetry = telemetry_collector

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_single(
        self,
        task: TaskDefinition,
        agent_factory: Callable[[TaskDefinition], AgentAdapter],
    ) -> TaskResult:
        """Evaluate a single task end-to-end (EVAL-01).

        Convenience method that runs one task through the full lifecycle:
        pool acquire -> agent factory -> EpisodeRunner -> TaskResult ->
        pool release.

        Args:
            task: The task definition to evaluate.
            agent_factory: Callable that creates a fresh
                :class:`~lunar_sandbox.episode.runner.AgentAdapter`
                for the given task.

        Returns:
            A :class:`~lunar_sandbox.scheduler.result.TaskResult` with
            outcome, timing, and error context.
        """
        return await self._execute_task_with_retry(task, agent_factory)

    async def run_batch(
        self,
        tasks: list[TaskDefinition],
        agent_factory: Callable[[TaskDefinition], AgentAdapter],
        on_task_complete: Callable[[TaskResult], None] | None = None,
        benchmark_name: str = "",
    ) -> BatchResult:
        """Evaluate a batch of tasks with bounded concurrency (EVAL-02).

        Executes all tasks with semaphore-bounded parallelism, fingerprint
        sorting for pool cache optimization, fail-fast support, retry
        logic, JSONL result streaming, and SQLite persistence.

        Args:
            tasks: List of task definitions to evaluate.
            agent_factory: Callable that creates a fresh
                :class:`~lunar_sandbox.episode.runner.AgentAdapter`
                per task.
            on_task_complete: Optional callback invoked after each task
                finishes.  Receives the :class:`TaskResult`.
            benchmark_name: Optional name for the benchmark being run.
                Stored in SQLite for cross-batch querying.

        Returns:
            A complete :class:`~lunar_sandbox.scheduler.result.BatchResult`
            with per-task results, aggregate metrics, and JSONL path.
        """
        config = self._config
        batch_id = f"batch-{uuid4().hex[:12]}"
        batch_start_mono = time.monotonic()
        batch_started_at = time.time()

        self._log.info(
            "batch_started",
            batch_id=batch_id,
            task_count=len(tasks),
            max_workers=config.max_workers,
            fail_fast=config.fail_fast,
        )

        # 1. Detect effective workers
        pool_capacity = self._pool._config.global_max_sandboxes
        effective = min(config.max_workers, pool_capacity)
        if effective < config.max_workers:
            self._log.warning(
                "workers_capped_by_pool",
                requested=config.max_workers,
                pool_capacity=pool_capacity,
                effective=effective,
            )

        # 2. Sort tasks by fingerprint for pool cache optimization
        sorted_tasks = sorted(tasks, key=lambda t: t.derive_fingerprint())

        # 3. Create concurrency primitives
        semaphore = asyncio.Semaphore(effective)
        cancel_event = asyncio.Event()
        jsonl_lock = asyncio.Lock()

        # 4. Open JSONL output file
        config.results_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = config.results_dir / f"{batch_id}.jsonl"
        jsonl_file = jsonl_path.open("w", encoding="utf-8")

        # 5. Define wrapped single-task coroutine
        async def run_single_wrapped(task: TaskDefinition) -> TaskResult:
            async with semaphore:
                # Check cancel event before starting work
                if cancel_event.is_set():
                    return TaskResult.cancelled(task.name)

                result = await self._execute_task_with_retry(
                    task, agent_factory
                )

                # Fail-fast: signal cancellation on error
                if config.fail_fast and result.is_error():
                    cancel_event.set()

                # Stream result to JSONL (lock-protected)
                async with jsonl_lock:
                    line = json.dumps(result.to_dict(), default=str) + "\n"
                    jsonl_file.write(line)
                    jsonl_file.flush()

                # Invoke callback if provided
                if on_task_complete is not None:
                    try:
                        on_task_complete(result)
                    except Exception:
                        self._log.warning(
                            "on_task_complete_callback_error",
                            task_name=task.name,
                            exc_info=True,
                        )

                return result

        # 6. Execute all tasks
        coros = [run_single_wrapped(t) for t in sorted_tasks]

        try:
            if config.batch_timeout > 0:
                raw_results = await asyncio.wait_for(
                    asyncio.gather(*coros, return_exceptions=True),
                    timeout=config.batch_timeout,
                )
            else:
                raw_results = await asyncio.gather(
                    *coros, return_exceptions=True
                )
        except asyncio.TimeoutError:
            # Batch timeout: signal cancellation and collect partial results
            cancel_event.set()
            self._log.warning(
                "batch_timeout",
                batch_id=batch_id,
                timeout=config.batch_timeout,
            )
            raw_results = []

        # 7. Close JSONL file
        jsonl_file.close()

        # Convert raw_results: safety net for unexpected exceptions
        results: list[TaskResult] = []
        for i, r in enumerate(raw_results):
            if isinstance(r, Exception):
                task_name = (
                    sorted_tasks[i].name if i < len(sorted_tasks) else "unknown"
                )
                results.append(
                    TaskResult.from_error(task_name, r, batch_start_mono)
                )
            else:
                results.append(r)

        # 8. Compute aggregate metrics
        batch_duration_ms = (time.monotonic() - batch_start_mono) * 1000
        batch_ended_at = time.time()
        aggregate = AggregateMetrics.from_results(results, batch_duration_ms)

        # 9. Build BatchResult
        batch_result = BatchResult(
            batch_id=batch_id,
            task_results=results,
            aggregate=aggregate,
            config=asdict(config),
            started_at=batch_started_at,
            ended_at=batch_ended_at,
            jsonl_path=str(jsonl_path),
        )

        # 10. Persist to SQLite
        db_path = config.trajectory_dir / "trajectories.db"
        try:
            with BatchResultStore(db_path) as store:
                store.save_batch(batch_result, benchmark_name=benchmark_name)
        except Exception:
            self._log.warning(
                "batch_persist_failed",
                batch_id=batch_id,
                db_path=str(db_path),
                exc_info=True,
            )

        self._log.info(
            "batch_completed",
            batch_id=batch_id,
            total=aggregate.total_tasks,
            passed=aggregate.passed,
            failed=aggregate.failed,
            errors=aggregate.errors,
            pass_rate=aggregate.pass_rate,
            duration_ms=batch_duration_ms,
        )

        return batch_result

    # ------------------------------------------------------------------
    # Internal: task execution
    # ------------------------------------------------------------------

    async def _execute_task(
        self,
        task: TaskDefinition,
        agent_factory: Callable[[TaskDefinition], AgentAdapter],
    ) -> TaskResult:
        """Execute a single task: acquire -> run -> release.

        Acquires a sandbox from the pool by fingerprint, creates the
        agent inside the semaphore-bounded section (avoiding early
        resource allocation), runs the episode, builds the result,
        and releases the sandbox back to the pool.

        Args:
            task: The task definition.
            agent_factory: Factory for creating an agent adapter.

        Returns:
            A :class:`TaskResult` with outcome and timing.
        """
        config = self._config
        fingerprint = task.derive_fingerprint()
        start_time = time.monotonic()
        sandbox = None

        try:
            alloc_start = time.monotonic()
            sandbox = await self._pool.acquire(fingerprint)
            if self._telemetry is not None:
                alloc_ms = (time.monotonic() - alloc_start) * 1000
                self._telemetry.record(
                    "allocate_latency", alloc_ms, fingerprint=fingerprint
                )

            # Create agent inside bounded section (pitfall 6)
            agent = agent_factory(task)

            runner = EpisodeRunner(
                sandbox=sandbox,
                task=task,
                agent_adapter=agent,
                trajectory_dir=config.trajectory_dir,
                telemetry_collector=self._telemetry,
            )

            # Per-task timeout via asyncio.wait_for
            if config.task_timeout > 0:
                episode_result = await asyncio.wait_for(
                    runner.run(),
                    timeout=config.task_timeout,
                )
            else:
                episode_result = await runner.run()

            # Record episode duration for successful completions
            if self._telemetry is not None:
                duration_ms = (time.monotonic() - start_time) * 1000
                self._telemetry.record(
                    "episode_duration", duration_ms, fingerprint=fingerprint
                )

            return TaskResult.from_episode(
                task.name, episode_result, start_time
            )

        except asyncio.TimeoutError:
            self._log.warning(
                "task_timeout",
                task_name=task.name,
                timeout=config.task_timeout,
            )
            return TaskResult.from_timeout(task.name, start_time)

        except Exception as exc:
            self._log.warning(
                "task_error",
                task_name=task.name,
                error=str(exc),
            )
            return TaskResult.from_error(task.name, exc, start_time)

        finally:
            if sandbox is not None:
                try:
                    await self._pool.release(sandbox)
                except Exception:
                    self._log.warning(
                        "pool_release_error",
                        task_name=task.name,
                        exc_info=True,
                    )

    async def _execute_task_with_retry(
        self,
        task: TaskDefinition,
        agent_factory: Callable[[TaskDefinition], AgentAdapter],
    ) -> TaskResult:
        """Execute a task with infra-error retry logic.

        Retries up to ``config.max_retries`` times on infrastructure
        errors (sandbox crash, timeout).  Agent failures and successes
        are returned immediately without retry.

        Args:
            task: The task definition.
            agent_factory: Factory for creating an agent adapter.

        Returns:
            The final :class:`TaskResult` with attempt number set.
        """
        config = self._config
        last_result: TaskResult | None = None

        for attempt in range(1 + config.max_retries):
            result = await self._execute_task(task, agent_factory)

            if not result.is_infra_error() or attempt == config.max_retries:
                result.attempt = attempt + 1
                return result

            last_result = result
            self._log.warning(
                "task_retry",
                task_name=task.name,
                attempt=attempt + 1,
                max_retries=config.max_retries,
                error_type=result.error_type,
                error_message=result.error_message,
            )

        # Should not be reached, but satisfy type checker
        assert last_result is not None  # noqa: S101
        last_result.attempt = config.max_retries + 1
        return last_result

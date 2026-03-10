"""Tests for BatchScheduler orchestration.

Tests run_single and run_batch with mocked pool, agent factory, and
EpisodeRunner. Uses asyncio.run() in test bodies per project convention [02-07].
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from lunar_sandbox.episode.result import EpisodeResult
from lunar_sandbox.episode.state import EpisodeOutcome
from lunar_sandbox.scheduler.config import BatchConfig
from lunar_sandbox.scheduler.result import TaskResult
from lunar_sandbox.scheduler.scheduler import BatchScheduler
from lunar_sandbox.scheduler.store import BatchResultStore
from lunar_sandbox.task.schema import RepoSource, TaskDefinition


# ---------- Helpers ----------


def _make_task(
    name: str = "test-task",
    fingerprint: str = "abc123",
) -> TaskDefinition:
    """Create a TaskDefinition with explicit fingerprint for predictable sorting."""
    return TaskDefinition(
        name=name,
        repo=RepoSource(path="/tmp/fake"),
        instructions="test instructions",
        test_command="echo ok",
        fingerprint=fingerprint,
    )


def _make_episode_result(
    outcome: EpisodeOutcome = EpisodeOutcome.COMPLETED,
    score: float | None = 1.0,
    step_count: int = 3,
    error_message: str | None = None,
) -> EpisodeResult:
    """Create a predictable EpisodeResult."""
    return EpisodeResult(
        episode_id="ep-mock",
        task_name="test-task",
        outcome=outcome,
        score=score,
        step_count=step_count,
        error_message=error_message,
        jsonl_path="/tmp/mock.jsonl",
    )


def _make_mock_pool(capacity: int = 32) -> MagicMock:
    """Create a mock SandboxPool with async acquire/release."""
    pool = MagicMock()
    pool._config = SimpleNamespace(global_max_sandboxes=capacity)

    mock_sandbox = MagicMock()
    mock_sandbox.config = SimpleNamespace(sandbox_id="mock-sb-1")
    mock_sandbox.state = SimpleNamespace(value="running")
    mock_sandbox.layers = SimpleNamespace(merged_dir=None)

    pool.acquire = AsyncMock(return_value=mock_sandbox)
    pool.release = AsyncMock()
    return pool


def _make_agent_factory() -> MagicMock:
    """Create a mock agent factory returning a mock AgentAdapter."""
    agent = MagicMock()
    agent.act = AsyncMock(return_value=("submit", {}))
    factory = MagicMock(return_value=agent)
    return factory


def _make_config(tmpdir: str, **overrides) -> BatchConfig:
    """Create a BatchConfig with temp directories."""
    return BatchConfig(
        trajectory_dir=Path(tmpdir) / "trajectories",
        results_dir=Path(tmpdir) / "results",
        **overrides,
    )


# ---------- run_single ----------


class TestRunSingle:
    """BatchScheduler.run_single() orchestration."""

    def test_success(self) -> None:
        """Single task -> pool.acquire, agent_factory, EpisodeRunner.run, pool.release in order."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir)
                task = _make_task()

                ep_result = _make_episode_result(EpisodeOutcome.COMPLETED, score=1.0)

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = AsyncMock(return_value=ep_result)
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    result = await scheduler.run_single(task, factory)

                assert result.outcome == "pass"
                assert result.score == 1.0

                # Verify pool lifecycle
                pool.acquire.assert_called_once()
                factory.assert_called_once_with(task)
                pool.release.assert_called_once()

        asyncio.run(run())

    def test_infra_error(self) -> None:
        """EpisodeRunner.run raises exception -> TaskResult with outcome='error'."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir, max_retries=0)
                task = _make_task()

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = AsyncMock(
                        side_effect=RuntimeError("sandbox crashed")
                    )
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    result = await scheduler.run_single(task, factory)

                assert result.outcome == "error"
                assert result.error_type == "infra_error"
                assert "sandbox crashed" in result.error_message

        asyncio.run(run())

    def test_timeout(self) -> None:
        """EpisodeRunner.run takes too long -> asyncio.TimeoutError caught."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir, task_timeout=0.01, max_retries=0)
                task = _make_task()

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    async def slow_run():
                        await asyncio.sleep(10)

                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = slow_run
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    result = await scheduler.run_single(task, factory)

                assert result.outcome == "error"
                assert result.error_type == "timeout"

        asyncio.run(run())

    def test_pool_release_on_error(self) -> None:
        """Even when run() raises, pool.release is still called (finally block)."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir, max_retries=0)
                task = _make_task()

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = AsyncMock(
                        side_effect=RuntimeError("boom")
                    )
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    result = await scheduler.run_single(task, factory)

                # Release must be called even on error
                pool.release.assert_called_once()

        asyncio.run(run())


# ---------- run_batch: basic ----------


class TestRunBatchBasic:
    """BatchScheduler.run_batch() basic batch execution."""

    def test_basic(self) -> None:
        """3 tasks -> all run, returns BatchResult with 3 task_results."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir)
                tasks = [
                    _make_task("task-1", "fp-a"),
                    _make_task("task-2", "fp-b"),
                    _make_task("task-3", "fp-c"),
                ]

                ep_result = _make_episode_result()

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = AsyncMock(return_value=ep_result)
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    batch = await scheduler.run_batch(tasks, factory)

                assert len(batch.task_results) == 3
                assert all(r.outcome == "pass" for r in batch.task_results)
                assert batch.aggregate.total_tasks == 3
                assert batch.aggregate.passed == 3

        asyncio.run(run())


# ---------- run_batch: fingerprint sorting ----------


class TestRunBatchFingerprintSorting:
    """Tasks are sorted by fingerprint before execution."""

    def test_sorted_by_fingerprint(self) -> None:
        """Verify pool.acquire receives fingerprints in sorted order."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir, max_workers=1)
                # Intentionally out of order
                tasks = [
                    _make_task("z-task", "fp-z"),
                    _make_task("a-task", "fp-a"),
                    _make_task("m-task", "fp-m"),
                ]

                ep_result = _make_episode_result()

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = AsyncMock(return_value=ep_result)
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    batch = await scheduler.run_batch(tasks, factory)

                # Extract fingerprints from acquire calls
                acquire_calls = pool.acquire.call_args_list
                acquired_fps = [call.args[0] for call in acquire_calls]

                # Should be sorted: fp-a, fp-m, fp-z
                assert acquired_fps == ["fp-a", "fp-m", "fp-z"]

        asyncio.run(run())


# ---------- run_batch: concurrency ----------


class TestRunBatchConcurrency:
    """Semaphore bounds concurrency."""

    def test_concurrency_bounded(self) -> None:
        """max_workers=2, run 5 tasks -> at most 2 concurrent."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir, max_workers=2)

                tasks = [_make_task(f"task-{i}", f"fp-{i:02d}") for i in range(5)]

                concurrent_count = 0
                max_concurrent = 0
                lock = asyncio.Lock()

                ep_result = _make_episode_result()

                async def tracked_run():
                    nonlocal concurrent_count, max_concurrent
                    async with lock:
                        concurrent_count += 1
                        if concurrent_count > max_concurrent:
                            max_concurrent = concurrent_count
                    await asyncio.sleep(0.01)
                    async with lock:
                        concurrent_count -= 1
                    return ep_result

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = tracked_run
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    batch = await scheduler.run_batch(tasks, factory)

                assert len(batch.task_results) == 5
                assert max_concurrent <= 2

        asyncio.run(run())


# ---------- run_batch: fail-fast ----------


class TestRunBatchFailFast:
    """fail_fast=True stops remaining tasks after first error."""

    def test_fail_fast_cancels_remaining(self) -> None:
        """First task errors -> remaining tasks get cancelled outcome."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir, fail_fast=True, max_workers=1, max_retries=0)

                tasks = [
                    _make_task("fail-task", "fp-01"),
                    _make_task("ok-task-1", "fp-02"),
                    _make_task("ok-task-2", "fp-03"),
                ]

                error_result = _make_episode_result(
                    EpisodeOutcome.INFRA_ERROR,
                    score=None,
                    error_message="infra crash",
                )
                success_result = _make_episode_result(EpisodeOutcome.COMPLETED, score=1.0)

                call_count = 0

                async def run_ep():
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return error_result
                    return success_result

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = run_ep
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    batch = await scheduler.run_batch(tasks, factory)

                # At least one task should have error, and cancelled results expected
                error_count = sum(1 for r in batch.task_results if r.outcome == "error")
                assert error_count >= 1

                # Some tasks should be cancelled (skipped due to fail-fast)
                cancelled = [r for r in batch.task_results if r.error_type == "cancelled"]
                assert len(cancelled) >= 1

        asyncio.run(run())


class TestRunBatchContinueOnFailure:
    """fail_fast=False (default) continues after errors."""

    def test_continue_after_error(self) -> None:
        """First task errors -> remaining tasks still run."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir, fail_fast=False, max_workers=1, max_retries=0)

                tasks = [
                    _make_task("error-task", "fp-01"),
                    _make_task("ok-task", "fp-02"),
                ]

                call_count = 0

                async def run_ep():
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return _make_episode_result(
                            EpisodeOutcome.AGENT_ERROR,
                            error_message="agent failed",
                        )
                    return _make_episode_result(EpisodeOutcome.COMPLETED, score=1.0)

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = run_ep
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    batch = await scheduler.run_batch(tasks, factory)

                # Both tasks should have run
                assert len(batch.task_results) == 2
                outcomes = [r.outcome for r in batch.task_results]
                assert "error" in outcomes
                assert "pass" in outcomes

        asyncio.run(run())


# ---------- run_batch: retry ----------


class TestRunBatchRetry:
    """Retry logic: infra errors retried, agent errors not."""

    def test_retry_infra_error(self) -> None:
        """Task fails with infra error, max_retries=1 -> retried once, second succeeds."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir, max_retries=1, max_workers=1)

                tasks = [_make_task("retry-task")]

                call_count = 0

                ep_error = _make_episode_result(
                    EpisodeOutcome.INFRA_ERROR,
                    score=None,
                    error_message="sandbox crashed",
                )
                ep_success = _make_episode_result(EpisodeOutcome.COMPLETED, score=1.0)

                async def run_ep():
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return ep_error
                    return ep_success

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = run_ep
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    batch = await scheduler.run_batch(tasks, factory)

                assert len(batch.task_results) == 1
                assert batch.task_results[0].outcome == "pass"
                assert batch.task_results[0].attempt == 2

        asyncio.run(run())

    def test_no_retry_agent_error(self) -> None:
        """Task fails with agent error -> NOT retried even with max_retries=1."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir, max_retries=1, max_workers=1)

                tasks = [_make_task("agent-fail-task")]

                ep_agent_error = _make_episode_result(
                    EpisodeOutcome.AGENT_ERROR,
                    score=None,
                    error_message="agent protocol violation",
                )

                run_count = 0

                async def run_ep():
                    nonlocal run_count
                    run_count += 1
                    return ep_agent_error

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = run_ep
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    batch = await scheduler.run_batch(tasks, factory)

                assert len(batch.task_results) == 1
                assert batch.task_results[0].outcome == "error"
                assert batch.task_results[0].error_type == "agent_error"
                # Agent error should NOT be retried, so run_count == 1
                assert run_count == 1
                assert batch.task_results[0].attempt == 1

        asyncio.run(run())


# ---------- run_batch: JSONL streaming ----------


class TestRunBatchJsonlStreaming:
    """After batch, verify JSONL file exists and contains valid JSON lines."""

    def test_jsonl_created(self) -> None:

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir)

                tasks = [
                    _make_task("t1", "fp-1"),
                    _make_task("t2", "fp-2"),
                ]

                ep_result = _make_episode_result()

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = AsyncMock(return_value=ep_result)
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    batch = await scheduler.run_batch(tasks, factory)

                # JSONL file should exist
                jsonl_path = Path(batch.jsonl_path)
                assert jsonl_path.exists()

                # Each line should be valid JSON
                lines = jsonl_path.read_text().strip().split("\n")
                assert len(lines) == 2

                for line in lines:
                    data = json.loads(line)
                    assert "task_name" in data
                    assert "outcome" in data

        asyncio.run(run())


# ---------- run_batch: callback ----------


class TestRunBatchCallback:
    """on_task_complete callback is called once per task."""

    def test_callback_invoked(self) -> None:

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir)

                tasks = [
                    _make_task("cb-1", "fp-1"),
                    _make_task("cb-2", "fp-2"),
                    _make_task("cb-3", "fp-3"),
                ]

                ep_result = _make_episode_result()
                callback_results: list[TaskResult] = []

                def on_complete(result: TaskResult) -> None:
                    callback_results.append(result)

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = AsyncMock(return_value=ep_result)
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    batch = await scheduler.run_batch(
                        tasks, factory, on_task_complete=on_complete
                    )

                assert len(callback_results) == 3

        asyncio.run(run())

    def test_callback_error_does_not_propagate(self) -> None:
        """Callback errors are caught and logged, never propagate."""

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir)

                tasks = [_make_task("cb-err", "fp-1")]

                ep_result = _make_episode_result()

                def broken_callback(result: TaskResult) -> None:
                    raise ValueError("callback broke")

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = AsyncMock(return_value=ep_result)
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    # Should NOT raise despite broken callback
                    batch = await scheduler.run_batch(
                        tasks, factory, on_task_complete=broken_callback
                    )

                assert len(batch.task_results) == 1
                assert batch.task_results[0].outcome == "pass"

        asyncio.run(run())


# ---------- run_batch: aggregate metrics ----------


class TestRunBatchAggregateMetrics:
    """BatchResult.aggregate has correct values."""

    def test_aggregate_correct(self) -> None:

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir, max_retries=0)

                tasks = [
                    _make_task("pass-task", "fp-1"),
                    _make_task("fail-task", "fp-2"),
                ]

                call_count = 0

                async def run_ep():
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return _make_episode_result(EpisodeOutcome.COMPLETED, score=1.0)
                    return _make_episode_result(EpisodeOutcome.COMPLETED, score=0.0)

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = run_ep
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    batch = await scheduler.run_batch(tasks, factory)

                assert batch.aggregate.total_tasks == 2
                assert batch.aggregate.passed == 1
                assert batch.aggregate.failed == 1
                assert batch.aggregate.pass_rate == 0.5

        asyncio.run(run())


# ---------- run_batch: SQLite persistence ----------


class TestRunBatchSqlitePersistence:
    """After batch, BatchResultStore has the batch data."""

    def test_persisted_to_sqlite(self) -> None:

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir)

                tasks = [_make_task("persist-task")]

                ep_result = _make_episode_result()

                with patch(
                    "lunar_sandbox.scheduler.scheduler.EpisodeRunner"
                ) as MockRunner:
                    mock_runner_instance = MagicMock()
                    mock_runner_instance.run = AsyncMock(return_value=ep_result)
                    MockRunner.return_value = mock_runner_instance

                    scheduler = BatchScheduler(pool, config)
                    batch = await scheduler.run_batch(
                        tasks, factory, benchmark_name="test-bench"
                    )

                # Check SQLite persistence
                db_path = config.trajectory_dir / "trajectories.db"
                with BatchResultStore(db_path) as store:
                    batches = store.query_batches()
                    assert len(batches) == 1
                    assert batches[0]["batch_id"] == batch.batch_id
                    assert batches[0]["benchmark_name"] == "test-bench"

                    results = store.query_batch_results(batch.batch_id)
                    assert len(results) == 1
                    assert results[0]["task_name"] == "persist-task"

        asyncio.run(run())


# ---------- run_batch: empty tasks ----------


class TestRunBatchEmptyTasks:
    """Empty task list -> BatchResult with 0 tasks, no crash."""

    def test_empty_tasks(self) -> None:

        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                pool = _make_mock_pool()
                factory = _make_agent_factory()
                config = _make_config(tmpdir)

                scheduler = BatchScheduler(pool, config)
                batch = await scheduler.run_batch([], factory)

                assert len(batch.task_results) == 0
                assert batch.aggregate.total_tasks == 0
                assert batch.aggregate.pass_rate == 0.0
                assert batch.aggregate.p50_wall_clock_ms is None

        asyncio.run(run())

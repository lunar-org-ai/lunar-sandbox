"""Core SDK engine: LunarEngine.

Provides :class:`LunarEngine` -- the primary programmatic interface to the
Lunar Sandbox evaluation engine.  Wraps the scheduler, pool, and trajectory
subsystems into a single object with start/stop lifecycle, async run/eval
methods, and sync convenience wrappers.

All subsystem imports are lazy (inside methods, not at module level) to
avoid importing Linux-only code on macOS, per research pitfall 3.

Usage::

    from lunar_sandbox.sdk import LunarEngine, EngineConfig

    engine = LunarEngine(EngineConfig(max_workers=4))
    result = engine.run_sync("tasks/my-task.yaml", my_agent)
    print(result.score)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from lunar_sandbox.sdk.agent_wrapper import normalize_agent
from lunar_sandbox.sdk.config import EngineConfig

if TYPE_CHECKING:
    from lunar_sandbox.pool.pool import SandboxPool
    from lunar_sandbox.scheduler.config import BatchConfig
    from lunar_sandbox.scheduler.result import BatchResult, TaskResult
    from lunar_sandbox.scheduler.scheduler import BatchScheduler
    from lunar_sandbox.scheduler.store import BatchResultStore
    from lunar_sandbox.task.schema import TaskDefinition
    from lunar_sandbox.trajectory.store import TrajectoryStore

__all__ = ["LunarEngine"]


class LunarEngine:
    """Primary programmatic interface to the Lunar Sandbox engine.

    Manages the lifecycle of the sandbox pool, batch scheduler, and
    trajectory store.  Provides async ``run()``/``eval()`` methods
    for single-task and batch evaluation, plus sync wrappers via
    ``asyncio.run()``.

    Args:
        config: Engine configuration.  Uses sensible defaults when
            ``None``.

    Example::

        async with LunarEngine() as engine:
            result = await engine.run("tasks/hello.yaml", my_agent)
    """

    __slots__ = (
        "_config",
        "_pool",
        "_scheduler",
        "_traj_store",
        "_batch_store",
        "_telemetry",
        "_started",
    )

    def __init__(self, config: EngineConfig | None = None) -> None:
        self._config = config if config is not None else EngineConfig()
        self._pool: SandboxPool | None = None
        self._scheduler: BatchScheduler | None = None
        self._traj_store: TrajectoryStore | None = None
        self._batch_store: BatchResultStore | None = None
        self._telemetry: Any = None
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize subsystems: pool, scheduler, trajectory store.

        Creates :class:`SandboxPool`, :class:`BatchScheduler`, and
        :class:`TrajectoryStore` with configs derived from
        :class:`EngineConfig`.  Starts the pool background tasks.

        When ``sandbox_backend`` is ``"docker"`` or ``"auto"`` (with
        native unavailable), the pool uses Docker containers instead
        of Linux kernel primitives.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if self._started:
            return

        # Lazy imports to avoid platform-gate issues on macOS
        from lunar_sandbox.pool.pool import SandboxPool
        from lunar_sandbox.scheduler.scheduler import BatchScheduler
        from lunar_sandbox.scheduler.store import BatchResultStore
        from lunar_sandbox.telemetry.collector import TelemetryCollector
        from lunar_sandbox.trajectory.store import TrajectoryStore

        self._telemetry = TelemetryCollector()

        pool_config = self._make_pool_config()
        sandbox_factory = self._resolve_sandbox_factory()
        self._pool = SandboxPool(
            pool_config,
            sandbox_factory=sandbox_factory,
            telemetry_collector=self._telemetry,
        )
        await self._pool.start()

        batch_config = self._make_batch_config()
        self._scheduler = BatchScheduler(self._pool, batch_config, telemetry_collector=self._telemetry)

        self._traj_store = TrajectoryStore(
            self._config.trajectory_dir / "trajectories.db"
        )
        self._traj_store.open()

        self._batch_store = BatchResultStore(
            self._config.trajectory_dir / "trajectories.db"
        )
        self._batch_store.open()

        self._started = True

    async def stop(self) -> None:
        """Shut down subsystems: pool, trajectory store, batch store.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if not self._started:
            return

        if self._pool is not None:
            await self._pool.shutdown()

        if self._traj_store is not None:
            self._traj_store.close()

        if self._batch_store is not None:
            self._batch_store.close()

        self._started = False

    async def __aenter__(self) -> LunarEngine:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # Public API: single task
    # ------------------------------------------------------------------

    async def run(
        self,
        task: TaskDefinition | str | Path,
        agent: Any,
        **kwargs: Any,
    ) -> TaskResult:
        """Run a single task evaluation.

        Auto-starts the engine if needed.  Accepts a
        :class:`TaskDefinition`, a YAML file path (str or Path), or a
        task name to look up.

        The ``agent`` parameter is normalized via :func:`normalize_agent`:
        it can be an AgentAdapter instance, a class, or a plain callable.

        Args:
            task: Task definition, YAML path, or task name string.
            agent: An AgentAdapter, a class, or a callable.
            **kwargs: Additional keyword arguments (reserved for future use).

        Returns:
            A :class:`TaskResult` with outcome, score, and timing.
        """
        await self._auto_start()

        task_def = self._resolve_task(task)
        agent_factory = normalize_agent(agent)

        assert self._scheduler is not None  # noqa: S101
        return await self._scheduler.run_single(task_def, agent_factory)

    def run_sync(
        self,
        task: TaskDefinition | str | Path,
        agent: Any,
        **kwargs: Any,
    ) -> TaskResult:
        """Synchronous wrapper for :meth:`run`.

        Uses ``asyncio.run()`` per codebase convention.
        """
        return asyncio.run(self.run(task, agent, **kwargs))

    # ------------------------------------------------------------------
    # Public API: batch evaluation
    # ------------------------------------------------------------------

    async def eval(
        self,
        benchmark: Any,
        agent_factory: Any,
        on_task_complete: Callable[[TaskResult], None] | None = None,
        **kwargs: Any,
    ) -> BatchResult:
        """Run a batch evaluation from a benchmark.

        Auto-starts the engine if needed.  Accepts a benchmark path
        (str or Path) or a pre-loaded list of :class:`TaskDefinition`
        objects.

        Args:
            benchmark: Benchmark YAML path, or list of TaskDefinitions.
            agent_factory: An agent factory callable, AgentAdapter class,
                or plain callable.
            on_task_complete: Optional callback invoked after each task
                finishes.
            **kwargs: Additional keyword arguments (reserved for future use).

        Returns:
            A complete :class:`BatchResult` with per-task results and
            aggregate metrics.
        """
        await self._auto_start()

        tasks, benchmark_name = self._resolve_benchmark(benchmark)
        normalized_factory = normalize_agent(agent_factory)

        assert self._scheduler is not None  # noqa: S101
        return await self._scheduler.run_batch(
            tasks,
            normalized_factory,
            on_task_complete=on_task_complete,
            benchmark_name=benchmark_name,
        )

    def eval_sync(
        self,
        benchmark: Any,
        agent_factory: Any,
        on_task_complete: Callable[[TaskResult], None] | None = None,
        **kwargs: Any,
    ) -> BatchResult:
        """Synchronous wrapper for :meth:`eval`.

        Uses ``asyncio.run()`` per codebase convention.
        """
        return asyncio.run(
            self.eval(benchmark, agent_factory, on_task_complete=on_task_complete, **kwargs)
        )

    # ------------------------------------------------------------------
    # Public API: replay and status
    # ------------------------------------------------------------------

    async def replay(self, episode_id: str) -> dict[str, Any]:
        """Query trajectory replay data for an episode.

        Returns episode metadata and step-by-step trajectory data
        from the SQLite trajectory store.

        Args:
            episode_id: The episode identifier to replay.

        Returns:
            Dict with ``"episode"`` metadata and ``"steps"`` list.
            Returns empty episode info if not found.
        """
        await self._auto_start()

        assert self._traj_store is not None  # noqa: S101
        episodes = self._traj_store.query_episodes(episode_id=episode_id)
        steps = self._traj_store.query_steps([episode_id])

        return {
            "episode": episodes[0] if episodes else {},
            "steps": steps,
        }

    async def pool_status(self) -> dict[str, Any]:
        """Return current pool status.

        Returns:
            Dict with running state, metrics, fingerprints, and targets.
        """
        await self._auto_start()

        assert self._pool is not None  # noqa: S101
        return await self._pool.status()

    # ------------------------------------------------------------------
    # Properties for advanced users
    # ------------------------------------------------------------------

    @property
    def pool(self) -> SandboxPool | None:
        """The underlying :class:`SandboxPool`, or ``None`` if not started."""
        return self._pool

    @property
    def telemetry_collector(self) -> Any:
        """The underlying :class:`TelemetryCollector`, or ``None`` if not started."""
        return self._telemetry

    async def telemetry_snapshot(self) -> dict[str, Any]:
        """Compute and return current telemetry snapshot as a dict.

        Returns a dict with metrics, throughput, cache_hit_rate, and any
        threshold breaches.  Returns empty dict if engine not started.

        NOTE: This reads from the collector via snapshot() (non-destructive).
        Do NOT call this AFTER flush_telemetry() -- flush drains the collector.
        For post-run snapshots, use the return value of flush_telemetry() instead.
        """
        await self._auto_start()
        if self._telemetry is None:
            return {}

        from lunar_sandbox.telemetry.compute import compute_snapshot

        samples = self._telemetry.snapshot()
        if not samples:
            return {"metrics": {}, "throughput_eps_per_min": 0.0, "cache_hit_rate": 0.0, "breaches": []}

        # Estimate duration from sample timestamps
        timestamps = [s.timestamp for s in samples]
        duration = max(timestamps) - min(timestamps) if len(timestamps) > 1 else 0.0

        snapshot = compute_snapshot(samples, "current", duration)
        return self._snapshot_to_dict(snapshot)

    def _snapshot_to_dict(self, snapshot: Any) -> dict[str, Any]:
        """Convert a TelemetrySnapshot to a dict with optional threshold breaches."""
        from lunar_sandbox.telemetry.compute import check_thresholds

        result: dict[str, Any] = {
            "run_id": snapshot.run_id,
            "metrics": {},
            "throughput_eps_per_min": snapshot.throughput_eps_per_min,
            "cache_hit_rate": snapshot.cache_hit_rate,
            "total_episodes": snapshot.total_episodes,
        }
        for name, stats in snapshot.metrics.items():
            result["metrics"][name] = {
                "p50": stats.p50,
                "p95": stats.p95,
                "mean": stats.mean,
                "count": stats.count,
                "min": stats.min_val,
                "max": stats.max_val,
            }

        # Check thresholds if configured
        thresholds = self._config.thresholds
        if thresholds is not None:
            breaches = check_thresholds(snapshot, thresholds)
            result["breaches"] = [
                {"metric": b.metric, "threshold": b.threshold, "actual": b.actual, "severity": b.severity}
                for b in breaches
            ]
        else:
            result["breaches"] = []

        return result

    async def flush_telemetry(
        self,
        run_id: str,
        started_at: float,
        ended_at: float,
        total_episodes: int,
    ) -> dict[str, Any]:
        """Flush collected telemetry samples to SQLite and return the snapshot.

        Called after a batch run completes.  Drains all samples from the
        collector, computes the snapshot, persists them with the run metadata,
        and returns the computed snapshot dict.

        IMPORTANT: This drains the collector (destructive).  The returned dict
        IS the snapshot -- do NOT call telemetry_snapshot() after this, as the
        collector will be empty.

        Args:
            run_id: Batch run ID to tag the samples with.
            started_at: Batch start timestamp (time.time()).
            ended_at: Batch end timestamp (time.time()).
            total_episodes: Number of episodes completed.

        Returns:
            Snapshot dict with metrics, throughput, cache_hit_rate, and breaches.
            Empty dict if no telemetry data was collected.
        """
        if self._telemetry is None:
            return {}

        from lunar_sandbox.telemetry.compute import compute_snapshot
        from lunar_sandbox.telemetry.store import TelemetryStore

        samples = self._telemetry.drain()
        if not samples:
            return {"metrics": {}, "throughput_eps_per_min": 0.0, "cache_hit_rate": 0.0, "breaches": []}

        duration = ended_at - started_at if ended_at > started_at else 0.0
        snapshot = compute_snapshot(samples, run_id, duration)

        # Convert to dict BEFORE persisting (we need the snapshot object for both)
        snapshot_data = self._snapshot_to_dict(snapshot)

        db_path = self._config.trajectory_dir / "trajectories.db"
        store = TelemetryStore(db_path)
        store.open()
        try:
            store.save_run(
                run_id=run_id,
                samples=samples,
                started_at=started_at,
                ended_at=ended_at,
                total_episodes=total_episodes,
                throughput=snapshot.throughput_eps_per_min,
                cache_hit_rate=snapshot.cache_hit_rate,
            )
        finally:
            store.close()

        return snapshot_data

    @property
    def trajectory_store(self) -> TrajectoryStore | None:
        """The underlying :class:`TrajectoryStore`, or ``None`` if not started."""
        return self._traj_store

    @property
    def batch_store(self) -> BatchResultStore | None:
        """The underlying :class:`BatchResultStore`, or ``None`` if not started."""
        return self._batch_store

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _auto_start(self) -> None:
        """Start the engine if not already started."""
        if not self._started:
            await self.start()

    def _make_pool_config(self) -> Any:
        """Derive a :class:`PoolConfig` from :class:`EngineConfig`."""
        from lunar_sandbox.pool.config import PoolConfig

        return PoolConfig(
            global_max_sandboxes=self._config.effective_pool_size(),
            data_root=self._config.data_root,
        )

    def _make_batch_config(self) -> Any:
        """Derive a :class:`BatchConfig` from :class:`EngineConfig`."""
        from lunar_sandbox.scheduler.config import BatchConfig

        return BatchConfig(
            max_workers=self._config.effective_workers(),
            task_timeout=self._config.task_timeout,
            batch_timeout=self._config.batch_timeout,
            max_retries=self._config.max_retries,
            fail_fast=self._config.fail_fast,
            trajectory_dir=self._config.trajectory_dir,
            results_dir=self._config.results_dir,
        )

    def _resolve_sandbox_factory(self) -> Callable[..., object] | None:
        """Resolve which sandbox factory to use based on config.

        Returns:
            A sandbox factory callable for Docker, or None for native default.
        """
        backend = self._config.sandbox_backend

        if backend == "docker":
            return self._make_docker_factory()

        if backend == "native":
            return None  # Pool uses default native factory

        # "auto": try native, fall back to Docker
        try:
            from lunar_sandbox.kernel.detect import require_kernel_features

            require_kernel_features()
            return None  # Native works
        except Exception:
            return self._make_docker_factory()

    def _make_docker_factory(self) -> Callable[..., object]:
        """Create a Docker sandbox factory callable for the pool."""
        import structlog

        from lunar_sandbox.sandbox.docker_config import (
            DockerResourceLimits,
            DockerSandboxConfig,
        )
        from lunar_sandbox.sandbox.docker_sandbox import DockerSandbox

        _log = structlog.get_logger(__name__)

        image = self._config.docker_image
        # For Docker, use a user-writable directory instead of /var/lib/...
        data_root_str = self._config.data_root
        data_root_path = Path(data_root_str) if isinstance(data_root_str, str) else data_root_str
        if str(data_root_path).startswith("/var/lib"):
            data_root_path = Path.home() / ".lunar-sandbox" / "containers"

        def factory(fingerprint: str) -> DockerSandbox:
            from uuid import uuid4

            sandbox_id = f"lunar-{uuid4().hex[:8]}"
            config = DockerSandboxConfig(
                sandbox_id=sandbox_id,
                image=image,
                data_root=data_root_path,
            )
            sandbox = DockerSandbox(config)
            sandbox.create()
            _log.info(
                "docker_sandbox_created_by_factory",
                sandbox_id=sandbox_id,
                fingerprint=fingerprint,
            )
            return sandbox

        return factory

    def _resolve_task(self, task: TaskDefinition | str | Path) -> TaskDefinition:
        """Resolve a task argument to a :class:`TaskDefinition`.

        Accepts:
          - A :class:`TaskDefinition` instance (returned as-is).
          - A string or :class:`Path` pointing to a YAML file.

        Args:
            task: Task definition or path to a YAML task file.

        Returns:
            A validated :class:`TaskDefinition`.
        """
        from lunar_sandbox.task.schema import TaskDefinition

        if isinstance(task, TaskDefinition):
            return task

        from lunar_sandbox.task.loader import load_task

        return load_task(Path(task))

    def _resolve_benchmark(
        self, benchmark: Any
    ) -> tuple[list[TaskDefinition], str]:
        """Resolve a benchmark argument to a list of task definitions.

        Accepts:
          - A string or :class:`Path` pointing to a benchmark YAML file.
          - A list of :class:`TaskDefinition` objects (returned as-is).

        Args:
            benchmark: Benchmark YAML path or list of TaskDefinitions.

        Returns:
            Tuple of ``(task_definitions, benchmark_name)``.
        """
        if isinstance(benchmark, list):
            return benchmark, ""

        from lunar_sandbox.scheduler.benchmark import load_benchmark

        bench_def, tasks = load_benchmark(Path(benchmark))
        return tasks, bench_def.name

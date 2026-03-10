"""Core sandbox pool manager with acquire/release and FIFO queuing.

SandboxPool maintains pre-warmed sandbox instances keyed by fingerprint,
delivering sub-millisecond checkout via dict pop + health check. When the
idle pool has no match, sandboxes are created on-demand with semaphore
rate-limiting to prevent thundering herd.

Key design invariants:
  - asyncio.Lock protects all pool state mutations (dicts, counters)
  - Lock is NEVER held during blocking operations (create, destroy, reset)
  - asyncio.Condition provides FIFO fairness for burst demand at cap
  - Background reset runs as a fire-and-forget task via create_task
  - All sandbox I/O is offloaded via asyncio.to_thread
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import TYPE_CHECKING, Callable
from uuid import uuid4

import structlog

from lunar_sandbox.pool.config import PoolConfig
from lunar_sandbox.pool.entry import PoolEntry
from lunar_sandbox.pool.errors import PoolExhaustedError, PoolShuttingDownError
from lunar_sandbox.pool.memory import get_memory_pressure
from lunar_sandbox.pool.metrics import PoolMetrics

if TYPE_CHECKING:
    from lunar_sandbox.sandbox.sandbox import Sandbox

__all__ = ["SandboxPool"]


class SandboxPool:
    """Async pool manager for sandbox instances.

    Provides ``acquire()`` / ``release()`` for sandbox checkout with:
      - Per-fingerprint idle pools (OrderedDict for LRU)
      - Health + TTL gating on every checkout
      - FIFO queuing under global cap via asyncio.Condition
      - Semaphore-guarded creation to prevent thundering herd
      - Fire-and-forget background reset on release

    Args:
        config: Pool configuration with limits and thresholds.
        sandbox_factory: Optional async callable ``(fingerprint) -> Sandbox``
            for dependency injection. When None, the pool creates Sandbox
            instances using a default factory.
    """

    __slots__ = (
        "_config",
        "_idle_pools",
        "_active",
        "_known_fingerprints",
        "_targets",
        "_metrics",
        "_lock",
        "_condition",
        "_creation_semaphore",
        "_shutdown_event",
        "_sandbox_factory",
        "_replenish_task",
        "_log",
    )

    def __init__(
        self,
        config: PoolConfig,
        sandbox_factory: Callable[..., object] | None = None,
    ) -> None:
        self._config = config
        self._idle_pools: dict[str, OrderedDict[str, PoolEntry]] = {}
        self._active: dict[str, PoolEntry] = {}
        self._known_fingerprints: set[str] = set()
        self._targets: dict[str, int] = {}
        self._metrics = PoolMetrics()
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)
        self._creation_semaphore = asyncio.Semaphore(
            config.max_concurrent_creations
        )
        self._shutdown_event = asyncio.Event()
        self._sandbox_factory = sandbox_factory
        self._replenish_task: asyncio.Task[None] | None = None
        self._log = structlog.get_logger(__name__).bind(component="pool")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(self, fingerprint: str) -> Sandbox:
        """Acquire a sandbox for the given fingerprint.

        Happy path (pool hit): pops a healthy, non-expired sandbox from
        the idle pool -- sub-millisecond.

        Pool miss: creates a sandbox on-demand, blocking the caller
        until creation completes (~50-200 ms).

        At global cap: waits on asyncio.Condition for a release, then
        retries checkout or creation. FIFO fairness is guaranteed by
        asyncio.Condition's internal waiter queue.

        Args:
            fingerprint: 16-hex-char environment fingerprint.

        Returns:
            A Sandbox in RUNNING state ready for use.

        Raises:
            PoolShuttingDownError: If pool shutdown has been initiated.
            PoolExhaustedError: If at global cap with critical memory
                pressure and no idle sandboxes available.
        """
        if self._shutdown_event.is_set():
            raise PoolShuttingDownError(
                "Pool is shutting down -- acquire() rejected"
            )

        async with self._condition:
            # Try fast-path checkout from idle pool
            sandbox = await self._try_checkout(fingerprint)
            if sandbox is not None:
                self._metrics.record_hit(fingerprint)
                self._metrics.active_count = len(self._active)
                self._metrics.idle_count = self._total_idle()
                self._condition.notify()
                self._log.debug(
                    "pool_hit",
                    fingerprint=fingerprint,
                    idle_remaining=self._total_idle(),
                )
                return sandbox

            # Miss -- determine cold start status
            cold_start = fingerprint not in self._known_fingerprints
            self._known_fingerprints.add(fingerprint)
            if cold_start:
                self._targets[fingerprint] = min(
                    self._config.per_fingerprint_soft_limit, 2
                )

            # Global cap enforcement with FIFO wait
            while self._at_global_cap() and not self._has_idle(fingerprint):
                # Check for critical memory + all active = exhausted
                if self._at_global_cap() and self._total_idle() == 0:
                    pressure = get_memory_pressure()
                    if pressure >= self._config.memory_pressure_threshold:
                        raise PoolExhaustedError(
                            f"Pool exhausted: at global cap "
                            f"({self._config.global_max_sandboxes}), "
                            f"no idle sandboxes, memory pressure "
                            f"{pressure:.1%}"
                        )

                self._log.debug(
                    "pool_waiting_at_cap",
                    fingerprint=fingerprint,
                    pool_size=self._metrics.pool_size,
                    cap=self._config.global_max_sandboxes,
                )
                await self._condition.wait()

                # Check shutdown after wake
                if self._shutdown_event.is_set():
                    raise PoolShuttingDownError(
                        "Pool is shutting down -- acquire() rejected"
                    )

                # Retry checkout after being notified
                sandbox = await self._try_checkout(fingerprint)
                if sandbox is not None:
                    self._metrics.record_hit(fingerprint)
                    self._metrics.active_count = len(self._active)
                    self._metrics.idle_count = self._total_idle()
                    self._condition.notify()
                    return sandbox

        # Outside lock: create sandbox on-demand
        sandbox = await self._create_sandbox(fingerprint)

        # Re-acquire lock to register in active set
        async with self._condition:
            entry = PoolEntry(
                sandbox=sandbox,
                sandbox_id=sandbox.config.sandbox_id,
                fingerprint=fingerprint,
            )
            entry.mark_used()
            self._active[sandbox.config.sandbox_id] = entry
            self._metrics.record_miss(fingerprint, cold_start=cold_start)
            self._metrics.active_count = len(self._active)
            self._metrics.idle_count = self._total_idle()
            self._condition.notify()

        self._log.info(
            "pool_miss",
            fingerprint=fingerprint,
            cold_start=cold_start,
            sandbox_id=sandbox.config.sandbox_id,
        )
        return sandbox

    async def release(self, sandbox: Sandbox) -> None:
        """Release a sandbox back to the pool for background reset.

        Returns immediately -- the caller never waits for the reset.
        The sandbox is reset in a background task; if reset succeeds
        and the sandbox is healthy, it returns to the idle pool.

        Args:
            sandbox: The sandbox to release (must have been acquired).
        """
        async with self._condition:
            sid = sandbox.config.sandbox_id
            entry = self._active.pop(sid, None)
            if entry is None:
                self._log.warning(
                    "pool_release_unknown_sandbox", sandbox_id=sid
                )
                return
            self._metrics.active_count = len(self._active)

        # Fire-and-forget background reset
        asyncio.create_task(self._background_reset(entry))

        self._log.debug(
            "pool_released",
            sandbox_id=sid,
            fingerprint=entry.fingerprint,
        )

    async def start(self) -> None:
        """Start the pool manager.

        Placeholder for Plan 04 which adds background replenishment
        and eviction sweep tasks.
        """
        self._log.info("pool_started")

    @property
    def metrics(self) -> PoolMetrics:
        """Current pool metrics for external consumption."""
        return self._metrics

    # ------------------------------------------------------------------
    # Internal: checkout
    # ------------------------------------------------------------------

    async def _try_checkout(self, fingerprint: str) -> Sandbox | None:
        """Try to check out an idle sandbox for the fingerprint.

        Iterates the per-fingerprint idle pool in LRU order (oldest
        first). Destroys unhealthy or TTL-expired entries encountered
        along the way. Returns the first valid sandbox or None.

        MUST be called with self._lock held.
        Schedules destroy in background (does not hold lock for destroy).
        """
        fp_pool = self._idle_pools.get(fingerprint)
        if not fp_pool:
            return None

        while fp_pool:
            # Pop the LRU entry (oldest insertion = first)
            sid, entry = fp_pool.popitem(last=False)

            # Health gate
            if not entry.sandbox.is_healthy():
                self._metrics.total_health_check_failures += 1
                self._metrics.pool_size -= 1
                self._log.debug(
                    "pool_checkout_unhealthy",
                    sandbox_id=sid,
                    fingerprint=fingerprint,
                )
                # Schedule destroy outside lock
                asyncio.create_task(self._destroy_entry(entry))
                continue

            # TTL gate
            if entry.is_expired(self._config.ttl_seconds):
                self._metrics.total_ttl_expiries += 1
                self._metrics.pool_size -= 1
                self._log.debug(
                    "pool_checkout_ttl_expired",
                    sandbox_id=sid,
                    fingerprint=fingerprint,
                )
                asyncio.create_task(self._destroy_entry(entry))
                continue

            # Valid entry -- mark used and move to active
            entry.mark_used()
            self._active[sid] = entry
            return entry.sandbox

        return None

    # ------------------------------------------------------------------
    # Internal: creation
    # ------------------------------------------------------------------

    async def _create_sandbox(self, fingerprint: str) -> Sandbox:
        """Create a new sandbox, rate-limited by semaphore.

        Runs sandbox creation in a thread to avoid blocking the event
        loop. Tracks creation metrics and cleans up on failure.

        Args:
            fingerprint: Environment fingerprint for the new sandbox.

        Returns:
            A Sandbox in RUNNING state.

        Raises:
            Exception: Re-raises any creation failure after cleanup.
        """
        async with self._creation_semaphore:
            self._metrics.pending_creations += 1
            try:
                sandbox = await self._invoke_factory(fingerprint)
                self._metrics.total_creations += 1
                self._metrics.pool_size += 1
                return sandbox
            except Exception:
                self._metrics.total_creation_failures += 1
                self._log.exception(
                    "pool_creation_failed", fingerprint=fingerprint
                )
                raise
            finally:
                self._metrics.pending_creations -= 1

    async def _invoke_factory(self, fingerprint: str) -> Sandbox:
        """Invoke the sandbox factory or default creation path.

        When a custom factory is provided (DI), calls it directly.
        Otherwise builds a SandboxConfig and creates a Sandbox via
        asyncio.to_thread.
        """
        if self._sandbox_factory is not None:
            result = self._sandbox_factory(fingerprint)
            # Support both sync and async factories
            if asyncio.iscoroutine(result):
                return await result  # type: ignore[return-value]
            return result  # type: ignore[return-value]

        # Default factory: build config and create in thread
        from lunar_sandbox.sandbox.config import SandboxConfig
        from lunar_sandbox.sandbox.sandbox import Sandbox

        sandbox_id = f"pool-{uuid4().hex[:8]}"
        config = SandboxConfig(
            sandbox_id=sandbox_id,
            data_root=self._config.data_root,
        )
        sandbox = Sandbox(config)
        await asyncio.to_thread(sandbox.create)
        return sandbox

    # ------------------------------------------------------------------
    # Internal: background reset
    # ------------------------------------------------------------------

    async def _background_reset(self, entry: PoolEntry) -> None:
        """Reset a sandbox in the background and return to idle pool.

        Offloads the blocking reset() call to a thread. If reset
        succeeds and the sandbox remains healthy, it is placed back
        into the idle pool and waiters are notified. On failure, the
        sandbox is destroyed.
        """
        try:
            reset_ok = await asyncio.to_thread(entry.sandbox.reset)
        except Exception:
            self._log.exception(
                "pool_reset_exception",
                sandbox_id=entry.sandbox_id,
            )
            reset_ok = False

        if reset_ok and entry.sandbox.is_healthy():
            async with self._condition:
                fp_pool = self._idle_pools.setdefault(
                    entry.fingerprint, OrderedDict()
                )
                # Insert at end (most recently reset = freshest)
                fp_pool[entry.sandbox_id] = entry
                self._metrics.idle_count = self._total_idle()
                self._condition.notify()

            self._log.debug(
                "pool_reset_ok",
                sandbox_id=entry.sandbox_id,
                fingerprint=entry.fingerprint,
            )
        else:
            self._metrics.pool_size -= 1
            self._log.warning(
                "pool_reset_failed_destroying",
                sandbox_id=entry.sandbox_id,
                fingerprint=entry.fingerprint,
            )
            await self._destroy_entry(entry)

            # Notify waiters so they can try creating
            async with self._condition:
                self._metrics.idle_count = self._total_idle()
                self._condition.notify()

    # ------------------------------------------------------------------
    # Internal: destroy helper
    # ------------------------------------------------------------------

    async def _destroy_entry(self, entry: PoolEntry) -> None:
        """Destroy a sandbox entry via asyncio.to_thread.

        Catches and logs exceptions -- destruction failures should not
        propagate to callers.
        """
        try:
            await asyncio.to_thread(entry.sandbox.destroy)
        except Exception:
            self._log.exception(
                "pool_destroy_failed",
                sandbox_id=entry.sandbox_id,
            )

    # ------------------------------------------------------------------
    # Internal: capacity helpers
    # ------------------------------------------------------------------

    def _total_idle(self) -> int:
        """Count total idle sandboxes across all fingerprints."""
        return sum(len(pool) for pool in self._idle_pools.values())

    def _has_idle(self, fingerprint: str) -> bool:
        """Check if there are idle sandboxes for a fingerprint."""
        fp_pool = self._idle_pools.get(fingerprint)
        return bool(fp_pool)

    def _at_global_cap(self) -> bool:
        """Check if total sandboxes (idle + active + pending) >= cap."""
        return self._metrics.pool_size >= self._config.global_max_sandboxes

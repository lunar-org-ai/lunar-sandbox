"""Integration tests for SandboxPool with mock sandbox factory.

Tests pool acquire/release lifecycle, cold starts, pool hits, health checks,
FIFO ordering, shutdown behavior, metrics, and failed-reset scenarios.
Uses asyncio.run() in test bodies per project convention [02-07].
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from lunar_sandbox.pool.config import PoolConfig
from lunar_sandbox.pool.errors import PoolShuttingDownError
from lunar_sandbox.pool.pool import SandboxPool


# ---------- Mock sandbox factory ----------

_SANDBOX_COUNTER = 0


def _reset_counter() -> None:
    global _SANDBOX_COUNTER
    _SANDBOX_COUNTER = 0


class MockSandbox:
    """Simulates the Sandbox interface for pool testing.

    Provides config.sandbox_id, create(), reset(), destroy(), is_healthy().
    """

    def __init__(self, sandbox_id: str, *, healthy: bool = True, reset_ok: bool = True) -> None:
        self.config = SimpleNamespace(sandbox_id=sandbox_id)
        self._healthy = healthy
        self._reset_ok = reset_ok
        self.created = False
        self.destroyed = False
        self.reset_count = 0

    def create(self) -> None:
        self.created = True

    def reset(self) -> bool:
        self.reset_count += 1
        return self._reset_ok

    def destroy(self) -> None:
        self.destroyed = True

    def is_healthy(self) -> bool:
        return self._healthy


def _make_factory(*, healthy: bool = True, reset_ok: bool = True):
    """Create a factory function that produces MockSandbox instances with unique IDs."""

    def factory(fingerprint: str) -> MockSandbox:
        global _SANDBOX_COUNTER
        _SANDBOX_COUNTER += 1
        return MockSandbox(
            sandbox_id=f"mock-{_SANDBOX_COUNTER}",
            healthy=healthy,
            reset_ok=reset_ok,
        )

    return factory


def _make_pool(
    global_max: int = 32,
    per_fp: int = 8,
    factory=None,
    **kwargs,
) -> SandboxPool:
    """Create a SandboxPool with test-friendly config."""
    cfg = PoolConfig(
        global_max_sandboxes=global_max,
        per_fingerprint_soft_limit=per_fp,
        idle_timeout_seconds=120.0,
        ttl_seconds=300.0,
        replenish_interval_seconds=60.0,  # Long interval to avoid background interference
        **kwargs,
    )
    if factory is None:
        factory = _make_factory()
    return SandboxPool(config=cfg, sandbox_factory=factory)


# ---------- Test: cold start ----------


class TestAcquireColdStart:
    """First acquire for a fingerprint creates on-demand (cold start)."""

    def test_acquire_cold_start(self) -> None:
        _reset_counter()

        async def run() -> None:
            pool = _make_pool()
            sb = await pool.acquire("fp-new")
            assert sb is not None
            assert sb.config.sandbox_id == "mock-1"
            # Metrics: 1 miss, 1 cold start
            metrics = pool.metrics
            assert metrics.total_misses == 1
            assert metrics.total_cold_starts == 1
            assert metrics.total_hits == 0

        asyncio.run(run())


# ---------- Test: pool hit ----------


class TestAcquirePoolHit:
    """Acquire after release should be a pool hit."""

    def test_acquire_after_release_is_hit(self) -> None:
        _reset_counter()

        async def run() -> None:
            pool = _make_pool()
            sb1 = await pool.acquire("fp1")
            await pool.release(sb1)
            # Wait for background reset to complete
            await asyncio.sleep(0.05)

            sb2 = await pool.acquire("fp1")
            assert pool.metrics.total_hits == 1
            # Should reuse the same sandbox
            assert sb2.config.sandbox_id == sb1.config.sandbox_id

        asyncio.run(run())


# ---------- Test: release returns to pool ----------


class TestReleaseReturnsToPool:
    """Release + re-acquire after background reset is a pool hit."""

    def test_release_and_reacquire(self) -> None:
        _reset_counter()

        async def run() -> None:
            pool = _make_pool()
            sb1 = await pool.acquire("fp-a")
            await pool.release(sb1)
            await asyncio.sleep(0.05)  # Wait for background reset

            sb2 = await pool.acquire("fp-a")
            # Second acquire should be a hit
            assert pool.metrics.total_hits == 1
            assert pool.metrics.total_misses == 1  # First acquire was a miss

        asyncio.run(run())


# ---------- Test: unhealthy sandbox skipped ----------


class TestAcquireUnhealthySkipped:
    """Unhealthy sandbox in idle pool is destroyed, new one created."""

    def test_unhealthy_skipped_and_destroyed(self) -> None:
        _reset_counter()

        async def run() -> None:
            # First factory creates a healthy sandbox, second creates one that
            # will become unhealthy after reset
            sandboxes: list[MockSandbox] = []
            call_count = 0

            def factory(fingerprint: str) -> MockSandbox:
                nonlocal call_count
                call_count += 1
                sb = MockSandbox(sandbox_id=f"mock-{call_count}", healthy=True)
                sandboxes.append(sb)
                return sb

            pool = _make_pool(factory=factory)

            # Acquire and release -> sandbox goes to idle pool via background reset
            sb1 = await pool.acquire("fp1")
            await pool.release(sb1)
            await asyncio.sleep(0.05)

            # Now mark the sandbox as unhealthy
            sandboxes[0]._healthy = False

            # Next acquire should skip unhealthy, create new
            sb2 = await pool.acquire("fp1")
            assert sb2.config.sandbox_id == "mock-2"
            assert pool.metrics.total_health_check_failures == 1

        asyncio.run(run())


# ---------- Test: FIFO ordering ----------


class TestFifoOrdering:
    """When pool is at global cap, concurrent acquires queue in FIFO order."""

    def test_fifo_first_waiter_gets_first(self) -> None:
        """The first waiter to call acquire() is the first to succeed."""
        _reset_counter()

        async def run() -> None:
            # Pool with room for 3 sandboxes so each waiter can create
            # on-demand once they stop being blocked at cap
            pool = _make_pool(global_max=3, per_fp=3)
            await pool.start()

            results: list[int] = []
            barrier = asyncio.Event()

            # Fill all 3 slots to reach cap
            sb1 = await pool.acquire("fp1")
            sb2 = await pool.acquire("fp1")
            sb3 = await pool.acquire("fp1")

            async def waiter(idx: int) -> None:
                acquired_sb = await pool.acquire("fp1")
                results.append(idx)

            # Create 3 waiters that will queue on condition
            tasks = [asyncio.create_task(waiter(i)) for i in range(3)]
            await asyncio.sleep(0.05)  # Let them queue up

            # Release one at a time and let the FIFO waiter proceed
            await pool.release(sb1)
            await asyncio.sleep(0.05)  # Let first waiter complete

            await pool.release(sb2)
            await asyncio.sleep(0.05)

            await pool.release(sb3)
            await asyncio.sleep(0.05)

            await asyncio.gather(*tasks)

            # Verify all 3 waiters completed
            assert sorted(results) == [0, 1, 2]
            # First waiter should be first to acquire (FIFO)
            assert results[0] == 0

            await pool.shutdown()

        asyncio.run(run())


# ---------- Test: shutdown prevents acquire ----------


class TestShutdownPreventsAcquire:
    """After shutdown, acquire raises PoolShuttingDownError."""

    def test_acquire_after_shutdown_raises(self) -> None:
        _reset_counter()

        async def run() -> None:
            pool = _make_pool()
            await pool.start()
            await pool.shutdown()

            raised = False
            try:
                await pool.acquire("fp1")
            except PoolShuttingDownError:
                raised = True
            assert raised is True

        asyncio.run(run())


# ---------- Test: shutdown destroys idle ----------


class TestShutdownDestroysIdle:
    """Shutdown calls destroy on all idle sandboxes."""

    def test_shutdown_destroys_all_idle(self) -> None:
        _reset_counter()
        created_sandboxes: list[MockSandbox] = []

        def tracking_factory(fingerprint: str) -> MockSandbox:
            global _SANDBOX_COUNTER
            _SANDBOX_COUNTER += 1
            sb = MockSandbox(sandbox_id=f"mock-{_SANDBOX_COUNTER}")
            created_sandboxes.append(sb)
            return sb

        async def run() -> None:
            pool = _make_pool(factory=tracking_factory)
            await pool.start()

            # Acquire and release two sandboxes -> both go to idle pool
            sb1 = await pool.acquire("fp1")
            sb2 = await pool.acquire("fp2")
            await pool.release(sb1)
            await pool.release(sb2)
            await asyncio.sleep(0.05)  # Wait for background resets

            await pool.shutdown()

            # Both should have been destroyed
            destroyed_count = sum(1 for sb in created_sandboxes if sb.destroyed)
            assert destroyed_count == 2

        asyncio.run(run())


# ---------- Test: pool lifecycle ----------


class TestPoolLifecycle:
    """start/status/shutdown lifecycle."""

    def test_start_status_shutdown(self) -> None:
        _reset_counter()

        async def run() -> None:
            pool = _make_pool()

            # Before start -- not running
            status = await pool.status()
            assert status["running"] is False

            # Start
            await pool.start()
            status = await pool.status()
            assert status["running"] is True

            # Shutdown
            await pool.shutdown()
            status = await pool.status()
            assert status["running"] is False

        asyncio.run(run())


# ---------- Test: metrics snapshot ----------


class TestMetricsSnapshot:
    """Verify metrics after a sequence of operations."""

    def test_metrics_after_operations(self) -> None:
        _reset_counter()

        async def run() -> None:
            pool = _make_pool()

            # Cold start
            sb1 = await pool.acquire("fp1")
            # Release and re-acquire (pool hit)
            await pool.release(sb1)
            await asyncio.sleep(0.05)
            sb2 = await pool.acquire("fp1")

            snap = pool.metrics.snapshot()
            assert snap["total_misses"] == 1
            assert snap["total_cold_starts"] == 1
            assert snap["total_hits"] == 1
            assert snap["total_creations"] == 1
            assert snap["hit_rate"] == 0.5  # 1 hit / 2 acquisitions
            assert snap["hits_by_fingerprint"]["fp1"] == 1
            assert snap["misses_by_fingerprint"]["fp1"] == 1
            assert snap["cold_starts_by_fingerprint"]["fp1"] == 1

        asyncio.run(run())


# ---------- Test: background reset failure ----------


class TestBackgroundResetFailure:
    """When reset() returns False, sandbox is destroyed, not returned to pool."""

    def test_failed_reset_destroys_sandbox(self) -> None:
        _reset_counter()
        created_sandboxes: list[MockSandbox] = []

        def failing_reset_factory(fingerprint: str) -> MockSandbox:
            global _SANDBOX_COUNTER
            _SANDBOX_COUNTER += 1
            sb = MockSandbox(sandbox_id=f"mock-{_SANDBOX_COUNTER}", reset_ok=False)
            created_sandboxes.append(sb)
            return sb

        async def run() -> None:
            pool = _make_pool(factory=failing_reset_factory)

            # Acquire and release
            sb1 = await pool.acquire("fp1")
            await pool.release(sb1)
            await asyncio.sleep(0.05)  # Wait for background reset attempt

            # Reset failed -> sandbox destroyed, not in idle pool
            assert created_sandboxes[0].destroyed is True

            # Second acquire should be another miss (no sandbox in idle pool)
            sb2 = await pool.acquire("fp1")
            assert pool.metrics.total_misses == 2
            assert pool.metrics.total_hits == 0
            # Should be a new sandbox
            assert sb2.config.sandbox_id != sb1.config.sandbox_id

        asyncio.run(run())


# ---------- Test: multiple fingerprints ----------


class TestMultipleFingerprints:
    """Pool maintains separate idle pools per fingerprint."""

    def test_different_fingerprints_independent(self) -> None:
        _reset_counter()

        async def run() -> None:
            pool = _make_pool()

            sb1 = await pool.acquire("fp-alpha")
            sb2 = await pool.acquire("fp-beta")
            await pool.release(sb1)
            await pool.release(sb2)
            await asyncio.sleep(0.05)

            # Acquire fp-alpha -- should hit from fp-alpha's idle pool
            sb3 = await pool.acquire("fp-alpha")
            assert sb3.config.sandbox_id == sb1.config.sandbox_id

            # Acquire fp-beta -- should hit from fp-beta's idle pool
            sb4 = await pool.acquire("fp-beta")
            assert sb4.config.sandbox_id == sb2.config.sandbox_id

            assert pool.metrics.total_hits == 2

        asyncio.run(run())


# ---------- Test: release unknown sandbox ----------


class TestReleaseUnknownSandbox:
    """Releasing an unknown sandbox does not crash."""

    def test_release_unknown_is_noop(self) -> None:
        _reset_counter()

        async def run() -> None:
            pool = _make_pool()
            unknown = MockSandbox(sandbox_id="unknown-1")
            # Should not raise
            await pool.release(unknown)

        asyncio.run(run())

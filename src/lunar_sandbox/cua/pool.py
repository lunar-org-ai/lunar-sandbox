"""CUA container pool with pre-warm, CUA-specific fingerprints, and auto-replacement.

Wraps SandboxPool with a CUA-specific factory that creates CUASandbox instances
and pre-warms all containers before the pool is ready for episodes.  CUA
containers appear in a separate group in ``pool status`` output thanks to the
``cua-`` prefix in their fingerprints.

Key design:
- CUAPool.start() pre-warms exactly ``pool_size`` containers before returning
- CUA fingerprints are prefixed with ``cua-`` to distinguish them from coding
  pool fingerprints (which are 16-char hex strings with no prefix)
- Auto-replacement of unhealthy containers is handled by SandboxPool
  replenishment using the upgraded CUASandbox.reset() for full cleanup
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import structlog

from lunar_sandbox.pool.config import PoolConfig
from lunar_sandbox.pool.pool import SandboxPool
from lunar_sandbox.sandbox.cua_config import CUASandboxConfig
from lunar_sandbox.sandbox.cua_sandbox import CUASandbox

__all__ = ["CUAPool", "CUAPoolConfig", "cua_pool_fingerprint"]

log = structlog.get_logger(__name__)


@dataclass
class CUAPoolConfig:
    """Configuration for the CUA container pool.

    Attributes:
        pool_size: Number of CUA containers to pre-warm. All containers
            boot on pool.start() before the pool is ready for episodes.
        image: Docker image tag for CUA containers.
        data_root: Root directory for sandbox runtime data.
    """

    pool_size: int = 2
    image: str = "lunar-cua:latest"
    data_root: str = "/var/lib/lunar-sandbox"


def cua_pool_fingerprint(image: str = "lunar-cua:latest") -> str:
    """Return a CUA-specific fingerprint distinct from coding pool fingerprints.

    The ``cua-`` prefix guarantees CUA containers appear in a separate group
    in ``pool status`` output.  Coding pool fingerprints are 16 hex chars with
    no prefix (e.g. ``'3a4f8b2c1d9e7f0a'``), while CUA fingerprints look like
    ``'cua-a3f8d2b1c9e4'``.

    Args:
        image: Docker image tag used to create CUA containers.

    Returns:
        16-character string with ``'cua-'`` prefix followed by 12 hex chars.
    """
    import hashlib

    payload = f"cua:{image}"
    return "cua-" + hashlib.sha256(payload.encode()).hexdigest()[:12]


class CUAPool:
    """Pre-warmed pool of CUA containers for evaluation loops.

    Wraps SandboxPool with:
    - CUA-specific factory that creates CUASandbox instances
    - Fixed-size pre-warm: all containers boot on start()
    - CUA-specific fingerprint for separate pool grouping
    - Auto-replacement of unhealthy containers via SandboxPool replenishment

    The underlying SandboxPool handles acquire/release lifecycle, background
    reset (which calls the upgraded CUASandbox.reset() for full cleanup),
    FIFO fairness, and memory pressure eviction.

    Usage::

        config = CUAPoolConfig(pool_size=4)
        pool = CUAPool(config)
        await pool.start()               # Pre-warms 4 containers
        sandbox = await pool.acquire()   # Sub-ms checkout
        # ... run episode ...
        await pool.release(sandbox)      # Background reset
        await pool.shutdown()
    """

    def __init__(self, config: CUAPoolConfig) -> None:
        self._config = config
        self._fingerprint = cua_pool_fingerprint(config.image)
        pool_config = PoolConfig(
            global_max_sandboxes=config.pool_size,
            per_fingerprint_soft_limit=config.pool_size,
        )
        self._pool = SandboxPool(
            config=pool_config,
            sandbox_factory=self._make_sandbox,
        )
        self._log = log.bind(component="cua_pool")

    @property
    def fingerprint(self) -> str:
        """The CUA-specific fingerprint for this pool."""
        return self._fingerprint

    def _make_sandbox(self, fingerprint: str) -> CUASandbox:
        """Factory: create a CUASandbox instance for the pool.

        Args:
            fingerprint: CUA pool fingerprint (passed by SandboxPool).

        Returns:
            A CUASandbox in RUNNING state with desktop services ready.
        """
        from uuid import uuid4

        sandbox_id = f"cua-pool-{uuid4().hex[:8]}"
        cfg = CUASandboxConfig(
            sandbox_id=sandbox_id,
            data_root=Path(self._config.data_root),
            image=self._config.image,
        )
        sb = CUASandbox(cfg)
        sb.create()
        return sb

    async def start(self) -> None:
        """Start pool and pre-warm all containers before returning.

        Acquires then immediately releases all ``pool_size`` slots so that
        every container is booted and sitting idle in the pool when this
        method returns.
        """
        await self._pool.start()
        # Pre-warm by acquiring then releasing all slots
        sandboxes = []
        for _ in range(self._config.pool_size):
            sb = await self._pool.acquire(self._fingerprint)
            sandboxes.append(sb)
        for sb in sandboxes:
            await self._pool.release(sb)
        self._log.info(
            "cua_pool_warmed",
            size=self._config.pool_size,
            fingerprint=self._fingerprint,
        )

    async def acquire(self) -> CUASandbox:
        """Acquire a pre-warmed CUA sandbox from the pool.

        Returns:
            A CUASandbox in RUNNING state, ready for an episode.
        """
        sb = await self._pool.acquire(self._fingerprint)
        return sb  # type: ignore[return-value]

    async def release(self, sandbox: CUASandbox) -> None:
        """Release sandbox back to pool for background reset.

        Returns immediately. The sandbox is reset via CUASandbox.reset()
        (full cleanup) in a background task before returning to the idle pool.

        Args:
            sandbox: The sandbox to release (must have been acquired).
        """
        await self._pool.release(sandbox)

    async def shutdown(self) -> None:
        """Shut down pool and destroy all containers."""
        await self._pool.shutdown()
        self._log.info("cua_pool_shutdown")

    async def status(self) -> dict:
        """Return pool status including CUA fingerprint grouping.

        Returns:
            Dict with running state, metrics snapshot, known fingerprints,
            per-fingerprint targets, and per-fingerprint idle/active counts.
        """
        return await self._pool.status()

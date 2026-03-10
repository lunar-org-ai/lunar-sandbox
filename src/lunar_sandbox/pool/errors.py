"""Pool-specific error hierarchy.

All pool errors inherit from SandboxError through PoolError, enabling
callers to distinguish pool-level failures from sandbox-level failures
while still catching the common base class.
"""

from __future__ import annotations

from lunar_sandbox.sandbox.errors import SandboxError


class PoolError(SandboxError):
    """Base class for all pool-related errors."""

    pass


class PoolExhaustedError(PoolError):
    """Pool has no available sandboxes and cannot create more.

    Raised when all sandboxes are active, memory pressure is critical,
    or the global sandbox limit has been reached. Callers should retry
    after a backoff period or reject the request.
    """

    pass


class PoolShuttingDownError(PoolError):
    """Pool is in shutdown state and rejecting new requests.

    Raised when acquire() is called after the pool has begun its
    shutdown sequence. Callers should not retry -- the pool will
    not accept new work.
    """

    pass

"""Pool entry dataclass tracking per-sandbox metadata.

Each PoolEntry wraps a Sandbox instance with lifecycle metadata used
by the pool manager for expiry, idle detection, and LRU ordering.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lunar_sandbox.sandbox.sandbox import Sandbox


@dataclass
class PoolEntry:
    """Metadata wrapper for a pooled sandbox instance.

    Attributes:
        sandbox: The actual Sandbox instance. Forward-referenced to
            avoid circular imports between pool and sandbox packages.
        sandbox_id: Matches sandbox.config.sandbox_id for quick lookup.
        fingerprint: The 16-hex-char environment fingerprint used as
            the pool key for this sandbox.
        created_at: Monotonic timestamp of sandbox creation. Used for
            TTL expiry checks.
        last_used_at: Monotonic timestamp of last checkout. Used for
            idle timeout detection and LRU eviction ordering.
        checkout_count: Number of times this sandbox has been checked
            out from the pool. Useful for metrics and health monitoring.
    """

    sandbox: Sandbox
    sandbox_id: str
    fingerprint: str
    created_at: float = field(default_factory=time.monotonic)
    last_used_at: float = field(default_factory=time.monotonic)
    checkout_count: int = 0

    def is_expired(self, ttl_seconds: float) -> bool:
        """Check if this sandbox has exceeded its TTL.

        Args:
            ttl_seconds: Maximum allowed age in seconds.

        Returns:
            True if the sandbox age exceeds the TTL.
        """
        return (time.monotonic() - self.created_at) >= ttl_seconds

    def is_idle_too_long(self, idle_timeout: float) -> bool:
        """Check if this sandbox has been idle beyond the timeout.

        Args:
            idle_timeout: Maximum allowed idle time in seconds.

        Returns:
            True if the sandbox has been idle longer than the timeout.
        """
        return (time.monotonic() - self.last_used_at) >= idle_timeout

    def mark_used(self) -> None:
        """Record that this sandbox was checked out.

        Updates last_used_at to current monotonic time and increments
        the checkout counter.
        """
        self.last_used_at = time.monotonic()
        self.checkout_count += 1

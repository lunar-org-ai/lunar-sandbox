"""Pool metrics for monitoring and telemetry.

PoolMetrics tracks monotonic counters and current-state gauges for
the sandbox pool. Designed for downstream telemetry consumption in
Phase 7.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class PoolMetrics:
    """Structured metrics for pool monitoring and telemetry.

    Counters are monotonically increasing over the pool lifetime.
    Gauges reflect current state and may increase or decrease.
    Per-fingerprint counters enable fine-grained analysis of pool
    behavior per environment type.

    Attributes:
        total_hits: Successful pool acquisitions (sandbox was available).
        total_misses: Pool acquisitions that found no available sandbox.
        total_cold_starts: Subset of misses where no sandbox existed
            for the fingerprint at all (distinct from pool_miss where
            sandboxes exist but are all checked out).
        total_evictions: Sandboxes evicted due to memory pressure.
        total_ttl_expiries: Sandboxes destroyed for exceeding TTL.
        total_idle_timeouts: Sandboxes destroyed for being idle too long.
        total_creations: Total sandbox creation attempts.
        total_creation_failures: Failed sandbox creation attempts.
        total_health_check_failures: Health checks that found issues.
        hits_by_fingerprint: Hit count per fingerprint.
        misses_by_fingerprint: Miss count per fingerprint.
        cold_starts_by_fingerprint: Cold start count per fingerprint.
        pool_size: Current total sandboxes in the pool.
        idle_count: Current idle (available) sandboxes.
        active_count: Current checked-out sandboxes.
        pending_creations: Sandboxes currently being created.
    """

    # Monotonic counters
    total_hits: int = 0
    total_misses: int = 0
    total_cold_starts: int = 0
    total_evictions: int = 0
    total_ttl_expiries: int = 0
    total_idle_timeouts: int = 0
    total_creations: int = 0
    total_creation_failures: int = 0
    total_health_check_failures: int = 0

    # Per-fingerprint counters
    hits_by_fingerprint: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    misses_by_fingerprint: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    cold_starts_by_fingerprint: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )

    # Current-state gauges
    pool_size: int = 0
    idle_count: int = 0
    active_count: int = 0
    pending_creations: int = 0

    def record_hit(self, fingerprint: str) -> None:
        """Record a successful pool acquisition.

        Args:
            fingerprint: The environment fingerprint that was matched.
        """
        self.total_hits += 1
        self.hits_by_fingerprint[fingerprint] += 1

    def record_miss(self, fingerprint: str, *, cold_start: bool) -> None:
        """Record a failed pool acquisition.

        Args:
            fingerprint: The environment fingerprint that was requested.
            cold_start: True if no sandbox exists for this fingerprint
                at all (first request or all evicted). False if sandboxes
                exist but are all currently checked out.
        """
        self.total_misses += 1
        self.misses_by_fingerprint[fingerprint] += 1
        if cold_start:
            self.total_cold_starts += 1
            self.cold_starts_by_fingerprint[fingerprint] += 1

    def snapshot(self) -> dict:
        """Return all metrics as a serializable dictionary.

        Includes a computed ``hit_rate`` field: ratio of hits to total
        acquisitions (hits + misses). Returns 0.0 if no acquisitions
        have been recorded.

        Returns:
            Dictionary with all counter, gauge, and per-fingerprint
            metrics. All values are JSON-serializable.
        """
        total_acquisitions = self.total_hits + self.total_misses
        hit_rate = (
            self.total_hits / total_acquisitions if total_acquisitions > 0 else 0.0
        )

        return {
            # Counters
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "total_cold_starts": self.total_cold_starts,
            "total_evictions": self.total_evictions,
            "total_ttl_expiries": self.total_ttl_expiries,
            "total_idle_timeouts": self.total_idle_timeouts,
            "total_creations": self.total_creations,
            "total_creation_failures": self.total_creation_failures,
            "total_health_check_failures": self.total_health_check_failures,
            # Per-fingerprint (convert defaultdict to regular dict for serialization)
            "hits_by_fingerprint": dict(self.hits_by_fingerprint),
            "misses_by_fingerprint": dict(self.misses_by_fingerprint),
            "cold_starts_by_fingerprint": dict(self.cold_starts_by_fingerprint),
            # Gauges
            "pool_size": self.pool_size,
            "idle_count": self.idle_count,
            "active_count": self.active_count,
            "pending_creations": self.pending_creations,
            # Computed
            "hit_rate": hit_rate,
        }

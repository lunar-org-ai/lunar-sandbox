"""Pool configuration dataclass.

Defines PoolConfig with sensible defaults for sandbox pool management.
All parameters are user-tunable to constrain resources for different
deployment environments.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PoolConfig:
    """Configuration for the sandbox pool manager.

    Attributes:
        global_max_sandboxes: Hard cap on total sandboxes across all
            fingerprints. Prevents runaway resource consumption.
        per_fingerprint_soft_limit: Soft limit per fingerprint. The pool
            balances sandbox allocation within the global budget.
        idle_timeout_seconds: Destroy idle sandboxes after this period.
            Prevents unused sandboxes from consuming resources.
        ttl_seconds: Maximum sandbox age. Prevents stale cgroup/mount
            accumulation from long-lived sandboxes.
        replenish_interval_seconds: Background replenishment check
            frequency. Lower values provide faster warm-up but more
            CPU overhead.
        low_watermark_ratio: Replenish when idle count drops below this
            ratio of the per-fingerprint target. 0.25 means replenish
            when fewer than 25% of target sandboxes are idle.
        max_concurrent_creations: Cap simultaneous sandbox creations to
            prevent thundering herd on sudden demand spikes.
        replenish_batch_size: Maximum sandboxes created per replenishment
            cycle. Spreads creation load over multiple cycles.
        memory_pressure_threshold: Trigger soft eviction when system
            memory usage exceeds this ratio (0.0-1.0).
        data_root: Root directory for sandbox runtime data. Matches
            the default from SandboxConfig for consistency.
    """

    global_max_sandboxes: int = 32
    per_fingerprint_soft_limit: int = 8
    idle_timeout_seconds: float = 120.0
    ttl_seconds: float = 300.0
    replenish_interval_seconds: float = 2.0
    low_watermark_ratio: float = 0.25
    max_concurrent_creations: int = 4
    replenish_batch_size: int = 4
    memory_pressure_threshold: float = 0.85
    data_root: str = "/var/lib/lunar-sandbox"

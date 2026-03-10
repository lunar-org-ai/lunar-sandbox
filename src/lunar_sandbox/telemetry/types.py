"""Telemetry data types for performance measurement.

Provides dataclasses for metric samples, computed statistics,
telemetry snapshots, threshold configuration, and threshold
breach reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "MetricSample",
    "MetricStats",
    "TelemetrySnapshot",
    "ThresholdBreach",
    "ThresholdConfig",
]


@dataclass
class MetricSample:
    """A single timing measurement recorded during evaluation.

    Attributes:
        metric: Metric name -- one of ``"allocate_latency"``,
            ``"reset_latency"``, ``"time_to_first_action"``,
            ``"episode_duration"``, ``"cache_hit"`` (1.0/0.0).
        value: Measured value in milliseconds (or 1.0/0.0 for
            ``cache_hit``).
        fingerprint: Environment fingerprint (empty if not applicable).
        batch_run_id: Batch run ID (empty if not in batch context).
        timestamp: ``time.monotonic()`` value when recorded.
    """

    metric: str
    value: float
    fingerprint: str = ""
    batch_run_id: str = ""
    timestamp: float = 0.0


@dataclass
class MetricStats:
    """Computed statistics for a single metric.

    Attributes:
        p50: 50th percentile (median), or None if insufficient data.
        p95: 95th percentile, or None if insufficient data.
        mean: Arithmetic mean of all values.
        count: Number of samples.
        min_val: Minimum observed value.
        max_val: Maximum observed value.
    """

    p50: float | None
    p95: float | None
    mean: float
    count: int
    min_val: float
    max_val: float


@dataclass
class TelemetrySnapshot:
    """Computed telemetry for a single evaluation run.

    Attributes:
        run_id: Batch or synthetic run identifier.
        metrics: Per-metric statistics keyed by metric name.
        throughput_eps_per_min: Episodes completed per minute.
        cache_hit_rate: Fraction of cache hits (0.0--1.0).
        total_episodes: Number of episodes in this run.
        duration_seconds: Total run wall-clock duration in seconds.
    """

    run_id: str
    metrics: dict[str, MetricStats] = field(default_factory=dict)
    throughput_eps_per_min: float = 0.0
    cache_hit_rate: float = 0.0
    total_episodes: int = 0
    duration_seconds: float = 0.0


@dataclass
class ThresholdConfig:
    """Configurable performance thresholds for breach detection.

    Set a field to ``None`` to skip that check.

    Attributes:
        allocate_p95_ms: Maximum acceptable P95 allocate latency.
        reset_p95_ms: Maximum acceptable P95 reset latency.
        first_action_p95_ms: Maximum acceptable P95 time to first action.
        episode_p95_ms: Maximum acceptable P95 episode duration.
        cache_hit_rate_min: Minimum acceptable cache hit rate (0.0--1.0).
    """

    allocate_p95_ms: float | None = None
    reset_p95_ms: float | None = None
    first_action_p95_ms: float | None = None
    episode_p95_ms: float | None = None
    cache_hit_rate_min: float | None = None


@dataclass
class ThresholdBreach:
    """A detected threshold violation.

    Attributes:
        metric: Name of the metric that breached.
        threshold: Configured threshold value.
        actual: Observed value.
        severity: ``"warning"`` if within 1.5x, ``"critical"`` if beyond.
    """

    metric: str
    threshold: float
    actual: float
    severity: str  # "warning" or "critical"

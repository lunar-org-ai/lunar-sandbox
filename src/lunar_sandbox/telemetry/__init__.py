"""Performance telemetry for sandbox evaluation.

Provides in-memory collection, SQLite persistence, and statistical
computation for latency, throughput, and cache-hit metrics.
"""

from lunar_sandbox.telemetry.collector import TelemetryCollector
from lunar_sandbox.telemetry.compute import (
    check_thresholds,
    compare_runs,
    compute_metric_stats,
    compute_percentiles,
    compute_snapshot,
    compute_snapshot_by_fingerprint,
)
from lunar_sandbox.telemetry.store import TelemetryStore
from lunar_sandbox.telemetry.types import (
    MetricSample,
    MetricStats,
    TelemetrySnapshot,
    ThresholdBreach,
    ThresholdConfig,
)

__all__ = [
    "MetricSample",
    "MetricStats",
    "TelemetryCollector",
    "TelemetrySnapshot",
    "TelemetryStore",
    "ThresholdBreach",
    "ThresholdConfig",
    "check_thresholds",
    "compare_runs",
    "compute_metric_stats",
    "compute_percentiles",
    "compute_snapshot",
    "compute_snapshot_by_fingerprint",
]

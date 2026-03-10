"""Performance telemetry for sandbox evaluation.

Provides in-memory collection, SQLite persistence, and statistical
computation for latency, throughput, and cache-hit metrics.
"""

from lunar_sandbox.telemetry.collector import TelemetryCollector
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
    "ThresholdBreach",
    "ThresholdConfig",
]

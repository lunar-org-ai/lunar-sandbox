"""Pure computation functions for telemetry analysis.

Stateless functions that operate on metric samples and produce
computed statistics, threshold checks, and run comparisons.
No I/O, no state -- suitable for use in any context.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from lunar_sandbox.telemetry.types import (
    MetricSample,
    MetricStats,
    TelemetrySnapshot,
    ThresholdBreach,
    ThresholdConfig,
)

__all__ = [
    "check_thresholds",
    "compare_runs",
    "compute_metric_stats",
    "compute_percentiles",
    "compute_snapshot",
    "compute_snapshot_by_fingerprint",
]


def compute_percentiles(
    values: list[float],
) -> tuple[float | None, float | None]:
    """Compute P50 and P95 from a list of values.

    Uses :func:`statistics.quantiles` with ``n=100`` (same pattern
    as :meth:`AggregateMetrics.from_results`).

    Guards:
        - Empty list returns ``(None, None)``.
        - Single value returns ``(value, value)``.
        - Two or more values use ``statistics.quantiles``.

    Args:
        values: List of numeric measurements.

    Returns:
        Tuple of ``(p50, p95)`` or ``(None, None)`` for empty input.
    """
    if len(values) == 0:
        return (None, None)
    if len(values) == 1:
        return (values[0], values[0])
    percentiles = statistics.quantiles(values, n=100)
    return (percentiles[49], percentiles[94])


def compute_metric_stats(values: list[float]) -> MetricStats:
    """Compute full statistics for a list of metric values.

    Args:
        values: Non-empty list of numeric measurements.

    Returns:
        :class:`MetricStats` with percentiles, mean, count, min, max.

    Raises:
        ValueError: If ``values`` is empty.
    """
    if not values:
        raise ValueError("Cannot compute stats for empty values list")
    p50, p95 = compute_percentiles(values)
    return MetricStats(
        p50=p50,
        p95=p95,
        mean=statistics.mean(values),
        count=len(values),
        min_val=min(values),
        max_val=max(values),
    )


def compute_snapshot(
    samples: list[MetricSample],
    run_id: str,
    duration_seconds: float,
) -> TelemetrySnapshot:
    """Build a :class:`TelemetrySnapshot` from raw samples.

    Groups samples by metric name, computes statistics for each,
    derives throughput from ``episode_duration`` sample count, and
    computes cache hit rate from ``cache_hit`` samples.

    Args:
        samples: Raw metric samples for a single run.
        run_id: Run identifier.
        duration_seconds: Total run wall-clock duration in seconds.

    Returns:
        Populated :class:`TelemetrySnapshot`.
    """
    # Group values by metric name
    by_metric: dict[str, list[float]] = defaultdict(list)
    for s in samples:
        by_metric[s.metric].append(s.value)

    # Compute per-metric stats
    metrics: dict[str, MetricStats] = {}
    for metric_name, vals in by_metric.items():
        metrics[metric_name] = compute_metric_stats(vals)

    # Throughput: episodes / minutes
    episode_count = len(by_metric.get("episode_duration", []))
    minutes = duration_seconds / 60.0 if duration_seconds > 0 else 0.0
    throughput = episode_count / minutes if minutes > 0 else 0.0

    # Cache hit rate: mean of 1.0/0.0 values
    cache_values = by_metric.get("cache_hit", [])
    cache_hit_rate = statistics.mean(cache_values) if cache_values else 0.0

    return TelemetrySnapshot(
        run_id=run_id,
        metrics=metrics,
        throughput_eps_per_min=throughput,
        cache_hit_rate=cache_hit_rate,
        total_episodes=episode_count,
        duration_seconds=duration_seconds,
    )


def check_thresholds(
    snapshot: TelemetrySnapshot,
    config: ThresholdConfig,
) -> list[ThresholdBreach]:
    """Check computed telemetry against configured thresholds.

    For latency metrics, a breach occurs when the actual P95 exceeds
    the threshold.  For ``cache_hit_rate_min``, a breach occurs when
    the actual rate is below the threshold.

    Severity:
        - ``"warning"``: actual <= threshold * 1.5 (latency) or
          actual >= threshold / 1.5 (cache hit rate).
        - ``"critical"``: beyond the warning boundary.

    Args:
        snapshot: Computed telemetry snapshot.
        config: Threshold configuration.

    Returns:
        List of :class:`ThresholdBreach` objects (empty = all clear).
    """
    breaches: list[ThresholdBreach] = []

    # Latency threshold checks (metric_name -> config field)
    latency_checks: list[tuple[str, float | None]] = [
        ("allocate_latency", config.allocate_p95_ms),
        ("reset_latency", config.reset_p95_ms),
        ("time_to_first_action", config.first_action_p95_ms),
        ("episode_duration", config.episode_p95_ms),
    ]

    for metric_name, threshold in latency_checks:
        if threshold is None:
            continue
        stats = snapshot.metrics.get(metric_name)
        if stats is None or stats.p95 is None:
            continue
        actual = stats.p95
        if actual > threshold:
            severity = "warning" if actual <= threshold * 1.5 else "critical"
            breaches.append(
                ThresholdBreach(
                    metric=metric_name,
                    threshold=threshold,
                    actual=actual,
                    severity=severity,
                )
            )

    # Cache hit rate threshold (inverted: breach when actual < threshold)
    if config.cache_hit_rate_min is not None:
        if snapshot.cache_hit_rate < config.cache_hit_rate_min:
            threshold = config.cache_hit_rate_min
            actual = snapshot.cache_hit_rate
            # Warning if not too far below; critical if very far below
            severity = (
                "warning"
                if actual >= threshold / 1.5
                else "critical"
            )
            breaches.append(
                ThresholdBreach(
                    metric="cache_hit_rate",
                    threshold=threshold,
                    actual=actual,
                    severity=severity,
                )
            )

    return breaches


def compare_runs(
    snapshot_a: TelemetrySnapshot,
    snapshot_b: TelemetrySnapshot,
) -> list[dict]:
    """Compare two telemetry snapshots side by side.

    For each metric present in either snapshot, produces a comparison
    dict with P50/P95 values and percentage changes.  Also includes
    ``throughput`` and ``cache_hit_rate`` as special rows.

    Args:
        snapshot_a: Baseline snapshot.
        snapshot_b: Comparison snapshot.

    Returns:
        List of comparison dicts with keys: ``metric``, ``a_p50``,
        ``a_p95``, ``b_p50``, ``b_p95``, ``delta_p50``, ``delta_p95``,
        ``pct_change_p50``, ``pct_change_p95``.
    """
    comparisons: list[dict] = []

    # All metric names from both snapshots
    all_metrics = sorted(
        set(snapshot_a.metrics.keys()) | set(snapshot_b.metrics.keys())
    )

    for metric_name in all_metrics:
        stats_a = snapshot_a.metrics.get(metric_name)
        stats_b = snapshot_b.metrics.get(metric_name)

        a_p50 = stats_a.p50 if stats_a else None
        a_p95 = stats_a.p95 if stats_a else None
        b_p50 = stats_b.p50 if stats_b else None
        b_p95 = stats_b.p95 if stats_b else None

        comparisons.append({
            "metric": metric_name,
            "a_p50": a_p50,
            "a_p95": a_p95,
            "b_p50": b_p50,
            "b_p95": b_p95,
            "delta_p50": _delta(a_p50, b_p50),
            "delta_p95": _delta(a_p95, b_p95),
            "pct_change_p50": _pct_change(a_p50, b_p50),
            "pct_change_p95": _pct_change(a_p95, b_p95),
        })

    # Throughput comparison (special row)
    a_tp = snapshot_a.throughput_eps_per_min
    b_tp = snapshot_b.throughput_eps_per_min
    comparisons.append({
        "metric": "throughput_eps_per_min",
        "a_p50": a_tp,
        "a_p95": None,
        "b_p50": b_tp,
        "b_p95": None,
        "delta_p50": _delta(a_tp, b_tp),
        "delta_p95": None,
        "pct_change_p50": _pct_change(a_tp, b_tp),
        "pct_change_p95": None,
    })

    # Cache hit rate comparison (special row)
    a_chr = snapshot_a.cache_hit_rate
    b_chr = snapshot_b.cache_hit_rate
    comparisons.append({
        "metric": "cache_hit_rate",
        "a_p50": a_chr,
        "a_p95": None,
        "b_p50": b_chr,
        "b_p95": None,
        "delta_p50": _delta(a_chr, b_chr),
        "delta_p95": None,
        "pct_change_p50": _pct_change(a_chr, b_chr),
        "pct_change_p95": None,
    })

    return comparisons


def compute_snapshot_by_fingerprint(
    samples: list[MetricSample],
    run_id: str,
    duration_seconds: float,
) -> dict[str, TelemetrySnapshot]:
    """Compute per-fingerprint telemetry snapshots.

    Groups samples by fingerprint, then delegates to
    :func:`compute_snapshot` for each group.

    Args:
        samples: Raw metric samples for a single run.
        run_id: Run identifier.
        duration_seconds: Total run wall-clock duration in seconds.

    Returns:
        Dict keyed by fingerprint, values are per-fingerprint
        :class:`TelemetrySnapshot` objects.
    """
    by_fp: dict[str, list[MetricSample]] = defaultdict(list)
    for s in samples:
        by_fp[s.fingerprint].append(s)

    return {
        fp: compute_snapshot(fp_samples, f"{run_id}:{fp}", duration_seconds)
        for fp, fp_samples in by_fp.items()
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _delta(
    a: float | None,
    b: float | None,
) -> float | None:
    """Compute b - a, or None if either is None."""
    if a is None or b is None:
        return None
    return b - a


def _pct_change(
    a: float | None,
    b: float | None,
) -> float | None:
    """Compute percentage change from a to b.

    Returns ``(b - a) / a * 100`` if ``a != 0``, else ``None``.
    """
    if a is None or b is None:
        return None
    if a == 0:
        return None
    return (b - a) / a * 100

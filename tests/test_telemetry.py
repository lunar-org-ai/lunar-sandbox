"""Tests for telemetry data layer, compute functions, and DI acceptance.

Covers the TelemetryCollector (thread-safe record/drain/snapshot),
TelemetryStore (save/query/delete round-trips), compute functions
(percentiles, stats, snapshots, thresholds, run comparison), and
instrumentation DI acceptance for pool, scheduler, and runner.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

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


# ===================================================================
# Collector tests
# ===================================================================


class TestCollectorRecordAndSnapshot:
    """TelemetryCollector.record() and snapshot() work correctly."""

    def test_collector_record_and_snapshot(self) -> None:
        collector = TelemetryCollector()
        collector.record("allocate_latency", 10.0, fingerprint="fp-a")
        collector.record("reset_latency", 20.0, fingerprint="fp-b")
        collector.record("episode_duration", 30.0)

        snap = collector.snapshot()
        assert len(snap) == 3
        assert snap[0].metric == "allocate_latency"
        assert snap[0].value == 10.0
        assert snap[0].fingerprint == "fp-a"
        assert snap[1].metric == "reset_latency"
        assert snap[2].metric == "episode_duration"

        # snapshot does not clear
        assert collector.count() == 3

    def test_collector_drain_clears(self) -> None:
        collector = TelemetryCollector()
        collector.record("allocate_latency", 1.0)
        collector.record("reset_latency", 2.0)

        drained = collector.drain()
        assert len(drained) == 2
        assert drained[0].value == 1.0

        # buffer cleared
        assert collector.drain() == []
        assert collector.count() == 0

    def test_collector_empty(self) -> None:
        collector = TelemetryCollector()
        assert collector.snapshot() == []
        assert collector.drain() == []
        assert collector.count() == 0

    def test_collector_thread_safety(self) -> None:
        collector = TelemetryCollector()
        num_threads = 4
        samples_per_thread = 100

        def record_samples(thread_idx: int) -> None:
            for i in range(samples_per_thread):
                collector.record(
                    "test_metric",
                    float(thread_idx * 1000 + i),
                    fingerprint=f"fp-{thread_idx}",
                )

        threads = [
            threading.Thread(target=record_samples, args=(t,))
            for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        drained = collector.drain()
        assert len(drained) == num_threads * samples_per_thread  # exactly 400

    def test_collector_count(self) -> None:
        collector = TelemetryCollector()
        for i in range(5):
            collector.record("m", float(i))
        assert collector.count() == 5


# ===================================================================
# Store tests
# ===================================================================


def _make_samples(
    run_id: str, count: int = 10, metrics: list[str] | None = None,
    fingerprints: list[str] | None = None,
) -> list[MetricSample]:
    """Create test MetricSample objects."""
    metrics = metrics or ["allocate_latency"]
    fingerprints = fingerprints or ["fp-default"]
    samples = []
    for i in range(count):
        for m in metrics:
            for fp in fingerprints:
                samples.append(
                    MetricSample(
                        metric=m,
                        value=float(i * 10 + 1),
                        fingerprint=fp,
                        batch_run_id=run_id,
                        timestamp=time.monotonic() + i,
                    )
                )
    return samples


class TestStore:
    """TelemetryStore save/query/delete round-trips."""

    def test_store_save_and_query_run(self, tmp_path: Path) -> None:
        db = tmp_path / "telem.db"
        store = TelemetryStore(db)
        store.open()
        try:
            samples = _make_samples("run-1", count=10)
            store.save_run(
                run_id="run-1",
                samples=samples,
                started_at=1000.0,
                ended_at=1060.0,
                total_episodes=10,
                throughput=10.0,
                cache_hit_rate=0.8,
            )

            runs = store.query_runs()
            assert len(runs) == 1
            assert runs[0]["run_id"] == "run-1"
            assert runs[0]["total_episodes"] == 10
            assert runs[0]["throughput_eps_per_min"] == 10.0
            assert runs[0]["cache_hit_rate"] == 0.8

            queried = store.query_samples("run-1")
            assert len(queried) == 10
            assert queried[0]["metric"] == "allocate_latency"
        finally:
            store.close()

    def test_store_query_samples_with_filters(self, tmp_path: Path) -> None:
        db = tmp_path / "telem.db"
        store = TelemetryStore(db)
        store.open()
        try:
            samples = _make_samples(
                "run-1", count=5,
                metrics=["allocate_latency", "reset_latency"],
                fingerprints=["fp-a", "fp-b"],
            )
            store.save_run(
                run_id="run-1", samples=samples,
                started_at=1000.0, ended_at=1060.0,
                total_episodes=5, throughput=5.0, cache_hit_rate=0.5,
            )

            # Filter by metric
            alloc_only = store.query_samples("run-1", metric="allocate_latency")
            assert all(s["metric"] == "allocate_latency" for s in alloc_only)
            assert len(alloc_only) == 10  # 5 count * 2 fingerprints

            # Filter by fingerprint
            fp_a_only = store.query_samples("run-1", fingerprint="fp-a")
            assert all(s["fingerprint"] == "fp-a" for s in fp_a_only)
            assert len(fp_a_only) == 10  # 5 count * 2 metrics
        finally:
            store.close()

    def test_store_query_runs_ordering(self, tmp_path: Path) -> None:
        db = tmp_path / "telem.db"
        store = TelemetryStore(db)
        store.open()
        try:
            for i, started in enumerate([3000.0, 1000.0, 2000.0]):
                store.save_run(
                    run_id=f"run-{i}",
                    samples=[],
                    started_at=started,
                    ended_at=started + 60,
                    total_episodes=1,
                    throughput=1.0,
                    cache_hit_rate=0.0,
                )

            runs = store.query_runs()
            assert len(runs) == 3
            # ordered by started_at DESC
            assert runs[0]["run_id"] == "run-0"  # started_at=3000
            assert runs[1]["run_id"] == "run-2"  # started_at=2000
            assert runs[2]["run_id"] == "run-1"  # started_at=1000
        finally:
            store.close()

    def test_store_delete_run(self, tmp_path: Path) -> None:
        db = tmp_path / "telem.db"
        store = TelemetryStore(db)
        store.open()
        try:
            for rid in ["run-1", "run-2"]:
                store.save_run(
                    run_id=rid,
                    samples=_make_samples(rid, count=3),
                    started_at=1000.0, ended_at=1060.0,
                    total_episodes=3, throughput=3.0, cache_hit_rate=0.5,
                )

            deleted = store.delete_run("run-1")
            assert deleted is True

            runs = store.query_runs()
            assert len(runs) == 1
            assert runs[0]["run_id"] == "run-2"

            # samples also gone
            assert store.query_samples("run-1") == []
        finally:
            store.close()

    def test_store_delete_all(self, tmp_path: Path) -> None:
        db = tmp_path / "telem.db"
        store = TelemetryStore(db)
        store.open()
        try:
            for i in range(3):
                store.save_run(
                    run_id=f"run-{i}", samples=[],
                    started_at=1000.0, ended_at=1060.0,
                    total_episodes=1, throughput=1.0, cache_hit_rate=0.0,
                )

            count = store.delete_all()
            assert count == 3
            assert store.query_runs() == []
        finally:
            store.close()

    def test_store_export_samples(self, tmp_path: Path) -> None:
        db = tmp_path / "telem.db"
        store = TelemetryStore(db)
        store.open()
        try:
            samples = _make_samples("run-1", count=5)
            store.save_run(
                run_id="run-1", samples=samples,
                started_at=1000.0, ended_at=1060.0,
                total_episodes=5, throughput=5.0, cache_hit_rate=0.5,
            )

            exported = store.export_samples("run-1")
            assert len(exported) == 5
            assert all("metric" in row for row in exported)
            assert all("value" in row for row in exported)
        finally:
            store.close()

    def test_store_context_manager(self, tmp_path: Path) -> None:
        db = tmp_path / "telem.db"
        with TelemetryStore(db) as store:
            store.save_run(
                run_id="run-ctx", samples=[],
                started_at=1000.0, ended_at=1060.0,
                total_episodes=1, throughput=1.0, cache_hit_rate=0.0,
            )
            runs = store.query_runs()
            assert len(runs) == 1
        # Connection should be closed after with-block (no assertion needed,
        # just verifying no exception on exit)


# ===================================================================
# Compute tests
# ===================================================================


class TestPercentiles:
    """compute_percentiles edge cases and normal operation."""

    def test_percentiles_empty(self) -> None:
        p50, p95 = compute_percentiles([])
        assert p50 is None
        assert p95 is None

    def test_percentiles_single(self) -> None:
        p50, p95 = compute_percentiles([42.0])
        assert p50 == 42.0
        assert p95 == 42.0

    def test_percentiles_multiple(self) -> None:
        values = list(range(100))
        p50, p95 = compute_percentiles([float(v) for v in values])
        assert p50 is not None
        assert p95 is not None
        # P50 should be roughly the middle
        assert 45 <= p50 <= 55
        # P95 should be near the top
        assert 90 <= p95 <= 99


class TestMetricStats:
    """compute_metric_stats produces correct aggregates."""

    def test_metric_stats(self) -> None:
        stats = compute_metric_stats([1.0, 2.0, 3.0, 4.0, 5.0])
        assert stats.count == 5
        assert stats.mean == 3.0
        assert stats.min_val == 1.0
        assert stats.max_val == 5.0
        assert stats.p50 is not None
        assert stats.p95 is not None


class TestComputeSnapshot:
    """compute_snapshot builds correct TelemetrySnapshot."""

    def test_compute_snapshot(self) -> None:
        samples = []
        for i in range(20):
            metric_name = ["allocate_latency", "reset_latency", "episode_duration"][
                i % 3
            ]
            samples.append(
                MetricSample(
                    metric=metric_name,
                    value=float(i * 10),
                    fingerprint="fp-test",
                    timestamp=float(i),
                )
            )

        snap = compute_snapshot(samples, "test-run", 120.0)
        assert snap.run_id == "test-run"
        assert snap.duration_seconds == 120.0
        # All 3 metrics should be present
        assert len(snap.metrics) == 3
        for metric_name in ["allocate_latency", "reset_latency", "episode_duration"]:
            stats = snap.metrics[metric_name]
            assert stats.count > 0
            assert stats.p50 is not None

    def test_compute_snapshot_empty(self) -> None:
        snap = compute_snapshot([], "empty-run", 0.0)
        assert snap.metrics == {}
        assert snap.throughput_eps_per_min == 0.0
        assert snap.cache_hit_rate == 0.0
        assert snap.total_episodes == 0


class TestCheckThresholds:
    """check_thresholds produces correct breach reports."""

    def test_check_thresholds_no_breach(self) -> None:
        # P95 of allocate_latency = 50ms, threshold = 100ms -> no breach
        snap = TelemetrySnapshot(
            run_id="test",
            metrics={
                "allocate_latency": MetricStats(
                    p50=30.0, p95=50.0, mean=40.0, count=10,
                    min_val=10.0, max_val=60.0,
                ),
            },
        )
        config = ThresholdConfig(allocate_p95_ms=100.0)
        breaches = check_thresholds(snap, config)
        assert breaches == []

    def test_check_thresholds_breach(self) -> None:
        # P95 = 150ms, threshold = 100ms -> breach
        snap = TelemetrySnapshot(
            run_id="test",
            metrics={
                "allocate_latency": MetricStats(
                    p50=100.0, p95=150.0, mean=120.0, count=10,
                    min_val=80.0, max_val=160.0,
                ),
            },
        )
        config = ThresholdConfig(allocate_p95_ms=100.0)
        breaches = check_thresholds(snap, config)
        assert len(breaches) == 1
        assert breaches[0].metric == "allocate_latency"
        assert breaches[0].threshold == 100.0
        assert breaches[0].actual == 150.0
        # 150 <= 100 * 1.5 = 150, so warning
        assert breaches[0].severity == "warning"

    def test_check_thresholds_none_config(self) -> None:
        snap = TelemetrySnapshot(
            run_id="test",
            metrics={
                "allocate_latency": MetricStats(
                    p50=100.0, p95=500.0, mean=300.0, count=10,
                    min_val=50.0, max_val=600.0,
                ),
            },
        )
        # All thresholds None -> no breaches
        config = ThresholdConfig()
        breaches = check_thresholds(snap, config)
        assert breaches == []


class TestCompareRuns:
    """compare_runs produces correct deltas and percentages."""

    def test_compare_runs(self) -> None:
        snap_a = TelemetrySnapshot(
            run_id="a",
            metrics={
                "allocate_latency": MetricStats(
                    p50=50.0, p95=100.0, mean=70.0, count=10,
                    min_val=20.0, max_val=120.0,
                ),
            },
            throughput_eps_per_min=10.0,
            cache_hit_rate=0.8,
        )
        snap_b = TelemetrySnapshot(
            run_id="b",
            metrics={
                "allocate_latency": MetricStats(
                    p50=40.0, p95=80.0, mean=55.0, count=10,
                    min_val=15.0, max_val=90.0,
                ),
            },
            throughput_eps_per_min=12.0,
            cache_hit_rate=0.9,
        )

        comparisons = compare_runs(snap_a, snap_b)
        # Should have allocate_latency + throughput + cache_hit_rate rows
        assert len(comparisons) >= 3

        alloc_row = next(c for c in comparisons if c["metric"] == "allocate_latency")
        assert alloc_row["a_p95"] == 100.0
        assert alloc_row["b_p95"] == 80.0
        assert alloc_row["delta_p95"] == -20.0  # improvement
        assert alloc_row["pct_change_p95"] == -20.0  # -20%

    def test_compare_runs_handles_zero_baseline(self) -> None:
        snap_a = TelemetrySnapshot(
            run_id="a",
            metrics={
                "allocate_latency": MetricStats(
                    p50=0.0, p95=0.0, mean=0.0, count=1,
                    min_val=0.0, max_val=0.0,
                ),
            },
            throughput_eps_per_min=0.0,
            cache_hit_rate=0.0,
        )
        snap_b = TelemetrySnapshot(
            run_id="b",
            metrics={
                "allocate_latency": MetricStats(
                    p50=50.0, p95=100.0, mean=70.0, count=10,
                    min_val=20.0, max_val=120.0,
                ),
            },
            throughput_eps_per_min=10.0,
            cache_hit_rate=0.8,
        )

        comparisons = compare_runs(snap_a, snap_b)
        alloc_row = next(c for c in comparisons if c["metric"] == "allocate_latency")
        # baseline is 0 -> pct_change should be None (not divide-by-zero)
        assert alloc_row["pct_change_p95"] is None


class TestComputeSnapshotByFingerprint:
    """compute_snapshot_by_fingerprint groups by fingerprint."""

    def test_compute_snapshot_by_fingerprint(self) -> None:
        samples = []
        for i in range(10):
            fp = "fp-a" if i < 5 else "fp-b"
            samples.append(
                MetricSample(
                    metric="allocate_latency",
                    value=float(i * 10),
                    fingerprint=fp,
                    timestamp=float(i),
                )
            )

        result = compute_snapshot_by_fingerprint(samples, "test-run", 60.0)
        assert len(result) == 2
        assert "fp-a" in result
        assert "fp-b" in result
        assert result["fp-a"].metrics["allocate_latency"].count == 5
        assert result["fp-b"].metrics["allocate_latency"].count == 5


# ===================================================================
# Instrumentation DI acceptance tests
# ===================================================================


class TestInstrumentationDI:
    """Verify subsystems accept and work with/without telemetry collector."""

    def test_pool_accepts_collector(self) -> None:
        from lunar_sandbox.pool.config import PoolConfig
        from lunar_sandbox.pool.pool import SandboxPool

        collector = TelemetryCollector()
        pool = SandboxPool(PoolConfig(), telemetry_collector=collector)
        assert pool._telemetry is collector

    def test_pool_works_without_collector(self) -> None:
        from lunar_sandbox.pool.config import PoolConfig
        from lunar_sandbox.pool.pool import SandboxPool

        pool = SandboxPool(PoolConfig())
        assert pool._telemetry is None

    def test_scheduler_accepts_collector(self) -> None:
        from unittest.mock import MagicMock

        from lunar_sandbox.scheduler.scheduler import BatchScheduler

        collector = TelemetryCollector()
        mock_pool = MagicMock()
        scheduler = BatchScheduler(mock_pool, telemetry_collector=collector)
        assert scheduler._telemetry is collector

    def test_runner_accepts_collector(self) -> None:
        from unittest.mock import MagicMock

        from lunar_sandbox.episode.runner import EpisodeRunner

        collector = TelemetryCollector()
        runner = EpisodeRunner(
            sandbox=MagicMock(),
            task=MagicMock(),
            telemetry_collector=collector,
        )
        assert runner._telemetry is collector

    def test_runner_works_without_collector(self) -> None:
        from unittest.mock import MagicMock

        from lunar_sandbox.episode.runner import EpisodeRunner

        runner = EpisodeRunner(
            sandbox=MagicMock(),
            task=MagicMock(),
        )
        assert runner._telemetry is None


# ===================================================================
# Engine config tests
# ===================================================================


class TestEngineConfig:
    """EngineConfig threshold integration."""

    def test_engine_config_thresholds(self) -> None:
        from lunar_sandbox.sdk.config import EngineConfig

        config = EngineConfig(
            thresholds=ThresholdConfig(allocate_p95_ms=100.0)
        )
        assert config.thresholds is not None
        assert config.thresholds.allocate_p95_ms == 100.0

    def test_engine_config_default_thresholds(self) -> None:
        from lunar_sandbox.sdk.config import EngineConfig

        config = EngineConfig()
        assert config.thresholds is None

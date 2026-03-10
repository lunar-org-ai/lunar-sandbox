"""Tests for PoolMetrics counter tracking and snapshot generation.

Covers initial state, hit/miss recording, cold start tracking,
computed hit_rate, and per-fingerprint independence.
"""

from __future__ import annotations

from lunar_sandbox.pool.metrics import PoolMetrics


class TestPoolMetricsInitialState:
    """All counters start at zero."""

    def test_initial_hits_zero(self) -> None:
        m = PoolMetrics()
        assert m.total_hits == 0

    def test_initial_misses_zero(self) -> None:
        m = PoolMetrics()
        assert m.total_misses == 0

    def test_initial_cold_starts_zero(self) -> None:
        m = PoolMetrics()
        assert m.total_cold_starts == 0

    def test_initial_evictions_zero(self) -> None:
        m = PoolMetrics()
        assert m.total_evictions == 0

    def test_initial_gauges_zero(self) -> None:
        m = PoolMetrics()
        assert m.pool_size == 0
        assert m.idle_count == 0
        assert m.active_count == 0
        assert m.pending_creations == 0

    def test_initial_per_fingerprint_empty(self) -> None:
        m = PoolMetrics()
        assert dict(m.hits_by_fingerprint) == {}
        assert dict(m.misses_by_fingerprint) == {}
        assert dict(m.cold_starts_by_fingerprint) == {}


class TestPoolMetricsRecordHit:
    """record_hit increments total and per-fingerprint counters."""

    def test_increments_total_hits(self) -> None:
        m = PoolMetrics()
        m.record_hit("fp1")
        assert m.total_hits == 1

    def test_increments_per_fingerprint(self) -> None:
        m = PoolMetrics()
        m.record_hit("fp1")
        m.record_hit("fp1")
        assert m.hits_by_fingerprint["fp1"] == 2

    def test_multiple_fingerprints_independent(self) -> None:
        m = PoolMetrics()
        m.record_hit("fp1")
        m.record_hit("fp2")
        m.record_hit("fp2")
        assert m.hits_by_fingerprint["fp1"] == 1
        assert m.hits_by_fingerprint["fp2"] == 2
        assert m.total_hits == 3

    def test_does_not_affect_misses(self) -> None:
        m = PoolMetrics()
        m.record_hit("fp1")
        assert m.total_misses == 0


class TestPoolMetricsRecordMiss:
    """record_miss tracks misses and cold_start flag."""

    def test_increments_total_misses(self) -> None:
        m = PoolMetrics()
        m.record_miss("fp1", cold_start=False)
        assert m.total_misses == 1

    def test_cold_start_true_increments_cold_starts(self) -> None:
        m = PoolMetrics()
        m.record_miss("fp1", cold_start=True)
        assert m.total_cold_starts == 1
        assert m.cold_starts_by_fingerprint["fp1"] == 1

    def test_cold_start_false_does_not_increment(self) -> None:
        m = PoolMetrics()
        m.record_miss("fp1", cold_start=False)
        assert m.total_cold_starts == 0
        assert m.cold_starts_by_fingerprint["fp1"] == 0

    def test_miss_per_fingerprint(self) -> None:
        m = PoolMetrics()
        m.record_miss("fp1", cold_start=True)
        m.record_miss("fp2", cold_start=False)
        assert m.misses_by_fingerprint["fp1"] == 1
        assert m.misses_by_fingerprint["fp2"] == 1


class TestPoolMetricsSnapshot:
    """snapshot() returns all metrics as dict with computed hit_rate."""

    def test_empty_snapshot_hit_rate_zero(self) -> None:
        m = PoolMetrics()
        snap = m.snapshot()
        assert snap["hit_rate"] == 0.0

    def test_snapshot_hit_rate_computed(self) -> None:
        m = PoolMetrics()
        m.record_hit("fp1")
        m.record_hit("fp1")
        m.record_miss("fp1", cold_start=False)
        snap = m.snapshot()
        # 2 hits / 3 total = 0.6667
        assert abs(snap["hit_rate"] - 2 / 3) < 0.001

    def test_snapshot_contains_all_fields(self) -> None:
        m = PoolMetrics()
        snap = m.snapshot()
        expected_keys = {
            "total_hits",
            "total_misses",
            "total_cold_starts",
            "total_evictions",
            "total_ttl_expiries",
            "total_idle_timeouts",
            "total_creations",
            "total_creation_failures",
            "total_health_check_failures",
            "hits_by_fingerprint",
            "misses_by_fingerprint",
            "cold_starts_by_fingerprint",
            "pool_size",
            "idle_count",
            "active_count",
            "pending_creations",
            "hit_rate",
        }
        assert set(snap.keys()) == expected_keys

    def test_snapshot_per_fingerprint_as_regular_dict(self) -> None:
        """Per-fingerprint dicts converted from defaultdict to dict."""
        m = PoolMetrics()
        m.record_hit("fp1")
        snap = m.snapshot()
        assert type(snap["hits_by_fingerprint"]) is dict

    def test_snapshot_100_percent_hit_rate(self) -> None:
        m = PoolMetrics()
        m.record_hit("fp1")
        m.record_hit("fp1")
        snap = m.snapshot()
        assert snap["hit_rate"] == 1.0


class TestPoolMetricsPerFingerprintIndependence:
    """Per-fingerprint counters are independent."""

    def test_independent_hit_tracking(self) -> None:
        m = PoolMetrics()
        for _ in range(5):
            m.record_hit("fp-alpha")
        for _ in range(3):
            m.record_hit("fp-beta")
        assert m.hits_by_fingerprint["fp-alpha"] == 5
        assert m.hits_by_fingerprint["fp-beta"] == 3
        assert m.total_hits == 8

    def test_independent_miss_and_cold_start_tracking(self) -> None:
        m = PoolMetrics()
        m.record_miss("fp-alpha", cold_start=True)
        m.record_miss("fp-alpha", cold_start=False)
        m.record_miss("fp-beta", cold_start=True)
        assert m.cold_starts_by_fingerprint["fp-alpha"] == 1
        assert m.cold_starts_by_fingerprint["fp-beta"] == 1
        assert m.misses_by_fingerprint["fp-alpha"] == 2
        assert m.misses_by_fingerprint["fp-beta"] == 1
        assert m.total_cold_starts == 2

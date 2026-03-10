"""Tests for pool eviction strategies.

Covers TTL expiry, idle timeout, and LRU-diversity eviction selection.
All functions are pure (data in, data out) -- no async or sandbox mocking needed.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from unittest.mock import MagicMock, patch

from lunar_sandbox.pool.entry import PoolEntry
from lunar_sandbox.pool.evictor import (
    select_eviction_candidates,
    select_expired,
    select_idle_timeout,
)


def _make_entry(
    fingerprint: str = "fp1",
    sandbox_id: str = "sb1",
    created_offset: float = 0.0,
    last_used_offset: float = 0.0,
) -> PoolEntry:
    """Create a PoolEntry with controllable timestamps.

    Offsets are subtracted from current monotonic time, so
    created_offset=10 means "created 10 seconds ago".
    """
    now = time.monotonic()
    return PoolEntry(
        sandbox=MagicMock(),
        sandbox_id=sandbox_id,
        fingerprint=fingerprint,
        created_at=now - created_offset,
        last_used_at=now - last_used_offset,
    )


# ---------- select_expired ----------


class TestSelectExpired:
    """TTL expiry selects entries older than ttl_seconds."""

    def test_selects_expired_entry(self) -> None:
        entry = _make_entry(sandbox_id="s1", created_offset=10.0)
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", entry)]),
        }
        result = select_expired(pools, ttl_seconds=5.0)
        assert result == [entry]

    def test_skips_non_expired_entry(self) -> None:
        entry = _make_entry(sandbox_id="s1", created_offset=1.0)
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", entry)]),
        }
        result = select_expired(pools, ttl_seconds=5.0)
        assert result == []

    def test_selects_across_fingerprints(self) -> None:
        e1 = _make_entry(fingerprint="fp1", sandbox_id="s1", created_offset=20.0)
        e2 = _make_entry(fingerprint="fp2", sandbox_id="s2", created_offset=1.0)
        e3 = _make_entry(fingerprint="fp2", sandbox_id="s3", created_offset=30.0)
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", e1)]),
            "fp2": OrderedDict([("s2", e2), ("s3", e3)]),
        }
        result = select_expired(pools, ttl_seconds=5.0)
        result_ids = sorted(e.sandbox_id for e in result)
        assert result_ids == ["s1", "s3"]

    def test_empty_pools(self) -> None:
        pools: dict[str, OrderedDict[str, PoolEntry]] = {}
        result = select_expired(pools, ttl_seconds=5.0)
        assert result == []

    def test_all_expired(self) -> None:
        e1 = _make_entry(sandbox_id="s1", created_offset=100.0)
        e2 = _make_entry(sandbox_id="s2", created_offset=200.0)
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", e1), ("s2", e2)]),
        }
        result = select_expired(pools, ttl_seconds=5.0)
        result_ids = sorted(e.sandbox_id for e in result)
        assert result_ids == ["s1", "s2"]

    def test_removes_expired_from_pool(self) -> None:
        expired = _make_entry(sandbox_id="s1", created_offset=10.0)
        alive = _make_entry(sandbox_id="s2", created_offset=1.0)
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", expired), ("s2", alive)]),
        }
        select_expired(pools, ttl_seconds=5.0)
        assert "s1" not in pools["fp1"]
        assert "s2" in pools["fp1"]


# ---------- select_idle_timeout ----------


class TestSelectIdleTimeout:
    """Idle timeout selects entries idle longer than threshold."""

    def test_selects_idle_entry(self) -> None:
        entry = _make_entry(sandbox_id="s1", last_used_offset=200.0)
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", entry)]),
        }
        result = select_idle_timeout(pools, idle_timeout_seconds=120.0)
        assert result == [entry]

    def test_skips_recently_used(self) -> None:
        entry = _make_entry(sandbox_id="s1", last_used_offset=10.0)
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", entry)]),
        }
        result = select_idle_timeout(pools, idle_timeout_seconds=120.0)
        assert result == []

    def test_selects_across_fingerprints(self) -> None:
        e1 = _make_entry(fingerprint="fp1", sandbox_id="s1", last_used_offset=300.0)
        e2 = _make_entry(fingerprint="fp2", sandbox_id="s2", last_used_offset=5.0)
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", e1)]),
            "fp2": OrderedDict([("s2", e2)]),
        }
        result = select_idle_timeout(pools, idle_timeout_seconds=120.0)
        assert result == [e1]

    def test_empty_pools(self) -> None:
        pools: dict[str, OrderedDict[str, PoolEntry]] = {}
        result = select_idle_timeout(pools, idle_timeout_seconds=120.0)
        assert result == []

    def test_removes_idle_from_pool(self) -> None:
        idle = _make_entry(sandbox_id="s1", last_used_offset=200.0)
        active = _make_entry(sandbox_id="s2", last_used_offset=5.0)
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", idle), ("s2", active)]),
        }
        select_idle_timeout(pools, idle_timeout_seconds=120.0)
        assert "s1" not in pools["fp1"]
        assert "s2" in pools["fp1"]


# ---------- select_eviction_candidates (LRU-diversity) ----------


class TestSelectEvictionCandidates:
    """LRU-diversity eviction prefers fingerprints with most idle sandboxes."""

    def test_picks_from_largest_fingerprint(self) -> None:
        """Fingerprint with 3 idle should lose one before fp with 1 idle."""
        fp1_entries = [
            _make_entry(fingerprint="fp1", sandbox_id=f"s{i}", last_used_offset=float(i))
            for i in range(3)
        ]
        fp2_entry = _make_entry(fingerprint="fp2", sandbox_id="s10", last_used_offset=0.0)

        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict((e.sandbox_id, e) for e in fp1_entries),
            "fp2": OrderedDict([("s10", fp2_entry)]),
        }
        result = select_eviction_candidates(pools, count=1)
        assert len(result) == 1
        assert result[0].fingerprint == "fp1"

    def test_respects_keep_minimum(self) -> None:
        """Each fingerprint at keep_minimum=1 -> no evictions."""
        e1 = _make_entry(fingerprint="fp1", sandbox_id="s1")
        e2 = _make_entry(fingerprint="fp2", sandbox_id="s2")
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", e1)]),
            "fp2": OrderedDict([("s2", e2)]),
        }
        result = select_eviction_candidates(pools, count=1, keep_minimum=1)
        assert result == []

    def test_evicts_above_keep_minimum(self) -> None:
        """fp1 has 2 idle, keep_minimum=1 -> can evict 1 from fp1."""
        e1 = _make_entry(fingerprint="fp1", sandbox_id="s1", last_used_offset=10.0)
        e2 = _make_entry(fingerprint="fp1", sandbox_id="s2", last_used_offset=1.0)
        e3 = _make_entry(fingerprint="fp2", sandbox_id="s3")
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", e1), ("s2", e2)]),
            "fp2": OrderedDict([("s3", e3)]),
        }
        result = select_eviction_candidates(pools, count=1, keep_minimum=1)
        assert len(result) == 1
        assert result[0].fingerprint == "fp1"

    def test_returns_up_to_count(self) -> None:
        """Requesting count=2 with 5 idle entries returns exactly 2."""
        entries = [
            _make_entry(fingerprint="fp1", sandbox_id=f"s{i}", last_used_offset=float(i))
            for i in range(5)
        ]
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict((e.sandbox_id, e) for e in entries),
        }
        result = select_eviction_candidates(pools, count=2, keep_minimum=1)
        assert len(result) == 2

    def test_empty_pools(self) -> None:
        pools: dict[str, OrderedDict[str, PoolEntry]] = {}
        result = select_eviction_candidates(pools, count=5)
        assert result == []

    def test_selects_lru_entry(self) -> None:
        """Within a fingerprint, the least-recently-used entry is evicted first."""
        old = _make_entry(fingerprint="fp1", sandbox_id="old", last_used_offset=100.0)
        new = _make_entry(fingerprint="fp1", sandbox_id="new", last_used_offset=1.0)
        # OrderedDict insertion order: old first, new second
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("old", old), ("new", new)]),
        }
        result = select_eviction_candidates(pools, count=1, keep_minimum=0)
        assert len(result) == 1
        assert result[0].sandbox_id == "old"

    def test_mutates_input_pools(self) -> None:
        """select_eviction_candidates removes selected entries from the input dict."""
        e1 = _make_entry(fingerprint="fp1", sandbox_id="s1", last_used_offset=10.0)
        e2 = _make_entry(fingerprint="fp1", sandbox_id="s2", last_used_offset=1.0)
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict([("s1", e1), ("s2", e2)]),
        }
        select_eviction_candidates(pools, count=1, keep_minimum=0)
        assert len(pools["fp1"]) == 1

    def test_round_robin_across_fingerprints(self) -> None:
        """Eviction spreads across fingerprints rather than draining one."""
        fp1 = [_make_entry(fingerprint="fp1", sandbox_id=f"a{i}", last_used_offset=float(i)) for i in range(3)]
        fp2 = [_make_entry(fingerprint="fp2", sandbox_id=f"b{i}", last_used_offset=float(i)) for i in range(3)]
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict((e.sandbox_id, e) for e in fp1),
            "fp2": OrderedDict((e.sandbox_id, e) for e in fp2),
        }
        result = select_eviction_candidates(pools, count=2, keep_minimum=1)
        assert len(result) == 2
        fingerprints = {e.fingerprint for e in result}
        # Both fingerprints should contribute since they tie in count
        assert fingerprints == {"fp1", "fp2"}

    def test_keep_minimum_zero_allows_full_drain(self) -> None:
        """With keep_minimum=0, all idle sandboxes can be evicted."""
        entries = [
            _make_entry(fingerprint="fp1", sandbox_id=f"s{i}", last_used_offset=float(i))
            for i in range(3)
        ]
        pools: dict[str, OrderedDict[str, PoolEntry]] = {
            "fp1": OrderedDict((e.sandbox_id, e) for e in entries),
        }
        result = select_eviction_candidates(pools, count=10, keep_minimum=0)
        assert len(result) == 3
        assert len(pools["fp1"]) == 0

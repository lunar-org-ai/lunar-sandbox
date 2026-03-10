"""Tests for PoolConfig defaults/overrides and PoolEntry time methods.

Covers config default values, custom overrides, and entry lifecycle
methods (is_expired, is_idle_too_long, mark_used).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from lunar_sandbox.pool.config import PoolConfig
from lunar_sandbox.pool.entry import PoolEntry


# ---------- PoolConfig defaults ----------


class TestPoolConfigDefaults:
    """PoolConfig defaults match research-recommended values."""

    def test_global_max_sandboxes(self) -> None:
        cfg = PoolConfig()
        assert cfg.global_max_sandboxes == 32

    def test_per_fingerprint_soft_limit(self) -> None:
        cfg = PoolConfig()
        assert cfg.per_fingerprint_soft_limit == 8

    def test_idle_timeout_seconds(self) -> None:
        cfg = PoolConfig()
        assert cfg.idle_timeout_seconds == 120.0

    def test_ttl_seconds(self) -> None:
        cfg = PoolConfig()
        assert cfg.ttl_seconds == 300.0

    def test_low_watermark_ratio(self) -> None:
        cfg = PoolConfig()
        assert cfg.low_watermark_ratio == 0.25

    def test_max_concurrent_creations(self) -> None:
        cfg = PoolConfig()
        assert cfg.max_concurrent_creations == 4

    def test_replenish_batch_size(self) -> None:
        cfg = PoolConfig()
        assert cfg.replenish_batch_size == 4

    def test_memory_pressure_threshold(self) -> None:
        cfg = PoolConfig()
        assert cfg.memory_pressure_threshold == 0.85

    def test_all_defaults_tuple(self) -> None:
        """Single assertion checking all 8 key defaults."""
        cfg = PoolConfig()
        assert (
            cfg.global_max_sandboxes,
            cfg.per_fingerprint_soft_limit,
            cfg.idle_timeout_seconds,
            cfg.ttl_seconds,
            cfg.low_watermark_ratio,
            cfg.max_concurrent_creations,
            cfg.replenish_batch_size,
            cfg.memory_pressure_threshold,
        ) == (32, 8, 120.0, 300.0, 0.25, 4, 4, 0.85)


class TestPoolConfigOverrides:
    """User can override each PoolConfig parameter."""

    def test_custom_overrides(self) -> None:
        cfg = PoolConfig(
            global_max_sandboxes=64,
            per_fingerprint_soft_limit=16,
            idle_timeout_seconds=60.0,
            ttl_seconds=600.0,
            low_watermark_ratio=0.5,
            max_concurrent_creations=8,
            replenish_batch_size=2,
            memory_pressure_threshold=0.90,
        )
        assert cfg.global_max_sandboxes == 64
        assert cfg.per_fingerprint_soft_limit == 16
        assert cfg.idle_timeout_seconds == 60.0
        assert cfg.ttl_seconds == 600.0
        assert cfg.low_watermark_ratio == 0.5
        assert cfg.max_concurrent_creations == 8
        assert cfg.replenish_batch_size == 2
        assert cfg.memory_pressure_threshold == 0.90

    def test_partial_overrides(self) -> None:
        cfg = PoolConfig(global_max_sandboxes=100)
        assert cfg.global_max_sandboxes == 100
        assert cfg.per_fingerprint_soft_limit == 8  # default preserved


# ---------- PoolEntry time methods ----------


def _make_entry(
    created_offset: float = 0.0,
    last_used_offset: float = 0.0,
    checkout_count: int = 0,
) -> PoolEntry:
    """Create a PoolEntry with controllable timestamps."""
    now = time.monotonic()
    return PoolEntry(
        sandbox=MagicMock(),
        sandbox_id="test-sb",
        fingerprint="fp-test",
        created_at=now - created_offset,
        last_used_at=now - last_used_offset,
        checkout_count=checkout_count,
    )


class TestPoolEntryIsExpired:
    """PoolEntry.is_expired() checks age against TTL."""

    def test_expired_when_past_ttl(self) -> None:
        entry = _make_entry(created_offset=10.0)
        assert entry.is_expired(ttl_seconds=5.0) is True

    def test_not_expired_within_ttl(self) -> None:
        entry = _make_entry(created_offset=1.0)
        assert entry.is_expired(ttl_seconds=5.0) is False

    def test_boundary_at_ttl(self) -> None:
        """At exactly TTL boundary, should be expired (>= comparison)."""
        entry = _make_entry(created_offset=5.0)
        assert entry.is_expired(ttl_seconds=5.0) is True


class TestPoolEntryIsIdleTooLong:
    """PoolEntry.is_idle_too_long() checks idle duration."""

    def test_idle_too_long_when_past_timeout(self) -> None:
        entry = _make_entry(last_used_offset=200.0)
        assert entry.is_idle_too_long(idle_timeout=120.0) is True

    def test_not_idle_within_timeout(self) -> None:
        entry = _make_entry(last_used_offset=10.0)
        assert entry.is_idle_too_long(idle_timeout=120.0) is False


class TestPoolEntryMarkUsed:
    """PoolEntry.mark_used() updates last_used_at and increments checkout_count."""

    def test_updates_last_used_at(self) -> None:
        entry = _make_entry(last_used_offset=100.0)
        before = entry.last_used_at
        entry.mark_used()
        assert entry.last_used_at > before

    def test_increments_checkout_count(self) -> None:
        entry = _make_entry(checkout_count=0)
        entry.mark_used()
        assert entry.checkout_count == 1
        entry.mark_used()
        assert entry.checkout_count == 2

    def test_mark_used_last_used_at_is_current(self) -> None:
        entry = _make_entry(last_used_offset=50.0)
        before_mark = time.monotonic()
        entry.mark_used()
        after_mark = time.monotonic()
        assert before_mark <= entry.last_used_at <= after_mark

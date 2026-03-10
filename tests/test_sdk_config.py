"""Tests for EngineConfig defaults and customization.

Verifies default values, custom overrides, and the auto-detect
semantics of effective_workers() and effective_pool_size().
"""

from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path

from lunar_sandbox.sdk.config import EngineConfig


# ---------- Defaults ----------


class TestEngineConfigDefaults:
    """EngineConfig defaults match SDK specification."""

    def test_max_workers_default(self) -> None:
        cfg = EngineConfig()
        assert cfg.max_workers == 0

    def test_pool_size_default(self) -> None:
        cfg = EngineConfig()
        assert cfg.pool_size == 0

    def test_trajectory_dir_default(self) -> None:
        cfg = EngineConfig()
        assert cfg.trajectory_dir == Path("trajectories")

    def test_results_dir_default(self) -> None:
        cfg = EngineConfig()
        assert cfg.results_dir == Path("results")

    def test_task_timeout_default(self) -> None:
        cfg = EngineConfig()
        assert cfg.task_timeout == 1800.0

    def test_batch_timeout_default(self) -> None:
        cfg = EngineConfig()
        assert cfg.batch_timeout == 0.0

    def test_max_retries_default(self) -> None:
        cfg = EngineConfig()
        assert cfg.max_retries == 1

    def test_data_root_default(self) -> None:
        cfg = EngineConfig()
        assert cfg.data_root == "/var/lib/lunar-sandbox"

    def test_fail_fast_default(self) -> None:
        cfg = EngineConfig()
        assert cfg.fail_fast is False


# ---------- Custom values ----------


class TestEngineConfigCustom:
    """EngineConfig accepts and stores custom values."""

    def test_custom_workers(self) -> None:
        cfg = EngineConfig(max_workers=4)
        assert cfg.max_workers == 4

    def test_custom_task_timeout(self) -> None:
        cfg = EngineConfig(task_timeout=60.0)
        assert cfg.task_timeout == 60.0

    def test_custom_pool_size(self) -> None:
        cfg = EngineConfig(pool_size=10)
        assert cfg.pool_size == 10

    def test_custom_fail_fast(self) -> None:
        cfg = EngineConfig(fail_fast=True)
        assert cfg.fail_fast is True

    def test_is_dataclass(self) -> None:
        cfg = EngineConfig()
        # dataclass instances have __dataclass_fields__
        assert hasattr(cfg, "__dataclass_fields__")
        field_names = [f.name for f in fields(cfg)]
        assert "max_workers" in field_names
        assert "task_timeout" in field_names


# ---------- Effective values ----------


class TestEffectiveValues:
    """effective_workers() and effective_pool_size() auto-detect when zero."""

    def test_effective_workers_explicit(self) -> None:
        cfg = EngineConfig(max_workers=4)
        assert cfg.effective_workers() == 4

    def test_effective_workers_auto(self) -> None:
        cfg = EngineConfig(max_workers=0)
        result = cfg.effective_workers()
        # Should be at least 1, derived from os.cpu_count()
        assert result >= 1
        expected = max(1, os.cpu_count() or 1)
        assert result == expected

    def test_effective_pool_size_explicit(self) -> None:
        cfg = EngineConfig(pool_size=10)
        assert cfg.effective_pool_size() == 10

    def test_effective_pool_size_auto(self) -> None:
        cfg = EngineConfig(pool_size=0, max_workers=4)
        # Auto = effective_workers * 2
        assert cfg.effective_pool_size() == 8

    def test_effective_pool_size_auto_from_auto_workers(self) -> None:
        cfg = EngineConfig(pool_size=0, max_workers=0)
        expected = max(1, os.cpu_count() or 1) * 2
        assert cfg.effective_pool_size() == expected

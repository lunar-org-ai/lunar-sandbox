"""Tests for BatchConfig defaults and overrides.

Verifies that all default values match Phase 5 requirements and that
custom values properly override defaults.
"""

from __future__ import annotations

from pathlib import Path

from lunar_sandbox.scheduler.config import BatchConfig


# ---------- Defaults ----------


class TestBatchConfigDefaults:
    """BatchConfig defaults match Phase 5 requirements."""

    def test_max_workers(self) -> None:
        cfg = BatchConfig()
        assert cfg.max_workers == 8

    def test_max_steps(self) -> None:
        cfg = BatchConfig()
        assert cfg.max_steps == 50

    def test_task_timeout(self) -> None:
        cfg = BatchConfig()
        assert cfg.task_timeout == 1800.0

    def test_batch_timeout(self) -> None:
        cfg = BatchConfig()
        assert cfg.batch_timeout == 0.0

    def test_max_retries(self) -> None:
        cfg = BatchConfig()
        assert cfg.max_retries == 1

    def test_fail_fast(self) -> None:
        cfg = BatchConfig()
        assert cfg.fail_fast is False

    def test_trajectory_dir_default(self) -> None:
        cfg = BatchConfig()
        assert cfg.trajectory_dir == Path("trajectories")

    def test_results_dir_default(self) -> None:
        cfg = BatchConfig()
        assert cfg.results_dir == Path("results")

    def test_all_defaults_tuple(self) -> None:
        """Single assertion checking all 8 key defaults."""
        cfg = BatchConfig()
        assert (
            cfg.max_workers,
            cfg.max_steps,
            cfg.task_timeout,
            cfg.batch_timeout,
            cfg.max_retries,
            cfg.fail_fast,
            cfg.trajectory_dir,
            cfg.results_dir,
        ) == (8, 50, 1800.0, 0.0, 1, False, Path("trajectories"), Path("results"))


# ---------- Custom values ----------


class TestBatchConfigCustomValues:
    """User can override each BatchConfig parameter."""

    def test_custom_values(self) -> None:
        cfg = BatchConfig(
            max_workers=16,
            max_steps=100,
            task_timeout=3600.0,
            batch_timeout=7200.0,
            max_retries=3,
            fail_fast=True,
            trajectory_dir=Path("/tmp/traj"),
            results_dir=Path("/tmp/res"),
        )
        assert cfg.max_workers == 16
        assert cfg.max_steps == 100
        assert cfg.task_timeout == 3600.0
        assert cfg.batch_timeout == 7200.0
        assert cfg.max_retries == 3
        assert cfg.fail_fast is True
        assert cfg.trajectory_dir == Path("/tmp/traj")
        assert cfg.results_dir == Path("/tmp/res")

    def test_partial_overrides(self) -> None:
        cfg = BatchConfig(max_workers=4)
        assert cfg.max_workers == 4
        assert cfg.max_steps == 50  # default preserved
        assert cfg.fail_fast is False  # default preserved

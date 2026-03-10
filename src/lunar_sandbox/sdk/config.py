"""Engine configuration for the SDK layer.

Provides :class:`EngineConfig` -- the top-level configuration dataclass
that users set once and pass to :class:`LunarEngine`.  Subsystem configs
(:class:`BatchConfig`, :class:`PoolConfig`) are derived from it internally.

Uses a plain dataclass (not Pydantic) to match codebase convention
established by :class:`BatchConfig` and :class:`PoolConfig`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["EngineConfig"]


@dataclass
class EngineConfig:
    """Top-level configuration for the Lunar Sandbox engine.

    Provides sensible defaults for all settings.  Zero-valued
    ``max_workers`` and ``pool_size`` trigger auto-detection at
    engine startup time.

    Attributes:
        max_workers: Maximum parallel task executions.  ``0`` means
            auto-detect from ``os.cpu_count()``.
        pool_size: Maximum sandboxes in the pool.  ``0`` means
            auto-derive from ``max_workers * 2``.
        trajectory_dir: Directory for JSONL trajectory files and the
            SQLite trajectory database.
        results_dir: Directory for batch result JSONL and SQLite.
        task_timeout: Per-task timeout in seconds.  Defaults to 30 min.
        batch_timeout: Total batch timeout in seconds.  ``0.0`` means
            no batch-level timeout.
        max_retries: Maximum retries for infrastructure errors.
        data_root: Root directory for sandbox runtime data (OverlayFS
            layers, cgroups, etc.).
        fail_fast: Stop the entire batch on the first task failure.
    """

    max_workers: int = 0
    pool_size: int = 0
    trajectory_dir: Path = field(default_factory=lambda: Path("trajectories"))
    results_dir: Path = field(default_factory=lambda: Path("results"))
    task_timeout: float = 1800.0
    batch_timeout: float = 0.0
    max_retries: int = 1
    data_root: str = "/var/lib/lunar-sandbox"
    fail_fast: bool = False

    def effective_workers(self) -> int:
        """Return the effective worker count, auto-detecting if zero."""
        if self.max_workers > 0:
            return self.max_workers
        return max(1, os.cpu_count() or 1)

    def effective_pool_size(self) -> int:
        """Return the effective pool size, auto-deriving if zero."""
        if self.pool_size > 0:
            return self.pool_size
        return self.effective_workers() * 2

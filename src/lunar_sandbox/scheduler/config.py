"""Batch evaluation configuration.

Provides :class:`BatchConfig` -- the configuration dataclass for a batch
evaluation run.  Follows the codebase convention of plain dataclasses
(not Pydantic) for config types, consistent with :class:`PoolConfig`.

Design decision: ``on_task_complete`` callback is NOT included here.
It is runtime state (who to notify as tasks finish), not configuration
(how the batch should behave).  It belongs as a parameter to
``run_batch()`` in the scheduler, keeping BatchConfig serializable and
purely declarative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["BatchConfig"]


@dataclass
class BatchConfig:
    """Configuration for a batch evaluation run.

    Attributes:
        max_workers: Maximum parallel task executions.  Actual concurrency
            is ``min(max_workers, pool_capacity)``.
        max_steps: Default max agent steps per task.  Can be overridden
            per-task via ``TaskDefinition.max_steps`` or benchmark YAML.
        task_timeout: Per-task timeout in seconds.  Kills individual
            episode if exceeded.
        batch_timeout: Total batch timeout in seconds.  Stops entire run.
            ``0.0`` means no batch timeout.
        max_retries: Max retries for infrastructure errors only (sandbox
            crash, timeout).  ``0`` means no retry.
        fail_fast: Stop the entire batch on first task failure.
        trajectory_dir: Directory for JSONL trajectory files.
        results_dir: Directory for batch results (JSONL + SQLite).
    """

    max_workers: int = 8
    max_steps: int = 50
    task_timeout: float = 1800.0  # 30 min per task
    batch_timeout: float = 0.0  # 0 = no batch timeout
    max_retries: int = 1  # 1 retry for infra errors
    fail_fast: bool = False
    trajectory_dir: Path = field(default_factory=lambda: Path("trajectories"))
    results_dir: Path = field(default_factory=lambda: Path("results"))

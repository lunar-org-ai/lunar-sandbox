"""Benchmark YAML schema and loading.

Provides :class:`BenchmarkDefinition` and :class:`BenchmarkTask` Pydantic
models for validating benchmark YAML files, and :func:`load_benchmark` for
loading a benchmark with glob expansion and task resolution.

A benchmark YAML file defines a reusable evaluation suite::

    name: swe-bench-lite
    description: Lightweight subset of SWE-bench
    version: "1.0"
    defaults:
      timeout: 1800
      max_steps: 50
    tasks:
      - path: tasks/django-fix-queryset.yaml
      - path: "tasks/flask-*.yaml"
        timeout: 3600
        max_steps: 100
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from lunar_sandbox.task.loader import load_task
from lunar_sandbox.task.schema import TaskDefinition

__all__ = ["BenchmarkDefinition", "BenchmarkTask", "load_benchmark"]


class BenchmarkTask(BaseModel):
    """A single task reference within a benchmark.

    Attributes:
        path: YAML file path or glob pattern (e.g. ``"tasks/*.yaml"``).
            Resolved relative to the benchmark YAML file's parent directory.
        timeout: Per-task timeout override (seconds).  Takes priority over
            benchmark defaults.
        max_steps: Per-task max-steps override.  Takes priority over
            benchmark defaults.
        weight: For future weighted sampling.  Defaults to ``1.0``.
    """

    path: str
    timeout: int | None = None
    max_steps: int | None = None
    weight: float = 1.0


class BenchmarkDefinition(BaseModel):
    """Schema for a benchmark YAML file defining a reusable task suite.

    Attributes:
        name: Human-readable benchmark name.
        description: Optional description of the benchmark.
        version: Semantic version string.
        defaults: Default overrides applied to all tasks (e.g.
            ``{"timeout": 1800, "max_steps": 50}``).
        tasks: List of task references with optional per-task overrides.
    """

    name: str
    description: str = ""
    version: str = "1.0"
    defaults: dict[str, Any] = Field(default_factory=dict)
    tasks: list[BenchmarkTask]


def _is_glob_pattern(path_str: str) -> bool:
    """Return True if the path string contains glob metacharacters."""
    return "*" in path_str or "?" in path_str


def load_benchmark(
    yaml_path: Path,
) -> tuple[BenchmarkDefinition, list[TaskDefinition]]:
    """Load a benchmark YAML and resolve all task definitions.

    For each :class:`BenchmarkTask`:

    1. If the path contains glob characters (``*`` or ``?``), expand it
       relative to the benchmark file's parent directory.
    2. Otherwise, treat it as a direct file reference.
    3. Load each resolved path via :func:`~lunar_sandbox.task.loader.load_task`.
    4. Apply benchmark defaults, then per-task overrides (highest priority).

    Task name uniqueness is enforced: if duplicate names are detected,
    a ``"_2"``, ``"_3"`` suffix is appended.

    Args:
        yaml_path: Path to the benchmark YAML file.

    Returns:
        A tuple of ``(BenchmarkDefinition, list[TaskDefinition])``.

    Raises:
        FileNotFoundError: If *yaml_path* does not exist.
        FileNotFoundError: If a non-glob task path does not resolve to
            any file.
        ValueError: If a non-glob task path does not exist.
        yaml.YAMLError: If the YAML is malformed.
        pydantic.ValidationError: If the YAML fails schema validation.
    """
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        msg = f"Benchmark file not found: {yaml_path}"
        raise FileNotFoundError(msg)

    raw = yaml_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    benchmark = BenchmarkDefinition.model_validate(data)

    base_dir = yaml_path.parent
    defaults = benchmark.defaults
    task_definitions: list[TaskDefinition] = []
    name_counts: dict[str, int] = {}

    for bench_task in benchmark.tasks:
        # Resolve paths
        if _is_glob_pattern(bench_task.path):
            resolved_paths = sorted(base_dir.glob(bench_task.path))
        else:
            resolved = base_dir / bench_task.path
            if not resolved.exists():
                msg = f"Task file not found: {resolved} (referenced in benchmark '{benchmark.name}')"
                raise ValueError(msg)
            resolved_paths = [resolved]

        for task_path in resolved_paths:
            task_def = load_task(task_path)

            # Apply benchmark defaults (lower priority)
            if "timeout" in defaults and bench_task.timeout is None:
                task_def = _with_field(task_def, "timeout", defaults["timeout"])
            if "max_steps" in defaults and bench_task.max_steps is None:
                task_def = _with_field(task_def, "max_steps", defaults["max_steps"])

            # Apply per-task overrides (highest priority)
            if bench_task.timeout is not None:
                task_def = _with_field(task_def, "timeout", bench_task.timeout)
            if bench_task.max_steps is not None:
                task_def = _with_field(task_def, "max_steps", bench_task.max_steps)

            # Handle name uniqueness
            name = task_def.name or task_path.stem
            if not task_def.name:
                task_def = _with_field(task_def, "name", name)

            if name in name_counts:
                name_counts[name] += 1
                unique_name = f"{name}_{name_counts[name]}"
                task_def = _with_field(task_def, "name", unique_name)
            else:
                name_counts[name] = 1

            task_definitions.append(task_def)

    return benchmark, task_definitions


def _with_field(
    task_def: TaskDefinition,
    field_name: str,
    value: Any,
) -> TaskDefinition:
    """Return a copy of the TaskDefinition with one field overridden.

    Uses Pydantic's model_copy to create an immutable-style update.
    """
    return task_def.model_copy(update={field_name: value})

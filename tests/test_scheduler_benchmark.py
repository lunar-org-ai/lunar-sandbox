"""Tests for BenchmarkDefinition, BenchmarkTask, and load_benchmark.

Verifies YAML schema validation, glob expansion, default/override
application, and error handling for missing files and duplicates.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lunar_sandbox.scheduler.benchmark import (
    BenchmarkDefinition,
    BenchmarkTask,
    load_benchmark,
)


# ---------- Minimal task YAML helper ----------

_TASK_YAML = """\
name: {name}
repo:
  path: /tmp/fake
instructions: do something
test_command: echo ok
"""


def _write_task_yaml(directory: Path, name: str, content: str | None = None) -> Path:
    """Write a minimal valid task YAML into directory."""
    if content is None:
        content = _TASK_YAML.format(name=name)
    path = directory / f"{name}.yaml"
    path.write_text(content, encoding="utf-8")
    return path


# ---------- BenchmarkDefinition schema ----------


class TestBenchmarkDefinition:
    """Pydantic schema validation for BenchmarkDefinition."""

    def test_minimal(self) -> None:
        """name + tasks only is valid."""
        bd = BenchmarkDefinition(
            name="test-bench",
            tasks=[BenchmarkTask(path="task.yaml")],
        )
        assert bd.name == "test-bench"
        assert len(bd.tasks) == 1
        assert bd.description == ""
        assert bd.version == "1.0"
        assert bd.defaults == {}

    def test_full(self) -> None:
        """All fields populated."""
        bd = BenchmarkDefinition(
            name="swe-bench-lite",
            description="Lightweight subset of SWE-bench",
            version="2.0",
            defaults={"timeout": 1800, "max_steps": 50},
            tasks=[
                BenchmarkTask(path="tasks/t1.yaml", timeout=3600, max_steps=100, weight=2.0),
                BenchmarkTask(path="tasks/t2.yaml"),
            ],
        )
        assert bd.name == "swe-bench-lite"
        assert bd.description == "Lightweight subset of SWE-bench"
        assert bd.version == "2.0"
        assert bd.defaults == {"timeout": 1800, "max_steps": 50}
        assert len(bd.tasks) == 2


class TestBenchmarkTaskDefaults:
    """BenchmarkTask has correct defaults."""

    def test_defaults(self) -> None:
        bt = BenchmarkTask(path="task.yaml")
        assert bt.weight == 1.0
        assert bt.timeout is None
        assert bt.max_steps is None


# ---------- load_benchmark ----------


class TestLoadBenchmark:
    """load_benchmark() loads YAML and resolves tasks."""

    def test_single_task(self) -> None:
        """Create temp YAML with one task, verify loading."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            _write_task_yaml(td, "test-task")

            bench_yaml = td / "bench.yaml"
            bench_yaml.write_text(
                """\
name: simple-bench
tasks:
  - path: test-task.yaml
""",
                encoding="utf-8",
            )

            benchmark, tasks = load_benchmark(bench_yaml)
            assert benchmark.name == "simple-bench"
            assert len(tasks) == 1
            assert tasks[0].name == "test-task"
            assert tasks[0].instructions == "do something"

    def test_glob_pattern(self) -> None:
        """Glob "*.yaml" resolves multiple task YAMLs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            tasks_dir = td / "tasks"
            tasks_dir.mkdir()
            _write_task_yaml(tasks_dir, "alpha")
            _write_task_yaml(tasks_dir, "beta")
            _write_task_yaml(tasks_dir, "gamma")

            bench_yaml = td / "bench.yaml"
            bench_yaml.write_text(
                """\
name: glob-bench
tasks:
  - path: "tasks/*.yaml"
""",
                encoding="utf-8",
            )

            benchmark, tasks = load_benchmark(bench_yaml)
            assert len(tasks) == 3
            names = {t.name for t in tasks}
            assert names == {"alpha", "beta", "gamma"}

    def test_defaults_applied(self) -> None:
        """Benchmark defaults (timeout=600) applied to tasks without overrides."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            _write_task_yaml(td, "default-task")

            bench_yaml = td / "bench.yaml"
            bench_yaml.write_text(
                """\
name: defaults-bench
defaults:
  timeout: 600
  max_steps: 25
tasks:
  - path: default-task.yaml
""",
                encoding="utf-8",
            )

            _, tasks = load_benchmark(bench_yaml)
            assert len(tasks) == 1
            assert tasks[0].timeout == 600
            assert tasks[0].max_steps == 25

    def test_per_task_override(self) -> None:
        """BenchmarkTask timeout overrides benchmark default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            _write_task_yaml(td, "override-task")

            bench_yaml = td / "bench.yaml"
            bench_yaml.write_text(
                """\
name: override-bench
defaults:
  timeout: 600
tasks:
  - path: override-task.yaml
    timeout: 3600
""",
                encoding="utf-8",
            )

            _, tasks = load_benchmark(bench_yaml)
            assert tasks[0].timeout == 3600

    def test_file_not_found(self) -> None:
        """Nonexistent YAML -> FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_benchmark(Path("/tmp/nonexistent-benchmark-12345.yaml"))

    def test_duplicate_task_names(self) -> None:
        """Two tasks with same name get suffixed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            _write_task_yaml(td, "dup-task")

            # Write second task file with same name field but different filename
            second_yaml = td / "dup-task-copy.yaml"
            second_yaml.write_text(
                """\
name: dup-task
repo:
  path: /tmp/fake2
instructions: do something else
test_command: echo ok2
""",
                encoding="utf-8",
            )

            bench_yaml = td / "bench.yaml"
            bench_yaml.write_text(
                """\
name: dup-bench
tasks:
  - path: dup-task.yaml
  - path: dup-task-copy.yaml
""",
                encoding="utf-8",
            )

            _, tasks = load_benchmark(bench_yaml)
            assert len(tasks) == 2
            names = [t.name for t in tasks]
            assert "dup-task" in names
            assert "dup-task_2" in names

    def test_task_file_not_found_in_benchmark(self) -> None:
        """Non-glob task path that doesn't exist raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            bench_yaml = td / "bench.yaml"
            bench_yaml.write_text(
                """\
name: missing-task-bench
tasks:
  - path: nonexistent-task.yaml
""",
                encoding="utf-8",
            )

            with pytest.raises(ValueError, match="Task file not found"):
                load_benchmark(bench_yaml)

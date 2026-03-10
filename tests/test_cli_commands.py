"""Tests for CLI command registration, help text, and dry-run mode.

Uses typer.testing.CliRunner to verify all commands are registered,
help text shows expected options, and dry-run mode validates without
launching sandboxes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import typer
from typer.testing import CliRunner

from lunar_sandbox.cli.main import app

runner = CliRunner()


# ---------- Top-level app ----------


class TestAppHelp:
    """Top-level app has --help and --version."""

    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Lunar Sandbox" in result.output

    def test_version(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        # Should contain version string
        assert "lunar-sandbox" in result.output


# ---------- run command ----------


class TestRunCommand:
    """``lunar run`` command help and dry-run."""

    def test_help(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--agent" in result.output
        assert "--json" in result.output
        assert "--human" in result.output
        assert "--dry-run" in result.output
        assert "--workers" in result.output
        assert "-v" in result.output

    def test_dry_run_valid_task(self, tmp_path: Path) -> None:
        """--dry-run with a valid task YAML exits 0."""
        yaml_file = tmp_path / "task.yaml"
        yaml_file.write_text(
            "name: test-task\n"
            "repo:\n"
            "  path: /tmp/repo\n"
            "instructions: Do something\n"
            "test_command: pytest\n"
        )
        result = runner.invoke(app, ["run", str(yaml_file), "--dry-run"])
        assert result.exit_code == 0

    def test_dry_run_nonexistent_file(self) -> None:
        """--dry-run with nonexistent file exits with user error."""
        result = runner.invoke(app, ["run", "/nonexistent/task.yaml", "--dry-run"])
        assert result.exit_code == 3

    def test_dry_run_json_output(self, tmp_path: Path) -> None:
        """--dry-run --json produces JSON output."""
        yaml_file = tmp_path / "task.yaml"
        yaml_file.write_text(
            "name: json-test\n"
            "repo:\n"
            "  path: /tmp/repo\n"
            "instructions: Do something\n"
            "test_command: pytest\n"
        )
        result = runner.invoke(app, ["run", str(yaml_file), "--dry-run", "--json"])
        assert result.exit_code == 0
        assert "dry_run" in result.output
        assert "true" in result.output.lower()

    def test_dry_run_human_output(self, tmp_path: Path) -> None:
        """--dry-run --human produces human-readable output."""
        yaml_file = tmp_path / "task.yaml"
        yaml_file.write_text(
            "name: human-test\n"
            "repo:\n"
            "  path: /tmp/repo\n"
            "instructions: Do something\n"
            "test_command: pytest\n"
        )
        result = runner.invoke(app, ["run", str(yaml_file), "--dry-run", "--human"])
        assert result.exit_code == 0


# ---------- eval command ----------


class TestEvalCommand:
    """``lunar eval`` command help and dry-run."""

    def test_help(self) -> None:
        result = runner.invoke(app, ["eval", "--help"])
        assert result.exit_code == 0
        assert "--agent" in result.output
        assert "--workers" in result.output
        assert "--pass-threshold" in result.output
        assert "--json" in result.output
        assert "--human" in result.output
        assert "-v" in result.output
        assert "--dry-run" in result.output
        assert "--fail-fast" in result.output

    def test_dry_run_valid_benchmark(self, tmp_path: Path) -> None:
        """--dry-run with a valid benchmark YAML exits 0."""
        # Create a task file for the benchmark to reference
        task_file = tmp_path / "task.yaml"
        task_file.write_text(
            "name: bench-task\n"
            "repo:\n"
            "  path: /tmp/repo\n"
            "instructions: Do something\n"
            "test_command: pytest\n"
        )
        # Create benchmark YAML referencing the task
        bench_file = tmp_path / "benchmark.yaml"
        bench_file.write_text(
            "name: test-bench\n"
            "tasks:\n"
            f"  - path: {task_file}\n"
        )
        result = runner.invoke(app, ["eval", str(bench_file), "--dry-run"])
        assert result.exit_code == 0


# ---------- replay command ----------


class TestReplayCommand:
    """``lunar replay`` command help text."""

    def test_help(self) -> None:
        result = runner.invoke(app, ["replay", "--help"])
        assert result.exit_code == 0
        assert "--interactive" in result.output or "-i" in result.output
        assert "--step" in result.output or "-s" in result.output
        assert "--json" in result.output
        assert "--human" in result.output
        assert "--db" in result.output


# ---------- pool command ----------


class TestPoolCommand:
    """``lunar pool`` subcommands: start, status, stop."""

    def test_help(self) -> None:
        result = runner.invoke(app, ["pool", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "status" in result.output
        assert "stop" in result.output

    def test_status_no_daemon(self) -> None:
        """``pool status`` reports no daemon running."""
        with (
            patch("lunar_sandbox.cli.pool_cmd._read_pid", return_value=None),
        ):
            result = runner.invoke(app, ["pool", "status"])
            assert result.exit_code == 0

    def test_status_json_no_daemon(self) -> None:
        """``pool status --json`` reports no daemon in JSON."""
        with (
            patch("lunar_sandbox.cli.pool_cmd._read_pid", return_value=None),
        ):
            result = runner.invoke(app, ["pool", "status", "--json"])
            assert result.exit_code == 0
            assert "false" in result.output.lower()

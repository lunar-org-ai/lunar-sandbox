"""Tests for ``lunar telemetry`` CLI subcommands.

Uses typer.testing.CliRunner to verify show, compare, export, and clear
commands against a temporary SQLite database populated with test data.
Follows the same pattern as test_cli_commands.py from Phase 06-05.

The CliRunner captures both stdout and stderr, so structlog debug lines
may appear in output. Helper functions extract JSON from mixed output.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from typer.testing import CliRunner

from lunar_sandbox.cli.telemetry_cmd import app
from lunar_sandbox.telemetry.store import TelemetryStore
from lunar_sandbox.telemetry.types import MetricSample

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _populate_store(
    db_path: Path, num_runs: int = 2, samples_per_run: int = 10
) -> None:
    """Create a TelemetryStore with test data."""
    store = TelemetryStore(db_path)
    store.open()
    try:
        for i in range(1, num_runs + 1):
            run_id = f"run-{i}"
            base_time = time.time() - (num_runs - i) * 3600
            samples: list[MetricSample] = []
            for j in range(samples_per_run):
                for metric in [
                    "allocate_latency",
                    "reset_latency",
                    "episode_duration",
                ]:
                    samples.append(
                        MetricSample(
                            metric=metric,
                            value=float(j * 10 + i),
                            fingerprint=f"fp-{j % 2}",
                            batch_run_id=run_id,
                            timestamp=time.monotonic() + j,
                        )
                    )
                samples.append(
                    MetricSample(
                        metric="cache_hit",
                        value=1.0 if j % 3 != 0 else 0.0,
                        fingerprint=f"fp-{j % 2}",
                        batch_run_id=run_id,
                        timestamp=time.monotonic() + j,
                    )
                )
            store.save_run(
                run_id=run_id,
                samples=samples,
                started_at=base_time,
                ended_at=base_time + 60,
                total_episodes=samples_per_run,
                throughput=samples_per_run / 1.0,
                cache_hit_rate=0.67,
            )
    finally:
        store.close()


def _patch_db(monkeypatch, db_path: Path) -> None:
    """Monkeypatch _get_default_db_path to use a temp DB."""
    monkeypatch.setattr(
        "lunar_sandbox.cli.telemetry_cmd._get_default_db_path",
        lambda: db_path,
    )


def _extract_json(output: str) -> dict | list:
    """Extract and parse JSON from CLI output mixed with log lines.

    Finds the first line starting with '{' or '[' and parses the
    contiguous JSON block, skipping structlog lines before and after.
    """
    lines = output.strip().split("\n")
    json_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("{", "[")):
            json_start = i
            break
    if json_start is None:
        raise ValueError(f"No JSON found in output: {output!r}")

    # Accumulate lines until we can parse valid JSON
    for end in range(json_start + 1, len(lines) + 1):
        candidate = "\n".join(lines[json_start:end])
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    # Try the whole remainder
    return json.loads("\n".join(lines[json_start:]))


def _extract_csv(output: str) -> list[str]:
    """Extract CSV lines from mixed output, filtering out log lines."""
    lines = output.strip().split("\n")
    csv_lines = []
    found_header = False
    for line in lines:
        if not found_header:
            if line.startswith("run_id"):
                found_header = True
                csv_lines.append(line)
        else:
            # Stop if we hit a non-CSV line (e.g. "Exported N samples")
            if line.startswith("Exported") or line.startswith("20"):
                continue
            csv_lines.append(line)
    return csv_lines


# ===================================================================
# Show command tests
# ===================================================================


class TestShowCommand:
    """``lunar telemetry show`` command tests."""

    def test_show_no_data(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _patch_db(monkeypatch, db_path)
        # db does not exist -> "No telemetry data" message
        result = runner.invoke(app, ["show", "--human"])
        assert result.exit_code == 0
        assert "No telemetry data" in result.output

    def test_show_latest_run(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=1)
        _patch_db(monkeypatch, db_path)

        result = runner.invoke(app, ["show", "--human"])
        assert result.exit_code == 0
        assert "allocate_latency" in result.output

    def test_show_specific_run(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=2)
        _patch_db(monkeypatch, db_path)

        result = runner.invoke(app, ["show", "run-2", "--human"])
        assert result.exit_code == 0
        assert "run-2" in result.output

    def test_show_json_output(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=1)
        _patch_db(monkeypatch, db_path)

        result = runner.invoke(app, ["show", "--json"])
        assert result.exit_code == 0
        data = _extract_json(result.output)
        assert "metrics" in data

    def test_show_by_fingerprint(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=1)
        _patch_db(monkeypatch, db_path)

        result = runner.invoke(app, ["show", "--by-fingerprint", "--human"])
        assert result.exit_code == 0
        # Two fingerprints from the populated data: fp-0 and fp-1
        assert "fp-0" in result.output
        assert "fp-1" in result.output


# ===================================================================
# Compare command tests
# ===================================================================


class TestCompareCommand:
    """``lunar telemetry compare`` command tests."""

    def test_compare_two_runs(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=2)
        _patch_db(monkeypatch, db_path)

        result = runner.invoke(app, ["compare", "run-1", "run-2", "--human"])
        assert result.exit_code == 0
        assert "allocate_latency" in result.output

    def test_compare_json_output(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=2)
        _patch_db(monkeypatch, db_path)

        result = runner.invoke(app, ["compare", "run-1", "run-2", "--json"])
        assert result.exit_code == 0
        data = _extract_json(result.output)
        assert "comparisons" in data
        assert isinstance(data["comparisons"], list)

    def test_compare_missing_run(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=1)
        _patch_db(monkeypatch, db_path)

        result = runner.invoke(app, ["compare", "run-1", "nonexistent", "--human"])
        # Should exit with user error
        assert result.exit_code != 0
        assert "not found" in result.output


# ===================================================================
# Export command tests
# ===================================================================


class TestExportCommand:
    """``lunar telemetry export`` command tests."""

    def test_export_json(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=1)
        _patch_db(monkeypatch, db_path)

        result = runner.invoke(app, ["export", "run-1"])
        assert result.exit_code == 0
        data = _extract_json(result.output)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_export_csv(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=1)
        _patch_db(monkeypatch, db_path)

        result = runner.invoke(app, ["export", "run-1", "--format", "csv"])
        assert result.exit_code == 0
        csv_lines = _extract_csv(result.output)
        assert len(csv_lines) > 0, f"No CSV found in: {result.output!r}"
        assert "run_id" in csv_lines[0]
        assert "metric" in csv_lines[0]
        # Should have data rows after header
        assert len(csv_lines) > 1

    def test_export_to_file(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=1)
        _patch_db(monkeypatch, db_path)

        out_file = tmp_path / "output.json"
        result = runner.invoke(
            app, ["export", "run-1", "-o", str(out_file)]
        )
        assert result.exit_code == 0
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert isinstance(data, list)


# ===================================================================
# Clear command tests
# ===================================================================


class TestClearCommand:
    """``lunar telemetry clear`` command tests."""

    def test_clear_specific_run(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=2)
        _patch_db(monkeypatch, db_path)

        result = runner.invoke(
            app, ["clear", "--run-id", "run-1", "--force"]
        )
        assert result.exit_code == 0
        # CliRunner is non-TTY, so output mode is JSON
        assert "deleted" in result.output

        # Verify run-1 gone, run-2 remains
        store = TelemetryStore(db_path)
        store.open()
        try:
            runs = store.query_runs()
            run_ids = [r["run_id"] for r in runs]
            assert "run-1" not in run_ids
            assert "run-2" in run_ids
        finally:
            store.close()

    def test_clear_all(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=3)
        _patch_db(monkeypatch, db_path)

        result = runner.invoke(app, ["clear", "--all", "--force"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()

        # Verify all gone
        store = TelemetryStore(db_path)
        store.open()
        try:
            runs = store.query_runs()
            assert len(runs) == 0
        finally:
            store.close()

    def test_clear_without_flag(self, tmp_path: Path, monkeypatch) -> None:
        db_path = tmp_path / "telem.db"
        _populate_store(db_path, num_runs=1)
        _patch_db(monkeypatch, db_path)

        # Neither --run-id nor --all should produce error
        result = runner.invoke(app, ["clear", "--force"])
        assert result.exit_code != 0
        assert "Specify" in result.output or "error" in result.output.lower()

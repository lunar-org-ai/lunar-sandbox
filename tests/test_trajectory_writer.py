"""Unit tests for TrajectoryWriter JSONL streaming.

Tests file creation, one-line-per-step invariant, append mode, flush-after-write,
context manager protocol, close idempotency, and property accessors.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from lunar_sandbox.trajectory.models import StepState, TrajectoryStep
from lunar_sandbox.trajectory.writer import TrajectoryWriter


def _make_step(episode_id: str = "ep-test", step_idx: int = 0) -> TrajectoryStep:
    """Create a minimal valid TrajectoryStep."""
    return TrajectoryStep(
        episode_id=episode_id,
        step_idx=step_idx,
        timestamp=1700000000.0 + step_idx,
        state=StepState(cwd="/work"),
        action="execute_command",
        action_params={"command": f"echo {step_idx}"},
        observation={"stdout": str(step_idx)},
    )


class TestTrajectoryWriter:
    """Tests for TrajectoryWriter JSONL streaming."""

    def test_writer_creates_directory(self) -> None:
        """Writer creates trajectory_dir if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "a" / "b" / "c"
            w = TrajectoryWriter(nested, "ep-1")
            w.open()
            try:
                assert nested.is_dir()
            finally:
                w.close()

    def test_writer_creates_jsonl_file(self) -> None:
        """After open + write_step + close, file exists with correct name."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            w = TrajectoryWriter(d, "ep-abc")
            w.open()
            w.write_step(_make_step(episode_id="ep-abc"))
            w.close()
            assert (d / "ep-abc.jsonl").exists()

    def test_writer_one_line_per_step(self) -> None:
        """Writing N steps produces N lines, each valid JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            w = TrajectoryWriter(d, "ep-lines")
            w.open()
            n = 5
            for i in range(n):
                w.write_step(_make_step(step_idx=i))
            w.close()

            lines = (d / "ep-lines.jsonl").read_text().strip().split("\n")
            assert len(lines) == n
            for line in lines:
                parsed = json.loads(line)
                assert "episode_id" in parsed
                assert "action" in parsed

    def test_writer_append_mode(self) -> None:
        """Opening an existing file appends (doesn't overwrite)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            # First write
            w1 = TrajectoryWriter(d, "ep-append")
            w1.open()
            w1.write_step(_make_step(step_idx=0))
            w1.close()

            # Second write
            w2 = TrajectoryWriter(d, "ep-append")
            w2.open()
            w2.write_step(_make_step(step_idx=1))
            w2.close()

            lines = (d / "ep-append.jsonl").read_text().strip().split("\n")
            assert len(lines) == 2

    def test_writer_flush_after_each_step(self) -> None:
        """After write_step, data is readable from disk immediately."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            w = TrajectoryWriter(d, "ep-flush")
            w.open()
            w.write_step(_make_step(step_idx=0))
            # Without closing, data should be on disk (flushed)
            content = (d / "ep-flush.jsonl").read_text()
            assert content.strip() != ""
            parsed = json.loads(content.strip())
            assert parsed["step_idx"] == 0
            w.close()

    def test_writer_context_manager(self) -> None:
        """with TrajectoryWriter(...) as w: opens and closes correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            with TrajectoryWriter(d, "ep-ctx") as w:
                assert w.is_open
                w.write_step(_make_step())
            assert not w.is_open
            assert (d / "ep-ctx.jsonl").exists()

    def test_writer_close_idempotent(self) -> None:
        """Calling close() twice doesn't raise."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            w = TrajectoryWriter(d, "ep-idem")
            w.open()
            w.close()
            w.close()  # should not raise

    def test_writer_path_property(self) -> None:
        """.path returns correct Path."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            w = TrajectoryWriter(d, "ep-path")
            assert w.path == d / "ep-path.jsonl"

    def test_writer_is_open_property(self) -> None:
        """.is_open reflects state correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            w = TrajectoryWriter(d, "ep-open")
            assert not w.is_open
            w.open()
            assert w.is_open
            w.close()
            assert not w.is_open

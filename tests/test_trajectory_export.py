"""Unit tests for trajectory JSONL and Parquet export.

Tests filtered export to JSONL (by task, by score, empty result) and
Parquet export (ImportError when pyarrow unavailable, basic export when present).
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from lunar_sandbox.trajectory.store import TrajectoryStore


def _seed_store(store: TrajectoryStore) -> None:
    """Insert test data: 3 episodes across 2 tasks with varying scores."""
    episodes = [
        ("ep-x1", "task-x", 0.9, 1700000100.0),
        ("ep-x2", "task-x", 0.4, 1700000200.0),
        ("ep-y1", "task-y", 0.7, 1700000300.0),
    ]
    for eid, task, score, started in episodes:
        meta = {
            "episode_id": eid,
            "task_name": task,
            "outcome": "completed",
            "score": score,
            "step_count": 2,
            "duration_ms": 300.0,
            "started_at": started,
            "ended_at": started + 0.3,
            "is_complete": True,
            "sandbox_id": "sbx-test",
        }
        steps = []
        for i in range(2):
            steps.append(
                {
                    "episode_id": eid,
                    "step_idx": i,
                    "timestamp": started + i * 0.1,
                    "action": "execute_command",
                    "action_params": {"command": f"echo {i}"},
                    "observation": {"stdout": str(i)},
                    "reward": 0.0,
                    "state": {"cwd": "/work", "open_files": [], "recent_actions": []},
                }
            )
        store.ingest_episode(meta, steps)


class TestExportJSONL:
    """Tests for JSONL export."""

    def test_export_jsonl_basic(self) -> None:
        """export_jsonl produces valid JSONL with enriched steps."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            out_path = Path(tmp) / "export.jsonl"
            with TrajectoryStore(db_path) as store:
                _seed_store(store)
                count = store.export_jsonl(out_path)
            assert count == 6  # 3 episodes x 2 steps
            lines = out_path.read_text().strip().split("\n")
            assert len(lines) == 6
            for line in lines:
                parsed = json.loads(line)
                # Enriched with episode-level fields
                assert "score" in parsed
                assert "task_name" in parsed

    def test_export_jsonl_filter_by_task(self) -> None:
        """Only steps from matching task are exported."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            out_path = Path(tmp) / "export.jsonl"
            with TrajectoryStore(db_path) as store:
                _seed_store(store)
                count = store.export_jsonl(out_path, task_name="task-x")
            assert count == 4  # 2 episodes x 2 steps for task-x

    def test_export_jsonl_filter_by_score(self) -> None:
        """Score range filter works."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            out_path = Path(tmp) / "export.jsonl"
            with TrajectoryStore(db_path) as store:
                _seed_store(store)
                count = store.export_jsonl(out_path, min_score=0.5)
            # ep-x1 (0.9) and ep-y1 (0.7) match, 2 steps each = 4
            assert count == 4

    def test_export_jsonl_empty_result(self) -> None:
        """No matching episodes produces empty file, returns 0."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            out_path = Path(tmp) / "export.jsonl"
            with TrajectoryStore(db_path) as store:
                _seed_store(store)
                count = store.export_jsonl(out_path, task_name="nonexistent")
            assert count == 0
            assert out_path.read_text() == ""


class TestExportParquet:
    """Tests for Parquet export."""

    def test_export_parquet_import_error(self) -> None:
        """When pyarrow not available, raises ImportError."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            out_path = Path(tmp) / "export.parquet"
            with TrajectoryStore(db_path) as store:
                _seed_store(store)
                # Mock pyarrow as not importable
                import builtins

                real_import = builtins.__import__

                def mock_import(name, *args, **kwargs):
                    if name == "pyarrow" or name.startswith("pyarrow."):
                        raise ImportError("mocked")
                    return real_import(name, *args, **kwargs)

                with patch("builtins.__import__", side_effect=mock_import):
                    with pytest.raises(ImportError, match="pyarrow"):
                        store.export_parquet(out_path)

    def test_export_parquet_basic(self) -> None:
        """If pyarrow installed, produces valid .parquet file."""
        pa = pytest.importorskip("pyarrow")
        pq = pytest.importorskip("pyarrow.parquet")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            out_path = Path(tmp) / "export.parquet"
            with TrajectoryStore(db_path) as store:
                _seed_store(store)
                count = store.export_parquet(out_path)
            assert count == 6
            assert out_path.exists()
            table = pq.read_table(str(out_path))
            assert table.num_rows == 6
            assert "episode_id" in table.column_names
            assert "score" in table.column_names
            assert "task_name" in table.column_names

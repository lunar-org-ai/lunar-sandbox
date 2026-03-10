"""Unit tests for TrajectoryStore SQLite persistence.

Tests database creation, WAL mode, schema (tables + indexes), episode ingestion,
JSONL ingestion (including corrupt lines), and all four query patterns: by task,
by score, by time, and by action type.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from lunar_sandbox.trajectory.store import TrajectoryStore


def _make_episode_meta(
    episode_id: str = "ep-1",
    task_name: str = "task-a",
    outcome: str = "completed",
    score: float = 1.0,
    step_count: int = 2,
    started_at: float | None = None,
) -> dict:
    """Build a minimal episode metadata dict."""
    return {
        "episode_id": episode_id,
        "task_name": task_name,
        "outcome": outcome,
        "score": score,
        "step_count": step_count,
        "duration_ms": 500.0,
        "started_at": started_at or time.time(),
        "ended_at": (started_at or time.time()) + 0.5,
        "is_complete": True,
        "sandbox_id": "sbx-test",
    }


def _make_steps(episode_id: str = "ep-1", count: int = 2) -> list[dict]:
    """Build a list of step dicts."""
    steps = []
    for i in range(count):
        steps.append(
            {
                "episode_id": episode_id,
                "step_idx": i,
                "timestamp": 1700000000.0 + i,
                "action": "execute_command" if i % 2 == 0 else "read_file",
                "action_params": {"command": f"cmd-{i}"},
                "observation": {"stdout": f"out-{i}"},
                "reward": 0.0,
                "duration_ms": 100.0,
                "cpu_time_ms": 50.0,
                "file_diff": None,
                "token_usage": None,
                "cost_usd": None,
                "source": "api",
                "state": {"cwd": "/work", "open_files": [], "recent_actions": []},
            }
        )
    return steps


class TestTrajectoryStoreLifecycle:
    """Tests for store creation, WAL mode, and schema."""

    def test_store_creates_database(self) -> None:
        """open() creates .db file."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            store = TrajectoryStore(db_path)
            store.open()
            try:
                assert db_path.exists()
            finally:
                store.close()

    def test_store_wal_mode(self) -> None:
        """PRAGMA journal_mode returns 'wal'."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                assert store._conn is not None
                row = store._conn.execute("PRAGMA journal_mode").fetchone()
                assert row[0] == "wal"

    def test_store_schema_tables(self) -> None:
        """episodes and steps tables exist."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                assert store._conn is not None
                tables = {
                    r[0]
                    for r in store._conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                assert "episodes" in tables
                assert "steps" in tables

    def test_store_schema_indexes(self) -> None:
        """All six indexes exist."""
        expected = {
            "idx_episodes_task",
            "idx_episodes_score",
            "idx_episodes_started",
            "idx_steps_action",
            "idx_steps_episode",
            "idx_steps_timestamp",
        }
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                assert store._conn is not None
                indexes = {
                    r[0]
                    for r in store._conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    ).fetchall()
                }
                assert expected.issubset(indexes)

    def test_store_context_manager(self) -> None:
        """with TrajectoryStore(...) as s: works."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                assert store._conn is not None
            # After exiting, connection is closed
            assert store._conn is None


class TestTrajectoryStoreIngestion:
    """Tests for episode and JSONL ingestion."""

    def test_store_ingest_episode(self) -> None:
        """Ingest metadata + steps, verify data in both tables."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            meta = _make_episode_meta()
            steps = _make_steps(count=3)
            with TrajectoryStore(db_path) as store:
                count = store.ingest_episode(meta, steps)
                assert count == 3
                # Verify episodes table
                eps = store.query_episodes(episode_id="ep-1")
                assert len(eps) == 1
                assert eps[0]["task_name"] == "task-a"
                # Verify steps table
                st = store.query_steps(["ep-1"])
                assert len(st) == 3

    def test_store_ingest_from_jsonl(self) -> None:
        """Write a JSONL file manually, ingest it, verify."""
        with tempfile.TemporaryDirectory() as tmp:
            # Write JSONL
            jsonl_path = Path(tmp) / "ep-j.jsonl"
            steps = _make_steps(episode_id="ep-j", count=4)
            with open(jsonl_path, "w") as f:
                for s in steps:
                    f.write(json.dumps(s) + "\n")

            meta = _make_episode_meta(episode_id="ep-j")
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                count = store.ingest_from_jsonl(jsonl_path, meta)
                assert count == 4
                eps = store.query_episodes(episode_id="ep-j")
                assert len(eps) == 1

    def test_store_ingest_corrupt_jsonl(self) -> None:
        """JSONL with bad last line -- should skip it, ingest others."""
        with tempfile.TemporaryDirectory() as tmp:
            jsonl_path = Path(tmp) / "ep-corrupt.jsonl"
            steps = _make_steps(episode_id="ep-corrupt", count=3)
            with open(jsonl_path, "w") as f:
                for s in steps:
                    f.write(json.dumps(s) + "\n")
                f.write("THIS IS NOT JSON\n")

            meta = _make_episode_meta(episode_id="ep-corrupt")
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                count = store.ingest_from_jsonl(jsonl_path, meta)
                # 3 good lines, 1 corrupt line skipped
                assert count == 3

    def test_store_multiple_episodes(self) -> None:
        """Ingest 3+ episodes, verify queries return correct subsets."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                for i in range(4):
                    task = "task-a" if i < 2 else "task-b"
                    meta = _make_episode_meta(
                        episode_id=f"ep-{i}",
                        task_name=task,
                        score=float(i),
                        started_at=1700000000.0 + i,
                    )
                    steps = _make_steps(episode_id=f"ep-{i}", count=2)
                    store.ingest_episode(meta, steps)

                # Total episodes
                assert store.count_episodes() == 4
                # By task
                assert store.count_episodes(task_name="task-a") == 2
                assert store.count_episodes(task_name="task-b") == 2
                # Query by task
                eps_a = store.query_episodes(task_name="task-a")
                assert len(eps_a) == 2
                assert all(e["task_name"] == "task-a" for e in eps_a)


class TestTrajectoryStoreQueries:
    """Tests for all four query patterns."""

    def _populate(self, store: TrajectoryStore) -> None:
        """Insert test data: 3 episodes with different tasks, scores, times."""
        episodes = [
            ("ep-a1", "task-alpha", 0.8, 1700000100.0),
            ("ep-a2", "task-alpha", 0.3, 1700000200.0),
            ("ep-b1", "task-beta", 0.9, 1700000300.0),
        ]
        for eid, task, score, started in episodes:
            meta = _make_episode_meta(
                episode_id=eid,
                task_name=task,
                score=score,
                started_at=started,
            )
            steps = _make_steps(episode_id=eid, count=2)
            store.ingest_episode(meta, steps)

    def test_store_query_by_task(self) -> None:
        """query_episodes(task_name=...) returns correct episodes."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                self._populate(store)
                results = store.query_episodes(task_name="task-alpha")
                assert len(results) == 2
                assert all(r["task_name"] == "task-alpha" for r in results)

    def test_store_query_by_score(self) -> None:
        """query_episodes_by_score(min_score=...) filters correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                self._populate(store)
                results = store.query_episodes_by_score(min_score=0.5)
                assert len(results) == 2
                assert all(r["score"] >= 0.5 for r in results)

    def test_store_query_by_time(self) -> None:
        """query_episodes_by_time(start_time=..., end_time=...) filters correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                self._populate(store)
                results = store.query_episodes_by_time(
                    start_time=1700000150.0,
                    end_time=1700000250.0,
                )
                assert len(results) == 1
                assert results[0]["episode_id"] == "ep-a2"

    def test_store_query_by_action(self) -> None:
        """query_steps_by_action(action=...) returns matching steps."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                self._populate(store)
                # _make_steps alternates execute_command / read_file
                results = store.query_steps_by_action("execute_command")
                # 3 episodes x 2 steps each, step 0 is execute_command
                assert len(results) == 3
                assert all(r["action"] == "execute_command" for r in results)

    def test_store_query_steps(self) -> None:
        """query_steps(episode_ids) returns steps in order."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                self._populate(store)
                results = store.query_steps(["ep-a1", "ep-b1"])
                assert len(results) == 4
                # Verify ordering: ep-a1 steps first, then ep-b1
                assert results[0]["episode_id"] == "ep-a1"
                assert results[0]["step_idx"] == 0
                assert results[1]["episode_id"] == "ep-a1"
                assert results[1]["step_idx"] == 1
                assert results[2]["episode_id"] == "ep-b1"
                assert results[2]["step_idx"] == 0

    def test_store_count_episodes(self) -> None:
        """count_episodes() and count_episodes(task_name=...) work."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            with TrajectoryStore(db_path) as store:
                self._populate(store)
                assert store.count_episodes() == 3
                assert store.count_episodes(task_name="task-alpha") == 2
                assert store.count_episodes(task_name="task-beta") == 1
                assert store.count_episodes(task_name="nonexistent") == 0

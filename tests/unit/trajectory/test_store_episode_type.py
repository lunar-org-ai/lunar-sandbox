"""Tests for TrajectoryStore episode_type migration and query support."""

import tempfile
import time
from pathlib import Path

import pytest
from lunar_sandbox.trajectory.store import TrajectoryStore


class TestEpisodeTypeMigration:
    def test_migration_adds_column(self, tmp_path):
        """Opening store creates episodes table with episode_type column."""
        store = TrajectoryStore(tmp_path / "test.db")
        store.open()
        try:
            cols = {
                r[1] for r in store._conn.execute(
                    "PRAGMA table_info(episodes)"
                ).fetchall()
            }
            assert "episode_type" in cols
        finally:
            store.close()

    def test_migration_is_idempotent(self, tmp_path):
        """Opening store twice does not fail."""
        db = tmp_path / "test.db"
        s1 = TrajectoryStore(db)
        s1.open()
        s1.close()
        s2 = TrajectoryStore(db)
        s2.open()
        cols = {
            r[1] for r in s2._conn.execute(
                "PRAGMA table_info(episodes)"
            ).fetchall()
        }
        assert "episode_type" in cols
        s2.close()

    def test_default_episode_type_is_coding(self, tmp_path):
        """Ingested episode without explicit type defaults to 'coding'."""
        store = TrajectoryStore(tmp_path / "test.db")
        store.open()
        try:
            store.ingest_episode(
                {
                    "episode_id": "ep-default",
                    "task_name": "t1",
                    "outcome": "completed",
                    "started_at": time.time(),
                },
                [],
            )
            eps = store.query_episodes(episode_id="ep-default")
            assert len(eps) == 1
            assert eps[0].get("episode_type", "coding") == "coding"
        finally:
            store.close()

    def test_cua_episode_type(self, tmp_path):
        """CUA episode ingested with episode_type='cua' is queryable."""
        store = TrajectoryStore(tmp_path / "test.db")
        store.open()
        try:
            store.ingest_episode(
                {
                    "episode_id": "ep-cua",
                    "task_name": "web-task",
                    "outcome": "completed",
                    "started_at": time.time(),
                    "episode_type": "cua",
                },
                [
                    {
                        "episode_id": "ep-cua",
                        "step_idx": 0,
                        "timestamp": time.time(),
                        "action": "screenshot",
                        "action_params": {},
                        "observation": {"screenshot_path": "screenshots/step_000.jpg"},
                    },
                ],
            )
            cua_eps = store.query_episodes(episode_type="cua")
            assert len(cua_eps) == 1
            assert cua_eps[0]["episode_id"] == "ep-cua"

            steps = store.query_steps(["ep-cua"])
            assert len(steps) == 1
        finally:
            store.close()

    def test_query_episodes_filters_by_type(self, tmp_path):
        """query_episodes with episode_type filters correctly."""
        store = TrajectoryStore(tmp_path / "test.db")
        store.open()
        try:
            for eid, etype in [("ep-c1", "coding"), ("ep-c2", "coding"), ("ep-u1", "cua")]:
                store.ingest_episode(
                    {
                        "episode_id": eid,
                        "task_name": "t",
                        "outcome": "completed",
                        "started_at": time.time(),
                        "episode_type": etype,
                    },
                    [],
                )

            assert len(store.query_episodes(episode_type="coding")) == 2
            assert len(store.query_episodes(episode_type="cua")) == 1
            assert len(store.query_episodes()) == 3
        finally:
            store.close()

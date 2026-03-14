"""Tests for CUA screenshot retention policy."""

import os
import tempfile
import time
from pathlib import Path

import pytest
from lunar_sandbox.cua.retention import RetentionPolicy, cleanup_episodes


class TestRetentionPolicy:
    def test_default_keeps_forever(self):
        policy = RetentionPolicy()
        assert policy.keep_forever is True

    def test_keep_forever_deletes_nothing(self, tmp_path):
        self._make_episode(tmp_path, "ep-1")
        policy = RetentionPolicy()
        deleted = cleanup_episodes(tmp_path, policy)
        assert deleted == 0
        assert (tmp_path / "ep-1" / "screenshots").exists()

    def test_delete_after_export(self, tmp_path):
        self._make_episode(tmp_path, "ep-1")
        self._make_episode(tmp_path, "ep-2")
        policy = RetentionPolicy(keep_forever=False, delete_after_export=True)
        deleted = cleanup_episodes(tmp_path, policy, exported_episode_ids={"ep-1"})
        assert deleted == 1
        assert not (tmp_path / "ep-1" / "screenshots").exists()
        assert (tmp_path / "ep-1" / "ep-1.jsonl").exists()  # JSONL preserved
        assert (tmp_path / "ep-2" / "screenshots").exists()

    def test_delete_after_days(self, tmp_path):
        self._make_episode(tmp_path, "ep-old")
        self._make_episode(tmp_path, "ep-new")
        # Make ep-old screenshots 10 days old
        old_time = time.time() - 86400 * 10
        os.utime(tmp_path / "ep-old" / "screenshots", (old_time, old_time))
        policy = RetentionPolicy(keep_forever=False, delete_after_days=7)
        deleted = cleanup_episodes(tmp_path, policy)
        assert deleted == 1
        assert not (tmp_path / "ep-old" / "screenshots").exists()
        assert (tmp_path / "ep-old" / "ep-old.jsonl").exists()
        assert (tmp_path / "ep-new" / "screenshots").exists()

    def test_nonexistent_directory(self, tmp_path):
        policy = RetentionPolicy(keep_forever=False, delete_after_days=1)
        deleted = cleanup_episodes(tmp_path / "nonexistent", policy)
        assert deleted == 0

    @staticmethod
    def _make_episode(root: Path, episode_id: str) -> None:
        ep_dir = root / episode_id
        ss_dir = ep_dir / "screenshots"
        ss_dir.mkdir(parents=True)
        (ss_dir / "step_000.jpg").write_bytes(b"fake-jpg")
        (ep_dir / f"{episode_id}.jsonl").write_text("{}\n")

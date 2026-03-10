"""Unit tests for OverlayFS upper layer diff inspection.

Tests inspect_upper_layer, snapshot_upper_state, and diff_snapshots
using tmp_path for fake upper directories. Platform-independent
(no actual OverlayFS mount needed).
"""

from __future__ import annotations

from pathlib import Path

from lunar_sandbox.actions.diff import (
    diff_snapshots,
    inspect_upper_layer,
    snapshot_upper_state,
)


class TestInspectUpperLayer:
    """Tests for inspect_upper_layer()."""

    def test_inspect_empty_upper(self, tmp_path: Path) -> None:
        """Empty directory returns empty FileDiff."""
        upper = tmp_path / "upper"
        upper.mkdir()

        diff = inspect_upper_layer(upper)
        assert diff.created == []
        assert diff.modified == []
        assert diff.deleted == []

    def test_inspect_created_files(self, tmp_path: Path) -> None:
        """Files in upper with no lower dirs = created."""
        upper = tmp_path / "upper"
        upper.mkdir()
        (upper / "new_file.py").write_text("content")
        (upper / "another.txt").write_text("more content")

        diff = inspect_upper_layer(upper)
        assert sorted(diff.created) == ["another.txt", "new_file.py"]
        assert diff.modified == []
        assert diff.deleted == []

    def test_inspect_created_with_lower(self, tmp_path: Path) -> None:
        """Files in upper that also exist in lower = modified."""
        upper = tmp_path / "upper"
        upper.mkdir()
        lower = tmp_path / "lower"
        lower.mkdir()

        # File exists in both upper and lower.
        (lower / "shared.py").write_text("original")
        (upper / "shared.py").write_text("modified")

        # File exists only in upper.
        (upper / "new.py").write_text("brand new")

        diff = inspect_upper_layer(upper, lower_dirs=[lower])
        assert diff.created == ["new.py"]
        assert diff.modified == ["shared.py"]

    def test_inspect_nested_files(self, tmp_path: Path) -> None:
        """Files in subdirectories detected."""
        upper = tmp_path / "upper"
        upper.mkdir()
        subdir = upper / "src" / "pkg"
        subdir.mkdir(parents=True)
        (subdir / "module.py").write_text("code")

        diff = inspect_upper_layer(upper)
        assert "src/pkg/module.py" in diff.created


class TestSnapshotUpperState:
    """Tests for snapshot_upper_state()."""

    def test_snapshot_empty(self, tmp_path: Path) -> None:
        """Empty dir returns empty set."""
        upper = tmp_path / "upper"
        upper.mkdir()

        snap = snapshot_upper_state(upper)
        assert snap == set()

    def test_snapshot_upper_state(self, tmp_path: Path) -> None:
        """Returns set of relative paths."""
        upper = tmp_path / "upper"
        upper.mkdir()
        (upper / "a.txt").write_text("a")
        sub = upper / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("b")

        snap = snapshot_upper_state(upper)
        assert snap == {"a.txt", "sub/b.txt"}


class TestDiffSnapshots:
    """Tests for diff_snapshots()."""

    def test_diff_snapshots_new_files(self, tmp_path: Path) -> None:
        """after - before = created."""
        upper = tmp_path / "upper"
        upper.mkdir()

        before: set[str] = set()
        (upper / "new.txt").write_text("new")
        after = {"new.txt"}

        diff = diff_snapshots(before, after, upper)
        assert diff.created == ["new.txt"]
        assert diff.deleted == []

    def test_diff_snapshots_removed_files(self, tmp_path: Path) -> None:
        """before - after = deleted."""
        upper = tmp_path / "upper"
        upper.mkdir()

        before = {"old.txt"}
        after: set[str] = set()

        diff = diff_snapshots(before, after, upper)
        assert diff.deleted == ["old.txt"]
        assert diff.created == []

    def test_diff_snapshots_modified_files(self, tmp_path: Path) -> None:
        """Files in both snapshots classified as modified."""
        upper = tmp_path / "upper"
        upper.mkdir()
        (upper / "common.txt").write_text("updated content")

        before = {"common.txt"}
        after = {"common.txt"}

        diff = diff_snapshots(before, after, upper)
        assert diff.modified == ["common.txt"]
        assert diff.created == []
        assert diff.deleted == []

    def test_diff_snapshots_mixed(self, tmp_path: Path) -> None:
        """Mix of created, modified, and deleted files."""
        upper = tmp_path / "upper"
        upper.mkdir()
        (upper / "kept.txt").write_text("still here")
        (upper / "added.txt").write_text("brand new")

        before = {"kept.txt", "removed.txt"}
        after = {"kept.txt", "added.txt"}

        diff = diff_snapshots(before, after, upper)
        assert diff.created == ["added.txt"]
        assert diff.modified == ["kept.txt"]
        assert diff.deleted == ["removed.txt"]

"""OverlayFS upper layer diff inspection for file change detection.

Provides utilities to detect which files were created, modified, or deleted
in an OverlayFS upper layer after an action executes. This is the mechanism
that populates ``ActionResponse.side_effects``.

**Important:** ``inspect_upper_layer`` must be called *after* the action has
completed and the filesystem is quiescent. Calling it during an action may
produce incomplete results.

For per-action diffs, use the snapshot workflow:
1. ``before = snapshot_upper_state(upper_dir)``
2. Run the action.
3. ``after = snapshot_upper_state(upper_dir)``
4. ``diff = diff_snapshots(before, after, upper_dir)``
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import structlog

from lunar_sandbox.actions.types import FileDiff

__all__ = [
    "inspect_upper_layer",
    "snapshot_upper_state",
    "diff_snapshots",
]

log = structlog.get_logger(__name__)


def inspect_upper_layer(
    upper_dir: Path,
    lower_dirs: list[Path] | None = None,
) -> FileDiff:
    """Inspect an OverlayFS upper layer to detect file changes.

    Walks ``upper_dir`` and classifies every entry as created, modified,
    or deleted relative to the lower layers.

    Args:
        upper_dir: Path to the OverlayFS upper (writable) directory.
        lower_dirs: Optional list of lower-layer paths. When provided,
            files that exist in any lower dir are classified as *modified*;
            files that do not exist in any lower dir are *created*. When
            ``None``, all non-whiteout files are treated as *created*.

    Returns:
        A ``FileDiff`` with lists of created, modified, and deleted
        relative paths.
    """
    created: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []

    upper_str = str(upper_dir)

    for dirpath, dirnames, filenames in os.walk(upper_str):
        # Check for opaque directory marker (entire directory replaced).
        try:
            xattr_val = os.getxattr(dirpath, b"trusted.overlay.opaque")
            if xattr_val == b"y":
                rel_dir = os.path.relpath(dirpath, upper_str)
                if rel_dir != ".":
                    log.debug("opaque_directory_detected", path=rel_dir)
        except (OSError, AttributeError):
            # getxattr may not be available or may fail on non-overlayfs.
            pass

        for name in filenames:
            full_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(full_path, upper_str)

            try:
                st = os.lstat(full_path)
            except PermissionError:
                log.warning("permission_denied", path=rel_path)
                continue
            except OSError as exc:
                log.warning("stat_failed", path=rel_path, error=str(exc))
                continue

            # Whiteout detection: character device with rdev == 0.
            if stat.S_ISCHR(st.st_mode) and st.st_rdev == 0:
                deleted.append(rel_path)
                continue

            # Classify as created or modified.
            if lower_dirs is not None and _exists_in_lower(rel_path, lower_dirs):
                modified.append(rel_path)
            else:
                created.append(rel_path)

        # Also check directory-level whiteouts for subdirectories.
        for dname in list(dirnames):
            full_dpath = os.path.join(dirpath, dname)
            try:
                st = os.lstat(full_dpath)
            except (PermissionError, OSError):
                continue
            if stat.S_ISCHR(st.st_mode) and st.st_rdev == 0:
                rel_dpath = os.path.relpath(full_dpath, upper_str)
                deleted.append(rel_dpath)
                dirnames.remove(dname)

    return FileDiff(created=sorted(created), modified=sorted(modified), deleted=sorted(deleted))


def snapshot_upper_state(upper_dir: Path) -> set[str]:
    """Return a set of relative file paths currently in the upper directory.

    Used for per-action diff computation: take a snapshot before the action,
    another after, then pass both to ``diff_snapshots``.

    Args:
        upper_dir: Path to the OverlayFS upper directory.

    Returns:
        Set of relative path strings for all regular files found.
    """
    paths: set[str] = set()
    upper_str = str(upper_dir)

    for dirpath, _dirnames, filenames in os.walk(upper_str):
        for name in filenames:
            full_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(full_path, upper_str)
            paths.add(rel_path)

    return paths


def diff_snapshots(
    before: set[str],
    after: set[str],
    upper_dir: Path,
) -> FileDiff:
    """Compute a ``FileDiff`` from two upper-layer snapshots.

    Args:
        before: Snapshot taken before the action.
        after: Snapshot taken after the action.
        upper_dir: Path to the upper directory (used for mtime checks
            on files present in both snapshots).

    Returns:
        A ``FileDiff`` classifying paths as created, modified, or deleted.
    """
    created_paths = sorted(after - before)
    deleted_paths = sorted(before - after)

    # Files present in both snapshots may have been modified.
    modified_paths: list[str] = []
    common = before & after
    for rel_path in sorted(common):
        full_path = upper_dir / rel_path
        try:
            # If the file is in both snapshots, conservatively classify
            # as modified -- the content may have changed in place.
            if full_path.exists():
                modified_paths.append(rel_path)
        except (PermissionError, OSError):
            continue

    return FileDiff(
        created=created_paths,
        modified=modified_paths,
        deleted=deleted_paths,
    )


def _exists_in_lower(rel_path: str, lower_dirs: list[Path]) -> bool:
    """Check whether *rel_path* exists in any of the lower layer directories."""
    for lower in lower_dirs:
        if (lower / rel_path).exists():
            return True
    return False

"""CUA episode screenshot retention policy.

CUA episodes generate screenshot files at every step (80-150 KB each).
Without a retention policy, disk usage grows linearly with episode count.

RetentionPolicy provides three modes:
- keep_forever (default): no automatic deletion.
- delete_after_days: remove screenshots older than N days.
- delete_after_export: remove screenshots after successful Parquet export.

The JSONL trajectory file is the single source of truth and is NEVER deleted.
Only the ``screenshots/`` subdirectory inside each episode directory is removed.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

__all__ = ["RetentionPolicy", "cleanup_episodes"]

log = structlog.get_logger(__name__)


@dataclass
class RetentionPolicy:
    """Configures when to delete CUA episode screenshot data.

    Only the screenshots directory is deleted -- the JSONL trajectory
    file is always preserved as the single source of truth.

    Attributes:
        keep_forever: If True, never delete anything (default).
            When True, all other options are ignored.
        delete_after_days: Delete screenshot directories older than
            this many days. None means no age-based deletion.
        delete_after_export: If True, delete screenshots after
            a successful Parquet export has been created.
    """

    keep_forever: bool = True
    delete_after_days: float | None = None
    delete_after_export: bool = False


def cleanup_episodes(
    trajectory_dir: Path,
    policy: RetentionPolicy,
    *,
    exported_episode_ids: set[str] | None = None,
) -> int:
    """Apply retention policy to episode screenshot directories.

    Scans trajectory_dir for episode subdirectories and deletes
    their screenshots/ folders according to the policy. The JSONL
    file inside each episode directory is NEVER deleted.

    Args:
        trajectory_dir: Root trajectory directory containing episode
            subdirectories (e.g. traces/).
        policy: Retention policy to apply.
        exported_episode_ids: Set of episode IDs that have been
            successfully exported to Parquet. Used when
            policy.delete_after_export is True.

    Returns:
        Number of episode screenshot directories deleted.
    """
    if policy.keep_forever:
        return 0

    deleted = 0
    now = time.time()

    if not trajectory_dir.exists():
        return 0

    for episode_dir in trajectory_dir.iterdir():
        if not episode_dir.is_dir():
            continue

        screenshots_dir = episode_dir / "screenshots"
        if not screenshots_dir.exists():
            continue

        should_delete = False

        # Check age-based deletion
        if policy.delete_after_days is not None:
            # Use the screenshots directory mtime as proxy for episode age
            dir_mtime = screenshots_dir.stat().st_mtime
            age_days = (now - dir_mtime) / 86400.0
            if age_days > policy.delete_after_days:
                should_delete = True
                log.debug(
                    "retention_age_delete",
                    episode_id=episode_dir.name,
                    age_days=round(age_days, 1),
                    threshold_days=policy.delete_after_days,
                )

        # Check export-based deletion
        if (
            policy.delete_after_export
            and exported_episode_ids
            and episode_dir.name in exported_episode_ids
        ):
            should_delete = True
            log.debug(
                "retention_export_delete",
                episode_id=episode_dir.name,
            )

        if should_delete:
            try:
                shutil.rmtree(screenshots_dir)
                deleted += 1
                log.info(
                    "retention_screenshots_deleted",
                    episode_id=episode_dir.name,
                    path=str(screenshots_dir),
                )
            except OSError as exc:
                log.warning(
                    "retention_delete_failed",
                    episode_id=episode_dir.name,
                    error=str(exc),
                )

    if deleted > 0:
        log.info("retention_cleanup_complete", deleted_count=deleted)

    return deleted

# SPDX-License-Identifier: MIT
"""OverlayFS mount, unmount, and reset operations.

Provides the core filesystem layering mechanism for sandbox isolation.
The ephemeral diff layer captures all writes; resetting discards the diff
and remounts for instant rollback without rebuilding.

Anti-patterns enforced:
- NEVER recycle upper/work dirs by deleting contents (inode collision risk)
- NEVER use MNT_FORCE (only valid for NFS)
- Always destroy and recreate upper/work dirs on reset
"""

from __future__ import annotations

import os
import shutil

import structlog

from lunar_sandbox.kernel.mount import MNT_DETACH, mount, umount2

__all__ = [
    "mount_overlay",
    "unmount_overlay",
    "reset_overlay",
]

log = structlog.get_logger(__name__)


def mount_overlay(
    lower_dirs: list[str],
    upper_dir: str,
    work_dir: str,
    merged_dir: str,
    *,
    volatile: bool = True,
    userxattr: bool = False,
) -> None:
    """Mount an OverlayFS with the given layer configuration.

    Args:
        lower_dirs: Ordered list of lower (readonly) directories.
            Leftmost has highest priority (OverlayFS semantics).
            Typical order: [seed, deps, base].
        upper_dir: Writable ephemeral diff directory.
        work_dir: OverlayFS workdir (must be on same filesystem as upper_dir).
        merged_dir: Mount point where merged view appears.
        volatile: If True, append ``volatile`` option to skip sync on unmount.
            Safe for ephemeral layers that are discarded on reset.
        userxattr: If True, append ``userxattr`` option. Required when
            operating inside user namespaces.

    Raises:
        OSError: On mount failure or non-Linux platform.
    """
    lowerdir_str = ":".join(lower_dirs)
    options = f"lowerdir={lowerdir_str},upperdir={upper_dir},workdir={work_dir}"

    if volatile:
        options += ",volatile"
    if userxattr:
        options += ",userxattr"

    log.debug(
        "mount_overlay",
        lower_dirs=lower_dirs,
        upper_dir=upper_dir,
        work_dir=work_dir,
        merged_dir=merged_dir,
        volatile=volatile,
        userxattr=userxattr,
        options=options,
    )

    mount("overlay", merged_dir, "overlay", flags=0, options=options)

    log.info("overlay_mounted", merged_dir=merged_dir, layers=len(lower_dirs))


def unmount_overlay(merged_dir: str, *, force: bool = False) -> None:
    """Unmount an OverlayFS mount point.

    Attempts a clean unmount first. If that fails and ``force`` is True,
    falls back to lazy unmount (MNT_DETACH). Never uses MNT_FORCE
    (only valid for NFS).

    If the clean unmount succeeds, or the lazy unmount succeeds, the
    function returns normally. If both fail, raises OSError -- the caller
    should abandon the sandbox entirely per project policy.

    Args:
        merged_dir: Mount point to unmount.
        force: If True, attempt lazy unmount on clean failure.

    Raises:
        OSError: If unmount fails (caller should abandon sandbox).
    """
    log.debug("unmount_overlay", merged_dir=merged_dir, force=force)

    try:
        umount2(merged_dir, 0)
        log.info("overlay_unmounted", merged_dir=merged_dir, method="clean")
        return
    except OSError:
        if not force:
            raise
        log.warning(
            "overlay_clean_unmount_failed",
            merged_dir=merged_dir,
            fallback="lazy_unmount",
        )

    # Lazy unmount as fallback -- detaches from namespace immediately
    umount2(merged_dir, MNT_DETACH)
    log.info("overlay_unmounted", merged_dir=merged_dir, method="lazy")


def reset_overlay(
    upper_dir: str,
    work_dir: str,
    merged_dir: str,
    lower_dirs: list[str],
    *,
    volatile: bool = True,
    userxattr: bool = False,
) -> None:
    """Reset an OverlayFS by discarding the ephemeral diff and remounting.

    This is the fast-path for episode reset. Steps:
    1. Unmount the overlay (lazy fallback enabled)
    2. Destroy upper_dir and work_dir entirely (never recycle contents)
    3. Recreate fresh empty upper_dir and work_dir
    4. Remount with same layer configuration

    Args:
        upper_dir: Writable ephemeral diff directory to destroy and recreate.
        work_dir: OverlayFS workdir to destroy and recreate.
        merged_dir: Mount point to unmount and remount.
        lower_dirs: Lower directory list for remounting (same order).
        volatile: Volatile option for remount.
        userxattr: Userxattr option for remount.

    Raises:
        OSError: If unmount or remount fails.
    """
    log.info("reset_overlay_start", merged_dir=merged_dir)

    # Step 1: Unmount (force=True enables lazy fallback)
    unmount_overlay(merged_dir, force=True)
    log.debug("reset_step_1_unmounted", merged_dir=merged_dir)

    # Step 2: Destroy upper and work dirs entirely
    # NEVER recycle by deleting contents -- always destroy and recreate
    # to avoid inode collisions and whiteout leaks
    shutil.rmtree(upper_dir)
    shutil.rmtree(work_dir)
    log.debug("reset_step_2_destroyed", upper_dir=upper_dir, work_dir=work_dir)

    # Step 3: Recreate fresh empty dirs
    os.makedirs(upper_dir, mode=0o755)
    os.makedirs(work_dir, mode=0o755)
    log.debug("reset_step_3_recreated", upper_dir=upper_dir, work_dir=work_dir)

    # Step 4: Remount with same configuration
    mount_overlay(
        lower_dirs=lower_dirs,
        upper_dir=upper_dir,
        work_dir=work_dir,
        merged_dir=merged_dir,
        volatile=volatile,
        userxattr=userxattr,
    )
    log.info("reset_overlay_complete", merged_dir=merged_dir)

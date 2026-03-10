# SPDX-License-Identifier: MIT
"""Paranoia reset and timeout enforcement for sandboxes.

Implements the full paranoia reset sequence: kill all processes, verify
clean, reset overlay, verify merged dir. On any failure the sandbox is
abandoned -- never fight a zombie mount.

Timeout enforcement uses SIGTERM + grace period + SIGKILL, tracking the
outcome as "completed", "timeout_graceful", or "timeout_killed".
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

import structlog

from lunar_sandbox.filesystem.layers import LayerManager, SandboxLayers
from lunar_sandbox.kernel.cgroups import kill_cgroup_processes, read_cgroup_procs

__all__ = [
    "paranoia_reset",
    "enforce_timeout",
    "GRACE_PERIOD_SECONDS",
]

log = structlog.get_logger(__name__)

# Default grace period between SIGTERM and SIGKILL (seconds).
GRACE_PERIOD_SECONDS: int = 5

# Short pause after kill to let the kernel reap zombies.
_REAP_DELAY: float = 0.1

# Poll interval for enforce_timeout wait loop (seconds).
_POLL_INTERVAL: float = 0.05


def paranoia_reset(
    sandbox_id: str,
    cgroup_path: Path,
    layers: SandboxLayers,
    layer_manager: LayerManager,
) -> bool:
    """Full paranoia reset: kill, verify, unmount, remount, verify.

    Returns True if the sandbox was cleanly reset and is ready for a new
    episode.  Returns False if any step failed -- the caller MUST abandon
    the sandbox (mark it broken) and never attempt repair.

    Steps:
        1. Kill all processes in the cgroup.
        2. Wait briefly for zombie reaping.
        3. Verify no processes remain in the cgroup.
        4. Reset the OverlayFS overlay (unmount, wipe upper+work, remount).
        5. If OSError during reset -> return False (abandon).
        6. Verify the merged directory is accessible and empty.

    Args:
        sandbox_id: Identifier for logging.
        cgroup_path: Path to the sandbox's cgroup directory.
        layers: Sandbox filesystem layer configuration.
        layer_manager: Manager that orchestrates OverlayFS operations.

    Returns:
        True if reset succeeded and sandbox is clean, False otherwise.
    """
    log.info("paranoia_reset_start", sandbox_id=sandbox_id)

    # Step 1: Kill all processes via cgroup
    try:
        kill_cgroup_processes(cgroup_path)
        log.debug("paranoia_reset_kill_done", sandbox_id=sandbox_id)
    except OSError as exc:
        log.warning(
            "paranoia_reset_kill_failed",
            sandbox_id=sandbox_id,
            error=str(exc),
        )
        return False

    # Step 2: Wait for kernel to reap zombies
    time.sleep(_REAP_DELAY)

    # Step 3: Verify no processes remain
    try:
        remaining = read_cgroup_procs(cgroup_path)
    except OSError as exc:
        log.warning(
            "paranoia_reset_read_procs_failed",
            sandbox_id=sandbox_id,
            error=str(exc),
        )
        return False

    if remaining:
        log.warning(
            "paranoia_reset_processes_remain",
            sandbox_id=sandbox_id,
            remaining_pids=remaining,
        )
        return False

    log.debug("paranoia_reset_procs_clear", sandbox_id=sandbox_id)

    # Step 4: Reset overlay (unmount, wipe upper+work, remount)
    try:
        layer_manager.reset_sandbox(layers)
        log.debug("paranoia_reset_overlay_done", sandbox_id=sandbox_id)
    except OSError as exc:
        # Step 5: Never fight a zombie mount -- abandon sandbox
        log.warning(
            "paranoia_reset_overlay_failed",
            sandbox_id=sandbox_id,
            error=str(exc),
        )
        return False

    # Step 6: Verify merged directory is accessible and empty
    try:
        merged = layers.merged_dir
        if not merged.is_dir():
            log.warning(
                "paranoia_reset_merged_not_dir",
                sandbox_id=sandbox_id,
                merged_dir=str(merged),
            )
            return False

        contents = list(merged.iterdir())
        if contents:
            log.warning(
                "paranoia_reset_merged_not_empty",
                sandbox_id=sandbox_id,
                merged_dir=str(merged),
                count=len(contents),
            )
            return False
    except OSError as exc:
        log.warning(
            "paranoia_reset_verify_failed",
            sandbox_id=sandbox_id,
            error=str(exc),
        )
        return False

    log.info("paranoia_reset_complete", sandbox_id=sandbox_id)
    return True


def enforce_timeout(
    pid: int,
    timeout_seconds: float,
    grace_period: float = GRACE_PERIOD_SECONDS,
) -> str:
    """Wait for a process to exit, enforcing a timeout with graceful shutdown.

    Polls ``os.waitpid(WNOHANG)`` until the process exits or the deadline
    is reached.  On timeout:

    1. Send SIGTERM (graceful shutdown request).
    2. Poll for ``grace_period`` seconds.
    3. If still alive: send SIGKILL, then blocking ``waitpid``.

    Args:
        pid: Process ID to wait for.
        timeout_seconds: Maximum wall-clock seconds to wait.
        grace_period: Seconds between SIGTERM and SIGKILL (default 5).

    Returns:
        ``"completed"`` if the process exited within the timeout,
        ``"timeout_graceful"`` if SIGTERM was enough,
        ``"timeout_killed"`` if SIGKILL was required.
    """
    log.debug(
        "enforce_timeout_start",
        pid=pid,
        timeout_seconds=timeout_seconds,
        grace_period=grace_period,
    )

    deadline = time.monotonic() + timeout_seconds

    # --- Phase 1: Wait for normal completion ---
    while time.monotonic() < deadline:
        try:
            wpid, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            # Process already reaped
            log.debug("enforce_timeout_already_reaped", pid=pid)
            return "completed"

        if wpid != 0:
            log.debug("enforce_timeout_completed", pid=pid, status=status)
            return "completed"

        time.sleep(_POLL_INTERVAL)

    # --- Phase 2: Timeout reached -- send SIGTERM ---
    log.info("enforce_timeout_sending_sigterm", pid=pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        # Died between last poll and now
        _safe_waitpid(pid)
        return "completed"

    # --- Phase 3: Grace period after SIGTERM ---
    grace_deadline = time.monotonic() + grace_period

    while time.monotonic() < grace_deadline:
        try:
            wpid, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            log.debug("enforce_timeout_graceful_reaped", pid=pid)
            return "timeout_graceful"

        if wpid != 0:
            log.info("enforce_timeout_graceful_exit", pid=pid, status=status)
            return "timeout_graceful"

        time.sleep(_POLL_INTERVAL)

    # --- Phase 4: Still alive -- SIGKILL ---
    log.warning("enforce_timeout_sending_sigkill", pid=pid)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        _safe_waitpid(pid)
        return "timeout_graceful"

    # Blocking wait -- SIGKILL is unconditional
    _safe_waitpid(pid)
    log.warning("enforce_timeout_killed", pid=pid)
    return "timeout_killed"


def _safe_waitpid(pid: int) -> None:
    """Blocking waitpid that ignores ChildProcessError (already reaped)."""
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass

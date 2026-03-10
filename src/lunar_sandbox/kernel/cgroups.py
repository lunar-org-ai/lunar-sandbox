# SPDX-License-Identifier: MIT
"""Cgroups v2 resource limit management for sandboxes.

Manages the lifecycle of per-sandbox cgroups under /sys/fs/cgroup/:
create with resource limits, assign processes, enumerate PIDs,
kill all processes, and destroy (cleanup).

All limits are written BEFORE any process is added to the cgroup,
ensuring no process ever runs without resource constraints.

The cgroup v2 "no internal processes" constraint is handled by
creating dedicated child cgroups for each sandbox.

All functions are importable on any platform but raise OSError at call
time on non-Linux systems.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path
from typing import Final

import structlog

from lunar_sandbox.sandbox.config import ResourceLimits

__all__ = [
    "create_sandbox_cgroup",
    "assign_process_to_cgroup",
    "read_cgroup_procs",
    "kill_cgroup_processes",
    "destroy_sandbox_cgroup",
    "CGROUP_ROOT",
    "SANDBOX_CGROUP_PREFIX",
]

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CGROUP_ROOT: Final[Path] = Path("/sys/fs/cgroup")
SANDBOX_CGROUP_PREFIX: Final[str] = "lunar-sandbox"

_IS_LINUX: Final[bool] = sys.platform == "linux"

# Max wait time for cgroup processes to die (seconds)
_KILL_WAIT_TIMEOUT: Final[float] = 5.0
_KILL_POLL_INTERVAL: Final[float] = 0.1


def _require_linux() -> None:
    """Raise OSError if not running on Linux."""
    if not _IS_LINUX:
        raise OSError(
            "Cgroup operations require Linux. "
            "Current platform: " + sys.platform
        )


def _cgroup_path(sandbox_id: str) -> Path:
    """Return the cgroup directory path for a sandbox.

    Args:
        sandbox_id: Unique sandbox identifier.

    Returns:
        Path to the sandbox's cgroup directory.
    """
    return CGROUP_ROOT / f"{SANDBOX_CGROUP_PREFIX}-{sandbox_id}"


def _detect_root_block_device() -> str | None:
    """Detect the major:minor of the root block device.

    Reads /proc/self/mountinfo to find the device backing /.

    Returns:
        "major:minor" string, or None if detection fails.
    """
    try:
        with open("/proc/self/mountinfo") as f:
            for line in f:
                parts = line.split()
                # mountinfo format: id parent major:minor root mount_point ...
                if len(parts) >= 5 and parts[4] == "/":
                    return parts[2]
    except OSError:
        log.debug("detect_root_block_device_failed")
    return None


def _enable_controllers(parent: Path) -> None:
    """Enable CPU, memory, pids, and I/O controllers in the parent cgroup.

    Writes to the parent's subtree_control to allow child cgroups
    to use these controllers.

    Args:
        parent: Path to the parent cgroup directory.
    """
    subtree_control = parent / "cgroup.subtree_control"
    controllers = "+cpu +memory +pids +io"

    try:
        subtree_control.write_text(controllers)
        log.debug("enabled_controllers", parent=str(parent), controllers=controllers)
    except OSError as exc:
        log.warning(
            "enable_controllers_failed",
            parent=str(parent),
            controllers=controllers,
            error=str(exc),
        )
        # Try enabling one at a time -- some may already be enabled
        for controller in ["+cpu", "+memory", "+pids", "+io"]:
            try:
                subtree_control.write_text(controller)
            except OSError:
                log.debug(
                    "enable_single_controller_failed",
                    parent=str(parent),
                    controller=controller,
                )


def create_sandbox_cgroup(sandbox_id: str, limits: ResourceLimits) -> Path:
    """Create a cgroup for a sandbox and configure resource limits.

    Creates the cgroup directory, enables controllers in the parent,
    and writes all resource limits BEFORE any process is assigned.

    Args:
        sandbox_id: Unique sandbox identifier.
        limits: Resource limits to apply.

    Returns:
        Path to the created cgroup directory.

    Raises:
        OSError: On non-Linux platform or cgroup creation failure.
    """
    _require_linux()

    cgroup_dir = _cgroup_path(sandbox_id)
    log.debug(
        "create_sandbox_cgroup",
        sandbox_id=sandbox_id,
        cgroup_dir=str(cgroup_dir),
    )

    # Enable controllers in the parent (root cgroup)
    _enable_controllers(cgroup_dir.parent)

    # Create the sandbox cgroup directory
    cgroup_dir.mkdir(parents=False, exist_ok=True)

    # --- Write resource limits ---

    # CPU: cpu.max format is "quota period" in microseconds
    cpu_max = cgroup_dir / "cpu.max"
    cpu_max.write_text(f"{limits.cpu_quota_us} {limits.cpu_period_us}\n")
    log.debug(
        "cgroup_cpu_limit",
        quota_us=limits.cpu_quota_us,
        period_us=limits.cpu_period_us,
    )

    # Memory: memory.max in bytes
    memory_max = cgroup_dir / "memory.max"
    memory_max.write_text(f"{limits.memory_max_bytes}\n")
    log.debug("cgroup_memory_limit", bytes=limits.memory_max_bytes)

    # PIDs: pids.max
    pids_max = cgroup_dir / "pids.max"
    pids_max.write_text(f"{limits.pids_max}\n")
    log.debug("cgroup_pids_limit", max=limits.pids_max)

    # I/O: io.max (optional, requires block device detection)
    if limits.io_max_rbps > 0 or limits.io_max_wbps > 0:
        dev = _detect_root_block_device()
        if dev is not None:
            io_parts: list[str] = [dev]
            if limits.io_max_rbps > 0:
                io_parts.append(f"rbps={limits.io_max_rbps}")
            if limits.io_max_wbps > 0:
                io_parts.append(f"wbps={limits.io_max_wbps}")
            io_max = cgroup_dir / "io.max"
            io_line = " ".join(io_parts)
            io_max.write_text(io_line + "\n")
            log.debug("cgroup_io_limit", io_max=io_line)
        else:
            log.warning(
                "cgroup_io_limit_skipped",
                reason="Could not detect root block device",
            )

    log.debug("sandbox_cgroup_created", cgroup_dir=str(cgroup_dir))
    return cgroup_dir


def assign_process_to_cgroup(cgroup_path: Path, pid: int) -> None:
    """Add a process to a sandbox cgroup.

    Args:
        cgroup_path: Path to the cgroup directory.
        pid: Process ID to add.

    Raises:
        OSError: On non-Linux platform or if assignment fails.
    """
    _require_linux()

    procs_file = cgroup_path / "cgroup.procs"
    procs_file.write_text(f"{pid}\n")
    log.debug("assigned_process_to_cgroup", pid=pid, cgroup=str(cgroup_path))


def read_cgroup_procs(cgroup_path: Path) -> list[int]:
    """Read all PIDs in a cgroup.

    Args:
        cgroup_path: Path to the cgroup directory.

    Returns:
        List of PIDs currently in the cgroup.

    Raises:
        OSError: On non-Linux platform.
    """
    _require_linux()

    procs_file = cgroup_path / "cgroup.procs"
    try:
        content = procs_file.read_text().strip()
        if not content:
            return []
        return [int(pid) for pid in content.split("\n") if pid.strip()]
    except FileNotFoundError:
        return []


def kill_cgroup_processes(cgroup_path: Path) -> None:
    """Send SIGKILL to all processes in a cgroup and wait for them to die.

    Reads cgroup.procs, sends SIGKILL to each PID, then polls until
    the cgroup is empty or the timeout is reached.

    Args:
        cgroup_path: Path to the cgroup directory.

    Raises:
        OSError: On non-Linux platform.
    """
    _require_linux()

    pids = read_cgroup_procs(cgroup_path)
    if not pids:
        log.debug("kill_cgroup_no_processes", cgroup=str(cgroup_path))
        return

    log.debug("kill_cgroup_processes", cgroup=str(cgroup_path), pids=pids)

    # Try cgroup.kill first (available in kernel 5.14+)
    kill_file = cgroup_path / "cgroup.kill"
    if kill_file.exists():
        try:
            kill_file.write_text("1\n")
            log.debug("cgroup_kill_used", cgroup=str(cgroup_path))
        except OSError:
            log.debug("cgroup_kill_fallback_to_sigkill")
            _sigkill_pids(pids)
    else:
        _sigkill_pids(pids)

    # Wait for processes to die
    deadline = time.monotonic() + _KILL_WAIT_TIMEOUT
    while time.monotonic() < deadline:
        remaining = read_cgroup_procs(cgroup_path)
        if not remaining:
            log.debug("cgroup_processes_cleared", cgroup=str(cgroup_path))
            return
        time.sleep(_KILL_POLL_INTERVAL)

    remaining = read_cgroup_procs(cgroup_path)
    if remaining:
        log.warning(
            "cgroup_processes_not_cleared",
            cgroup=str(cgroup_path),
            remaining_pids=remaining,
        )


def _sigkill_pids(pids: list[int]) -> None:
    """Send SIGKILL to each PID, ignoring errors for already-dead processes."""
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # Already dead
        except PermissionError:
            log.warning("sigkill_permission_denied", pid=pid)


def destroy_sandbox_cgroup(cgroup_path: Path) -> None:
    """Kill all processes in a cgroup, then remove it.

    Sends SIGKILL to all processes, waits for them to die, then
    removes the cgroup directory.

    Args:
        cgroup_path: Path to the cgroup directory.

    Raises:
        OSError: On non-Linux platform or if removal fails after
            processes are cleared.
    """
    _require_linux()

    if not cgroup_path.exists():
        log.debug("destroy_cgroup_already_gone", cgroup=str(cgroup_path))
        return

    log.debug("destroy_sandbox_cgroup", cgroup=str(cgroup_path))

    # Kill all processes first
    kill_cgroup_processes(cgroup_path)

    # Remove the cgroup directory (must be empty of processes)
    try:
        cgroup_path.rmdir()
        log.debug("cgroup_removed", cgroup=str(cgroup_path))
    except OSError as exc:
        log.warning(
            "cgroup_rmdir_failed",
            cgroup=str(cgroup_path),
            error=str(exc),
        )
        raise

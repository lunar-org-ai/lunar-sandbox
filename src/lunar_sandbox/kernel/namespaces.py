# SPDX-License-Identifier: MIT
"""Linux namespace creation via fork+unshare pattern.

Creates fully isolated process environments using Linux namespaces:
PID, mount, network, UTS, IPC, and user namespaces.  The critical
subtlety is that CLONE_NEWPID only takes effect after the *next*
fork -- so we need a double-fork pattern:

    parent --fork--> child --unshare--> child --fork--> grandchild (PID 1)

The grandchild becomes PID 1 in the new PID namespace, sets up the
mount namespace (pivot_root, proc mount), and execs the target command.

All functions are importable on any platform but raise OSError at call
time on non-Linux systems.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
from collections.abc import Callable
from typing import Final

import structlog

from lunar_sandbox.kernel.mount import (
    MS_NODEV,
    MS_NOEXEC,
    MS_NOSUID,
    MS_PRIVATE,
    MS_REC,
    MNT_DETACH,
    mount,
    pivot_root,
    umount2,
)

__all__ = [
    "create_sandboxed_process",
    "setup_mount_namespace",
    "set_hostname",
    # Namespace clone flags
    "CLONE_NEWNS",
    "CLONE_NEWPID",
    "CLONE_NEWNET",
    "CLONE_NEWUTS",
    "CLONE_NEWIPC",
    "CLONE_NEWUSER",
]

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
_IS_LINUX: Final[bool] = sys.platform == "linux"

# ---------------------------------------------------------------------------
# Namespace clone flags (from linux/sched.h)
# On Python 3.12+ these are available as os.CLONE_NEW* but we define
# them explicitly for clarity and to avoid AttributeError on non-Linux.
# ---------------------------------------------------------------------------
CLONE_NEWNS: Final[int] = 0x00020000
CLONE_NEWUTS: Final[int] = 0x04000000
CLONE_NEWIPC: Final[int] = 0x08000000
CLONE_NEWUSER: Final[int] = 0x10000000
CLONE_NEWPID: Final[int] = 0x20000000
CLONE_NEWNET: Final[int] = 0x40000000

# Combined flags for full sandbox isolation
_ALL_NAMESPACES: Final[int] = (
    CLONE_NEWNS
    | CLONE_NEWPID
    | CLONE_NEWNET
    | CLONE_NEWUTS
    | CLONE_NEWIPC
    | CLONE_NEWUSER
)

# Old root mount point inside the new root (used by pivot_root)
_PUT_OLD: Final[str] = ".old_root"


def _require_linux() -> None:
    """Raise OSError if not running on Linux."""
    if not _IS_LINUX:
        raise OSError(
            "Namespace operations require Linux. "
            "Current platform: " + sys.platform
        )


def _write_id_mapping(
    child_pid: int,
    real_uid: int,
    real_gid: int,
) -> None:
    """Write UID/GID mappings for the child's user namespace.

    Maps root (0) inside the namespace to the real user outside.
    Must write 'deny' to setgroups before writing gid_map.

    Args:
        child_pid: PID of the child process in the parent namespace.
        real_uid: Real UID of the parent process.
        real_gid: Real GID of the parent process.
    """
    proc = f"/proc/{child_pid}"

    log.debug(
        "writing_id_mappings",
        child_pid=child_pid,
        real_uid=real_uid,
        real_gid=real_gid,
    )

    # Deny setgroups before writing gid_map (required by kernel)
    with open(f"{proc}/setgroups", "w") as f:
        f.write("deny")

    # Map root inside namespace -> real user outside
    with open(f"{proc}/uid_map", "w") as f:
        f.write(f"0 {real_uid} 1\n")

    with open(f"{proc}/gid_map", "w") as f:
        f.write(f"0 {real_gid} 1\n")


def setup_mount_namespace(rootfs: str) -> None:
    """Set up the mount namespace for a sandboxed process.

    Makes all mounts private (prevents propagation to host), mounts
    a fresh /proc inside the new rootfs, then calls pivot_root to
    switch the root filesystem and unmounts the old root.

    Args:
        rootfs: Absolute path to the new root filesystem.

    Raises:
        OSError: On mount/pivot_root failure or non-Linux platform.
    """
    _require_linux()

    log.debug("setup_mount_namespace", rootfs=rootfs)

    # Make all mounts private so nothing propagates to the host
    mount(None, "/", None, MS_REC | MS_PRIVATE)

    # Bind-mount rootfs onto itself (pivot_root requires new_root
    # to be a mount point)
    mount(rootfs, rootfs, None, os.ST_NOSUID | MS_REC | 4096)  # MS_BIND = 4096

    # Mount proc inside the new rootfs
    proc_path = os.path.join(rootfs, "proc")
    os.makedirs(proc_path, exist_ok=True)
    mount("proc", proc_path, "proc", MS_NOSUID | MS_NODEV | MS_NOEXEC)

    # Create put_old directory for pivot_root
    put_old = os.path.join(rootfs, _PUT_OLD)
    os.makedirs(put_old, exist_ok=True)

    # Switch root filesystem
    pivot_root(rootfs, put_old)

    log.debug("pivot_root_complete", rootfs=rootfs)

    # Now we are inside the new root. Unmount old root and remove it.
    old_root = os.path.join("/", _PUT_OLD)
    umount2(old_root, MNT_DETACH)

    try:
        os.rmdir(old_root)
    except OSError:
        # May fail if not empty; lazy unmount handles it
        log.debug("rmdir_old_root_failed", path=old_root)


def set_hostname(hostname: str) -> None:
    """Set the hostname inside the UTS namespace.

    Must be called after unshare(CLONE_NEWUTS).

    Args:
        hostname: New hostname to set.

    Raises:
        OSError: On non-Linux platform or if sethostname fails.
    """
    _require_linux()
    log.debug("set_hostname", hostname=hostname)
    socket.sethostname(hostname)


def create_sandboxed_process(
    command: list[str],
    rootfs: str,
    setup_fn: Callable[[], None] | None = None,
) -> int:
    """Create a fully isolated process in new Linux namespaces.

    Implements the double-fork pattern required by CLONE_NEWPID:

    1. Parent forks child
    2. Parent writes UID/GID mappings for child's user namespace
    3. Child calls os.unshare() with all namespace flags
    4. Child forks again (grandchild becomes PID 1 in new PID ns)
    5. Child (intermediate) waits for grandchild, exits with its status
    6. Grandchild sets up mount namespace (pivot_root, proc)
    7. Grandchild applies setup_fn (seccomp, cgroup, etc.)
    8. Grandchild execs the target command

    Args:
        command: Command and arguments to exec (e.g. ["/bin/sh"]).
        rootfs: Absolute path to the root filesystem for the sandbox.
        setup_fn: Optional callback invoked after mount setup but before
            exec. Used for seccomp filter loading, cgroup assignment, etc.

    Returns:
        PID of the intermediate child process (parent should waitpid this).

    Raises:
        OSError: On non-Linux platform or if fork/unshare fails.
    """
    _require_linux()

    real_uid = os.getuid()
    real_gid = os.getgid()

    log.debug(
        "create_sandboxed_process",
        command=command,
        rootfs=rootfs,
        real_uid=real_uid,
        real_gid=real_gid,
    )

    # --- Synchronization pipe: parent signals child after writing ID maps ---
    # Child reads from pipe_r; parent writes to pipe_w after ID maps are set.
    pipe_r, pipe_w = os.pipe()

    # --- First fork: parent -> child ---
    child_pid = os.fork()

    if child_pid != 0:
        # ---- PARENT ----
        os.close(pipe_r)

        log.debug("parent_forked_child", child_pid=child_pid)

        # Write UID/GID mappings for the child's user namespace
        _write_id_mapping(child_pid, real_uid, real_gid)

        # Signal child that ID maps are ready
        os.write(pipe_w, b"x")
        os.close(pipe_w)

        return child_pid

    # ---- CHILD (will become intermediate process) ----
    os.close(pipe_w)

    try:
        # Wait for parent to write ID mappings before unsharing
        os.read(pipe_r, 1)
        os.close(pipe_r)

        # Unshare all namespaces
        log.debug("child_unsharing_namespaces")
        os.unshare(_ALL_NAMESPACES)

        # CRITICAL: Fork again because CLONE_NEWPID only takes effect
        # on the NEXT fork. The grandchild will be PID 1 in the new
        # PID namespace.
        grandchild_pid = os.fork()

        if grandchild_pid != 0:
            # ---- INTERMEDIATE CHILD: wait for grandchild ----
            log.debug(
                "intermediate_waiting_for_grandchild",
                grandchild_pid=grandchild_pid,
            )
            _, status = os.waitpid(grandchild_pid, 0)

            if os.WIFEXITED(status):
                os._exit(os.WEXITSTATUS(status))
            elif os.WIFSIGNALED(status):
                # Re-raise the signal that killed the grandchild
                sig = os.WTERMSIG(status)
                signal.signal(sig, signal.SIG_DFL)
                os.kill(os.getpid(), sig)
            os._exit(1)

        # ---- GRANDCHILD (PID 1 in new PID namespace) ----
        log.debug("grandchild_starting_setup")

        # Set hostname to sandbox identifier
        set_hostname("sandbox")

        # Set up the mount namespace (pivot_root, proc, etc.)
        setup_mount_namespace(rootfs)

        # Change to root directory inside the new root
        os.chdir("/")

        # Apply optional setup (seccomp, cgroup assignment, etc.)
        if setup_fn is not None:
            log.debug("grandchild_calling_setup_fn")
            setup_fn()

        # Exec the target command (replaces this process)
        log.debug("grandchild_execvp", command=command)
        os.execvp(command[0], command)

    except Exception:
        # Log and exit with error -- never let exceptions escape
        # from a forked child
        log.exception("sandboxed_process_setup_failed")
        os._exit(1)

# SPDX-License-Identifier: MIT
"""Seccomp-bpf syscall filtering for sandboxes.

Builds a default-ALLOW seccomp filter that blocks dangerous syscalls
(returning EPERM) to prevent namespace escape, kernel manipulation,
privilege escalation, and other dangerous operations.

The filter must be loaded AFTER fork but BEFORE exec, with
PR_SET_NO_NEW_PRIVS set first.

Handles import gracefully: if neither 'seccomp' nor 'pyseccomp' is
available (or if libseccomp is not installed), functions return None
instead of raising -- allowing non-Linux development.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import sys
from typing import Any, Final

import structlog

__all__ = [
    "create_sandbox_seccomp_filter",
    "load_seccomp_in_sandbox",
]

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
_IS_LINUX: Final[bool] = sys.platform == "linux"

# ---------------------------------------------------------------------------
# Graceful import of seccomp library
# ---------------------------------------------------------------------------
_seccomp_module: Any = None
_SECCOMP_AVAILABLE: bool = False

try:
    import seccomp as _seccomp_module  # type: ignore[no-redef]

    _SECCOMP_AVAILABLE = True
    log.debug("seccomp_module_loaded", source="seccomp")
except (ImportError, RuntimeError):
    try:
        import pyseccomp as _seccomp_module  # type: ignore[no-redef]

        _SECCOMP_AVAILABLE = True
        log.debug("seccomp_module_loaded", source="pyseccomp")
    except (ImportError, RuntimeError):
        log.debug("seccomp_module_not_available")

# ---------------------------------------------------------------------------
# prctl constants for PR_SET_NO_NEW_PRIVS
# ---------------------------------------------------------------------------
PR_SET_NO_NEW_PRIVS: Final[int] = 38

# ---------------------------------------------------------------------------
# Dangerous syscalls to block (returns EPERM)
# ---------------------------------------------------------------------------
# Each group is annotated with the threat it mitigates.

# Kernel manipulation -- prevent rebooting/loading kernel modules
_KERNEL_MANIPULATION: Final[list[str]] = [
    "reboot",
    "kexec_load",
    "kexec_file_load",
    "init_module",
    "finit_module",
    "delete_module",
    "create_module",
]

# Namespace escape -- prevent breaking out of the sandbox
_NAMESPACE_ESCAPE: Final[list[str]] = [
    "unshare",
    "setns",
    "mount",
    "umount2",
    "pivot_root",
]

# Privilege escalation -- prevent gaining additional privileges
_PRIVILEGE_ESCALATION: Final[list[str]] = [
    "keyctl",
    "add_key",
    "request_key",
]

# System control -- prevent system-wide modifications
_SYSTEM_CONTROL: Final[list[str]] = [
    "acct",
    "quotactl",
    "swapon",
    "swapoff",
    "settimeofday",
    "clock_settime",
]

# Dangerous I/O -- prevent raw hardware access
_DANGEROUS_IO: Final[list[str]] = [
    "iopl",
    "ioperm",
]

# eBPF escape -- prevent loading BPF programs
_EBPF_ESCAPE: Final[list[str]] = [
    "bpf",
]

# Process inspection -- prevent inspecting other processes
_PROCESS_INSPECTION: Final[list[str]] = [
    "process_vm_readv",
    "process_vm_writev",
    "ptrace",
]

# Obsolete/dangerous -- legacy syscalls with no legitimate sandbox use
_OBSOLETE_DANGEROUS: Final[list[str]] = [
    "uselib",
    "get_kernel_syms",
    "query_module",
    "lookup_dcookie",
    "perf_event_open",
    "open_by_handle_at",
]

# Combined list of all blocked syscalls
BLOCKED_SYSCALLS: Final[list[str]] = (
    _KERNEL_MANIPULATION
    + _NAMESPACE_ESCAPE
    + _PRIVILEGE_ESCALATION
    + _SYSTEM_CONTROL
    + _DANGEROUS_IO
    + _EBPF_ESCAPE
    + _PROCESS_INSPECTION
    + _OBSOLETE_DANGEROUS
)


def create_sandbox_seccomp_filter() -> Any | None:
    """Create a seccomp-bpf filter for sandbox isolation.

    Builds a default-ALLOW filter that blocks dangerous syscalls by
    returning EPERM. This approach is more compatible than default-DENY
    because it only blocks known-dangerous operations.

    Returns:
        A seccomp.SyscallFilter instance, or None if the seccomp library
        is not available (e.g., on macOS or missing libseccomp).
    """
    if not _SECCOMP_AVAILABLE or _seccomp_module is None:
        log.debug(
            "create_seccomp_filter_skipped",
            reason="seccomp library not available",
        )
        return None

    log.debug("creating_seccomp_filter", blocked_count=len(BLOCKED_SYSCALLS))

    # ALLOW by default, block specific dangerous syscalls
    f = _seccomp_module.SyscallFilter(defaction=_seccomp_module.ALLOW)

    blocked = 0
    skipped = 0

    for syscall_name in BLOCKED_SYSCALLS:
        try:
            f.add_rule(
                _seccomp_module.ERRNO(errno.EPERM),
                syscall_name,
            )
            blocked += 1
        except Exception:
            # Some syscalls may not exist on the current architecture
            # (e.g., get_kernel_syms on aarch64). Skip gracefully.
            log.debug("seccomp_syscall_skip", syscall=syscall_name)
            skipped += 1

    log.debug(
        "seccomp_filter_created",
        blocked=blocked,
        skipped=skipped,
        total=len(BLOCKED_SYSCALLS),
    )

    return f


def _set_no_new_privs() -> None:
    """Set PR_SET_NO_NEW_PRIVS via prctl.

    This is required before loading a seccomp filter. It prevents the
    process (and its children) from gaining new privileges through
    execve of setuid/setgid binaries.

    Uses ctypes to call prctl(2) directly.

    Raises:
        OSError: If prctl fails.
    """
    libc_name = ctypes.util.find_library("c")
    if libc_name is None:
        raise OSError("Cannot locate libc for prctl")

    libc = ctypes.CDLL(libc_name, use_errno=True)

    ret = libc.prctl(
        ctypes.c_int(PR_SET_NO_NEW_PRIVS),
        ctypes.c_ulong(1),
        ctypes.c_ulong(0),
        ctypes.c_ulong(0),
        ctypes.c_ulong(0),
    )
    if ret != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"prctl(PR_SET_NO_NEW_PRIVS): {os.strerror(err)}")

    log.debug("pr_set_no_new_privs_set")


def load_seccomp_in_sandbox(
    filter: Any | None,  # seccomp.SyscallFilter | None
) -> None:
    """Load a seccomp filter into the current process.

    Must be called AFTER fork but BEFORE exec. Sets PR_SET_NO_NEW_PRIVS
    first (required by kernel), then loads the filter.

    Args:
        filter: A seccomp.SyscallFilter instance from
            create_sandbox_seccomp_filter(), or None (no-op).

    Raises:
        OSError: On non-Linux platform, or if prctl/filter.load fails.
    """
    if filter is None:
        log.debug("load_seccomp_skipped", reason="no filter provided")
        return

    if not _IS_LINUX:
        raise OSError(
            "Seccomp filter loading requires Linux. "
            "Current platform: " + sys.platform
        )

    log.debug("loading_seccomp_filter")

    # Must set NO_NEW_PRIVS before loading filter
    _set_no_new_privs()

    # Load the BPF filter into the kernel
    filter.load()

    log.debug("seccomp_filter_loaded")

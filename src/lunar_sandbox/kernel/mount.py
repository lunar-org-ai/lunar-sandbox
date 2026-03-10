# SPDX-License-Identifier: MIT
"""Raw Linux mount syscall wrappers via ctypes.

Provides direct access to mount(2), umount2(2), and pivot_root(2) syscalls
without requiring external C dependencies. All functions raise OSError on
non-Linux platforms at call time (import is always safe).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import platform
import sys
from typing import Final

import structlog

__all__ = [
    "mount",
    "umount2",
    "pivot_root",
    # Mount flags (from linux/mount.h)
    "MS_RDONLY",
    "MS_NOSUID",
    "MS_NODEV",
    "MS_NOEXEC",
    "MS_BIND",
    "MS_REC",
    "MS_PRIVATE",
    "MS_REMOUNT",
    # Umount flags
    "MNT_FORCE",
    "MNT_DETACH",
    "MNT_EXPIRE",
]

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Mount flags from linux/mount.h
# ---------------------------------------------------------------------------
MS_RDONLY: Final[int] = 1
MS_NOSUID: Final[int] = 2
MS_NODEV: Final[int] = 4
MS_NOEXEC: Final[int] = 8
MS_REMOUNT: Final[int] = 32
MS_BIND: Final[int] = 4096
MS_REC: Final[int] = 16384
MS_PRIVATE: Final[int] = 1 << 18  # 262144

# Umount flags
MNT_FORCE: Final[int] = 1
MNT_DETACH: Final[int] = 2
MNT_EXPIRE: Final[int] = 4

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
_IS_LINUX: Final[bool] = sys.platform == "linux"

# pivot_root syscall numbers by architecture
_SYS_PIVOT_ROOT: Final[dict[str, int]] = {
    "x86_64": 155,
    "aarch64": 217,
}

# ---------------------------------------------------------------------------
# libc singleton
# ---------------------------------------------------------------------------
_libc_cache: ctypes.CDLL | None = None


def _get_libc() -> ctypes.CDLL:
    """Load and cache libc with errno support.

    Returns:
        Loaded libc CDLL instance.

    Raises:
        OSError: If libc cannot be loaded (should never happen on Linux).
    """
    global _libc_cache  # noqa: PLW0603
    if _libc_cache is not None:
        return _libc_cache

    libc_name = ctypes.util.find_library("c")
    if libc_name is None:
        raise OSError("Cannot locate libc -- is this a standard Linux system?")

    _libc_cache = ctypes.CDLL(libc_name, use_errno=True)
    return _libc_cache


def _require_linux() -> None:
    """Raise OSError if not running on Linux."""
    if not _IS_LINUX:
        raise OSError("mount syscalls require Linux")


# ---------------------------------------------------------------------------
# Syscall wrappers
# ---------------------------------------------------------------------------


def mount(
    source: str | None,
    target: str,
    fstype: str | None,
    flags: int = 0,
    options: str = "",
) -> None:
    """Wrapper around mount(2) syscall.

    Args:
        source: Source device/path (or None for virtual filesystems).
        target: Mount point path.
        fstype: Filesystem type (e.g. "overlay", "tmpfs", or None for bind).
        flags: Mount flags (e.g. MS_RDONLY | MS_BIND).
        options: Comma-separated mount options string.

    Raises:
        OSError: On mount failure or non-Linux platform.
    """
    _require_linux()
    libc = _get_libc()

    c_source = source.encode() if source else None
    c_target = target.encode()
    c_fstype = fstype.encode() if fstype else None
    c_options = options.encode() if options else None

    log.debug(
        "mount",
        source=source,
        target=target,
        fstype=fstype,
        flags=flags,
        options=options,
    )

    ret = libc.mount(c_source, c_target, c_fstype, ctypes.c_ulong(flags), c_options)
    if ret != 0:
        errno = ctypes.get_errno()
        raise OSError(
            errno,
            f"mount({source!r}, {target!r}, {fstype!r}, flags={flags}): "
            f"{os.strerror(errno)}",
        )


def umount2(target: str, flags: int = 0) -> None:
    """Wrapper around umount2(2) syscall.

    Args:
        target: Mount point to unmount.
        flags: Umount flags (e.g. MNT_DETACH for lazy unmount).

    Raises:
        OSError: On unmount failure or non-Linux platform.
    """
    _require_linux()
    libc = _get_libc()

    c_target = target.encode()

    log.debug("umount2", target=target, flags=flags)

    ret = libc.umount2(c_target, ctypes.c_int(flags))
    if ret != 0:
        errno = ctypes.get_errno()
        raise OSError(
            errno,
            f"umount2({target!r}, flags={flags}): {os.strerror(errno)}",
        )


def pivot_root(new_root: str, put_old: str) -> None:
    """Wrapper around pivot_root(2) syscall via SYS_pivot_root.

    There is no glibc wrapper for pivot_root, so we invoke it through
    the generic syscall(2) interface with architecture-specific syscall
    numbers.

    Args:
        new_root: Path to new root filesystem.
        put_old: Path (under new_root) where old root will be moved.

    Raises:
        OSError: On failure, unsupported architecture, or non-Linux platform.
    """
    _require_linux()
    libc = _get_libc()

    arch = platform.machine()
    syscall_nr = _SYS_PIVOT_ROOT.get(arch)
    if syscall_nr is None:
        raise OSError(
            f"pivot_root: unsupported architecture {arch!r} "
            f"(supported: {', '.join(_SYS_PIVOT_ROOT)})"
        )

    c_new_root = new_root.encode()
    c_put_old = put_old.encode()

    log.debug("pivot_root", new_root=new_root, put_old=put_old, arch=arch)

    ret = libc.syscall(
        ctypes.c_long(syscall_nr),
        ctypes.c_char_p(c_new_root),
        ctypes.c_char_p(c_put_old),
    )
    if ret != 0:
        errno = ctypes.get_errno()
        raise OSError(
            errno,
            f"pivot_root({new_root!r}, {put_old!r}): {os.strerror(errno)}",
        )

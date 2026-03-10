"""Kernel feature detection for sandbox prerequisites.

Checks all required Linux kernel features at startup and reports
missing capabilities with actionable fix hints. Hard fails if any
feature is missing -- no graceful degradation.
"""

from __future__ import annotations

import platform
import re
from dataclasses import dataclass
from pathlib import Path

import structlog

from lunar_sandbox.sandbox.errors import KernelFeatureError

log = structlog.get_logger(__name__)

# Minimum kernel version required for full cgroups v2 + OverlayFS support
MIN_KERNEL_MAJOR = 5
MIN_KERNEL_MINOR = 15


@dataclass
class KernelFeature:
    """Result of checking a single kernel feature.

    Attributes:
        name: Human-readable feature name.
        available: Whether the feature was detected.
        detail: Description of what was found (version, path, etc.).
        fix_hint: Actionable instruction for enabling the feature.
    """

    name: str
    available: bool
    detail: str
    fix_hint: str


def _check_kernel_version() -> KernelFeature:
    """Check that kernel version is >= 5.15."""
    release = platform.release()
    match = re.match(r"(\d+)\.(\d+)", release)
    if not match:
        return KernelFeature(
            name="kernel_version",
            available=False,
            detail=f"Could not parse kernel version from '{release}'",
            fix_hint="Ensure you are running Linux kernel >= 5.15. "
            "Check with: uname -r",
        )
    major, minor = int(match.group(1)), int(match.group(2))
    ok = (major, minor) >= (MIN_KERNEL_MAJOR, MIN_KERNEL_MINOR)
    return KernelFeature(
        name="kernel_version",
        available=ok,
        detail=f"Kernel {major}.{minor} (from '{release}')",
        fix_hint=f"Upgrade to kernel >= {MIN_KERNEL_MAJOR}.{MIN_KERNEL_MINOR}. "
        f"Current: {major}.{minor}. "
        "On Ubuntu: apt install linux-generic-hwe-22.04",
    )


def _check_cgroups_v2() -> KernelFeature:
    """Check that cgroups v2 unified hierarchy is mounted."""
    controllers_path = Path("/sys/fs/cgroup/cgroup.controllers")
    if controllers_path.exists():
        try:
            controllers = controllers_path.read_text().strip()
            return KernelFeature(
                name="cgroups_v2",
                available=True,
                detail=f"Controllers: {controllers}",
                fix_hint="",
            )
        except OSError as exc:
            return KernelFeature(
                name="cgroups_v2",
                available=False,
                detail=f"File exists but unreadable: {exc}",
                fix_hint="Check permissions on /sys/fs/cgroup/cgroup.controllers",
            )
    return KernelFeature(
        name="cgroups_v2",
        available=False,
        detail="/sys/fs/cgroup/cgroup.controllers not found",
        fix_hint="Enable cgroups v2 unified hierarchy. "
        "Add 'systemd.unified_cgroup_hierarchy=1' to kernel boot parameters, "
        "or ensure your distro defaults to cgroups v2 (Ubuntu 22.04+, Fedora 31+).",
    )


def _check_overlayfs() -> KernelFeature:
    """Check that OverlayFS is available in /proc/filesystems."""
    proc_fs = Path("/proc/filesystems")
    if proc_fs.exists():
        try:
            content = proc_fs.read_text()
            if "overlay" in content:
                return KernelFeature(
                    name="overlayfs",
                    available=True,
                    detail="overlay found in /proc/filesystems",
                    fix_hint="",
                )
            return KernelFeature(
                name="overlayfs",
                available=False,
                detail="overlay not found in /proc/filesystems",
                fix_hint="Load the overlay kernel module: modprobe overlay. "
                "To persist: echo 'overlay' >> /etc/modules-load.d/overlay.conf",
            )
        except OSError as exc:
            return KernelFeature(
                name="overlayfs",
                available=False,
                detail=f"/proc/filesystems unreadable: {exc}",
                fix_hint="Check that /proc is mounted and readable.",
            )
    return KernelFeature(
        name="overlayfs",
        available=False,
        detail="/proc/filesystems not found (not Linux?)",
        fix_hint="OverlayFS requires Linux. Ensure /proc is mounted.",
    )


def _check_seccomp() -> KernelFeature:
    """Check that seccomp-bpf is available.

    Primary check: /proc/sys/kernel/seccomp/actions_avail
    Fallback: /proc/self/status Seccomp line
    """
    actions_path = Path("/proc/sys/kernel/seccomp/actions_avail")
    if actions_path.exists():
        try:
            actions = actions_path.read_text().strip()
            return KernelFeature(
                name="seccomp",
                available=True,
                detail=f"Actions: {actions}",
                fix_hint="",
            )
        except OSError:
            pass

    # Fallback: check /proc/self/status for Seccomp line
    status_path = Path("/proc/self/status")
    if status_path.exists():
        try:
            for line in status_path.read_text().splitlines():
                if line.startswith("Seccomp:"):
                    # Seccomp: 0 means available but not active
                    # Seccomp: 1 means strict, Seccomp: 2 means filter
                    return KernelFeature(
                        name="seccomp",
                        available=True,
                        detail=f"From /proc/self/status: {line.strip()}",
                        fix_hint="",
                    )
        except OSError:
            pass

    return KernelFeature(
        name="seccomp",
        available=False,
        detail="Neither /proc/sys/kernel/seccomp/actions_avail "
        "nor Seccomp line in /proc/self/status found",
        fix_hint="Enable CONFIG_SECCOMP and CONFIG_SECCOMP_FILTER in kernel config. "
        "Most modern distros have this enabled by default.",
    )


def _check_user_namespaces() -> KernelFeature:
    """Check that unprivileged user namespaces are available.

    Checks /proc/sys/kernel/unprivileged_userns_clone.
    If the file is absent, user namespaces are allowed (upstream default).
    If present and contains '1', they are allowed.
    If present and contains '0', they are disabled.
    """
    userns_path = Path("/proc/sys/kernel/unprivileged_userns_clone")
    if userns_path.exists():
        try:
            value = userns_path.read_text().strip()
            allowed = value == "1"
            return KernelFeature(
                name="user_namespaces",
                available=allowed,
                detail=f"unprivileged_userns_clone = {value}",
                fix_hint="" if allowed else
                "Enable unprivileged user namespaces: "
                "sysctl -w kernel.unprivileged_userns_clone=1. "
                "To persist: add 'kernel.unprivileged_userns_clone=1' "
                "to /etc/sysctl.d/99-userns.conf",
            )
        except OSError as exc:
            return KernelFeature(
                name="user_namespaces",
                available=False,
                detail=f"File exists but unreadable: {exc}",
                fix_hint="Check permissions on "
                "/proc/sys/kernel/unprivileged_userns_clone",
            )

    # File absent = allowed per upstream kernel default
    # Also covers non-Linux where /proc doesn't exist
    if not Path("/proc").exists():
        return KernelFeature(
            name="user_namespaces",
            available=False,
            detail="/proc not found (not Linux?)",
            fix_hint="User namespaces require Linux. "
            "Run on a Linux host with kernel >= 5.15.",
        )

    return KernelFeature(
        name="user_namespaces",
        available=True,
        detail="unprivileged_userns_clone not present "
        "(allowed by upstream default)",
        fix_hint="",
    )


def detect_kernel_features() -> list[KernelFeature]:
    """Detect all required kernel features.

    Returns a list of 5 KernelFeature results, one for each
    required capability. Features are checked in order:
    1. Kernel version >= 5.15
    2. cgroups v2 unified hierarchy
    3. OverlayFS support
    4. seccomp-bpf support
    5. User namespaces

    Returns:
        List of KernelFeature objects with detection results.
    """
    checks = [
        _check_kernel_version,
        _check_cgroups_v2,
        _check_overlayfs,
        _check_seccomp,
        _check_user_namespaces,
    ]
    features = []
    for check_fn in checks:
        feature = check_fn()
        log.info(
            "kernel_feature_check",
            feature=feature.name,
            available=feature.available,
            detail=feature.detail,
        )
        features.append(feature)
    return features


def require_kernel_features() -> None:
    """Require all kernel features or raise KernelFeatureError.

    Calls detect_kernel_features() and if ANY feature is unavailable,
    raises KernelFeatureError with a message listing ALL missing
    features and their fix hints.

    Per user decision: hard fail, no graceful degradation.

    Raises:
        KernelFeatureError: If one or more required features are missing.
            The error message lists every missing feature with its fix hint.
    """
    features = detect_kernel_features()
    missing = [f for f in features if not f.available]

    if not missing:
        log.info("kernel_features_ok", count=len(features))
        return

    lines = [f"Missing {len(missing)} required kernel feature(s):\n"]
    for feat in missing:
        lines.append(f"  - {feat.name}: {feat.detail}")
        lines.append(f"    Fix: {feat.fix_hint}")
        lines.append("")

    message = "\n".join(lines)

    # Use the first missing feature's name for the error fields,
    # but the full message contains ALL missing features
    raise KernelFeatureError(
        message,
        feature_name=missing[0].name if len(missing) == 1 else "multiple",
        fix_hint="See error message for per-feature fix hints",
    )

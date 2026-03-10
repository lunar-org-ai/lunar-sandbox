"""Error hierarchy for sandbox operations.

All sandbox errors inherit from SandboxError. Error types are categorized
to distinguish between agent failures and infrastructure issues.
"""

from __future__ import annotations


class SandboxError(Exception):
    """Base class for all sandbox errors."""

    pass


class KernelFeatureError(SandboxError):
    """Required kernel feature is missing.

    Raised at startup when kernel feature detection finds missing
    capabilities. Includes the feature name and an actionable hint
    for how to fix it.
    """

    def __init__(
        self,
        message: str,
        *,
        feature_name: str = "",
        fix_hint: str = "",
    ) -> None:
        super().__init__(message)
        self.feature_name = feature_name
        self.fix_hint = fix_hint


class InfraError(SandboxError):
    """Infrastructure failure (OverlayFS mid-run, disk full, etc.).

    These are NOT agent failures. When an InfraError occurs mid-run,
    the task is skipped and the batch continues. The episode is not
    counted against the agent's score.
    """

    pass


class ResetError(SandboxError):
    """Sandbox reset failed (unmount busy, process leak, etc.).

    When a reset fails, the sandbox should be abandoned entirely and
    a replacement warmed up. Never fight a zombie mount.
    """

    pass


class TimeoutError(SandboxError):
    """Episode exceeded its time limit.

    The grace period follows: SIGTERM -> wait grace_period_seconds ->
    SIGKILL. Partial traces are saved. Episode is scored as timeout.
    """

    def __init__(
        self,
        message: str,
        *,
        grace_period_used: bool = False,
    ) -> None:
        super().__init__(message)
        self.grace_period_used = grace_period_used


class ResourceLimitError(SandboxError):
    """Cgroup resource limit exceeded (OOM, CPU quota, pids max, etc.)."""

    pass

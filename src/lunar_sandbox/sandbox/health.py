# SPDX-License-Identifier: MIT
"""Per-sandbox health tracking with anomaly-based retirement.

Tracks mount count, reset success/failure, and anomalies for each sandbox
instance. A sandbox is retired (permanently marked as broken) when the
anomaly count reaches the threshold (default 3). Retired sandboxes should
be abandoned and replaced -- never repaired.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

__all__ = [
    "SandboxHealth",
]

log = structlog.get_logger(__name__)


class SandboxHealth:
    """Health state for a single sandbox instance.

    Attributes:
        sandbox_id: Unique identifier for the sandbox.
        anomaly_count: Number of anomalies recorded.
        anomaly_threshold: Retire after this many anomalies.
        mount_count: Total overlay mounts performed.
        reset_count: Total reset operations attempted.
        reset_failures: Number of failed reset operations.
        created_at: Monotonic timestamp of creation.
        retired: Whether the sandbox has been retired.
        retire_reason: Human-readable reason for retirement.
    """

    __slots__ = (
        "sandbox_id",
        "anomaly_count",
        "anomaly_threshold",
        "mount_count",
        "reset_count",
        "reset_failures",
        "created_at",
        "retired",
        "retire_reason",
    )

    def __init__(
        self,
        sandbox_id: str,
        *,
        anomaly_threshold: int = 3,
    ) -> None:
        self.sandbox_id = sandbox_id
        self.anomaly_count: int = 0
        self.anomaly_threshold = anomaly_threshold
        self.mount_count: int = 0
        self.reset_count: int = 0
        self.reset_failures: int = 0
        self.created_at: float = time.monotonic()
        self.retired: bool = False
        self.retire_reason: str | None = None

    def record_mount(self) -> None:
        """Record a successful overlay mount."""
        self.mount_count += 1
        log.debug(
            "health_mount_recorded",
            sandbox_id=self.sandbox_id,
            mount_count=self.mount_count,
        )

    def record_reset(self, success: bool) -> None:
        """Record a reset operation and its outcome.

        On failure, also records an anomaly which may trigger retirement.

        Args:
            success: Whether the reset completed cleanly.
        """
        self.reset_count += 1
        if not success:
            self.reset_failures += 1
            self.record_anomaly("reset_failure")
        log.debug(
            "health_reset_recorded",
            sandbox_id=self.sandbox_id,
            success=success,
            reset_count=self.reset_count,
            reset_failures=self.reset_failures,
        )

    def record_anomaly(self, reason: str) -> None:
        """Record an anomaly event.

        Increments the anomaly counter. The caller should check
        :meth:`should_retire` after recording to decide whether
        to abandon the sandbox.

        Args:
            reason: Short description of the anomaly.
        """
        self.anomaly_count += 1
        log.warning(
            "health_anomaly_recorded",
            sandbox_id=self.sandbox_id,
            reason=reason,
            anomaly_count=self.anomaly_count,
            threshold=self.anomaly_threshold,
        )

    def should_retire(self) -> bool:
        """Check whether the sandbox should be retired.

        A sandbox should be retired when:
        - It has been explicitly retired (via :meth:`retire`), or
        - Its anomaly count has reached the threshold.

        Returns:
            True if the sandbox should be retired.
        """
        return self.retired or self.anomaly_count >= self.anomaly_threshold

    def retire(self, reason: str) -> None:
        """Explicitly retire this sandbox.

        After retirement, :meth:`should_retire` always returns True.

        Args:
            reason: Human-readable reason for retirement.
        """
        self.retired = True
        self.retire_reason = reason
        log.warning(
            "health_sandbox_retired",
            sandbox_id=self.sandbox_id,
            reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize health state to a dictionary.

        Returns:
            Dictionary with all health tracking fields.
        """
        return {
            "sandbox_id": self.sandbox_id,
            "anomaly_count": self.anomaly_count,
            "anomaly_threshold": self.anomaly_threshold,
            "mount_count": self.mount_count,
            "reset_count": self.reset_count,
            "reset_failures": self.reset_failures,
            "retired": self.retired,
            "retire_reason": self.retire_reason,
        }

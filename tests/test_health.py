"""Unit tests for per-sandbox health tracking.

Verifies anomaly counting, retirement thresholds, manual retirement,
reset success/failure recording, mount tracking, and serialization.
"""

from __future__ import annotations

from lunar_sandbox.sandbox.health import SandboxHealth


class TestSandboxHealthInit:
    """Tests for initial health state."""

    def test_initial_health_is_clean(self) -> None:
        """Freshly created SandboxHealth has zero counts and is not retired."""
        health = SandboxHealth("sb-001")
        assert health.anomaly_count == 0
        assert health.mount_count == 0
        assert health.reset_count == 0
        assert health.reset_failures == 0
        assert health.retired is False
        assert health.retire_reason is None

    def test_initial_should_not_retire(self) -> None:
        """A fresh sandbox should not be retired."""
        health = SandboxHealth("sb-001")
        assert health.should_retire() is False


class TestAnomalyRetirement:
    """Tests for anomaly-based retirement logic."""

    def test_retire_after_threshold(self) -> None:
        """3 anomalies (default threshold) triggers should_retire."""
        health = SandboxHealth("sb-001")
        health.record_anomaly("issue-1")
        health.record_anomaly("issue-2")
        health.record_anomaly("issue-3")
        assert health.should_retire() is True
        assert health.anomaly_count == 3

    def test_below_threshold_not_retired(self) -> None:
        """2 anomalies with default threshold=3 does not trigger retirement."""
        health = SandboxHealth("sb-001")
        health.record_anomaly("issue-1")
        health.record_anomaly("issue-2")
        assert health.should_retire() is False
        assert health.anomaly_count == 2

    def test_custom_threshold(self) -> None:
        """Custom anomaly_threshold=5 requires 5 anomalies to retire."""
        health = SandboxHealth("sb-001", anomaly_threshold=5)
        for i in range(4):
            health.record_anomaly(f"issue-{i}")
        assert health.should_retire() is False
        health.record_anomaly("issue-4")
        assert health.should_retire() is True
        assert health.anomaly_count == 5


class TestManualRetirement:
    """Tests for explicit retirement."""

    def test_manual_retire(self) -> None:
        """retire() sets retired=True and stores reason."""
        health = SandboxHealth("sb-001")
        health.retire("too many errors")
        assert health.should_retire() is True
        assert health.retired is True
        assert health.retire_reason == "too many errors"

    def test_manual_retire_overrides_count(self) -> None:
        """Manual retirement triggers should_retire even with zero anomalies."""
        health = SandboxHealth("sb-001")
        assert health.anomaly_count == 0
        health.retire("admin request")
        assert health.should_retire() is True


class TestResetRecording:
    """Tests for reset success/failure tracking."""

    def test_reset_failure_counts_as_anomaly(self) -> None:
        """A failed reset increments anomaly_count."""
        health = SandboxHealth("sb-001")
        health.record_reset(success=False)
        assert health.anomaly_count == 1
        assert health.reset_count == 1
        assert health.reset_failures == 1

    def test_reset_success_no_anomaly(self) -> None:
        """A successful reset does NOT increment anomaly_count."""
        health = SandboxHealth("sb-001")
        health.record_reset(success=True)
        assert health.anomaly_count == 0
        assert health.reset_count == 1
        assert health.reset_failures == 0

    def test_three_reset_failures_triggers_retirement(self) -> None:
        """3 failed resets trigger retirement via anomaly threshold."""
        health = SandboxHealth("sb-001")
        for _ in range(3):
            health.record_reset(success=False)
        assert health.should_retire() is True
        assert health.anomaly_count == 3


class TestMountTracking:
    """Tests for mount count tracking."""

    def test_mount_count_tracking(self) -> None:
        """record_mount increments mount_count."""
        health = SandboxHealth("sb-001")
        health.record_mount()
        health.record_mount()
        assert health.mount_count == 2


class TestSerialization:
    """Tests for to_dict() serialization."""

    def test_to_dict_serialization(self) -> None:
        """to_dict returns dictionary with all health fields."""
        health = SandboxHealth("sb-001", anomaly_threshold=5)
        health.record_mount()
        health.record_reset(success=True)
        health.record_anomaly("test-anomaly")

        d = health.to_dict()
        assert d["sandbox_id"] == "sb-001"
        assert d["anomaly_count"] == 1
        assert d["anomaly_threshold"] == 5
        assert d["mount_count"] == 1
        assert d["reset_count"] == 1
        assert d["reset_failures"] == 0
        assert d["retired"] is False
        assert d["retire_reason"] is None

    def test_to_dict_after_retirement(self) -> None:
        """to_dict reflects retired state and reason."""
        health = SandboxHealth("sb-001")
        health.retire("broken filesystem")
        d = health.to_dict()
        assert d["retired"] is True
        assert d["retire_reason"] == "broken filesystem"

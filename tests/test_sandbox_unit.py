"""Unit tests for the Sandbox class (state machine, config defaults).

Tests the Sandbox lifecycle state machine and configuration without
invoking any Linux kernel operations. All kernel calls are mocked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lunar_sandbox.sandbox.config import ResourceLimits, SandboxConfig
from lunar_sandbox.sandbox.sandbox import Sandbox, SandboxState


class TestSandboxStateEnum:
    """Tests for the SandboxState enum."""

    def test_sandbox_state_enum_values(self) -> None:
        """All expected lifecycle states exist."""
        expected = {"created", "running", "stopped", "resetting", "broken", "destroyed"}
        actual = {s.value for s in SandboxState}
        assert actual == expected

    def test_state_values_are_strings(self) -> None:
        """Each state value is a lowercase string."""
        for state in SandboxState:
            assert isinstance(state.value, str)
            assert state.value == state.value.lower()


class TestSandboxInit:
    """Tests for Sandbox initialization (CREATED state)."""

    def test_sandbox_initial_state(self, sample_config: SandboxConfig) -> None:
        """A new Sandbox starts in CREATED state."""
        sb = Sandbox(sample_config)
        assert sb.state == SandboxState.CREATED

    def test_sandbox_is_healthy_initial(self, sample_config: SandboxConfig) -> None:
        """A newly created Sandbox is healthy."""
        sb = Sandbox(sample_config)
        assert sb.is_healthy() is True

    def test_sandbox_layers_none_initially(self, sample_config: SandboxConfig) -> None:
        """Layers are None before create() is called."""
        sb = Sandbox(sample_config)
        assert sb.layers is None

    def test_sandbox_cgroup_none_initially(self, sample_config: SandboxConfig) -> None:
        """Cgroup path is None before create() is called."""
        sb = Sandbox(sample_config)
        assert sb.cgroup_path is None

    def test_sandbox_pid_none_initially(self, sample_config: SandboxConfig) -> None:
        """PID is None before create() is called."""
        sb = Sandbox(sample_config)
        assert sb.pid is None

    def test_sandbox_config_accessible(self, sample_config: SandboxConfig) -> None:
        """The config object is accessible via property."""
        sb = Sandbox(sample_config)
        assert sb.config is sample_config


class TestSandboxConfigDefaults:
    """Tests for SandboxConfig default values."""

    def test_sandbox_config_memory_default(self) -> None:
        """Default memory_max_bytes is 512 MiB."""
        limits = ResourceLimits()
        assert limits.memory_max_bytes == 512 * 1024 * 1024

    def test_sandbox_config_pids_default(self) -> None:
        """Default pids_max is 256."""
        limits = ResourceLimits()
        assert limits.pids_max == 256

    def test_sandbox_config_grace_period(self) -> None:
        """Default grace_period_seconds is 5."""
        config = SandboxConfig(sandbox_id="test")
        assert config.grace_period_seconds == 5

    def test_sandbox_config_anomaly_threshold(self) -> None:
        """Default anomaly_threshold is 3."""
        config = SandboxConfig(sandbox_id="test")
        assert config.anomaly_threshold == 3

    def test_sandbox_config_cpu_defaults(self) -> None:
        """Default CPU quota is 100_000 us with period 100_000 us (1 core)."""
        limits = ResourceLimits()
        assert limits.cpu_quota_us == 100_000
        assert limits.cpu_period_us == 100_000

    def test_sandbox_config_io_defaults(self) -> None:
        """Default I/O limits are 0 (unlimited)."""
        limits = ResourceLimits()
        assert limits.io_max_rbps == 0
        assert limits.io_max_wbps == 0


class TestSandboxHealthStates:
    """Tests for is_healthy() in various states."""

    def test_broken_sandbox_not_healthy(self, sample_config: SandboxConfig) -> None:
        """A BROKEN sandbox reports as unhealthy."""
        sb = Sandbox(sample_config)
        sb._state = SandboxState.BROKEN  # Force state for unit test
        assert sb.is_healthy() is False

    def test_destroyed_sandbox_not_healthy(self, sample_config: SandboxConfig) -> None:
        """A DESTROYED sandbox reports as unhealthy."""
        sb = Sandbox(sample_config)
        sb._state = SandboxState.DESTROYED
        assert sb.is_healthy() is False

    def test_retired_sandbox_not_healthy(self, sample_config: SandboxConfig) -> None:
        """A sandbox retired by health tracker is unhealthy."""
        sb = Sandbox(sample_config)
        sb.health.retire("test reason")
        assert sb.is_healthy() is False


class TestSandboxStateGuard:
    """Tests for _require_state() preventing invalid transitions."""

    def test_execute_requires_running_or_stopped(
        self, sample_config: SandboxConfig
    ) -> None:
        """execute() raises RuntimeError from CREATED state."""
        sb = Sandbox(sample_config)
        with pytest.raises(RuntimeError, match="expected one of"):
            sb.execute(["echo", "hello"])

    def test_reset_requires_running_or_stopped(
        self, sample_config: SandboxConfig
    ) -> None:
        """reset() raises RuntimeError from CREATED state."""
        sb = Sandbox(sample_config)
        with pytest.raises(RuntimeError, match="expected one of"):
            sb.reset()

    def test_destroy_from_any_state(self, sample_config: SandboxConfig) -> None:
        """destroy() does not raise from CREATED state (allowed from any state)."""
        sb = Sandbox(sample_config)
        # Should not raise -- destroy is allowed from any state
        sb.destroy()
        assert sb.state == SandboxState.DESTROYED

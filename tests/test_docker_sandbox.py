"""Unit tests for DockerSandbox (no Docker daemon required).

Tests state machine, configuration, and error handling using mocked
subprocess calls.  Integration tests that require a running Docker
daemon are marked with ``@pytest.mark.docker``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lunar_sandbox.sandbox.docker_config import (
    DockerResourceLimits,
    DockerSandboxConfig,
)
from lunar_sandbox.sandbox.docker_sandbox import DockerSandbox, DockerSandboxLayers
from lunar_sandbox.sandbox.sandbox import SandboxState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config(tmp_path: Path) -> DockerSandboxConfig:
    return DockerSandboxConfig(
        sandbox_id="test-sb-001",
        image="python:3.12-slim",
        data_root=tmp_path / "sandbox-data",
    )


@pytest.fixture
def sandbox(config: DockerSandboxConfig) -> DockerSandbox:
    return DockerSandbox(config)


# ---------------------------------------------------------------------------
# Init & state
# ---------------------------------------------------------------------------


def test_initial_state(sandbox: DockerSandbox) -> None:
    assert sandbox.state == SandboxState.CREATED
    assert sandbox.container_id is None
    assert sandbox.layers is None
    assert sandbox.is_healthy()


def test_config_property(sandbox: DockerSandbox, config: DockerSandboxConfig) -> None:
    assert sandbox.config is config
    assert sandbox.config.sandbox_id == "test-sb-001"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@patch("lunar_sandbox.sandbox.docker_sandbox.subprocess.run")
def test_create_success(mock_run: MagicMock, sandbox: DockerSandbox) -> None:
    # First call: docker info (check)
    # Second call: docker run
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),  # docker info
        MagicMock(returncode=0, stdout="abc123def456\n", stderr=""),  # docker run
    ]

    sandbox.create()

    assert sandbox.state == SandboxState.RUNNING
    assert sandbox.container_id == "abc123def456"
    assert sandbox.layers is not None
    assert sandbox.layers.sandbox_id == "test-sb-001"
    assert sandbox.layers.merged_dir.exists()


@patch("lunar_sandbox.sandbox.docker_sandbox.subprocess.run")
def test_create_docker_not_available(mock_run: MagicMock, sandbox: DockerSandbox) -> None:
    mock_run.side_effect = FileNotFoundError("docker not found")

    with pytest.raises(RuntimeError, match="Docker CLI not found"):
        sandbox.create()

    assert sandbox.state == SandboxState.CREATED


@patch("lunar_sandbox.sandbox.docker_sandbox.subprocess.run")
def test_create_docker_run_fails(mock_run: MagicMock, sandbox: DockerSandbox) -> None:
    mock_run.side_effect = [
        MagicMock(returncode=0),  # docker info OK
        MagicMock(returncode=1, stdout="", stderr="image not found"),  # docker run fails
    ]

    with pytest.raises(RuntimeError, match="docker run failed"):
        sandbox.create()


def test_create_wrong_state(sandbox: DockerSandbox) -> None:
    sandbox._state = SandboxState.RUNNING
    with pytest.raises(RuntimeError, match="expected one of: created"):
        sandbox.create()


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------


@patch("lunar_sandbox.sandbox.docker_sandbox.subprocess.run")
def test_execute_string_command(mock_run: MagicMock, sandbox: DockerSandbox) -> None:
    sandbox._state = SandboxState.RUNNING

    mock_run.return_value = MagicMock(
        returncode=0, stdout="hello\n", stderr=""
    )

    result = sandbox.execute("echo hello")

    assert result["exit_code"] == 0
    assert result["stdout"] == "hello\n"
    assert result["timed_out"] is False
    assert sandbox.state == SandboxState.STOPPED

    # Should use sh -c for string commands
    call_args = mock_run.call_args[0][0]
    assert call_args == ["docker", "exec", "test-sb-001", "sh", "-c", "echo hello"]


@patch("lunar_sandbox.sandbox.docker_sandbox.subprocess.run")
def test_execute_list_command(mock_run: MagicMock, sandbox: DockerSandbox) -> None:
    sandbox._state = SandboxState.RUNNING

    mock_run.return_value = MagicMock(
        returncode=0, stdout="world\n", stderr=""
    )

    result = sandbox.execute(["echo", "world"])

    call_args = mock_run.call_args[0][0]
    assert call_args == ["docker", "exec", "test-sb-001", "echo", "world"]


@patch("lunar_sandbox.sandbox.docker_sandbox.subprocess.run")
def test_execute_timeout(mock_run: MagicMock, sandbox: DockerSandbox) -> None:
    sandbox._state = SandboxState.RUNNING

    exc = subprocess.TimeoutExpired(cmd="docker exec", timeout=5)
    exc.stdout = b"partial"
    exc.stderr = b""
    mock_run.side_effect = exc

    result = sandbox.execute("sleep 100", timeout=5)

    assert result["timed_out"] is True
    assert result["exit_code"] is None
    assert result["stdout"] == "partial"


def test_execute_wrong_state(sandbox: DockerSandbox) -> None:
    with pytest.raises(RuntimeError, match="expected one of"):
        sandbox.execute("echo test")


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


@patch("lunar_sandbox.sandbox.docker_sandbox.subprocess.run")
def test_reset_success(mock_run: MagicMock, sandbox: DockerSandbox) -> None:
    sandbox._state = SandboxState.RUNNING

    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    ok = sandbox.reset()

    assert ok is True
    assert sandbox.state == SandboxState.RUNNING
    assert sandbox.health.reset_count == 1
    assert sandbox.health.reset_failures == 0


@patch("lunar_sandbox.sandbox.docker_sandbox.subprocess.run")
def test_reset_failure_marks_broken(mock_run: MagicMock, sandbox: DockerSandbox) -> None:
    sandbox._state = SandboxState.RUNNING

    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

    ok = sandbox.reset()

    assert ok is False
    assert sandbox.state == SandboxState.BROKEN
    assert not sandbox.is_healthy()


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------


@patch("lunar_sandbox.sandbox.docker_sandbox.subprocess.run")
def test_destroy(mock_run: MagicMock, sandbox: DockerSandbox) -> None:
    sandbox._state = SandboxState.RUNNING
    sandbox._container_id = "abc123"

    mock_run.return_value = MagicMock(returncode=0)

    sandbox.destroy()

    assert sandbox.state == SandboxState.DESTROYED
    assert sandbox.container_id is None
    assert sandbox.layers is None
    assert not sandbox.is_healthy()


@patch("lunar_sandbox.sandbox.docker_sandbox.subprocess.run")
def test_destroy_from_any_state(mock_run: MagicMock, sandbox: DockerSandbox) -> None:
    """Destroy can be called from any state."""
    mock_run.return_value = MagicMock(returncode=0)

    for state in SandboxState:
        sandbox._state = state
        sandbox.destroy()
        assert sandbox.state == SandboxState.DESTROYED


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


def test_docker_resource_limits_defaults() -> None:
    limits = DockerResourceLimits()
    assert limits.cpus == 1.0
    assert limits.memory_bytes == 512 * 1024 * 1024
    assert limits.pids_limit == 256


def test_docker_sandbox_config_defaults() -> None:
    config = DockerSandboxConfig(sandbox_id="test")
    assert config.image == "python:3.12-slim"
    assert config.workspace_dir == "/workspace"
    assert config.network_enabled is True


# ---------------------------------------------------------------------------
# Layers shim
# ---------------------------------------------------------------------------


def test_docker_sandbox_layers() -> None:
    layers = DockerSandboxLayers(
        sandbox_id="test",
        merged_dir=Path("/tmp/test/workspace"),
        host_socket_dir=Path("/tmp/test/sockets"),
    )
    assert layers.sandbox_id == "test"
    assert layers.merged_dir == Path("/tmp/test/workspace")


# ---------------------------------------------------------------------------
# Engine config
# ---------------------------------------------------------------------------


def test_engine_config_sandbox_backend() -> None:
    from lunar_sandbox.sdk.config import EngineConfig

    config = EngineConfig(sandbox_backend="docker", docker_image="ubuntu:22.04")
    assert config.sandbox_backend == "docker"
    assert config.docker_image == "ubuntu:22.04"


def test_engine_config_default_backend() -> None:
    from lunar_sandbox.sdk.config import EngineConfig

    config = EngineConfig()
    assert config.sandbox_backend == "auto"

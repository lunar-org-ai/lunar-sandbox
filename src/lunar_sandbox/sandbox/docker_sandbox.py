"""Docker-based sandbox lifecycle management.

Provides ``DockerSandbox`` -- a sandbox implementation that uses Docker
containers instead of Linux kernel primitives (namespaces, cgroups,
OverlayFS).  This makes the sandbox work on macOS and any system with
Docker installed.

State machine (same as native Sandbox)::

    CREATED -> RUNNING -> STOPPED -> RESETTING -> RUNNING  (happy path)
                                  -> BROKEN                (reset failed)
    any     -> DESTROYED                                   (explicit destroy)

Each sandbox maps to one Docker container.  Commands run via
``docker exec``, filesystem access via ``docker cp``, and reset
clears the workspace directory inside the container.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from lunar_sandbox.sandbox.docker_config import DockerSandboxConfig
from lunar_sandbox.sandbox.health import SandboxHealth
from lunar_sandbox.sandbox.sandbox import SandboxState

__all__ = [
    "DockerSandbox",
    "DockerSandboxLayers",
]

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DockerSandboxLayers:
    """Compatibility shim matching SandboxLayers interface.

    The ``merged_dir`` points to a host-side directory that is
    bind-mounted into the container at ``/workspace``.  This allows
    the EpisodeRunner to resolve socket paths and copy files.

    Attributes:
        sandbox_id: Sandbox identifier.
        merged_dir: Host directory bind-mounted to container workspace.
        host_socket_dir: Host directory bind-mounted for IPC sockets.
    """

    sandbox_id: str
    merged_dir: Path
    host_socket_dir: Path


class DockerSandbox:
    """Docker-based sandbox lifecycle management.

    Uses Docker containers for isolation instead of Linux kernel
    primitives.  Compatible with the same interface expected by
    ``EpisodeRunner`` and ``SandboxPool``.

    Lifecycle:
        1. ``__init__``: configure (state = CREATED)
        2. ``create()``: docker run (state = RUNNING)
        3. ``execute()``: docker exec
        4. ``reset()``: clean workspace (state = RUNNING or BROKEN)
        5. ``destroy()``: docker rm -f (state = DESTROYED)
    """

    __slots__ = (
        "_config",
        "_state",
        "_health",
        "_layers",
        "_container_id",
        "_host_workspace",
        "_host_socket_dir",
        "_log",
    )

    def __init__(self, config: DockerSandboxConfig) -> None:
        self._config = config
        self._state = SandboxState.CREATED
        self._health = SandboxHealth(
            sandbox_id=config.sandbox_id,
            anomaly_threshold=config.anomaly_threshold,
        )
        self._layers: DockerSandboxLayers | None = None
        self._container_id: str | None = None
        self._host_workspace: Path | None = None
        self._host_socket_dir: Path | None = None
        self._log = log.bind(sandbox_id=config.sandbox_id)

        self._log.debug("docker_sandbox_initialized", state=self._state.value)

    # -----------------------------------------------------------------
    # Public properties
    # -----------------------------------------------------------------

    @property
    def config(self) -> DockerSandboxConfig:
        return self._config

    @property
    def state(self) -> SandboxState:
        return self._state

    @property
    def health(self) -> SandboxHealth:
        return self._health

    @property
    def layers(self) -> DockerSandboxLayers | None:
        return self._layers

    @property
    def container_id(self) -> str | None:
        return self._container_id

    # -----------------------------------------------------------------
    # Lifecycle methods
    # -----------------------------------------------------------------

    def create(self) -> None:
        """Create and start the Docker container.

        Transitions: CREATED -> RUNNING

        Steps:
            1. Verify Docker is available.
            2. Create host directories for bind mounts.
            3. ``docker run -d`` with resource limits.
            4. Record health mount.

        Raises:
            RuntimeError: If Docker is not available or container fails.
        """
        self._require_state(SandboxState.CREATED)
        self._log.info("docker_sandbox_creating")

        # Step 1: Verify Docker is available
        _check_docker()

        # Step 2: Create host directories
        data_root = self._config.data_root / self._config.sandbox_id
        data_root.mkdir(parents=True, exist_ok=True)

        self._host_workspace = data_root / "workspace"
        self._host_workspace.mkdir(exist_ok=True)

        self._host_socket_dir = data_root / "sockets"
        self._host_socket_dir.mkdir(exist_ok=True)

        # Step 3: Build docker run command
        limits = self._config.resource_limits
        cmd = [
            "docker", "run", "-d",
            "--name", self._config.sandbox_id,
            # Resource limits
            f"--cpus={limits.cpus}",
            f"--memory={limits.memory_bytes}",
            f"--pids-limit={limits.pids_limit}",
            # Workspace bind mount
            "-v", f"{self._host_workspace}:{self._config.workspace_dir}",
            # Socket directory bind mount (for ActionExecutor IPC)
            "-v", f"{self._host_socket_dir}:/var/run/lunar",
            # Working directory
            "-w", self._config.workspace_dir,
        ]

        # Network
        if not self._config.network_enabled:
            cmd.append("--network=none")

        # Extra mounts
        for host_path, container_path in self._config.extra_mounts:
            cmd.extend(["-v", f"{host_path}:{container_path}"])

        # Extra env vars
        for key, val in self._config.extra_env.items():
            cmd.extend(["-e", f"{key}={val}"])

        # Image + long-running entrypoint (sleep infinity keeps container alive)
        cmd.extend([self._config.image, "sleep", "infinity"])

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"docker run failed (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )

        self._container_id = result.stdout.strip()[:12]

        # Build layers shim
        self._layers = DockerSandboxLayers(
            sandbox_id=self._config.sandbox_id,
            merged_dir=self._host_workspace,
            host_socket_dir=self._host_socket_dir,
        )

        self._health.record_mount()
        self._state = SandboxState.RUNNING

        self._log.info(
            "docker_sandbox_created",
            container_id=self._container_id,
            image=self._config.image,
        )

    def execute(
        self,
        command: list[str] | str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a command inside the container via docker exec.

        Args:
            command: Command to execute (list or shell string).
            timeout: Maximum seconds to wait (None = no timeout).

        Returns:
            Dictionary with keys:
                - ``exit_code``: Process exit code (int or None if killed).
                - ``stdout``: Standard output (str).
                - ``stderr``: Standard error (str).
                - ``timed_out``: Whether the timeout was exceeded (bool).
                - ``timeout_action``: "completed", "timeout_graceful", or
                  "timeout_killed".
        """
        self._require_state(SandboxState.RUNNING, SandboxState.STOPPED)
        self._log.debug("docker_execute", command=command, timeout=timeout)

        cmd = ["docker", "exec", self._config.sandbox_id]

        if isinstance(command, str):
            cmd.extend(["sh", "-c", command])
        else:
            cmd.extend(command)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            self._state = SandboxState.STOPPED
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timed_out": False,
                "timeout_action": "completed",
            }
        except subprocess.TimeoutExpired as exc:
            self._state = SandboxState.STOPPED
            return {
                "exit_code": None,
                "stdout": (exc.stdout or b"").decode(errors="replace")
                    if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                "stderr": (exc.stderr or b"").decode(errors="replace")
                    if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
                "timed_out": True,
                "timeout_action": "timeout_killed",
            }

    def copy_to(self, src: str | Path, dst: str) -> None:
        """Copy a file or directory from the host into the container.

        Args:
            src: Host path to copy from.
            dst: Container path to copy to.
        """
        self._require_state(SandboxState.RUNNING, SandboxState.STOPPED)

        result = subprocess.run(
            ["docker", "cp", str(src), f"{self._config.sandbox_id}:{dst}"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"docker cp failed: {result.stderr.strip()}"
            )

    def copy_from(self, src: str, dst: str | Path) -> None:
        """Copy a file or directory from the container to the host.

        Args:
            src: Container path to copy from.
            dst: Host path to copy to.
        """
        self._require_state(SandboxState.RUNNING, SandboxState.STOPPED)

        result = subprocess.run(
            ["docker", "cp", f"{self._config.sandbox_id}:{src}", str(dst)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"docker cp failed: {result.stderr.strip()}"
            )

    def reset(self) -> bool:
        """Reset the sandbox by cleaning the workspace.

        Transitions: RUNNING/STOPPED -> RESETTING -> RUNNING (success)
                     RUNNING/STOPPED -> RESETTING -> BROKEN  (failure)

        Returns:
            True if reset succeeded and sandbox is ready for next episode.
            False if reset failed and sandbox is now BROKEN.
        """
        self._require_state(SandboxState.RUNNING, SandboxState.STOPPED)

        self._log.info("docker_sandbox_resetting")
        self._state = SandboxState.RESETTING

        try:
            # Clean workspace inside container
            result = subprocess.run(
                [
                    "docker", "exec", self._config.sandbox_id,
                    "sh", "-c",
                    f"rm -rf {self._config.workspace_dir}/* "
                    f"{self._config.workspace_dir}/.[!.]* 2>/dev/null; true",
                ],
                capture_output=True, text=True, timeout=30,
            )

            success = result.returncode == 0
            self._health.record_reset(success)

            if not success:
                self._state = SandboxState.BROKEN
                self._health.retire("docker reset failed")
                self._log.warning(
                    "docker_sandbox_reset_failed",
                    stderr=result.stderr.strip(),
                )
                return False

            if self._health.should_retire():
                self._state = SandboxState.BROKEN
                self._log.warning(
                    "docker_sandbox_retired_by_health",
                    anomaly_count=self._health.anomaly_count,
                )
                return False

            self._state = SandboxState.RUNNING
            self._log.info("docker_sandbox_reset_complete")
            return True

        except Exception as exc:
            self._state = SandboxState.BROKEN
            self._health.retire(f"reset exception: {exc}")
            self._log.error("docker_sandbox_reset_error", error=str(exc))
            return False

    def destroy(self) -> None:
        """Destroy the sandbox: stop and remove the container, clean host dirs.

        Can be called from ANY state.
        """
        self._log.info(
            "docker_sandbox_destroying", current_state=self._state.value,
        )

        # Remove the container (force)
        if self._container_id is not None or self._config.sandbox_id:
            name = self._config.sandbox_id
            try:
                subprocess.run(
                    ["docker", "rm", "-f", name],
                    capture_output=True, text=True, timeout=30,
                )
            except Exception as exc:
                self._log.warning(
                    "docker_sandbox_destroy_container_failed",
                    error=str(exc),
                )
            self._container_id = None

        # Clean up host directories
        data_root = self._config.data_root / self._config.sandbox_id
        if data_root.exists():
            try:
                shutil.rmtree(data_root)
            except OSError as exc:
                self._log.warning(
                    "docker_sandbox_destroy_dirs_failed",
                    error=str(exc),
                )

        self._layers = None
        self._host_workspace = None
        self._host_socket_dir = None
        self._state = SandboxState.DESTROYED
        self._log.info("docker_sandbox_destroyed")

    # -----------------------------------------------------------------
    # Query methods
    # -----------------------------------------------------------------

    def is_healthy(self) -> bool:
        """Check whether the sandbox is healthy and usable."""
        if self._state in (SandboxState.BROKEN, SandboxState.DESTROYED):
            return False
        return not self._health.should_retire()

    def is_container_running(self) -> bool:
        """Check if the Docker container is actually running."""
        try:
            result = subprocess.run(
                [
                    "docker", "inspect", "-f",
                    "{{.State.Running}}",
                    self._config.sandbox_id,
                ],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip() == "true"
        except Exception:
            return False

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _require_state(self, *allowed: SandboxState) -> None:
        if self._state not in allowed:
            allowed_names = ", ".join(s.value for s in allowed)
            raise RuntimeError(
                f"DockerSandbox {self._config.sandbox_id} is in state "
                f"{self._state.value}, expected one of: {allowed_names}"
            )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _check_docker() -> None:
    """Verify Docker daemon is reachable."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Docker daemon not reachable: {result.stderr.strip()}"
            )
    except FileNotFoundError:
        raise RuntimeError(
            "Docker CLI not found. Install Docker: https://docs.docker.com/get-docker/"
        )

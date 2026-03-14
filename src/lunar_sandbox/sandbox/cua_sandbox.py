"""CUA (Computer-Using Agent) sandbox lifecycle management.

Extends :class:`DockerSandbox` for CUA containers that run a full X11 desktop
stack (Xvfb, Openbox, x11vnc, websockify) rather than a simple ``sleep infinity``
entrypoint.

Key differences from DockerSandbox:

- ``create()`` is fully overridden to skip the ``sleep infinity`` entrypoint and
  expose the noVNC port on the host.
- ``health_check()`` polls all four desktop services using ``docker exec``.
- ``reset()`` kills open application windows instead of clearing workspace files.
- ``execute()`` prepends ``DISPLAY=...`` to every command so xdotool and maim
  work correctly, and restores state to ``RUNNING`` after each exec call (the
  container keeps running between exec calls).

State machine::

    CREATED -> RUNNING -> STOPPED -> RESETTING -> RUNNING  (happy path)
                                   -> BROKEN               (reset failed)
    any     -> DESTROYED                                    (explicit destroy)
"""

from __future__ import annotations

import subprocess
import time
from typing import Any

import structlog

from lunar_sandbox.sandbox.cua_config import CUASandboxConfig
from lunar_sandbox.sandbox.cua_errors import ContainerError
from lunar_sandbox.sandbox.docker_sandbox import DockerSandbox, DockerSandboxLayers, _check_docker
from lunar_sandbox.sandbox.sandbox import SandboxState

__all__ = ["CUASandbox"]

log = structlog.get_logger(__name__)

# How long to poll health_check() after container start before giving up.
_STARTUP_TIMEOUT_SECONDS = 15
# Interval between health check polls during startup.
_STARTUP_POLL_INTERVAL_SECONDS = 1.0


class CUASandbox(DockerSandbox):
    """Lifecycle manager for CUA Docker containers.

    Extends :class:`DockerSandbox` with CUA-specific container management:

    - Starts the image's own desktop entrypoint (no ``sleep infinity``).
    - Exposes the noVNC port to the host for VNC debugging.
    - Injects ``DISPLAY`` into every ``execute()`` call.
    - Restores sandbox state to ``RUNNING`` after ``execute()`` (the CUA
      container keeps running between exec calls).
    - Resets by killing open application windows, not by clearing workspace
      files.

    Usage::

        config = CUASandboxConfig(sandbox_id="cua-01")
        sandbox = CUASandbox(config)
        sandbox.create()                    # Starts desktop stack
        ok = sandbox.health_check()         # Verifies Xvfb/Openbox/x11vnc/websockify
        result = sandbox.execute("echo hi") # Runs command with DISPLAY set
        sandbox.reset()                     # Kills app windows, keeps desktop
        sandbox.destroy()                   # Removes container and host dirs
    """

    __slots__ = ("_cua_config",)

    def __init__(self, config: CUASandboxConfig) -> None:
        super().__init__(config)
        self._cua_config = config

    # ------------------------------------------------------------------
    # Lifecycle overrides
    # ------------------------------------------------------------------

    def create(self) -> None:
        """Create and start the CUA Docker container.

        Overrides :meth:`DockerSandbox.create` completely -- the parent appends
        ``["sleep", "infinity"]`` to the docker run command, which would
        suppress the CUA entrypoint.

        The override:

        1. Checks Docker availability.
        2. Creates host bind-mount directories.
        3. Builds a docker run command with CUA-specific flags:
           - Environment variables: ``DISPLAY``, ``RESOLUTION``,
             ``COLOR_DEPTH``, ``VNC_PORT``, ``NOVNC_PORT``.
           - Port exposure: ``-p {novnc_port}:{novnc_port}`` for VNC
             debugging access from the host.
           - **No trailing command** -- the image's ENTRYPOINT handles startup.
        4. Polls :meth:`health_check` until all four services are ready.
        5. Sets state to ``RUNNING``.

        Raises:
            RuntimeError: If Docker is unavailable, the container fails to
                start, or the desktop services are not healthy within
                ``_STARTUP_TIMEOUT_SECONDS`` seconds.
        """
        self._require_state(SandboxState.CREATED)
        self._log.info("cua_sandbox_creating", image=self._cua_config.image)

        # Step 1: Verify Docker is available.
        _check_docker()

        # Step 2: Create host bind-mount directories.
        data_root = self._config.data_root / self._config.sandbox_id
        data_root.mkdir(parents=True, exist_ok=True)

        self._host_workspace = data_root / "workspace"
        self._host_workspace.mkdir(exist_ok=True)

        self._host_socket_dir = data_root / "sockets"
        self._host_socket_dir.mkdir(exist_ok=True)

        # Step 3: Build docker run command.
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
            # Socket directory bind mount for IPC
            "-v", f"{self._host_socket_dir}:/var/run/lunar",
            # Working directory
            "-w", self._config.workspace_dir,
        ]

        # Network (CUA containers need network for browser tasks).
        if not self._config.network_enabled:
            cmd.append("--network=none")

        # Extra mounts.
        for host_path, container_path in self._config.extra_mounts:
            cmd.extend(["-v", f"{host_path}:{container_path}"])

        # CUA environment variables (injected by CUASandboxConfig.__post_init__
        # into extra_env, but we emit them explicitly for clarity).
        for key, val in self._config.extra_env.items():
            cmd.extend(["-e", f"{key}={val}"])

        # Port exposure: noVNC port for VNC debugging access from the host.
        novnc_port = self._cua_config.novnc_port
        cmd.extend(["-p", f"{novnc_port}:{novnc_port}"])

        # Image only -- no trailing command; the ENTRYPOINT handles desktop startup.
        cmd.append(self._config.image)

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"docker run failed (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )

        self._container_id = result.stdout.strip()[:12]

        # Build layers shim (same structure as DockerSandbox).
        self._layers = DockerSandboxLayers(
            sandbox_id=self._config.sandbox_id,
            merged_dir=self._host_workspace,
            host_socket_dir=self._host_socket_dir,
        )

        self._health.record_mount()

        # Step 4: Wait for desktop services to be ready.
        # Set state to RUNNING first so execute() (called by health_check())
        # passes the state guard.
        self._state = SandboxState.RUNNING

        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        last_exc: Exception | None = None
        ready = False
        while time.monotonic() < deadline:
            try:
                if self.health_check():
                    ready = True
                    break
            except ContainerError as exc:
                last_exc = exc
            except Exception as exc:
                last_exc = exc
            time.sleep(_STARTUP_POLL_INTERVAL_SECONDS)

        if not ready:
            raise RuntimeError(
                f"CUA container {self._config.sandbox_id} desktop services "
                f"did not become healthy within {_STARTUP_TIMEOUT_SECONDS}s. "
                f"Last error: {last_exc}"
            )

        # Step 5: Restore RUNNING state.
        # health_check() calls execute() which (in the parent) sets state to
        # STOPPED. We must restore RUNNING after create() completes.
        self._state = SandboxState.RUNNING

        self._log.info(
            "cua_sandbox_created",
            container_id=self._container_id,
            image=self._config.image,
            resolution=self._cua_config.resolution,
            novnc_port=novnc_port,
        )

    def execute(
        self,
        command: list[str] | str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a command inside the CUA container with DISPLAY set.

        Prepends the X11 DISPLAY identifier to every command so that xdotool,
        maim, and xdpyinfo work correctly inside the container.

        After the exec completes the state is restored to ``RUNNING`` (the CUA
        container keeps running between exec calls -- only the exec'd process
        finished, not the container itself).

        Args:
            command: Shell string or list of arguments to run.
            timeout: Maximum seconds to wait (``None`` = no timeout).

        Returns:
            Dict with ``exit_code``, ``stdout``, ``stderr``, ``timed_out``,
            and ``timeout_action`` keys.
        """
        display = self._cua_config.display

        if isinstance(command, str):
            # Prepend DISPLAY for sh -c invocations.
            prefixed: list[str] | str = f"DISPLAY={display} {command}"
        else:
            # Inject env directive before the command list.
            prefixed = ["env", f"DISPLAY={display}"] + list(command)

        result = super().execute(prefixed, timeout)

        # The parent sets state to STOPPED after every exec call.  CUA
        # containers stay alive between exec calls, so restore RUNNING.
        self._state = SandboxState.RUNNING

        return result

    def health_check(self) -> bool:
        """Verify all four desktop services are running inside the container.

        Checks:
        1. Xvfb: ``xdpyinfo -display {DISPLAY}`` exits 0.
        2. Openbox: ``pgrep openbox`` exits 0.
        3. x11vnc: ``pgrep x11vnc`` exits 0.
        4. websockify: ``pgrep -f websockify`` exits 0.

        Returns:
            ``True`` if all four services are running.
            ``False`` if any service is not yet running.

        Raises:
            ContainerError: If the container itself is not running (docker exec
                fails because the container is stopped or removed).
        """
        display = self._cua_config.display

        checks = [
            # xdpyinfo exits 0 only when the X server accepts connections.
            f"xdpyinfo -display {display}",
            "pgrep openbox",
            "pgrep x11vnc",
            "pgrep -f websockify",
        ]

        for check_cmd in checks:
            # Call super().execute() directly to avoid the double DISPLAY
            # prefix that CUASandbox.execute() would add.  We include DISPLAY
            # in the check strings manually above.
            result = super().execute(check_cmd, timeout=5)

            # Restore state immediately (parent sets it to STOPPED).
            self._state = SandboxState.RUNNING

            if result.get("timed_out"):
                self._log.debug(
                    "cua_health_check_timeout", check=check_cmd,
                )
                return False

            exit_code = result.get("exit_code")

            # A non-zero exit_code from `docker exec` itself (not the inner
            # command) usually means the container is not running.
            # docker exec returns 126/127/125 for container-level errors;
            # pgrep returns 1 when no processes matched (service not running).
            if exit_code == 125 or exit_code == 126 or exit_code == 127:
                raise ContainerError(
                    f"Container {self._config.sandbox_id} is not running "
                    f"(docker exec exit {exit_code} for: {check_cmd})",
                    container_id=self._container_id,
                )

            if exit_code != 0:
                self._log.debug(
                    "cua_health_check_service_not_ready",
                    check=check_cmd,
                    exit_code=exit_code,
                )
                return False

        return True

    def reset(self) -> bool:
        """Reset the CUA desktop without restarting the container.

        Unlike :meth:`DockerSandbox.reset`, this does **not** clear the
        workspace directory.  Instead it kills open application windows and
        verifies the desktop services are still healthy.

        The X11 stack (Xvfb, Openbox, x11vnc, websockify) continues running
        throughout -- only user-opened application windows are closed.

        Transitions: RUNNING/STOPPED -> RESETTING -> RUNNING (success)
                     RUNNING/STOPPED -> RESETTING -> BROKEN  (failure)

        Returns:
            ``True`` if the desktop is healthy and ready for the next episode.
            ``False`` if the desktop services are unhealthy after the reset
            (sandbox is now BROKEN).
        """
        self._require_state(SandboxState.RUNNING, SandboxState.STOPPED)

        self._log.info("cua_sandbox_resetting")
        self._state = SandboxState.RESETTING

        display = self._cua_config.display

        try:
            # Close all visible windows gracefully via xdotool.
            # The `|| true` and `2>/dev/null` ensure this never fails even if
            # no windows are open.
            close_cmd = (
                f"DISPLAY={display} xdotool search --onlyvisible --name '' "
                f"| xargs -I{{}} xdotool windowclose {{}} 2>/dev/null || true"
            )
            super().execute(close_cmd, timeout=10)
            self._state = SandboxState.RUNNING  # Restore after parent sets STOPPED.

            # Give windows time to close cleanly.
            time.sleep(1.0)

            # Force-kill stubborn application processes.  Use `|| true` so the
            # command succeeds even if none of these processes are running.
            pkill_cmd = (
                "pkill -f chromium || true; "
                "pkill -f lxterminal || true; "
                "pkill -f mousepad || true; "
                "pkill -f pcmanfm || true"
            )
            super().execute(pkill_cmd, timeout=10)
            self._state = SandboxState.RUNNING  # Restore after parent sets STOPPED.

        except Exception as exc:
            self._state = SandboxState.BROKEN
            self._health.retire(f"cua reset exception during app kill: {exc}")
            self._log.error("cua_sandbox_reset_kill_error", error=str(exc))
            return False

        # Verify the desktop services survived the reset.
        try:
            healthy = self.health_check()
        except ContainerError as exc:
            healthy = False
            self._log.error("cua_sandbox_reset_container_error", error=str(exc))

        if not healthy:
            self._state = SandboxState.BROKEN
            self._health.retire("desktop services unhealthy after CUA reset")
            self._log.warning("cua_sandbox_reset_failed_health")
            return False

        # STATE RESTORATION: health_check() calls execute() which sets state to
        # STOPPED via the parent.  Restore RUNNING explicitly.
        self._state = SandboxState.RUNNING

        self._health.record_reset(True)
        self._log.info("cua_sandbox_reset_complete")
        return True

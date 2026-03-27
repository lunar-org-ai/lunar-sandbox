"""Windows CUA sandbox lifecycle management.

Manages a Windows VM (local QEMU or Azure) via SSH, providing the
same lifecycle interface as :class:`CUASandbox` (create, execute,
health_check, reset, destroy).

Commands run via ``ssh`` to the Windows VM.  The CUA helper PowerShell
script handles screenshots, mouse/keyboard input.

State machine::

    CREATED -> RUNNING -> STOPPED -> RESETTING -> RUNNING  (happy path)
                                   -> BROKEN               (reset failed)
    any     -> DESTROYED                                    (explicit destroy)
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from lunar_sandbox.sandbox.cua_errors import ActionFailed, ContainerError
from lunar_sandbox.sandbox.health import SandboxHealth
from lunar_sandbox.sandbox.sandbox import SandboxState
from lunar_sandbox.windows.config import WindowsCUAConfig

__all__ = ["WindowsCUASandbox", "WindowsSandboxLayers"]

log = structlog.get_logger(__name__)

# Startup timeout for verifying VM connectivity.
_STARTUP_TIMEOUT_SECONDS = 120
_STARTUP_POLL_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class WindowsSandboxLayers:
    """Compatibility shim matching SandboxLayers interface for Windows VMs.

    Attributes:
        sandbox_id: Sandbox identifier.
        merged_dir: Host-side directory for trajectory data and screenshots.
        host_socket_dir: Host-side directory (unused for Windows, kept for compat).
    """

    sandbox_id: str
    merged_dir: Path
    host_socket_dir: Path


class WindowsCUASandbox:
    """Lifecycle manager for Windows CUA virtual machines.

    Connects to a Windows VM via SSH and executes commands remotely.
    The VM must have:
    - OpenSSH Server enabled
    - RDP enabled (for live viewing)
    - ``cua_helper.ps1`` installed at the configured ``helper_path``

    Usage::

        config = WindowsCUAConfig(
            sandbox_id="win-01",
            ssh_host="192.168.1.100",
            ssh_user="lunar",
            ssh_key_path="~/.ssh/id_rsa",
        )
        sandbox = WindowsCUASandbox(config)
        sandbox.create()                    # Verifies SSH connectivity
        ok = sandbox.health_check()         # Checks helper script works
        result = sandbox.execute("dir")     # Runs command on Windows
        sandbox.reset()                     # Kills apps, clears workspace
        sandbox.destroy()                   # Shuts down VM (if local)
    """

    __slots__ = (
        "_config",
        "_state",
        "_health",
        "_layers",
        "_host_workspace",
        "_host_socket_dir",
        "_provider",
        "_log",
    )

    def __init__(
        self,
        config: WindowsCUAConfig,
        provider: Any | None = None,
    ) -> None:
        self._config = config
        self._state = SandboxState.CREATED
        self._health = SandboxHealth(
            sandbox_id=config.sandbox_id,
            anomaly_threshold=config.anomaly_threshold,
        )
        self._layers: WindowsSandboxLayers | None = None
        self._host_workspace: Path | None = None
        self._host_socket_dir: Path | None = None
        self._provider = provider
        self._log = log.bind(sandbox_id=config.sandbox_id)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> WindowsCUAConfig:
        return self._config

    @property
    def state(self) -> SandboxState:
        return self._state

    @property
    def health(self) -> SandboxHealth:
        return self._health

    @property
    def layers(self) -> WindowsSandboxLayers | None:
        return self._layers

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(self) -> None:
        """Create the sandbox: start VM (if local) and verify SSH connectivity.

        Transitions: CREATED -> RUNNING

        Steps:
            1. Start the VM via the provider (if configured).
            2. Create host directories for trajectory data.
            3. Poll SSH connectivity until the VM responds.
            4. Verify the CUA helper script is installed.

        Raises:
            RuntimeError: If SSH connectivity cannot be established.
        """
        self._require_state(SandboxState.CREATED)
        self._log.info("windows_sandbox_creating", host=self._config.ssh_host)

        # Step 1: Start VM via provider (if local QEMU or Azure).
        if self._provider is not None:
            self._log.info("windows_sandbox_starting_vm")
            self._provider.start()

        # Step 2: Create host directories.
        data_root = self._config.data_root / self._config.sandbox_id
        data_root.mkdir(parents=True, exist_ok=True)

        self._host_workspace = data_root / "workspace"
        self._host_workspace.mkdir(exist_ok=True)

        self._host_socket_dir = data_root / "sockets"
        self._host_socket_dir.mkdir(exist_ok=True)

        self._layers = WindowsSandboxLayers(
            sandbox_id=self._config.sandbox_id,
            merged_dir=self._host_workspace,
            host_socket_dir=self._host_socket_dir,
        )

        # Step 3: Poll SSH connectivity.
        self._state = SandboxState.RUNNING  # Allow execute() calls

        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        last_exc: Exception | None = None
        connected = False

        while time.monotonic() < deadline:
            try:
                result = self.execute("echo LUNAR_OK", timeout=10)
                if result["exit_code"] == 0 and "LUNAR_OK" in result["stdout"]:
                    connected = True
                    break
            except Exception as exc:
                last_exc = exc
            time.sleep(_STARTUP_POLL_INTERVAL_SECONDS)

        if not connected:
            self._state = SandboxState.CREATED
            raise RuntimeError(
                f"Windows VM {self._config.sandbox_id} SSH not reachable "
                f"within {_STARTUP_TIMEOUT_SECONDS}s at "
                f"{self._config.ssh_user}@{self._config.ssh_host}:"
                f"{self._config.ssh_port}. Last error: {last_exc}"
            )

        # Step 4: Verify helper script exists.
        helper_check = self.execute(
            f'powershell -Command "Test-Path \'{self._config.helper_path}\'"',
            timeout=15,
        )
        if "True" not in helper_check.get("stdout", ""):
            self._log.warning(
                "windows_sandbox_helper_missing",
                helper_path=self._config.helper_path,
            )

        self._health.record_mount()
        self._state = SandboxState.RUNNING

        self._log.info(
            "windows_sandbox_created",
            host=self._config.ssh_host,
            rdp_url=self._config.rdp_url,
        )

    def execute(
        self,
        command: list[str] | str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a command on the Windows VM via SSH.

        Args:
            command: Command to execute (string for cmd.exe, list for raw args).
            timeout: Maximum seconds to wait (None = no timeout).

        Returns:
            Dict with ``exit_code``, ``stdout``, ``stderr``, ``timed_out``,
            and ``timeout_action`` keys.
        """
        self._require_state(SandboxState.RUNNING, SandboxState.STOPPED)

        ssh_cmd = self._config.ssh_command_prefix()

        if isinstance(command, str):
            ssh_cmd.append(command)
        else:
            ssh_cmd.extend(command)

        self._log.debug("windows_execute", command=command, timeout=timeout)

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            self._state = SandboxState.RUNNING  # VM stays alive between calls
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timed_out": False,
                "timeout_action": "completed",
            }
        except subprocess.TimeoutExpired as exc:
            self._state = SandboxState.RUNNING
            return {
                "exit_code": None,
                "stdout": (exc.stdout or b"").decode(errors="replace")
                    if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                "stderr": (exc.stderr or b"").decode(errors="replace")
                    if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
                "timed_out": True,
                "timeout_action": "timeout_killed",
            }

    def execute_helper(
        self,
        action: str,
        timeout: float | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """Execute the CUA helper script with the given action and parameters.

        Builds a PowerShell command that invokes ``cua_helper.ps1`` with
        the specified action and named parameters.

        Args:
            action: CUA action name (e.g. ``"screenshot"``, ``"left_click"``).
            timeout: Maximum seconds to wait.
            **params: Action-specific parameters passed as -Name Value pairs.

        Returns:
            Result dict from :meth:`execute`.
        """
        helper = self._config.helper_path

        # Build parameter string
        param_parts = [f"-Action {action}"]
        for key, val in params.items():
            if isinstance(val, str) and " " in val:
                param_parts.append(f'-{key} "{val}"')
            else:
                param_parts.append(f"-{key} {val}")

        ps_cmd = f"powershell -ExecutionPolicy Bypass -File \"{helper}\" {' '.join(param_parts)}"
        return self.execute(ps_cmd, timeout=timeout)

    def health_check(self) -> bool:
        """Verify the Windows VM is accessible and the helper script works.

        Checks:
        1. SSH connectivity via echo command.
        2. CUA helper health_check action (verifies screen capture works).

        Returns:
            True if all checks pass, False otherwise.

        Raises:
            ContainerError: If the VM is completely unreachable.
        """
        # 1. SSH connectivity
        try:
            result = self.execute("echo LUNAR_OK", timeout=10)
        except Exception as exc:
            raise ContainerError(
                f"Windows VM {self._config.sandbox_id} is unreachable: {exc}",
            )

        if result.get("timed_out") or result.get("exit_code") != 0:
            self._log.debug("windows_health_ssh_failed", result=result)
            return False

        # 2. Helper health check
        result = self.execute_helper("health_check", timeout=15)
        if result.get("exit_code") != 0 or "HEALTHY" not in result.get("stdout", ""):
            self._log.debug("windows_health_helper_failed", result=result)
            return False

        return True

    def reset(self) -> bool:
        """Reset the Windows desktop for the next episode.

        Steps:
        1. Close all user applications (taskkill).
        2. Clear workspace directory.
        3. Clear browser profiles and temp files.
        4. Verify health.

        Transitions: RUNNING/STOPPED -> RESETTING -> RUNNING (success)
                     RUNNING/STOPPED -> RESETTING -> BROKEN  (failure)

        Returns:
            True if reset succeeded, False if sandbox is now BROKEN.
        """
        self._require_state(SandboxState.RUNNING, SandboxState.STOPPED)
        self._log.info("windows_sandbox_resetting")
        self._state = SandboxState.RESETTING

        try:
            # 1. Kill user applications
            kill_cmd = (
                'taskkill /F /IM chrome.exe 2>nul & '
                'taskkill /F /IM msedge.exe 2>nul & '
                'taskkill /F /IM firefox.exe 2>nul & '
                'taskkill /F /IM notepad.exe 2>nul & '
                'taskkill /F /IM explorer.exe 2>nul & '
                'start explorer.exe & '  # Restart explorer shell
                'exit /b 0'
            )
            self.execute(kill_cmd, timeout=15)

            # 2. Clear workspace
            self.execute(
                r'powershell -Command "Remove-Item C:\workspace\* -Recurse -Force -ErrorAction SilentlyContinue"',
                timeout=10,
            )

            # 3. Clear temp files and browser data
            clear_cmd = (
                'powershell -Command "'
                'Remove-Item $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue; '
                'Remove-Item $env:LOCALAPPDATA\\Google\\Chrome\\User` Data\\Default\\Cache\\* -Recurse -Force -ErrorAction SilentlyContinue; '
                'Remove-Item $env:LOCALAPPDATA\\Google\\Chrome\\User` Data\\Default\\Cookies* -Force -ErrorAction SilentlyContinue; '
                'Remove-Item $env:LOCALAPPDATA\\Google\\Chrome\\User` Data\\Default\\History* -Force -ErrorAction SilentlyContinue'
                '"'
            )
            self.execute(clear_cmd, timeout=10)

            time.sleep(1)  # Let explorer restart

        except Exception as exc:
            self._state = SandboxState.BROKEN
            self._health.retire(f"windows reset exception: {exc}")
            self._log.error("windows_sandbox_reset_error", error=str(exc))
            return False

        # 4. Verify health
        try:
            healthy = self.health_check()
        except ContainerError:
            healthy = False

        if not healthy:
            self._state = SandboxState.BROKEN
            self._health.retire("unhealthy after windows reset")
            self._log.warning("windows_sandbox_reset_failed_health")
            return False

        self._state = SandboxState.RUNNING
        self._health.record_reset(True)
        self._log.info("windows_sandbox_reset_complete")
        return True

    def destroy(self) -> None:
        """Destroy the sandbox: stop VM (if local) and clean up host dirs.

        Can be called from ANY state.
        """
        self._log.info("windows_sandbox_destroying", state=self._state.value)

        # Stop the VM via provider
        if self._provider is not None:
            try:
                self._provider.stop()
            except Exception as exc:
                self._log.warning("windows_sandbox_vm_stop_failed", error=str(exc))

        # Clean up host directories
        data_root = self._config.data_root / self._config.sandbox_id
        if data_root.exists():
            try:
                shutil.rmtree(data_root)
            except OSError as exc:
                self._log.warning("windows_sandbox_cleanup_failed", error=str(exc))

        self._layers = None
        self._host_workspace = None
        self._host_socket_dir = None
        self._state = SandboxState.DESTROYED
        self._log.info("windows_sandbox_destroyed")

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        """Check whether the sandbox is healthy and usable."""
        if self._state in (SandboxState.BROKEN, SandboxState.DESTROYED):
            return False
        return not self._health.should_retire()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_state(self, *allowed: SandboxState) -> None:
        if self._state not in allowed:
            allowed_names = ", ".join(s.value for s in allowed)
            raise RuntimeError(
                f"WindowsCUASandbox {self._config.sandbox_id} is in state "
                f"{self._state.value}, expected one of: {allowed_names}"
            )

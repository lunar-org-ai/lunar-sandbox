"""Azure Windows CUA sandbox using ``az vm run-command invoke`` for execution.

Bypasses SSH entirely — executes PowerShell commands on the Windows VM
via the Azure v1 run-command API (``invoke``).  This avoids the slow
OpenSSH Server install (~10-15 min on first boot) and port 22 firewall
issues.

Uses ``az vm run-command invoke --command-id RunPowerShellScript`` which
is the simplest, most reliable Azure remote execution method.  Commands
are written to a temp file to avoid shell quoting issues.

State machine::

    CREATED -> RUNNING -> STOPPED -> RESETTING -> RUNNING
                                   -> BROKEN
    any     -> DESTROYED
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import structlog

from lunar_sandbox.sandbox.health import SandboxHealth
from lunar_sandbox.sandbox.sandbox import SandboxState
from lunar_sandbox.windows.config import WindowsCUAConfig
from lunar_sandbox.windows.providers import _find_az_binary

__all__ = ["AzureWindowsCUASandbox"]

log = structlog.get_logger(__name__)

_STARTUP_TIMEOUT_SECONDS = 60
_STARTUP_POLL_INTERVAL_SECONDS = 10.0

# Actions whose output is too large for the 4KB az run-command stdout limit.
# These actions use SSH for output transfer instead.
_LARGE_OUTPUT_ACTIONS = frozenset({"screenshot"})


class AzureWindowsCUASandbox:
    """Windows CUA sandbox that uses ``az vm run-command invoke`` (v1 API).

    All command execution goes through the Azure control plane, so no
    SSH/OpenSSH is needed on the Windows VM.  The v1 invoke API is
    synchronous and doesn't leave resource state on the VM (unlike the
    v2 create API which can get stuck in "Creating" state).

    Usage::

        config = WindowsCUAConfig(sandbox_id="win-01", ssh_host="<vm-ip>")
        sandbox = AzureWindowsCUASandbox(
            config,
            resource_group="lunar-cua",
            vm_name="cua-windows",
        )
        sandbox.create()
        result = sandbox.execute("Write-Output 'hello'")
        sandbox.destroy()
    """

    __slots__ = (
        "_config",
        "_resource_group",
        "_vm_name",
        "_az_bin",
        "_state",
        "_health",
        "_layers",
        "_host_workspace",
        "_host_socket_dir",
        "_provider",
        "_log",
        "_ssh_ready",
        "_skip_cursor_position",
    )

    def __init__(
        self,
        config: WindowsCUAConfig,
        resource_group: str,
        vm_name: str,
        provider: Any | None = None,
    ) -> None:
        self._config = config
        self._resource_group = resource_group
        self._vm_name = vm_name
        self._az_bin = _find_az_binary()
        self._state = SandboxState.CREATED
        self._health = SandboxHealth(
            sandbox_id=config.sandbox_id,
            anomaly_threshold=config.anomaly_threshold,
        )
        self._layers = None
        self._host_workspace: Path | None = None
        self._host_socket_dir: Path | None = None
        self._provider = provider
        self._log = log.bind(sandbox_id=config.sandbox_id)
        self._ssh_ready = False
        # Skip per-step cursor_position calls — each az run-command invoke
        # adds ~30s latency and the model doesn't need cursor coordinates.
        self._skip_cursor_position = True

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
    def layers(self):
        return self._layers

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(self) -> None:
        """Verify VM is reachable via run-command and set up host dirs."""
        self._require_state(SandboxState.CREATED)
        self._log.info("azure_sandbox_creating", vm=self._vm_name)

        # Host directories for trajectory data
        data_root = self._config.data_root / self._config.sandbox_id
        data_root.mkdir(parents=True, exist_ok=True)
        self._host_workspace = data_root / "workspace"
        self._host_workspace.mkdir(exist_ok=True)
        self._host_socket_dir = data_root / "sockets"
        self._host_socket_dir.mkdir(exist_ok=True)

        from lunar_sandbox.windows.sandbox import WindowsSandboxLayers
        self._layers = WindowsSandboxLayers(
            sandbox_id=self._config.sandbox_id,
            merged_dir=self._host_workspace,
            host_socket_dir=self._host_socket_dir,
        )

        # Test connectivity
        self._state = SandboxState.RUNNING
        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        connected = False
        last_exc = None

        while time.monotonic() < deadline:
            try:
                result = self.execute("Write-Output 'LUNAR_OK'", timeout=60)
                if result["exit_code"] == 0 and "LUNAR_OK" in result["stdout"]:
                    connected = True
                    break
            except Exception as exc:
                last_exc = exc
            time.sleep(_STARTUP_POLL_INTERVAL_SECONDS)

        if not connected:
            self._state = SandboxState.CREATED
            raise RuntimeError(
                f"Azure VM {self._vm_name} not reachable via run-command "
                f"within {_STARTUP_TIMEOUT_SECONDS}s. Last error: {last_exc}"
            )

        self._health.record_mount()
        self._state = SandboxState.RUNNING

        # Pre-enable SSH so screenshots work out of the box.
        # This is a no-op if SSH is already running.
        try:
            self._ensure_ssh()
        except Exception as exc:
            self._log.warning(
                "azure_ssh_pre_enable_failed",
                error=str(exc),
                hint="Screenshots may fail. Enable OpenSSH manually via RDP.",
            )

        self._log.info("azure_sandbox_created", vm=self._vm_name)

    def execute(
        self,
        command: list[str] | str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a PowerShell command on the VM.

        Uses ``az vm run-command invoke --command-id RunPowerShellScript``
        (v1 API).  The script is written to a temp file and passed via
        ``--scripts @file`` to avoid shell quoting issues.
        """
        self._require_state(SandboxState.RUNNING, SandboxState.STOPPED)

        if isinstance(command, list):
            command = " ".join(command)

        self._log.debug("azure_execute", command=command[:100])

        # Write script to temp file to avoid shell escaping nightmares
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ps1", delete=False, prefix="cua_"
        ) as f:
            f.write(command)
            script_path = f.name

        az_timeout = int(timeout or 120)

        cmd = [
            self._az_bin, "vm", "run-command", "invoke",
            "--resource-group", self._resource_group,
            "--name", self._vm_name,
            "--command-id", "RunPowerShellScript",
            "--scripts", f"@{script_path}",
            "-o", "json",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=az_timeout + 60,
            )
        except subprocess.TimeoutExpired:
            self._state = SandboxState.RUNNING
            Path(script_path).unlink(missing_ok=True)
            return {
                "exit_code": None,
                "stdout": "",
                "stderr": "az vm run-command invoke timed out",
                "timed_out": True,
                "timeout_action": "timeout_killed",
            }
        finally:
            Path(script_path).unlink(missing_ok=True)

        self._state = SandboxState.RUNNING

        # Parse response — v1 invoke returns {"value": [{"message": "..."}]}
        stdout = ""
        stderr = ""
        exit_code = -1

        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                for entry in data.get("value", []):
                    code = entry.get("code", "")
                    msg = entry.get("message", "")
                    if "StdOut" in code:
                        stdout = msg
                    elif "StdErr" in code:
                        stderr = msg
                # v1 API doesn't return exit code directly;
                # treat non-empty stderr as failure
                exit_code = 1 if (stderr.strip() and not stdout.strip()) else 0
            except json.JSONDecodeError:
                stdout = result.stdout
                exit_code = 0
        else:
            stderr = result.stderr
            exit_code = result.returncode

        return {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": False,
            "timeout_action": "completed",
        }

    # ------------------------------------------------------------------
    # SSH support (for large outputs like screenshots)
    # ------------------------------------------------------------------

    def _ensure_ssh(self) -> None:
        """Ensure SSH is available for large-output transfers.

        The az run-command ``invoke`` API has a 4KB stdout limit which is
        too small for screenshot base64 data (~50-100KB). SSH has no such
        limit.

        Strategy:
        1. Try connecting via SSH directly (fast if already enabled).
        2. If that fails, enable OpenSSH via az run-command and open port 22.
        """
        if self._ssh_ready:
            return

        self._log.info("azure_ssh_checking")

        # Step 1: Try SSH directly — may already be running from setup.ps1
        test = self._execute_ssh("echo SSH_OK", timeout=10)
        if test["exit_code"] == 0 and "SSH_OK" in test.get("stdout", ""):
            self._ssh_ready = True
            self._log.info("azure_ssh_ready", method="already_available")
            return

        # Step 2: Start sshd via az run-command (fast if already installed)
        self._log.info("azure_ssh_enabling")
        result = self.execute(
            r"""
            $svc = Get-Service sshd -ErrorAction SilentlyContinue
            if ($svc) {
                Start-Service sshd -ErrorAction SilentlyContinue
                Set-Service -Name sshd -StartupType Automatic
                Write-Output 'SSH_STARTED'
            } else {
                Write-Output 'SSH_NOT_INSTALLED'
            }
            """,
            timeout=60,
        )
        status = result.get("stdout", "").strip()

        if "SSH_NOT_INSTALLED" in status:
            # Full install needed — this downloads from Windows Update
            self._log.info("azure_ssh_installing")
            install_result = self.execute(
                r"""
                Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
                Start-Service sshd
                Set-Service -Name sshd -StartupType Automatic
                Write-Output 'SSH_INSTALLED'
                """,
                timeout=600,  # Can take 10+ minutes
            )
            status = install_result.get("stdout", "").strip()
            if "SSH_INSTALLED" not in status:
                raise RuntimeError(
                    "Failed to install OpenSSH on Azure VM. "
                    "Install it manually via RDP or run setup.ps1 on the VM."
                )

        # Step 3: Open port 22 in the NSG (idempotent)
        try:
            subprocess.run(
                [
                    self._az_bin, "vm", "open-port",
                    "--resource-group", self._resource_group,
                    "--name", self._vm_name,
                    "--port", "22",
                    "--priority", "1010",
                    "-o", "none",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception as exc:
            self._log.warning("azure_ssh_open_port_failed", error=str(exc))

        # Step 4: Verify SSH connectivity
        test = self._execute_ssh("echo SSH_OK", timeout=15)
        if test["exit_code"] == 0 and "SSH_OK" in test.get("stdout", ""):
            self._ssh_ready = True
            self._log.info("azure_ssh_ready", method="enabled")
        else:
            raise RuntimeError(
                f"SSH enabled but cannot connect. "
                f"stderr: {test.get('stderr', '')}"
            )

    def _execute_ssh(
        self,
        command: str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a command on the VM via SSH (no output size limit).

        For password auth, tries ``sshpass`` first, then falls back to
        the ``SSH_ASKPASS`` environment trick (works without sshpass).
        """
        import shutil

        ssh_cmd = self._config.ssh_command_prefix()
        env = None

        if self._config.ssh_password and not self._config.ssh_key_path:
            if shutil.which("sshpass"):
                ssh_cmd = [
                    "sshpass", "-p", self._config.ssh_password,
                ] + ssh_cmd
            else:
                # Fallback: use SSH_ASKPASS with a helper script that echoes
                # the password.  DISPLAY must be set and SSH_ASKPASS_REQUIRE
                # forces its use even without a terminal.
                import os
                askpass_script = Path(tempfile.mktemp(suffix=".sh", prefix="askpass_"))
                askpass_script.write_text(
                    f"#!/bin/sh\necho '{self._config.ssh_password}'\n"
                )
                askpass_script.chmod(0o700)
                env = {
                    **os.environ,
                    "SSH_ASKPASS": str(askpass_script),
                    "SSH_ASKPASS_REQUIRE": "force",
                    "DISPLAY": ":0",
                }

        ssh_cmd.append(command)

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout or 120,
                env=env,
                stdin=subprocess.DEVNULL,
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timed_out": False,
                "timeout_action": "completed",
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": None,
                "stdout": "",
                "stderr": "SSH command timed out",
                "timed_out": True,
                "timeout_action": "timeout_killed",
            }
        finally:
            # Clean up askpass script if created
            if env and "SSH_ASKPASS" in env:
                Path(env["SSH_ASKPASS"]).unlink(missing_ok=True)

    def _execute_via_interactive_task(
        self,
        helper: str,
        args_str: str,
        timeout: float | None,
    ) -> dict[str, Any]:
        """Run the helper in the interactive RDP session via SSH.

        Creates a scheduled task with ``LogonType Interactive`` to get
        desktop access (needed for GDI+ screenshots and SendKeys), but
        uses SSH (~2s) instead of az run-command (~30s) for speed.

        The wrapper script is written to a temp file on the HOST, then
        piped to the VM via SSH stdin to avoid shell quoting issues.
        """
        user = self._config.ssh_user
        vm_poll = int(timeout or 30)
        import uuid as _uuid
        call_id = _uuid.uuid4().hex[:8]
        out_path = f"C:\\lunar-cua\\out_{call_id}.tmp"
        done_path = f"C:\\lunar-cua\\done_{call_id}.tmp"
        run_path = f"C:\\lunar-cua\\run_{call_id}.ps1"
        wrapper_path = f"C:\\lunar-cua\\wrap_{call_id}.ps1"

        # Build the wrapper PowerShell script (no quoting issues since
        # it's written to a file, not passed on the command line).
        wrapper_content = (
            f"# Runner script (executed in interactive session)\n"
            f"$runBody = @'\n"
            f"try {{\n"
            f'  $r = & "{helper}" {args_str}\n'
            f'  $r | Out-File -FilePath "{out_path}" -Encoding ASCII -NoNewline\n'
            f"}} catch {{\n"
            f'  $_.Exception.Message | Out-File -FilePath "{out_path}" -Encoding ASCII\n'
            f"}}\n"
            f'"done" | Out-File -FilePath "{done_path}" -Encoding UTF8\n'
            f"'@\n"
            f'$runBody | Set-Content -Path "{run_path}" -Encoding UTF8\n'
            f"\n"
            f'$a = New-ScheduledTaskAction -Execute "powershell.exe"'
            f' -Argument "-ExecutionPolicy Bypass -File {run_path}"\n'
            f'$p = New-ScheduledTaskPrincipal -UserId "{user}"'
            f" -LogonType Interactive -RunLevel Highest\n"
            f"$s = New-ScheduledTaskSettingsSet"
            f" -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries\n"
            f'Register-ScheduledTask -TaskName "cua_{call_id}"'
            f" -Action $a -Principal $p -Settings $s -Force | Out-Null\n"
            f'Start-ScheduledTask -TaskName "cua_{call_id}"\n'
            f"\n"
            f"$deadline = (Get-Date).AddSeconds({vm_poll})\n"
            f'while (-not (Test-Path "{done_path}") -and (Get-Date) -lt $deadline) {{\n'
            f"  Start-Sleep -Milliseconds 200\n"
            f"}}\n"
            f"\n"
            f'if (Test-Path "{out_path}") {{ Get-Content "{out_path}" -Raw }}\n'
            f'elseif (-not (Test-Path "{done_path}")) {{ Write-Error "Task timed out" }}\n'
            f'Unregister-ScheduledTask -TaskName "cua_{call_id}"'
            f" -Confirm:$false -ErrorAction SilentlyContinue\n"
            f'Remove-Item "{run_path}","{out_path}","{done_path}","{wrapper_path}"'
            f" -Force -ErrorAction SilentlyContinue\n"
        )

        # Write wrapper to a local temp file, upload via SSH, then execute it.
        # This avoids all shell quoting issues with double quotes.
        local_tmp = Path(tempfile.mktemp(suffix=".ps1", prefix="cua_wrap_"))
        local_tmp.write_text(wrapper_content)

        try:
            # Upload the wrapper script to the VM
            self._execute_ssh(
                f'powershell -Command "'
                f"[IO.File]::WriteAllText('{wrapper_path}',"
                f" [Text.Encoding]::UTF8.GetString("
                f"[Convert]::FromBase64String('"
                f"{__import__('base64').b64encode(wrapper_content.encode()).decode()}"
                f"')))\"",
                timeout=15,
            )

            # Execute the wrapper
            return self._execute_ssh(
                f'powershell -ExecutionPolicy Bypass -File "{wrapper_path}"',
                timeout=timeout or 60,
            )
        finally:
            local_tmp.unlink(missing_ok=True)

    def execute_helper(
        self,
        action: str,
        timeout: float | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """Execute the CUA helper in the interactive user's desktop session.

        ``az vm run-command invoke`` runs as SYSTEM which has no desktop,
        so GDI+ calls like ``CopyFromScreen`` fail.  This method wraps the
        helper invocation in a scheduled task that runs as the logged-in
        user with ``LogonType Interactive``, giving it access to the real
        desktop for screenshots, mouse, and keyboard input.

        For large-output actions (screenshots), SSH is used instead of
        az run-command to avoid the 4KB stdout limit.
        """
        helper = self._config.helper_path
        param_parts = [f"-Action {action}"]
        for key, val in params.items():
            if isinstance(val, str) and " " in val:
                param_parts.append(f'-{key} "{val}"')
            else:
                param_parts.append(f"-{key} {val}")

        # Use SSH for all helper actions (scheduled task for desktop access).
        # SSH is ~2s vs az run-command ~30s per call.
        self._ensure_ssh()
        return self._execute_via_interactive_task(
            helper, " ".join(param_parts), timeout
        )

    def health_check(self) -> bool:
        """Verify the VM responds to run-command."""
        try:
            result = self.execute("Write-Output 'HEALTHY'", timeout=60)
            return result.get("exit_code") == 0 and "HEALTHY" in result.get("stdout", "")
        except Exception:
            return False

    def reset(self) -> bool:
        """Reset the Windows desktop."""
        self._require_state(SandboxState.RUNNING, SandboxState.STOPPED)
        self._log.info("azure_sandbox_resetting")
        self._state = SandboxState.RESETTING

        try:
            self.execute(
                'taskkill /F /IM chrome.exe 2>$null; '
                'taskkill /F /IM msedge.exe 2>$null; '
                'taskkill /F /IM firefox.exe 2>$null; '
                'taskkill /F /IM notepad.exe 2>$null; '
                'Remove-Item C:\\workspace\\* -Recurse -Force -ErrorAction SilentlyContinue',
                timeout=60,
            )
        except Exception as exc:
            self._state = SandboxState.BROKEN
            self._health.retire(f"reset failed: {exc}")
            return False

        if not self.health_check():
            self._state = SandboxState.BROKEN
            self._health.retire("unhealthy after reset")
            return False

        self._state = SandboxState.RUNNING
        self._health.record_reset(True)
        return True

    def destroy(self) -> None:
        """Clean up host dirs. Does NOT delete the Azure VM."""
        self._log.info("azure_sandbox_destroying")
        data_root = self._config.data_root / self._config.sandbox_id
        if data_root.exists():
            import shutil
            try:
                shutil.rmtree(data_root)
            except OSError:
                pass
        self._layers = None
        self._state = SandboxState.DESTROYED

    def is_healthy(self) -> bool:
        if self._state in (SandboxState.BROKEN, SandboxState.DESTROYED):
            return False
        return not self._health.should_retire()

    def _require_state(self, *allowed: SandboxState) -> None:
        if self._state not in allowed:
            allowed_names = ", ".join(s.value for s in allowed)
            raise RuntimeError(
                f"AzureWindowsCUASandbox {self._config.sandbox_id} is in state "
                f"{self._state.value}, expected one of: {allowed_names}"
            )

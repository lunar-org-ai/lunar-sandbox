"""Windows CUA sandbox configuration.

Defines WindowsCUAConfig for Windows VM-based CUA sandboxes.
Supports both local QEMU VMs and remote Azure VMs via SSH.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WindowsCUAConfig:
    """Per-sandbox configuration for Windows CUA virtual machines.

    Connection is always via SSH (OpenSSH built into Windows 10+).
    The CUA helper PowerShell script must be pre-installed at
    ``helper_path`` on the VM.

    Attributes:
        sandbox_id: Unique identifier for this sandbox instance.
        ssh_host: SSH hostname or IP address of the Windows VM.
        ssh_port: SSH port (default 22).
        ssh_user: SSH username for the Windows VM.
        ssh_key_path: Path to the SSH private key file. If None,
            uses the default SSH key (~/.ssh/id_rsa).
        ssh_password: SSH password (used if ssh_key_path is None).
            For Azure VMs, this is the admin password set at creation.
        rdp_port: RDP port on the Windows VM (default 3389).
        width: Horizontal display resolution in pixels.
        height: Vertical display resolution in pixels.
        action_delay_ms: Milliseconds to wait after each action.
        screenshot_quality: JPEG quality for screenshots (1-100).
            70 balances fidelity and payload size.
        helper_path: Path to cua_helper.ps1 on the Windows VM.
        data_root: Host directory for sandbox runtime data.
        network_enabled: Whether the VM has network access.
        anomaly_threshold: Number of anomalies before retiring.
        provider: VM provider type (``"local"`` or ``"azure"``).
    """

    sandbox_id: str
    ssh_host: str = "localhost"
    ssh_port: int = 22
    ssh_user: str = "lunar"
    ssh_key_path: str | None = None
    ssh_password: str | None = None
    rdp_port: int = 3389
    width: int = 1280
    height: int = 800
    action_delay_ms: int = 100
    screenshot_quality: int = 70
    helper_path: str = r"C:\lunar-cua\cua_helper.ps1"
    data_root: Path = Path("/tmp/lunar-sandbox")
    network_enabled: bool = True
    anomaly_threshold: int = 3
    provider: str = "local"

    # Extra SSH options (e.g. StrictHostKeyChecking=no for new VMs)
    ssh_options: dict[str, str] = field(default_factory=lambda: {
        "StrictHostKeyChecking": "no",
        "UserKnownHostsFile": "/dev/null",
        "ConnectTimeout": "10",
    })

    @property
    def resolution(self) -> str:
        """Display resolution string, e.g. ``"1280x800"``."""
        return f"{self.width}x{self.height}"

    @property
    def rdp_url(self) -> str:
        """RDP connection URL for live viewing."""
        if self.ssh_host == "localhost" or self.ssh_host == "127.0.0.1":
            return f"rdp://localhost:{self.rdp_port}"
        return f"rdp://{self.ssh_host}:{self.rdp_port}"

    def ssh_command_prefix(self) -> list[str]:
        """Build the SSH command prefix for executing remote commands.

        Returns:
            List of strings forming the ssh command up to (but not
            including) the remote command itself.
        """
        cmd = ["ssh"]

        # SSH options
        for key, val in self.ssh_options.items():
            cmd.extend(["-o", f"{key}={val}"])

        # Port
        cmd.extend(["-p", str(self.ssh_port)])

        # Authentication
        if self.ssh_key_path:
            cmd.extend(["-i", self.ssh_key_path])

        # User@host
        cmd.append(f"{self.ssh_user}@{self.ssh_host}")

        return cmd

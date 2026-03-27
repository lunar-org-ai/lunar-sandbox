"""Windows VM providers: Local (QEMU) and Azure.

Each provider manages the lifecycle of a Windows VM and exposes
SSH/RDP connection details.  The :class:`WindowsCUASandbox` delegates
VM start/stop to the provider.

Usage::

    # Local QEMU VM
    provider = LocalWindowsProvider(LocalWindowsProviderConfig(
        qcow2_path="/path/to/windows.qcow2",
    ))
    provider.start()
    ssh_config = provider.get_ssh_config()

    # Azure VM
    provider = AzureWindowsProvider(AzureWindowsProviderConfig(
        resource_group="my-rg",
        vm_name="cua-win-01",
    ))
    provider.start()
    ssh_config = provider.get_ssh_config()
"""

from __future__ import annotations

import os
import shutil
import subprocess
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import structlog

__all__ = [
    "WindowsVMProvider",
    "LocalWindowsProvider",
    "LocalWindowsProviderConfig",
    "AzureWindowsProvider",
    "AzureWindowsProviderConfig",
]

log = structlog.get_logger(__name__)


def _find_az_binary() -> str:
    """Locate the ``az`` CLI binary.

    Jupyter kernels and virtualenvs often have a stripped PATH that
    misses Homebrew or system install locations. This function checks
    ``shutil.which`` first, then falls back to well-known paths.

    Returns:
        Absolute path to the ``az`` binary.

    Raises:
        FileNotFoundError: If ``az`` is not found anywhere.
    """
    found = shutil.which("az")
    if found:
        return found

    for directory in (
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        os.path.expanduser("~/.local/bin"),
    ):
        candidate = os.path.join(directory, "az")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    raise FileNotFoundError(
        "Azure CLI (az) not found. Install it:\n"
        "  brew install azure-cli\n"
        "  https://learn.microsoft.com/en-us/cli/azure/install-azure-cli"
    )


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------

class WindowsVMProvider(Protocol):
    """Protocol for Windows VM lifecycle management.

    Both local (QEMU) and cloud (Azure) providers implement this
    interface so that :class:`WindowsCUASandbox` can work with either.
    """

    def start(self) -> None:
        """Start or create the Windows VM."""
        ...

    def stop(self) -> None:
        """Stop (but don't delete) the Windows VM."""
        ...

    def destroy(self) -> None:
        """Permanently destroy the VM and associated resources."""
        ...

    def get_ssh_config(self) -> dict[str, Any]:
        """Return SSH connection details.

        Returns:
            Dict with keys: ``host``, ``port``, ``user``, ``key_path``
            (or ``password``).
        """
        ...

    def get_rdp_url(self) -> str:
        """Return the RDP connection URL for live viewing."""
        ...

    def is_running(self) -> bool:
        """Check if the VM is currently running."""
        ...


# ---------------------------------------------------------------------------
# Local QEMU provider
# ---------------------------------------------------------------------------

@dataclass
class LocalWindowsProviderConfig:
    """Configuration for a local Windows VM via QEMU.

    Attributes:
        qcow2_path: Path to the Windows QCOW2 disk image.
        memory_mb: RAM allocation in megabytes (default 4096).
        cpus: Number of CPU cores (default 2).
        ssh_host_port: Host port forwarded to guest port 22.
        rdp_host_port: Host port forwarded to guest port 3389.
        vnc_display: QEMU VNC display number (for QEMU monitor,
            not the Windows desktop VNC).
        enable_kvm: Use KVM acceleration on Linux. Ignored on macOS
            (uses HVF automatically).
        extra_qemu_args: Additional QEMU command-line arguments.
    """

    qcow2_path: str = ""
    memory_mb: int = 4096
    cpus: int = 2
    ssh_host_port: int = 2222
    rdp_host_port: int = 3389
    vnc_display: int = 1
    enable_kvm: bool = True
    extra_qemu_args: list[str] = field(default_factory=list)


class LocalWindowsProvider:
    """Manages a local Windows VM using QEMU.

    Starts QEMU with port forwarding for SSH (22) and RDP (3389).
    Works on macOS (HVF acceleration) and Linux (KVM acceleration).

    The Windows QCOW2 image must be pre-built with:
    - OpenSSH Server enabled
    - RDP enabled
    - ``cua_helper.ps1`` installed at ``C:\\lunar-cua\\cua_helper.ps1``

    See ``setup.ps1`` for automated provisioning.
    """

    def __init__(self, config: LocalWindowsProviderConfig) -> None:
        self._config = config
        self._process: subprocess.Popen | None = None
        self._log = log.bind(provider="local_qemu")

    def start(self) -> None:
        """Start the QEMU VM.

        Builds the QEMU command with:
        - CPU/memory allocation
        - Port forwarding (SSH + RDP)
        - Platform-specific acceleration (KVM/HVF)

        Raises:
            FileNotFoundError: If the QCOW2 image doesn't exist.
            RuntimeError: If QEMU fails to start.
        """
        if self._process is not None and self._process.poll() is None:
            self._log.info("local_vm_already_running")
            return

        qcow2 = Path(self._config.qcow2_path)
        if not qcow2.exists():
            raise FileNotFoundError(
                f"Windows QCOW2 image not found: {qcow2}\n"
                f"Create one with: qemu-img create -f qcow2 windows.qcow2 60G\n"
                f"Then install Windows from ISO."
            )

        # Detect platform for acceleration
        import platform
        system = platform.system()

        cmd = ["qemu-system-x86_64"]

        # Acceleration
        if system == "Darwin":
            cmd.extend(["-accel", "hvf"])
        elif system == "Linux" and self._config.enable_kvm:
            cmd.extend(["-accel", "kvm"])

        # Resources
        cmd.extend([
            "-m", str(self._config.memory_mb),
            "-smp", str(self._config.cpus),
        ])

        # Disk
        cmd.extend(["-drive", f"file={qcow2},format=qcow2"])

        # Network with port forwarding
        hostfwd = (
            f"hostfwd=tcp::{self._config.ssh_host_port}-:22,"
            f"hostfwd=tcp::{self._config.rdp_host_port}-:3389"
        )
        cmd.extend(["-nic", f"user,{hostfwd}"])

        # Display (headless -- use RDP for viewing)
        cmd.extend(["-display", "none"])

        # VNC for QEMU monitor (optional, not Windows desktop)
        cmd.extend(["-vnc", f":{self._config.vnc_display}"])

        # Extra args
        cmd.extend(self._config.extra_qemu_args)

        self._log.info("local_vm_starting", cmd=" ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Give QEMU a moment to start
        time.sleep(2)

        if self._process.poll() is not None:
            stderr = self._process.stderr.read().decode() if self._process.stderr else ""
            raise RuntimeError(
                f"QEMU failed to start (exit {self._process.returncode}): {stderr}"
            )

        self._log.info(
            "local_vm_started",
            pid=self._process.pid,
            ssh_port=self._config.ssh_host_port,
            rdp_port=self._config.rdp_host_port,
        )

    def stop(self) -> None:
        """Stop the QEMU VM gracefully."""
        if self._process is None:
            return
        self._log.info("local_vm_stopping")
        self._process.terminate()
        try:
            self._process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._process = None
        self._log.info("local_vm_stopped")

    def destroy(self) -> None:
        """Stop the VM. Does NOT delete the QCOW2 image."""
        self.stop()

    def get_ssh_config(self) -> dict[str, Any]:
        return {
            "host": "localhost",
            "port": self._config.ssh_host_port,
            "user": "lunar",
            "key_path": None,
        }

    def get_rdp_url(self) -> str:
        return f"rdp://localhost:{self._config.rdp_host_port}"

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None


# ---------------------------------------------------------------------------
# Azure provider
# ---------------------------------------------------------------------------

@dataclass
class AzureWindowsProviderConfig:
    """Configuration for an Azure Windows VM.

    Attributes:
        resource_group: Azure resource group name.
        vm_name: Name for the Azure VM.
        location: Azure region (default ``eastus``).
        vm_size: Azure VM size (default ``Standard_D2s_v3`` -- 2 vCPU, 8 GB).
        image: Azure VM image URN (default Windows 11).
        admin_username: Admin username for the VM.
        admin_password: Admin password for the VM. Must meet Azure
            complexity requirements (12+ chars, upper/lower/digit/special).
        ssh_key_path: Path to SSH public key for the VM. If None,
            password auth is used.
        open_ports: Ports to open in the NSG (default: SSH + RDP).
        tags: Azure resource tags.
    """

    resource_group: str = "lunar-cua"
    vm_name: str = "cua-windows"
    location: str = "eastus"
    vm_size: str = "Standard_D2s_v3"
    image: str = "MicrosoftWindowsDesktop:windows-11:win11-24h2-pro:latest"
    admin_username: str = "lunar"
    admin_password: str = ""
    ssh_key_path: str | None = None
    open_ports: list[int] = field(default_factory=lambda: [22, 3389])
    tags: dict[str, str] = field(default_factory=lambda: {"purpose": "cua-sandbox"})


class AzureWindowsProvider:
    """Manages a Windows VM on Azure via the ``az`` CLI.

    Prerequisites:
    - Azure CLI installed and authenticated (``az login``)
    - Sufficient Azure quota for the configured VM size

    After creation, the VM needs one-time setup:
    - SSH into the VM and run ``setup.ps1`` to enable OpenSSH and install
      the CUA helper script.

    Usage::

        config = AzureWindowsProviderConfig(
            resource_group="my-rg",
            vm_name="cua-win-01",
            admin_password="<your-password-here>",
        )
        provider = AzureWindowsProvider(config)
        provider.start()  # Creates VM if not exists, starts if stopped
        ssh = provider.get_ssh_config()
        # ssh['host'] is the public IP
        # ssh['port'] is 22
    """

    def __init__(self, config: AzureWindowsProviderConfig) -> None:
        self._config = config
        self._public_ip: str | None = None
        self._log = log.bind(provider="azure", vm_name=config.vm_name)

    def start(self) -> None:
        """Create or start the Azure Windows VM.

        If the VM doesn't exist, creates it with the configured settings.
        If it exists but is stopped, starts it.

        Raises:
            RuntimeError: If ``az`` CLI is not available or command fails.
        """
        self._check_az_cli()

        if self._vm_exists():
            if not self.is_running():
                self._log.info("azure_vm_starting")
                self._az([
                    "vm", "start",
                    "--resource-group", self._config.resource_group,
                    "--name", self._config.vm_name,
                ])
        else:
            self._create_vm()

        # Get public IP
        self._public_ip = self._get_public_ip()
        self._log.info(
            "azure_vm_ready",
            public_ip=self._public_ip,
            rdp_url=self.get_rdp_url(),
        )

    def stop(self) -> None:
        """Stop (deallocate) the Azure VM to avoid charges."""
        self._log.info("azure_vm_stopping")
        self._az([
            "vm", "deallocate",
            "--resource-group", self._config.resource_group,
            "--name", self._config.vm_name,
        ])
        self._log.info("azure_vm_stopped")

    def destroy(self) -> None:
        """Delete the Azure VM and its associated resources."""
        self._log.info("azure_vm_destroying")
        self._az([
            "vm", "delete",
            "--resource-group", self._config.resource_group,
            "--name", self._config.vm_name,
            "--yes",
            "--force-deletion", "true",
        ])
        self._public_ip = None
        self._log.info("azure_vm_destroyed")

    def get_ssh_config(self) -> dict[str, Any]:
        if self._public_ip is None:
            self._public_ip = self._get_public_ip()
        return {
            "host": self._public_ip,
            "port": 22,
            "user": self._config.admin_username,
            "password": self._config.admin_password,
            "key_path": self._config.ssh_key_path,
        }

    def get_rdp_url(self) -> str:
        if self._public_ip is None:
            self._public_ip = self._get_public_ip()
        return f"rdp://{self._public_ip}:3389"

    def is_running(self) -> bool:
        try:
            result = self._az([
                "vm", "get-instance-view",
                "--resource-group", self._config.resource_group,
                "--name", self._config.vm_name,
                "--query", "instanceView.statuses[1].displayStatus",
                "-o", "tsv",
            ])
            return "running" in result.stdout.lower()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_az_cli(self) -> None:
        """Verify Azure CLI is installed and authenticated."""
        az_bin = _find_az_binary()
        self._az_bin = az_bin
        result = subprocess.run(
            [az_bin, "account", "show"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Azure CLI not authenticated. Run: az login"
            )

    def _az(self, args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
        """Run an ``az`` CLI command.

        Args:
            args: Arguments after ``az``.
            timeout: Maximum seconds to wait (default 600 = 10 min).
                VM creation can take 5-8 minutes on Azure.

        Returns:
            CompletedProcess with the result.

        Raises:
            RuntimeError: If the command fails.
        """
        az_bin = getattr(self, "_az_bin", None) or _find_az_binary()
        cmd = [az_bin] + args
        self._log.debug("azure_cli", cmd=" ".join(cmd))

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"az {' '.join(args[:2])} failed: {result.stderr.strip()}"
            )
        return result

    def _vm_exists(self) -> bool:
        """Check if the VM already exists in the resource group."""
        try:
            self._az([
                "vm", "show",
                "--resource-group", self._config.resource_group,
                "--name", self._config.vm_name,
            ])
            return True
        except RuntimeError:
            return False

    def _create_vm(self) -> None:
        """Create a new Azure Windows VM."""
        self._log.info("azure_vm_creating")

        # Ensure resource group exists
        try:
            self._az([
                "group", "create",
                "--name", self._config.resource_group,
                "--location", self._config.location,
            ])
        except RuntimeError:
            pass  # Group may already exist

        # Build VM create command
        cmd = [
            "vm", "create",
            "--resource-group", self._config.resource_group,
            "--name", self._config.vm_name,
            "--location", self._config.location,
            "--image", self._config.image,
            "--size", self._config.vm_size,
            "--admin-username", self._config.admin_username,
            "--public-ip-sku", "Standard",
        ]

        # Authentication
        if self._config.admin_password:
            cmd.extend(["--admin-password", self._config.admin_password])
        if self._config.ssh_key_path:
            cmd.extend(["--ssh-key-values", self._config.ssh_key_path])

        # Tags
        if self._config.tags:
            tag_strs = [f"{k}={v}" for k, v in self._config.tags.items()]
            cmd.extend(["--tags"] + tag_strs)

        self._az(cmd)

        # Open ports
        if self._config.open_ports:
            ports_str = " ".join(str(p) for p in self._config.open_ports)
            self._az([
                "vm", "open-port",
                "--resource-group", self._config.resource_group,
                "--name", self._config.vm_name,
                "--port", ports_str,
                "--priority", "1000",
            ])

        self._log.info("azure_vm_created")

    def _get_public_ip(self) -> str:
        """Get the public IP address of the VM."""
        result = self._az([
            "vm", "show",
            "--resource-group", self._config.resource_group,
            "--name", self._config.vm_name,
            "--show-details",
            "--query", "publicIps",
            "-o", "tsv",
        ])
        ip = result.stdout.strip()
        if not ip:
            raise RuntimeError(
                f"No public IP found for VM {self._config.vm_name}"
            )
        return ip

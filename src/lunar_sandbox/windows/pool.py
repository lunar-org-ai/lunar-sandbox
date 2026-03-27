"""Windows CUA container pool with pre-warm and auto-replacement.

Mirrors :class:`CUAPool` but creates :class:`WindowsCUASandbox` instances
backed by either local QEMU VMs or Azure VMs.

Key differences from CUAPool:
- VMs are slower to start (~60-300s vs ~3s for Docker), so pre-warming
  is even more important.
- Pool size is typically smaller (1-2) due to VM cost/resources.
- Each VM requires a unique SSH port (for local) or IP (for Azure).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from lunar_sandbox.pool.config import PoolConfig
from lunar_sandbox.pool.pool import SandboxPool
from lunar_sandbox.windows.config import WindowsCUAConfig
from lunar_sandbox.windows.providers import (
    AzureWindowsProvider,
    AzureWindowsProviderConfig,
    LocalWindowsProvider,
    LocalWindowsProviderConfig,
)
from lunar_sandbox.windows.sandbox import WindowsCUASandbox

__all__ = ["WindowsCUAPool", "WindowsCUAPoolConfig", "windows_pool_fingerprint"]

log = structlog.get_logger(__name__)


@dataclass
class WindowsCUAPoolConfig:
    """Configuration for the Windows CUA VM pool.

    Attributes:
        pool_size: Number of Windows VMs to pre-warm. Keep small
            (1-2) for local VMs; can be larger for Azure.
        provider: VM provider type (``"local"`` or ``"azure"``).
        local_config: Config for local QEMU provider (used when
            provider is ``"local"``).
        azure_config: Config for Azure provider (used when provider
            is ``"azure"``).
        ssh_user: Default SSH username for all VMs.
        ssh_key_path: Default SSH key path for all VMs.
        data_root: Root directory for sandbox runtime data.
        base_ssh_port: Starting SSH port for local VMs.
            Each VM gets base_ssh_port + index.
        base_rdp_port: Starting RDP port for local VMs.
            Each VM gets base_rdp_port + index.
    """

    pool_size: int = 1
    provider: str = "local"
    local_config: LocalWindowsProviderConfig = field(
        default_factory=LocalWindowsProviderConfig
    )
    azure_config: AzureWindowsProviderConfig = field(
        default_factory=AzureWindowsProviderConfig
    )
    ssh_user: str = "lunar"
    ssh_key_path: str | None = None
    data_root: str = "/tmp/lunar-sandbox"
    base_ssh_port: int = 2222
    base_rdp_port: int = 3389


def windows_pool_fingerprint(provider: str = "local") -> str:
    """Return a Windows-CUA-specific fingerprint.

    Uses ``win-`` prefix to distinguish from Linux CUA (``cua-``) and
    coding pool fingerprints.

    Args:
        provider: VM provider type (``"local"`` or ``"azure"``).

    Returns:
        16-character string with ``win-`` prefix.
    """
    import hashlib

    payload = f"windows-cua:{provider}"
    return "win-" + hashlib.sha256(payload.encode()).hexdigest()[:12]


class WindowsCUAPool:
    """Pre-warmed pool of Windows CUA virtual machines.

    Wraps SandboxPool with:
    - Windows-specific factory creating WindowsCUASandbox instances
    - Provider-aware VM creation (local QEMU or Azure)
    - Unique port assignment for local VMs
    - ``win-`` prefixed fingerprint for pool grouping

    Usage::

        config = WindowsCUAPoolConfig(
            pool_size=1,
            provider="local",
            local_config=LocalWindowsProviderConfig(
                qcow2_path="/path/to/windows.qcow2",
            ),
        )
        pool = WindowsCUAPool(config)
        await pool.start()              # Pre-warms VMs (slow!)
        sandbox = await pool.acquire()  # Returns ready VM
        # ... run episode ...
        await pool.release(sandbox)     # Background reset
        await pool.shutdown()           # Stops all VMs
    """

    def __init__(self, config: WindowsCUAPoolConfig) -> None:
        self._config = config
        self._fingerprint = windows_pool_fingerprint(config.provider)
        self._vm_index = 0

        pool_config = PoolConfig(
            global_max_sandboxes=config.pool_size,
            per_fingerprint_soft_limit=config.pool_size,
        )
        self._pool = SandboxPool(
            config=pool_config,
            sandbox_factory=self._make_sandbox,
        )
        self._log = log.bind(component="windows_cua_pool")

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def _make_sandbox(self, fingerprint: str) -> WindowsCUASandbox:
        """Factory: create a WindowsCUASandbox for the pool.

        For local VMs, each sandbox gets a unique SSH/RDP port.
        For Azure VMs, each sandbox gets a unique VM name.
        """
        from uuid import uuid4

        idx = self._vm_index
        self._vm_index += 1

        sandbox_id = f"win-pool-{uuid4().hex[:8]}"

        if self._config.provider == "local":
            local_cfg = LocalWindowsProviderConfig(
                qcow2_path=self._config.local_config.qcow2_path,
                memory_mb=self._config.local_config.memory_mb,
                cpus=self._config.local_config.cpus,
                ssh_host_port=self._config.base_ssh_port + idx,
                rdp_host_port=self._config.base_rdp_port + idx,
                enable_kvm=self._config.local_config.enable_kvm,
                extra_qemu_args=self._config.local_config.extra_qemu_args,
            )
            provider = LocalWindowsProvider(local_cfg)

            sandbox_config = WindowsCUAConfig(
                sandbox_id=sandbox_id,
                ssh_host="localhost",
                ssh_port=local_cfg.ssh_host_port,
                ssh_user=self._config.ssh_user,
                ssh_key_path=self._config.ssh_key_path,
                rdp_port=local_cfg.rdp_host_port,
                data_root=Path(self._config.data_root),
                provider="local",
            )

        elif self._config.provider == "azure":
            azure_cfg = AzureWindowsProviderConfig(
                resource_group=self._config.azure_config.resource_group,
                vm_name=f"{self._config.azure_config.vm_name}-{idx}",
                location=self._config.azure_config.location,
                vm_size=self._config.azure_config.vm_size,
                image=self._config.azure_config.image,
                admin_username=self._config.azure_config.admin_username,
                admin_password=self._config.azure_config.admin_password,
                ssh_key_path=self._config.azure_config.ssh_key_path,
            )
            provider = AzureWindowsProvider(azure_cfg)

            # SSH config will be filled after provider.start()
            sandbox_config = WindowsCUAConfig(
                sandbox_id=sandbox_id,
                ssh_host="pending",  # Updated in create()
                ssh_port=22,
                ssh_user=self._config.azure_config.admin_username,
                ssh_password=self._config.azure_config.admin_password,
                ssh_key_path=self._config.azure_config.ssh_key_path,
                data_root=Path(self._config.data_root),
                provider="azure",
            )
        else:
            raise ValueError(f"Unknown provider: {self._config.provider}")

        sb = WindowsCUASandbox(sandbox_config, provider=provider)
        sb.create()
        return sb

    async def start(self) -> None:
        """Start pool and pre-warm all VMs before returning.

        This can take several minutes for QEMU or Azure VMs.
        """
        await self._pool.start()
        sandboxes = []
        for _ in range(self._config.pool_size):
            sb = await self._pool.acquire(self._fingerprint)
            sandboxes.append(sb)
        for sb in sandboxes:
            await self._pool.release(sb)
        self._log.info(
            "windows_pool_warmed",
            size=self._config.pool_size,
            provider=self._config.provider,
        )

    async def acquire(self) -> WindowsCUASandbox:
        """Acquire a pre-warmed Windows sandbox from the pool."""
        sb = await self._pool.acquire(self._fingerprint)
        return sb  # type: ignore[return-value]

    async def release(self, sandbox: WindowsCUASandbox) -> None:
        """Release sandbox back to pool for background reset."""
        await self._pool.release(sandbox)

    async def shutdown(self) -> None:
        """Shut down pool and destroy all VMs."""
        await self._pool.shutdown()
        self._log.info("windows_pool_shutdown")

    async def status(self) -> dict:
        """Return pool status."""
        return await self._pool.status()

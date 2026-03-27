"""Windows CUA (Computer-Using Agent) support.

Provides sandbox, action handler, VM providers, and pool management
for running CUA episodes on Windows virtual machines -- either locally
via QEMU or remotely on Azure.

Quick start (local VM)::

    from lunar_sandbox.windows import (
        WindowsCUAConfig,
        WindowsCUASandbox,
        WindowsCUAActionHandler,
        LocalWindowsProvider,
        LocalWindowsProviderConfig,
    )

    # 1. Create provider and sandbox
    provider = LocalWindowsProvider(LocalWindowsProviderConfig(
        qcow2_path="/path/to/windows.qcow2",
    ))
    config = WindowsCUAConfig(
        sandbox_id="win-01",
        ssh_host="localhost",
        ssh_port=2222,
    )
    sandbox = WindowsCUASandbox(config, provider=provider)
    sandbox.create()

    # 2. Create action handler
    handler = WindowsCUAActionHandler(sandbox, config)

    # 3. Use the same CUA actions as Linux
    screenshot = handler.screenshot()
    handler.left_click(300, 400)
    handler.type_text("hello")

    # 4. Watch live via RDP
    print(f"Connect via RDP: {config.rdp_url}")

Quick start (Azure VM)::

    from lunar_sandbox.windows import (
        WindowsCUAConfig,
        WindowsCUASandbox,
        WindowsCUAActionHandler,
        AzureWindowsProvider,
        AzureWindowsProviderConfig,
    )

    provider = AzureWindowsProvider(AzureWindowsProviderConfig(
        resource_group="my-rg",
        vm_name="cua-win-01",
        admin_password="<your-password-here>",
    ))
    provider.start()
    ssh = provider.get_ssh_config()

    config = WindowsCUAConfig(
        sandbox_id="win-azure-01",
        ssh_host=ssh["host"],
        ssh_port=ssh["port"],
        ssh_user=ssh["user"],
        ssh_password=ssh["password"],
    )
    sandbox = WindowsCUASandbox(config, provider=provider)
    sandbox.create()

    handler = WindowsCUAActionHandler(sandbox, config)
    print(f"Watch live via RDP: {provider.get_rdp_url()}")
"""

from lunar_sandbox.windows.action_handler import WindowsCUAActionHandler
from lunar_sandbox.windows.config import WindowsCUAConfig
from lunar_sandbox.windows.pool import WindowsCUAPool, WindowsCUAPoolConfig
from lunar_sandbox.windows.providers import (
    AzureWindowsProvider,
    AzureWindowsProviderConfig,
    LocalWindowsProvider,
    LocalWindowsProviderConfig,
    WindowsVMProvider,
)
from lunar_sandbox.windows.sandbox import WindowsCUASandbox

__all__ = [
    # Config
    "WindowsCUAConfig",
    # Sandbox
    "WindowsCUASandbox",
    # Action handler
    "WindowsCUAActionHandler",
    # Providers
    "WindowsVMProvider",
    "LocalWindowsProvider",
    "LocalWindowsProviderConfig",
    "AzureWindowsProvider",
    "AzureWindowsProviderConfig",
    # Pool
    "WindowsCUAPool",
    "WindowsCUAPoolConfig",
]

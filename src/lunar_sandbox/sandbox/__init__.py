"""Sandbox configuration, error types, and lifecycle management."""

from lunar_sandbox.sandbox.config import ResourceLimits, SandboxConfig
from lunar_sandbox.sandbox.cua_config import CUASandboxConfig
from lunar_sandbox.sandbox.cua_errors import ActionFailed, ActionTimeout, ContainerError
from lunar_sandbox.sandbox.cua_sandbox import CUASandbox
from lunar_sandbox.sandbox.docker_config import DockerResourceLimits, DockerSandboxConfig
from lunar_sandbox.sandbox.docker_sandbox import DockerSandbox, DockerSandboxLayers
from lunar_sandbox.sandbox.health import SandboxHealth
from lunar_sandbox.sandbox.sandbox import Sandbox, SandboxState

__all__ = [
    "DockerSandbox",
    "DockerSandboxConfig",
    "DockerSandboxLayers",
    "DockerResourceLimits",
    "Sandbox",
    "SandboxState",
    "SandboxConfig",
    "ResourceLimits",
    "SandboxHealth",
    # CUA extensions
    "CUASandbox",
    "CUASandboxConfig",
    "ActionTimeout",
    "ActionFailed",
    "ContainerError",
]

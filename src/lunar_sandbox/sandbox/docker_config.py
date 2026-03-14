"""Docker sandbox configuration.

Defines DockerSandboxConfig -- per-sandbox configuration for
Docker-based sandboxes.  Maps resource limits to Docker's
``--memory``, ``--cpus``, ``--pids-limit`` flags.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DockerResourceLimits:
    """Resource limits expressed in Docker-native units.

    Attributes:
        cpus: Number of CPUs (fractional OK, e.g. 1.5).
        memory_bytes: Hard memory limit in bytes (default 512 MiB).
        pids_limit: Max number of processes inside the container.
    """

    cpus: float = 1.0
    memory_bytes: int = 512 * 1024 * 1024
    pids_limit: int = 256


@dataclass
class DockerSandboxConfig:
    """Per-sandbox configuration for Docker-based sandboxes.

    Attributes:
        sandbox_id: Unique identifier for this sandbox instance.
        image: Docker image to use (must exist locally or be pullable).
        resource_limits: Docker resource constraints.
        workspace_dir: Directory inside the container used as the
            working directory for all commands.
        data_root: Host directory for sandbox runtime data
            (bind-mount directories, logs).
        network_enabled: Whether the container has network access.
        extra_mounts: Additional bind mounts as (host_path, container_path) pairs.
        extra_env: Extra environment variables to set in the container.
        anomaly_threshold: Number of anomalies before retiring.
    """

    sandbox_id: str
    image: str = "python:3.12-slim"
    resource_limits: DockerResourceLimits = field(
        default_factory=DockerResourceLimits
    )
    workspace_dir: str = "/workspace"
    data_root: Path = Path("/tmp/lunar-sandbox")
    network_enabled: bool = True
    extra_mounts: list[tuple[str, str]] = field(default_factory=list)
    extra_env: dict[str, str] = field(default_factory=dict)
    anomaly_threshold: int = 3

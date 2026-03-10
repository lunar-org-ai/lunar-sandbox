"""Sandbox configuration dataclasses.

Defines ResourceLimits (cgroups v2 parameters) and SandboxConfig
(per-sandbox instance configuration).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Default memory limit: 512 MiB
_DEFAULT_MEMORY_MAX = 512 * 1024 * 1024


@dataclass
class ResourceLimits:
    """Cgroups v2 resource limits for a sandbox.

    Attributes:
        cpu_quota_us: CPU quota in microseconds per period.
            100_000 with period 100_000 = 1 full CPU core.
        cpu_period_us: CPU period in microseconds.
        memory_max_bytes: Hard memory limit in bytes (512 MiB default).
        pids_max: Maximum number of processes/threads.
        io_max_rbps: Max read bytes/sec (0 = unlimited).
            Written to cgroup io.max as "major:minor rbps=X".
        io_max_wbps: Max write bytes/sec (0 = unlimited).
            Written to cgroup io.max as "major:minor wbps=Y".
    """

    cpu_quota_us: int = 100_000
    cpu_period_us: int = 100_000
    memory_max_bytes: int = _DEFAULT_MEMORY_MAX
    pids_max: int = 256
    io_max_rbps: int = 0
    io_max_wbps: int = 0


@dataclass
class SandboxConfig:
    """Per-sandbox instance configuration.

    Attributes:
        sandbox_id: Unique identifier for this sandbox instance.
        resource_limits: Cgroups v2 resource constraints.
        base_dir: Path to the base (read-only) filesystem layer.
        deps_dir: Optional path to the dependency layer directory.
        seed_dir: Optional path to the seed data layer directory.
        data_root: Root directory for sandbox runtime data
            (overlay workdirs, cgroup mountpoints, logs).
        grace_period_seconds: Seconds to wait between SIGTERM and
            SIGKILL on timeout. 5s per research recommendation.
        anomaly_threshold: Number of anomalies (reset failures,
            mount errors) before retiring a sandbox. 3 per research
            recommendation.
        use_tmpfs_upper: Whether to use tmpfs for the OverlayFS
            upper (ephemeral diff) layer. True for performance.
    """

    sandbox_id: str
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    base_dir: Path = Path()
    deps_dir: Path | None = None
    seed_dir: Path | None = None
    data_root: Path = Path("/var/lib/lunar-sandbox")
    grace_period_seconds: int = 5
    anomaly_threshold: int = 3
    use_tmpfs_upper: bool = True

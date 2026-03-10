# SPDX-License-Identifier: MIT
"""Unified sandbox lifecycle management.

Provides the ``Sandbox`` class -- the single entry point for creating,
executing in, resetting, and destroying sandboxes.  Wires together all
kernel primitives (namespaces, cgroups, seccomp, OverlayFS) into a
coherent lifecycle with health tracking and paranoia reset.

State machine::

    CREATED -> RUNNING -> STOPPED -> RESETTING -> RUNNING  (happy path)
                                  -> BROKEN                (reset failed)
    any     -> DESTROYED                                   (explicit destroy)
"""

from __future__ import annotations

import enum
import os
import signal
import subprocess
from pathlib import Path
from typing import Any

import structlog

from lunar_sandbox.filesystem.layers import LayerManager, SandboxLayers
from lunar_sandbox.kernel.cgroups import (
    assign_process_to_cgroup,
    create_sandbox_cgroup,
    destroy_sandbox_cgroup,
)
from lunar_sandbox.kernel.detect import require_kernel_features
from lunar_sandbox.kernel.namespaces import create_sandboxed_process
from lunar_sandbox.kernel.seccomp import (
    create_sandbox_seccomp_filter,
    load_seccomp_in_sandbox,
)
from lunar_sandbox.sandbox.config import SandboxConfig
from lunar_sandbox.sandbox.health import SandboxHealth
from lunar_sandbox.sandbox.reset import enforce_timeout, paranoia_reset

__all__ = [
    "Sandbox",
    "SandboxState",
]

log = structlog.get_logger(__name__)


class SandboxState(enum.Enum):
    """Lifecycle states for a sandbox instance."""

    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    RESETTING = "resetting"
    BROKEN = "broken"
    DESTROYED = "destroyed"


class Sandbox:
    """Unified sandbox lifecycle management.

    Creates a fully isolated Linux sandbox with OverlayFS filesystem,
    cgroups v2 resource limits, namespace isolation, and seccomp filtering.

    The lifecycle is:
        1. ``__init__``: configure (state = CREATED)
        2. ``create()``: set up kernel primitives (state = RUNNING)
        3. ``execute()``: run commands in the sandbox
        4. ``reset()``: paranoia reset for next episode (state = RUNNING or BROKEN)
        5. ``destroy()``: tear everything down (state = DESTROYED)

    A sandbox that fails reset is marked BROKEN and must be abandoned.
    Health tracking retires a sandbox after ``anomaly_threshold`` anomalies.
    """

    __slots__ = (
        "_config",
        "_state",
        "_health",
        "_layers",
        "_cgroup_path",
        "_pid",
        "_layer_manager",
        "_log",
    )

    def __init__(self, config: SandboxConfig) -> None:
        """Initialize a sandbox in the CREATED state.

        Does NOT create any kernel resources -- call :meth:`create` for that.

        Args:
            config: Sandbox configuration including resource limits,
                filesystem paths, and tuning parameters.
        """
        self._config = config
        self._state = SandboxState.CREATED
        self._health = SandboxHealth(
            sandbox_id=config.sandbox_id,
            anomaly_threshold=config.anomaly_threshold,
        )
        self._layers: SandboxLayers | None = None
        self._cgroup_path: Path | None = None
        self._pid: int | None = None
        self._layer_manager = LayerManager(data_root=config.data_root)
        self._log = structlog.get_logger(__name__).bind(
            sandbox_id=config.sandbox_id,
        )

        self._log.debug("sandbox_initialized", state=self._state.value)

    # -----------------------------------------------------------------
    # Public properties
    # -----------------------------------------------------------------

    @property
    def config(self) -> SandboxConfig:
        """Sandbox configuration (read-only)."""
        return self._config

    @property
    def state(self) -> SandboxState:
        """Current lifecycle state."""
        return self._state

    @property
    def health(self) -> SandboxHealth:
        """Health tracking for this sandbox."""
        return self._health

    @property
    def layers(self) -> SandboxLayers | None:
        """Filesystem layer configuration, or None if not yet created."""
        return self._layers

    @property
    def cgroup_path(self) -> Path | None:
        """Path to the sandbox's cgroup directory, or None."""
        return self._cgroup_path

    @property
    def pid(self) -> int | None:
        """PID of the sandbox's init process, or None."""
        return self._pid

    # -----------------------------------------------------------------
    # Lifecycle methods
    # -----------------------------------------------------------------

    def create(self) -> None:
        """Create the sandbox: kernel feature check, filesystem, cgroup, process.

        Transitions: CREATED -> RUNNING

        Steps:
            1. Verify all required kernel features (hard fail).
            2. Create sandbox directories via LayerManager.
            3. Mount the OverlayFS overlay.
            4. Create a cgroup with resource limits.
            5. Prepare seccomp filter.
            6. Fork a sandboxed init process with namespace isolation.
            7. Record mount in health tracker.

        Raises:
            KernelFeatureError: If required kernel features are missing.
            OSError: If any kernel operation fails.
            RuntimeError: If called in wrong state.
        """
        self._require_state(SandboxState.CREATED)

        self._log.info("sandbox_creating")

        # Step 1: Hard fail if kernel lacks required features
        require_kernel_features()

        # Step 2: Create sandbox directory structure
        self._layers = self._layer_manager.create_sandbox_dirs(
            sandbox_id=self._config.sandbox_id,
            base_dir=self._config.base_dir,
            deps_dir=self._config.deps_dir,
            seed_dir=self._config.seed_dir,
        )

        # Step 3: Mount OverlayFS
        self._layer_manager.mount_sandbox(
            self._layers,
            volatile=self._config.use_tmpfs_upper,
        )

        # Step 4: Create cgroup with resource limits
        self._cgroup_path = create_sandbox_cgroup(
            sandbox_id=self._config.sandbox_id,
            limits=self._config.resource_limits,
        )

        # Step 5: Prepare seccomp filter (may be None on platforms without libseccomp)
        seccomp_filter = create_sandbox_seccomp_filter()

        # Step 6: Fork sandboxed process with a setup_fn that assigns
        # cgroup and loads seccomp inside the child.
        cgroup_path = self._cgroup_path

        def _child_setup() -> None:
            """Run inside the sandboxed child: assign cgroup + load seccomp."""
            assign_process_to_cgroup(cgroup_path, os.getpid())
            load_seccomp_in_sandbox(seccomp_filter)

        rootfs = str(self._layers.merged_dir)
        self._pid = create_sandboxed_process(
            command=["/bin/sh"],
            rootfs=rootfs,
            setup_fn=_child_setup,
        )

        # Step 7: Track mount in health and transition state
        self._health.record_mount()
        self._state = SandboxState.RUNNING

        self._log.info(
            "sandbox_created",
            pid=self._pid,
            cgroup=str(self._cgroup_path),
            rootfs=rootfs,
        )

    def execute(
        self,
        command: list[str] | str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a command in the sandbox.

        Simplified for Phase 1 -- runs the command as a subprocess within
        the sandbox's merged root and applies timeout enforcement.
        Phase 2 will add a structured action API.

        Args:
            command: Command to execute (list or shell string).
            timeout: Maximum seconds to wait (None = no timeout).

        Returns:
            Dictionary with keys:
                - ``exit_code``: Process exit code (int or None if killed).
                - ``stdout``: Standard output (str).
                - ``stderr``: Standard error (str).
                - ``timed_out``: Whether the timeout was exceeded (bool).
                - ``timeout_action``: "completed", "timeout_graceful", or
                  "timeout_killed".

        Raises:
            RuntimeError: If sandbox is not in RUNNING or STOPPED state.
        """
        self._require_state(SandboxState.RUNNING, SandboxState.STOPPED)

        self._log.debug("sandbox_execute", command=command, timeout=timeout)

        # Build the command to run inside the sandbox rootfs
        if self._layers is None:
            raise RuntimeError("Sandbox layers not initialized")

        shell = isinstance(command, str)

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=shell,
                cwd=str(self._layers.merged_dir),
            )
            self._state = SandboxState.STOPPED
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timed_out": False,
                "timeout_action": "completed",
            }
        except subprocess.TimeoutExpired as exc:
            self._state = SandboxState.STOPPED
            return {
                "exit_code": None,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "timed_out": True,
                "timeout_action": "timeout_killed",
            }

    def reset(self) -> bool:
        """Full paranoia reset: kill, verify, unmount, remount, verify.

        Transitions: RUNNING/STOPPED -> RESETTING -> RUNNING (success)
                     RUNNING/STOPPED -> RESETTING -> BROKEN  (failure)

        On failure, the sandbox is marked BROKEN and the health tracker
        records a retirement. The sandbox MUST be abandoned.

        Returns:
            True if reset succeeded and sandbox is ready for next episode.
            False if reset failed and sandbox is now BROKEN.
        """
        self._require_state(SandboxState.RUNNING, SandboxState.STOPPED)

        self._log.info("sandbox_resetting")
        self._state = SandboxState.RESETTING

        if self._cgroup_path is None or self._layers is None:
            self._log.error("sandbox_reset_missing_resources")
            self._state = SandboxState.BROKEN
            self._health.retire("reset called with missing resources")
            return False

        # Execute the full paranoia reset sequence
        success = paranoia_reset(
            sandbox_id=self._config.sandbox_id,
            cgroup_path=self._cgroup_path,
            layers=self._layers,
            layer_manager=self._layer_manager,
        )

        # Record outcome in health tracker
        self._health.record_reset(success)

        if not success:
            self._state = SandboxState.BROKEN
            self._health.retire("paranoia reset failed")
            self._log.warning("sandbox_reset_failed_broken")
            return False

        # Check if health tracker thinks we should retire
        if self._health.should_retire():
            self._state = SandboxState.BROKEN
            self._log.warning(
                "sandbox_retired_by_health",
                anomaly_count=self._health.anomaly_count,
                threshold=self._health.anomaly_threshold,
            )
            return False

        self._state = SandboxState.RUNNING
        self._log.info("sandbox_reset_complete")
        return True

    def destroy(self) -> None:
        """Destroy the sandbox: kill process, remove cgroup, remove filesystem.

        Can be called from ANY state. After destroy, the sandbox is
        permanently in DESTROYED state.
        """
        self._log.info("sandbox_destroying", current_state=self._state.value)

        # Kill the sandbox init process if still alive
        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGKILL)
                self._log.debug("sandbox_destroy_killed_pid", pid=self._pid)
            except ProcessLookupError:
                pass  # Already dead
            except PermissionError:
                self._log.warning("sandbox_destroy_kill_permission_denied", pid=self._pid)
            self._pid = None

        # Destroy the cgroup
        if self._cgroup_path is not None:
            try:
                destroy_sandbox_cgroup(self._cgroup_path)
            except OSError as exc:
                self._log.warning(
                    "sandbox_destroy_cgroup_failed",
                    error=str(exc),
                )
            self._cgroup_path = None

        # Destroy the filesystem layers
        if self._layers is not None:
            try:
                self._layer_manager.destroy_sandbox(self._layers)
            except OSError as exc:
                self._log.warning(
                    "sandbox_destroy_layers_failed",
                    error=str(exc),
                )
            self._layers = None

        self._state = SandboxState.DESTROYED
        self._log.info("sandbox_destroyed")

    # -----------------------------------------------------------------
    # Query methods
    # -----------------------------------------------------------------

    def is_healthy(self) -> bool:
        """Check whether the sandbox is healthy and usable.

        A sandbox is unhealthy if:
        - It has been retired by the health tracker.
        - It is in BROKEN or DESTROYED state.

        Returns:
            True if the sandbox can still be used.
        """
        if self._state in (SandboxState.BROKEN, SandboxState.DESTROYED):
            return False
        return not self._health.should_retire()

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _require_state(self, *allowed: SandboxState) -> None:
        """Assert the sandbox is in one of the allowed states.

        Args:
            *allowed: Acceptable states.

        Raises:
            RuntimeError: If current state is not in *allowed*.
        """
        if self._state not in allowed:
            allowed_names = ", ".join(s.value for s in allowed)
            raise RuntimeError(
                f"Sandbox {self._config.sandbox_id} is in state "
                f"{self._state.value}, expected one of: {allowed_names}"
            )

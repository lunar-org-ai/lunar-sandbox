# SPDX-License-Identifier: MIT
"""4-layer directory structure management for OverlayFS sandbox stacks.

Manages the per-sandbox directory layout under ``/var/lib/lunar-sandbox/``
and orchestrates mount/unmount/reset operations through the OverlayFS module.

Layer stack (bottom to top):
1. base   -- readonly OS + runtime (e.g. Python 3.12 rootfs)
2. deps   -- readonly cached dependencies (optional, None if no deps)
3. seed   -- readonly task seed files (optional, None if no seed)
4. upper  -- writable ephemeral diff (discarded on reset)

OverlayFS lower dirs are ordered leftmost = highest priority, so the
lower list is built as: [seed, deps, base] (skipping None entries).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import structlog

from lunar_sandbox.kernel.overlayfs import (
    mount_overlay,
    reset_overlay,
    unmount_overlay,
)

__all__ = [
    "LayerManager",
    "SandboxLayers",
]

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SandboxLayers:
    """Describes the 4-layer directory structure for a single sandbox.

    Attributes:
        sandbox_id: Unique identifier for this sandbox instance.
        base_dir: Layer 1 -- readonly OS + runtime root filesystem.
        deps_dir: Layer 2 -- readonly cached dependencies (None if unused).
        seed_dir: Layer 3 -- readonly task seed files (None if unused).
        upper_dir: Layer 4 -- writable ephemeral diff directory.
        work_dir: OverlayFS internal workdir (same filesystem as upper_dir).
        merged_dir: Mount point where the merged overlay view appears.
    """

    sandbox_id: str
    base_dir: Path
    deps_dir: Path | None
    seed_dir: Path | None
    upper_dir: Path
    work_dir: Path
    merged_dir: Path


class LayerManager:
    """Manages per-sandbox directory structures and OverlayFS lifecycle.

    Creates, mounts, resets, and destroys sandbox filesystem stacks under
    a configurable data root (default: ``/var/lib/lunar-sandbox``).
    """

    def __init__(self, data_root: Path = Path("/var/lib/lunar-sandbox")) -> None:
        self._data_root = data_root
        log.debug("layer_manager_init", data_root=str(data_root))

    @property
    def data_root(self) -> Path:
        """Root directory for all sandbox data."""
        return self._data_root

    def create_sandbox_dirs(
        self,
        sandbox_id: str,
        base_dir: Path,
        deps_dir: Path | None = None,
        seed_dir: Path | None = None,
    ) -> SandboxLayers:
        """Create the per-sandbox directory structure.

        Creates ``upper/``, ``work/``, and ``merged/`` subdirectories under
        ``{data_root}/sandboxes/{sandbox_id}/``. The base, deps, and seed
        directories are expected to already exist (managed externally).

        Args:
            sandbox_id: Unique sandbox identifier.
            base_dir: Path to the readonly base layer.
            deps_dir: Path to the readonly deps layer (or None).
            seed_dir: Path to the readonly seed layer (or None).

        Returns:
            SandboxLayers describing the complete directory layout.
        """
        sandbox_root = self._data_root / "sandboxes" / sandbox_id
        upper_dir = sandbox_root / "upper"
        work_dir = sandbox_root / "work"
        merged_dir = sandbox_root / "merged"

        # Create directories (parents=True for first-time setup)
        upper_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        merged_dir.mkdir(parents=True, exist_ok=True)

        layers = SandboxLayers(
            sandbox_id=sandbox_id,
            base_dir=base_dir,
            deps_dir=deps_dir,
            seed_dir=seed_dir,
            upper_dir=upper_dir,
            work_dir=work_dir,
            merged_dir=merged_dir,
        )

        log.info(
            "sandbox_dirs_created",
            sandbox_id=sandbox_id,
            sandbox_root=str(sandbox_root),
            has_deps=deps_dir is not None,
            has_seed=seed_dir is not None,
        )

        return layers

    def mount_sandbox(self, layers: SandboxLayers, *, volatile: bool = True) -> None:
        """Mount the OverlayFS stack for a sandbox.

        Builds the lower_dirs list from the layers and calls mount_overlay.

        Args:
            layers: Sandbox layer configuration.
            volatile: Pass volatile option to OverlayFS (default True).

        Raises:
            OSError: If mount fails.
        """
        lower_dirs = self._build_lower_dirs(layers)

        log.info(
            "mount_sandbox",
            sandbox_id=layers.sandbox_id,
            lower_dirs=lower_dirs,
            volatile=volatile,
        )

        mount_overlay(
            lower_dirs=lower_dirs,
            upper_dir=str(layers.upper_dir),
            work_dir=str(layers.work_dir),
            merged_dir=str(layers.merged_dir),
            volatile=volatile,
        )

    def reset_sandbox(self, layers: SandboxLayers, *, volatile: bool = True) -> None:
        """Reset a sandbox by discarding ephemeral state and remounting.

        Delegates to reset_overlay which destroys and recreates the upper
        and work directories (never recycles by deleting contents).

        Args:
            layers: Sandbox layer configuration.
            volatile: Pass volatile option to OverlayFS (default True).

        Raises:
            OSError: If unmount or remount fails (caller should abandon sandbox).
        """
        lower_dirs = self._build_lower_dirs(layers)

        log.info("reset_sandbox", sandbox_id=layers.sandbox_id)

        reset_overlay(
            upper_dir=str(layers.upper_dir),
            work_dir=str(layers.work_dir),
            merged_dir=str(layers.merged_dir),
            lower_dirs=lower_dirs,
            volatile=volatile,
        )

    def destroy_sandbox(self, layers: SandboxLayers) -> None:
        """Unmount and completely remove a sandbox's directory tree.

        Attempts to unmount first (with lazy fallback), then removes the
        entire sandbox directory under ``{data_root}/sandboxes/{sandbox_id}/``.

        Args:
            layers: Sandbox layer configuration.
        """
        log.info("destroy_sandbox_start", sandbox_id=layers.sandbox_id)

        # Try to unmount; ignore errors (might already be unmounted)
        try:
            unmount_overlay(str(layers.merged_dir), force=True)
        except OSError:
            log.warning(
                "destroy_unmount_failed",
                sandbox_id=layers.sandbox_id,
                merged_dir=str(layers.merged_dir),
            )

        # Remove the entire sandbox directory tree
        sandbox_root = self._data_root / "sandboxes" / layers.sandbox_id
        if sandbox_root.exists():
            shutil.rmtree(sandbox_root)
            log.info(
                "sandbox_destroyed",
                sandbox_id=layers.sandbox_id,
                path=str(sandbox_root),
            )
        else:
            log.warning(
                "sandbox_dir_not_found",
                sandbox_id=layers.sandbox_id,
                path=str(sandbox_root),
            )

    def _build_lower_dirs(self, layers: SandboxLayers) -> list[str]:
        """Build the OverlayFS lower dirs list from layer configuration.

        Order matters: leftmost = highest priority in OverlayFS semantics.
        Result: [seed, deps, base] with None entries skipped.

        Args:
            layers: Sandbox layer configuration.

        Returns:
            Ordered list of lower directory paths as strings.
        """
        lower: list[str] = []

        # Seed is highest priority (leftmost)
        if layers.seed_dir is not None:
            lower.append(str(layers.seed_dir))

        # Deps is middle priority
        if layers.deps_dir is not None:
            lower.append(str(layers.deps_dir))

        # Base is always present (lowest priority, rightmost)
        lower.append(str(layers.base_dir))

        return lower

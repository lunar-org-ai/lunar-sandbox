"""Unit tests for layer directory management.

Tests the SandboxLayers dataclass, directory creation, lower-dir ordering,
and sandbox destruction. Uses tmp_path to avoid touching real filesystems.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from lunar_sandbox.filesystem.layers import LayerManager, SandboxLayers


class TestSandboxLayersDataclass:
    """Tests for the SandboxLayers frozen dataclass."""

    def test_sandbox_layers_dataclass(self) -> None:
        """SandboxLayers stores all layer paths and sandbox_id."""
        layers = SandboxLayers(
            sandbox_id="sb-001",
            base_dir=Path("/base"),
            deps_dir=Path("/deps"),
            seed_dir=Path("/seed"),
            upper_dir=Path("/upper"),
            work_dir=Path("/work"),
            merged_dir=Path("/merged"),
        )
        assert layers.sandbox_id == "sb-001"
        assert layers.base_dir == Path("/base")
        assert layers.deps_dir == Path("/deps")
        assert layers.seed_dir == Path("/seed")
        assert layers.upper_dir == Path("/upper")
        assert layers.work_dir == Path("/work")
        assert layers.merged_dir == Path("/merged")

    def test_sandbox_layers_frozen(self) -> None:
        """SandboxLayers is immutable (frozen=True)."""
        layers = SandboxLayers(
            sandbox_id="sb-001",
            base_dir=Path("/base"),
            deps_dir=None,
            seed_dir=None,
            upper_dir=Path("/upper"),
            work_dir=Path("/work"),
            merged_dir=Path("/merged"),
        )
        import dataclasses
        with __import__("pytest").raises(dataclasses.FrozenInstanceError):
            layers.sandbox_id = "changed"  # type: ignore[misc]

    def test_sandbox_layers_optional_dirs_none(self) -> None:
        """deps_dir and seed_dir can be None."""
        layers = SandboxLayers(
            sandbox_id="sb-001",
            base_dir=Path("/base"),
            deps_dir=None,
            seed_dir=None,
            upper_dir=Path("/upper"),
            work_dir=Path("/work"),
            merged_dir=Path("/merged"),
        )
        assert layers.deps_dir is None
        assert layers.seed_dir is None


class TestCreateSandboxDirs:
    """Tests for LayerManager.create_sandbox_dirs()."""

    def test_create_sandbox_dirs(self, data_root: Path, base_dir: Path) -> None:
        """create_sandbox_dirs creates upper/, work/, merged/ subdirectories."""
        mgr = LayerManager(data_root=data_root)
        layers = mgr.create_sandbox_dirs(
            sandbox_id="sb-001",
            base_dir=base_dir,
        )

        assert layers.upper_dir.exists()
        assert layers.work_dir.exists()
        assert layers.merged_dir.exists()
        assert layers.upper_dir.name == "upper"
        assert layers.work_dir.name == "work"
        assert layers.merged_dir.name == "merged"

    def test_create_sandbox_dirs_with_optional_layers(
        self, data_root: Path, base_dir: Path, tmp_path: Path
    ) -> None:
        """create_sandbox_dirs passes deps_dir and seed_dir through."""
        deps = tmp_path / "deps"
        deps.mkdir()
        seed = tmp_path / "seed"
        seed.mkdir()

        mgr = LayerManager(data_root=data_root)
        layers = mgr.create_sandbox_dirs(
            sandbox_id="sb-002",
            base_dir=base_dir,
            deps_dir=deps,
            seed_dir=seed,
        )

        assert layers.deps_dir == deps
        assert layers.seed_dir == seed


class TestBuildLowerDirs:
    """Tests for LayerManager._build_lower_dirs() ordering."""

    def _make_layers(
        self,
        base: str = "/base",
        deps: str | None = None,
        seed: str | None = None,
    ) -> SandboxLayers:
        """Helper to create a SandboxLayers with given paths."""
        return SandboxLayers(
            sandbox_id="sb-test",
            base_dir=Path(base),
            deps_dir=Path(deps) if deps else None,
            seed_dir=Path(seed) if seed else None,
            upper_dir=Path("/upper"),
            work_dir=Path("/work"),
            merged_dir=Path("/merged"),
        )

    def test_build_lower_dirs_all_layers(self) -> None:
        """With all layers: order is [seed, deps, base]."""
        mgr = LayerManager()
        layers = self._make_layers(
            base="/base", deps="/deps", seed="/seed"
        )
        lower = mgr._build_lower_dirs(layers)
        assert lower == ["/seed", "/deps", "/base"]

    def test_build_lower_dirs_no_deps(self) -> None:
        """Without deps: order is [seed, base]."""
        mgr = LayerManager()
        layers = self._make_layers(base="/base", seed="/seed")
        lower = mgr._build_lower_dirs(layers)
        assert lower == ["/seed", "/base"]

    def test_build_lower_dirs_base_only(self) -> None:
        """With base only: lower is [base]."""
        mgr = LayerManager()
        layers = self._make_layers(base="/base")
        lower = mgr._build_lower_dirs(layers)
        assert lower == ["/base"]

    def test_build_lower_dirs_no_seed(self) -> None:
        """Without seed: order is [deps, base]."""
        mgr = LayerManager()
        layers = self._make_layers(base="/base", deps="/deps")
        lower = mgr._build_lower_dirs(layers)
        assert lower == ["/deps", "/base"]


class TestDestroySandbox:
    """Tests for LayerManager.destroy_sandbox()."""

    def test_destroy_sandbox_removes_dirs(
        self, data_root: Path, base_dir: Path
    ) -> None:
        """destroy_sandbox removes the sandbox directory tree."""
        mgr = LayerManager(data_root=data_root)
        layers = mgr.create_sandbox_dirs(
            sandbox_id="sb-destroy",
            base_dir=base_dir,
        )

        # Confirm directories exist
        sandbox_root = data_root / "sandboxes" / "sb-destroy"
        assert sandbox_root.exists()

        # Mock unmount_overlay since we're not on Linux
        with patch("lunar_sandbox.filesystem.layers.unmount_overlay"):
            mgr.destroy_sandbox(layers)

        assert not sandbox_root.exists()

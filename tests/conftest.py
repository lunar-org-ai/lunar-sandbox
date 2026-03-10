"""Shared fixtures for lunar-sandbox test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from lunar_sandbox.sandbox.config import ResourceLimits, SandboxConfig


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """Provide a temporary data root directory for sandbox artifacts."""
    root = tmp_path / "lunar-sandbox"
    root.mkdir()
    return root


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    """Provide a temporary base layer directory."""
    d = tmp_path / "layers" / "base"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def sample_resource_limits() -> ResourceLimits:
    """Default ResourceLimits instance for testing."""
    return ResourceLimits()


@pytest.fixture
def sample_config(data_root: Path, base_dir: Path) -> SandboxConfig:
    """Provide a SandboxConfig wired to tmp_path directories."""
    return SandboxConfig(
        sandbox_id="test-sandbox-001",
        data_root=data_root,
        base_dir=base_dir,
    )

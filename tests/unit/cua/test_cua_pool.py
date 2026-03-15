"""Tests for CUA pool management and fingerprinting."""

import inspect
from unittest.mock import MagicMock

import pytest
from lunar_sandbox.cua.pool import CUAPool, CUAPoolConfig, cua_pool_fingerprint


class TestCUAPoolConfig:
    def test_defaults(self):
        cfg = CUAPoolConfig()
        assert cfg.pool_size == 2
        assert cfg.image == "lunar-cua:latest"
        assert cfg.data_root == "/var/lib/lunar-sandbox"

    def test_custom_values(self):
        cfg = CUAPoolConfig(pool_size=8, image="my-cua:v3")
        assert cfg.pool_size == 8
        assert cfg.image == "my-cua:v3"


class TestCUAPoolFingerprint:
    def test_has_cua_prefix(self):
        """CUA fingerprint starts with 'cua-' for visual distinction."""
        fp = cua_pool_fingerprint()
        assert fp.startswith("cua-")

    def test_deterministic(self):
        """Same image produces same fingerprint."""
        fp1 = cua_pool_fingerprint("lunar-cua:latest")
        fp2 = cua_pool_fingerprint("lunar-cua:latest")
        assert fp1 == fp2

    def test_different_images_different_fingerprints(self):
        """Different images produce different fingerprints."""
        fp1 = cua_pool_fingerprint("lunar-cua:latest")
        fp2 = cua_pool_fingerprint("custom-cua:v2")
        assert fp1 != fp2

    def test_distinct_from_coding_fingerprint(self):
        """CUA fingerprint format is distinct from coding fingerprints."""
        from lunar_sandbox.pool.fingerprint import pool_fingerprint
        coding_fp = pool_fingerprint("python3.12", ["numpy"])
        cua_fp = cua_pool_fingerprint()
        # Coding fingerprints are 16 hex chars; CUA has 'cua-' prefix
        assert not coding_fp.startswith("cua-")
        assert cua_fp.startswith("cua-")
        assert coding_fp != cua_fp


class TestCUAPool:
    def test_pool_creates_with_config(self):
        """CUAPool initialises with CUAPoolConfig."""
        cfg = CUAPoolConfig(pool_size=4)
        pool = CUAPool(cfg)
        assert pool.fingerprint.startswith("cua-")

    def test_pool_fingerprint_matches_config_image(self):
        """Pool fingerprint is derived from config image."""
        cfg1 = CUAPoolConfig(image="img-a:latest")
        cfg2 = CUAPoolConfig(image="img-b:latest")
        pool1 = CUAPool(cfg1)
        pool2 = CUAPool(cfg2)
        assert pool1.fingerprint != pool2.fingerprint


class TestCUASandboxReset:
    def test_reset_has_full_cleanup(self):
        """Verify CUASandbox.reset() includes full cleanup operations."""
        from lunar_sandbox.sandbox.cua_sandbox import CUASandbox

        source = inspect.getsource(CUASandbox.reset)
        # Must clear workspace
        assert "workspace" in source.lower() or "rm -rf" in source
        # Must verify windows
        assert "_verify_no_windows" in source
        # Must clear browser state
        assert "chromium" in source.lower()
        # Must check health
        assert "health_check" in source

    def test_verify_no_windows_method_exists(self):
        """_verify_no_windows has retry parameter."""
        from lunar_sandbox.sandbox.cua_sandbox import CUASandbox

        assert hasattr(CUASandbox, "_verify_no_windows")
        sig = inspect.signature(CUASandbox._verify_no_windows)
        assert "retry" in sig.parameters

    def test_verify_no_windows_retry_uses_windowkill(self):
        """Retry path uses windowkill (more aggressive than windowclose)."""
        from lunar_sandbox.sandbox.cua_sandbox import CUASandbox

        source = inspect.getsource(CUASandbox._verify_no_windows)
        assert "windowkill" in source

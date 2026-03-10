"""Unit tests for environment fingerprint computation.

Verifies determinism, order-independence, collision avoidance for
different inputs, and the task YAML override mechanism.
"""

from __future__ import annotations

from lunar_sandbox.filesystem.fingerprint import (
    compute_fingerprint,
    fingerprint_from_task_yaml,
)


class TestComputeFingerprint:
    """Tests for compute_fingerprint()."""

    def test_fingerprint_deterministic(self) -> None:
        """Same inputs always produce the same fingerprint."""
        fp1 = compute_fingerprint("python3.12", ["numpy", "pandas"])
        fp2 = compute_fingerprint("python3.12", ["numpy", "pandas"])
        assert fp1 == fp2

    def test_fingerprint_order_independent(self) -> None:
        """Dependency ordering does not affect the fingerprint."""
        fp1 = compute_fingerprint("python3.12", ["numpy", "pandas"])
        fp2 = compute_fingerprint("python3.12", ["pandas", "numpy"])
        assert fp1 == fp2

    def test_fingerprint_different_runtime(self) -> None:
        """Different runtimes produce different fingerprints."""
        fp_312 = compute_fingerprint("python3.12", ["numpy"])
        fp_311 = compute_fingerprint("python3.11", ["numpy"])
        assert fp_312 != fp_311

    def test_fingerprint_different_deps(self) -> None:
        """Different dependency lists produce different fingerprints."""
        fp_np = compute_fingerprint("python3.12", ["numpy"])
        fp_pd = compute_fingerprint("python3.12", ["pandas"])
        assert fp_np != fp_pd

    def test_fingerprint_length(self) -> None:
        """Fingerprint is exactly 16 hex characters."""
        fp = compute_fingerprint("python3.12", ["numpy", "pandas"])
        assert len(fp) == 16
        # Validate it's valid hex
        int(fp, 16)

    def test_fingerprint_empty_deps(self) -> None:
        """Fingerprint works with empty dependency list."""
        fp = compute_fingerprint("python3.12", [])
        assert len(fp) == 16

    def test_fingerprint_with_extras(self) -> None:
        """Extras are included in the fingerprint."""
        fp_no_extras = compute_fingerprint("python3.12", ["numpy"])
        fp_with_extras = compute_fingerprint(
            "python3.12", ["numpy"], extras={"cuda": "12.1"}
        )
        assert fp_no_extras != fp_with_extras

    def test_fingerprint_extras_order_independent(self) -> None:
        """Extras ordering does not affect the fingerprint."""
        fp1 = compute_fingerprint(
            "python3.12", [], extras={"cuda": "12.1", "arch": "x86_64"}
        )
        fp2 = compute_fingerprint(
            "python3.12", [], extras={"arch": "x86_64", "cuda": "12.1"}
        )
        assert fp1 == fp2


class TestFingerprintFromTaskYaml:
    """Tests for fingerprint_from_task_yaml()."""

    def test_fingerprint_from_task_yaml_override(self) -> None:
        """Explicit fingerprint in task config is returned directly."""
        config = {
            "runtime": "python3.12",
            "deps": ["numpy"],
            "fingerprint": "abcdef1234567890",
        }
        result = fingerprint_from_task_yaml(config)
        assert result == "abcdef1234567890"

    def test_fingerprint_from_task_yaml_auto(self) -> None:
        """Without override, fingerprint is auto-derived from runtime+deps."""
        config = {
            "runtime": "python3.12",
            "deps": ["numpy", "pandas"],
        }
        result = fingerprint_from_task_yaml(config)
        expected = compute_fingerprint("python3.12", ["numpy", "pandas"])
        assert result == expected

    def test_fingerprint_from_task_yaml_missing_fields(self) -> None:
        """Missing runtime/deps default to empty values."""
        config: dict = {}
        result = fingerprint_from_task_yaml(config)
        expected = compute_fingerprint("", [])
        assert result == expected

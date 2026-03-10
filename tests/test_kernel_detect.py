"""Unit tests for kernel feature detection.

Tests the KernelFeature dataclass structure, detection logic, and the
require_kernel_features gate. Uses mocks for /proc and /sys reads so
tests run on macOS and Linux without root.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lunar_sandbox.kernel.detect import (
    KernelFeature,
    detect_kernel_features,
    require_kernel_features,
)
from lunar_sandbox.sandbox.errors import KernelFeatureError


class TestKernelFeatureDataclass:
    """Tests for the KernelFeature dataclass."""

    def test_kernel_feature_has_fields(self) -> None:
        """KernelFeature exposes name, available, detail, fix_hint."""
        feat = KernelFeature(
            name="test_feat",
            available=True,
            detail="some detail",
            fix_hint="try this",
        )
        assert feat.name == "test_feat"
        assert feat.available is True
        assert feat.detail == "some detail"
        assert feat.fix_hint == "try this"

    def test_kernel_feature_unavailable(self) -> None:
        """KernelFeature can represent an unavailable feature."""
        feat = KernelFeature(
            name="missing",
            available=False,
            detail="not found",
            fix_hint="install it",
        )
        assert feat.available is False


class TestDetectKernelFeatures:
    """Tests for detect_kernel_features() function."""

    def test_detect_returns_five_features(self) -> None:
        """detect_kernel_features always returns exactly 5 KernelFeature objects."""
        features = detect_kernel_features()
        assert len(features) == 5
        for feat in features:
            assert isinstance(feat, KernelFeature)

    def test_all_features_have_names(self) -> None:
        """Every feature has a non-empty name string."""
        features = detect_kernel_features()
        for feat in features:
            assert feat.name, f"Feature has empty name: {feat}"
            assert isinstance(feat.name, str)

    def test_all_features_have_fix_hints(self) -> None:
        """Every unavailable feature has a non-empty fix_hint."""
        features = detect_kernel_features()
        for feat in features:
            if not feat.available:
                assert feat.fix_hint, (
                    f"Unavailable feature '{feat.name}' has empty fix_hint"
                )

    def test_feature_names_are_unique(self) -> None:
        """All feature names are distinct."""
        features = detect_kernel_features()
        names = [f.name for f in features]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"

    def test_expected_feature_names(self) -> None:
        """Detection checks the five expected kernel features."""
        features = detect_kernel_features()
        names = {f.name for f in features}
        expected = {
            "kernel_version",
            "cgroups_v2",
            "overlayfs",
            "seccomp",
            "user_namespaces",
        }
        assert names == expected


class TestRequireKernelFeatures:
    """Tests for require_kernel_features() using mocks."""

    def test_require_raises_on_missing(self) -> None:
        """require_kernel_features raises KernelFeatureError when features are missing."""
        fake_features = [
            KernelFeature("kernel_version", True, "5.15", ""),
            KernelFeature("cgroups_v2", False, "not found", "enable cgroups v2"),
            KernelFeature("overlayfs", True, "found", ""),
            KernelFeature("seccomp", False, "not found", "enable seccomp"),
            KernelFeature("user_namespaces", True, "ok", ""),
        ]
        with patch(
            "lunar_sandbox.kernel.detect.detect_kernel_features",
            return_value=fake_features,
        ):
            with pytest.raises(KernelFeatureError) as exc_info:
                require_kernel_features()
            assert "Missing 2 required kernel feature(s)" in str(exc_info.value)
            assert exc_info.value.feature_name == "multiple"

    def test_require_raises_single_missing(self) -> None:
        """Single missing feature uses its name, not 'multiple'."""
        fake_features = [
            KernelFeature("kernel_version", True, "5.15", ""),
            KernelFeature("cgroups_v2", False, "not found", "enable it"),
            KernelFeature("overlayfs", True, "found", ""),
            KernelFeature("seccomp", True, "found", ""),
            KernelFeature("user_namespaces", True, "ok", ""),
        ]
        with patch(
            "lunar_sandbox.kernel.detect.detect_kernel_features",
            return_value=fake_features,
        ):
            with pytest.raises(KernelFeatureError) as exc_info:
                require_kernel_features()
            assert exc_info.value.feature_name == "cgroups_v2"

    def test_require_passes_all_available(self) -> None:
        """require_kernel_features does not raise when all features are available."""
        fake_features = [
            KernelFeature("kernel_version", True, "5.15", ""),
            KernelFeature("cgroups_v2", True, "ok", ""),
            KernelFeature("overlayfs", True, "found", ""),
            KernelFeature("seccomp", True, "found", ""),
            KernelFeature("user_namespaces", True, "ok", ""),
        ]
        with patch(
            "lunar_sandbox.kernel.detect.detect_kernel_features",
            return_value=fake_features,
        ):
            # Should not raise
            require_kernel_features()

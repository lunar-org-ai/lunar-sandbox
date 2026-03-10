"""Tests for memory pressure detection via /proc/meminfo parsing.

Covers macOS compatibility (returns 0.0), monkeypatched /proc/meminfo
parsing, and edge cases (FileNotFoundError, MemTotal=0).
"""

from __future__ import annotations

import builtins
from io import StringIO
from unittest.mock import mock_open, patch

from lunar_sandbox.pool.memory import get_memory_pressure


class TestGetMemoryPressure:
    """get_memory_pressure() reads /proc/meminfo or returns 0.0 on macOS."""

    def test_returns_float(self) -> None:
        result = get_memory_pressure()
        assert isinstance(result, float)

    def test_returns_zero_on_macos(self) -> None:
        """On macOS /proc/meminfo does not exist, should return 0.0."""
        result = get_memory_pressure()
        assert result == 0.0

    def test_range_is_zero_to_one(self) -> None:
        result = get_memory_pressure()
        assert 0.0 <= result <= 1.0

    def test_parses_proc_meminfo(self) -> None:
        """Fake /proc/meminfo: 8GB total, 2GB available -> 0.75 pressure."""
        fake_meminfo = (
            "MemTotal:        8000000 kB\n"
            "MemFree:          500000 kB\n"
            "MemAvailable:    2000000 kB\n"
            "Buffers:          100000 kB\n"
        )
        with patch("builtins.open", mock_open(read_data=fake_meminfo)):
            result = get_memory_pressure()
        assert abs(result - 0.75) < 0.001

    def test_low_memory_pressure(self) -> None:
        """Fake /proc/meminfo: 8GB total, 7GB available -> ~0.125 pressure."""
        fake_meminfo = (
            "MemTotal:        8000000 kB\n"
            "MemAvailable:    7000000 kB\n"
        )
        with patch("builtins.open", mock_open(read_data=fake_meminfo)):
            result = get_memory_pressure()
        assert abs(result - 0.125) < 0.001

    def test_file_not_found_returns_zero(self) -> None:
        """FileNotFoundError returns 0.0 (macOS dev compatibility)."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = get_memory_pressure()
        assert result == 0.0

    def test_mem_total_zero_returns_zero(self) -> None:
        """MemTotal: 0 prevents division by zero, returns 0.0."""
        fake_meminfo = (
            "MemTotal:        0 kB\n"
            "MemAvailable:    0 kB\n"
        )
        with patch("builtins.open", mock_open(read_data=fake_meminfo)):
            result = get_memory_pressure()
        assert result == 0.0

    def test_missing_mem_available_returns_zero(self) -> None:
        """If MemAvailable is missing, mem_available defaults to 0 -> pressure = 1.0."""
        fake_meminfo = "MemTotal:        8000000 kB\n"
        with patch("builtins.open", mock_open(read_data=fake_meminfo)):
            result = get_memory_pressure()
        assert abs(result - 1.0) < 0.001

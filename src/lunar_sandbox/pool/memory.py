"""System memory pressure detection via /proc/meminfo.

Provides a single function to read current memory usage as a ratio.
Used by the pool evictor to trigger soft eviction when the system
is under memory pressure.

On non-Linux systems (macOS), returns 0.0 since /proc/meminfo does
not exist. This allows development on macOS without code changes.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

_PROC_MEMINFO = "/proc/meminfo"


def get_memory_pressure() -> float:
    """Read system memory pressure as a ratio from 0.0 to 1.0.

    Reads ``/proc/meminfo`` in a single ``f.read()`` call for an
    atomic snapshot. Parses ``MemTotal`` and ``MemAvailable`` fields
    to compute usage ratio.

    Returns:
        Memory usage ratio where 0.0 = all free and 1.0 = all used.
        Returns 0.0 on non-Linux systems (FileNotFoundError) or if
        MemTotal is zero.
    """
    try:
        with open(_PROC_MEMINFO) as f:
            content = f.read()
    except FileNotFoundError:
        return 0.0

    mem_total = 0
    mem_available = 0

    for line in content.splitlines():
        if line.startswith("MemTotal:"):
            mem_total = _parse_kb_value(line)
        elif line.startswith("MemAvailable:"):
            mem_available = _parse_kb_value(line)

    if mem_total == 0:
        return 0.0

    pressure = 1.0 - (mem_available / mem_total)

    if pressure > 0.7:
        logger.debug(
            "memory_pressure_elevated",
            pressure=round(pressure, 3),
            mem_total_kb=mem_total,
            mem_available_kb=mem_available,
        )

    return pressure


def _parse_kb_value(line: str) -> int:
    """Parse a kB value from a /proc/meminfo line.

    Expected format: ``FieldName:    12345 kB``

    Args:
        line: A single line from /proc/meminfo.

    Returns:
        Integer value in kB, or 0 if parsing fails.
    """
    parts = line.split()
    if len(parts) >= 2:
        try:
            return int(parts[1])
        except ValueError:
            return 0
    return 0

"""SHA-256 environment fingerprint computation.

Fingerprints identify sandbox environments for pool allocation.
They are deterministic: same inputs always produce the same hash,
regardless of input ordering.

Design: Tiered fingerprint approach. Base fingerprint (runtime + major deps)
for pool allocation. Task-specific deps injected as additional layer.
"""

from __future__ import annotations

import hashlib


def compute_fingerprint(
    runtime: str,
    deps: list[str],
    extras: dict[str, str] | None = None,
) -> str:
    """Compute a deterministic SHA-256 fingerprint for an environment.

    The fingerprint is order-independent: deps and extras are sorted
    before hashing. Truncated to 16 hex chars for readability --
    collisions are negligible per SHA-256 properties.

    Args:
        runtime: Runtime identifier (e.g., 'python3.12').
        deps: List of dependency specifiers (e.g., ['numpy>=1.24', 'pandas']).
        extras: Optional additional key-value pairs to include in the hash
            (e.g., {'cuda': '12.1', 'arch': 'x86_64'}).

    Returns:
        16-character hex string (first 64 bits of SHA-256 digest).
    """
    parts = [runtime]
    parts.extend(sorted(deps))

    if extras:
        for key in sorted(extras):
            parts.append(f"{key}={extras[key]}")

    canonical = "\n".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def fingerprint_from_task_yaml(task_config: dict) -> str:
    """Compute fingerprint from a task configuration dictionary.

    Supports user override: if ``task_config["fingerprint"]`` exists,
    it is returned directly without computation.

    Otherwise, extracts ``runtime`` and ``deps`` from the config and
    calls :func:`compute_fingerprint`.

    Args:
        task_config: Task configuration dictionary. Expected keys:
            - ``runtime`` (str): Runtime identifier.
            - ``deps`` (list[str]): Dependency list.
            - ``extras`` (dict[str, str], optional): Additional hash inputs.
            - ``fingerprint`` (str, optional): Explicit override.

    Returns:
        16-character hex fingerprint string.
    """
    # User override takes precedence
    override = task_config.get("fingerprint")
    if override is not None:
        return str(override)

    runtime = task_config.get("runtime", "")
    deps = task_config.get("deps", [])
    extras = task_config.get("extras")

    return compute_fingerprint(runtime, deps, extras)

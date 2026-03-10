"""Pool fingerprint builder composing all 5 required components.

Builds a deterministic fingerprint for pool keying by combining:
1. Runtime identifier (e.g., 'python3.12')
2. Dependencies hash (sorted list of dep specifiers)
3. Repository base (project/repo identifier)
4. Toolchain (e.g., 'poetry', 'pip', 'conda')
5. Resource class (e.g., 'default', 'gpu', 'high-memory')

Delegates to compute_fingerprint() from the filesystem package,
passing components 3-5 via the extras dict parameter.
"""

from __future__ import annotations

from lunar_sandbox.filesystem.fingerprint import compute_fingerprint


def pool_fingerprint(
    runtime: str,
    deps: list[str],
    repo_base: str = "",
    toolchain: str = "",
    resource_class: str = "",
) -> str:
    """Compute a pool-keying fingerprint with all 5 components.

    All 5 components contribute to the fingerprint when non-empty.
    Empty components are omitted from the hash inputs, so
    ``pool_fingerprint('py3.12', ['numpy'])`` produces the same
    result as ``compute_fingerprint('py3.12', ['numpy'])``.

    Args:
        runtime: Runtime identifier (e.g., 'python3.12').
        deps: List of dependency specifiers.
        repo_base: Repository or project base identifier.
        toolchain: Build toolchain identifier (e.g., 'poetry').
        resource_class: Resource class for sandbox sizing.

    Returns:
        16-character hex string fingerprint.
    """
    extras: dict[str, str] = {}

    if repo_base:
        extras["repo_base"] = repo_base
    if toolchain:
        extras["toolchain"] = toolchain
    if resource_class:
        extras["resource_class"] = resource_class

    return compute_fingerprint(
        runtime, deps, extras=extras if extras else None
    )

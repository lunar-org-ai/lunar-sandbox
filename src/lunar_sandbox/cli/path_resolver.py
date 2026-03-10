"""YAML task file search path resolution.

Resolves YAML paths by searching: literal path first, then CWD,
``~/.lunar/tasks/``, and each directory in ``LUNAR_TASKS_PATH``
(colon-separated on Unix).
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog

__all__ = ["resolve_yaml_path"]

log = structlog.get_logger(__name__)


def resolve_yaml_path(name: str) -> Path:
    """Resolve a task YAML file by name or path.

    Resolution order:

    1. Literal path (absolute or relative). If it exists, return it.
    2. If no extension, try appending ``.yaml`` and ``.yml``.
    3. Search directories: CWD, ``~/.lunar/tasks/``, then each
       directory in the ``LUNAR_TASKS_PATH`` environment variable
       (colon-separated on Unix).

    Args:
        name: File path or bare name to resolve.

    Returns:
        Resolved :class:`Path` to the YAML file.

    Raises:
        FileNotFoundError: If the file cannot be found in any
            search location. The error message lists all paths
            that were searched.
    """
    # 1. Try literal path
    literal = Path(name)
    if literal.is_absolute() and literal.exists():
        log.debug("yaml_resolved", path=str(literal), source="absolute")
        return literal.resolve()

    if literal.exists():
        log.debug("yaml_resolved", path=str(literal), source="relative")
        return literal.resolve()

    # 2. Build candidate names (with extensions if missing)
    candidates = [name]
    if not _has_yaml_extension(name):
        candidates.append(f"{name}.yaml")
        candidates.append(f"{name}.yml")

    # 3. Build search dirs (computed at call time so CWD is fresh)
    search_dirs = _build_search_dirs()

    for search_dir in search_dirs:
        for candidate in candidates:
            path = search_dir / candidate
            if path.exists():
                log.debug(
                    "yaml_resolved",
                    path=str(path),
                    source=str(search_dir),
                )
                return path.resolve()

    # Not found -- build helpful error message
    searched = [str(d) for d in search_dirs]
    msg = (
        f"Task file not found: {name!r}\n"
        f"Searched in: {', '.join(searched)}\n"
        f"Candidates tried: {', '.join(candidates)}"
    )
    raise FileNotFoundError(msg)


def _build_search_dirs() -> list[Path]:
    """Build the ordered list of directories to search.

    Returns:
        List of :class:`Path` objects: CWD, ``~/.lunar/tasks/``,
        then each entry in ``LUNAR_TASKS_PATH``.
    """
    dirs: list[Path] = []

    # CWD
    dirs.append(Path.cwd())

    # ~/.lunar/tasks/
    lunar_home = Path.home() / ".lunar" / "tasks"
    dirs.append(lunar_home)

    # LUNAR_TASKS_PATH (colon-separated)
    env_path = os.environ.get("LUNAR_TASKS_PATH", "")
    if env_path:
        for entry in env_path.split(":"):
            entry = entry.strip()
            if entry:
                dirs.append(Path(entry))

    return dirs


def _has_yaml_extension(name: str) -> bool:
    """Check if a filename already has a YAML extension."""
    lower = name.lower()
    return lower.endswith(".yaml") or lower.endswith(".yml")

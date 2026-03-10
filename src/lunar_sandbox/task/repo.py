"""Repo source resolution -- clone or copy into a seed layer directory.

Given a :class:`~lunar_sandbox.task.schema.RepoSource`, this module
materialises the source code into a target directory that will become
the seed (lower) layer of the OverlayFS stack.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import structlog

from lunar_sandbox.sandbox.errors import InfraError
from lunar_sandbox.task.schema import RepoSource

__all__ = [
    "setup_repo_source",
]

log = structlog.get_logger(__name__)


def setup_repo_source(
    repo: RepoSource,
    target_dir: Path,
    timeout: float = 120.0,
) -> None:
    """Materialise a repo source into *target_dir*.

    For git URLs the repository is cloned (shallow by default).
    For local paths the directory tree is copied via :func:`shutil.copytree`.

    Args:
        repo: Repository source specification.
        target_dir: Destination directory (will be created by clone/copy).
        timeout: Maximum seconds for git operations.

    Raises:
        InfraError: On clone failure, timeout, or missing ``git`` binary.
        ValueError: If *repo* has neither ``url`` nor ``path`` set.
    """
    if repo.url:
        log.info("cloning_repo", url=repo.url, ref=repo.ref, depth=repo.depth)
        _clone_repo(
            url=repo.url,
            target_dir=target_dir,
            ref=repo.ref,
            depth=repo.depth,
            timeout=timeout,
        )
        log.info("clone_complete", target=str(target_dir))
    elif repo.path:
        src = Path(repo.path)
        log.info("copying_local_repo", source=str(src))
        shutil.copytree(src, target_dir, dirs_exist_ok=True)
        log.info("copy_complete", target=str(target_dir))
    else:
        msg = "RepoSource has neither 'url' nor 'path' set"
        raise ValueError(msg)


def _clone_repo(
    url: str,
    target_dir: Path,
    ref: str | None,
    depth: int,
    timeout: float,
) -> None:
    """Clone a git repository into *target_dir*.

    Handles shallow clones, branch/tag refs, and full-SHA checkouts.
    Always applies a subprocess timeout to prevent hangs.
    """
    cmd: list[str] = ["git", "clone"]

    if depth > 0:
        cmd.extend(["--depth", str(depth)])

    # Branch/tag refs can be passed to --branch; full SHAs cannot.
    is_full_sha = ref is not None and len(ref) >= 40
    if ref and not is_full_sha:
        cmd.extend(["--branch", ref])

    cmd.extend([url, str(target_dir)])

    try:
        subprocess.run(  # noqa: S603
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise InfraError("git is not installed") from None
    except subprocess.TimeoutExpired:
        raise InfraError(f"git clone timed out after {timeout}s") from None
    except subprocess.CalledProcessError as exc:
        raise InfraError(f"git clone failed: {exc.stderr}") from exc

    # For full-SHA refs we need a separate checkout after clone.
    if is_full_sha:
        checkout_cmd = ["git", "-C", str(target_dir), "checkout", ref]
        try:
            subprocess.run(  # noqa: S603
                checkout_cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=30.0,
            )
        except FileNotFoundError:
            raise InfraError("git is not installed") from None
        except subprocess.TimeoutExpired:
            raise InfraError("git checkout timed out after 30s") from None
        except subprocess.CalledProcessError as exc:
            raise InfraError(f"git checkout failed: {exc.stderr}") from exc

"""JSONL streaming writer for trajectory steps.

Writes one JSON line per trajectory step with immediate flush for
crash safety. Each complete line in the output file is independently
parseable JSON, so partial files from crashed episodes remain readable.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from types import TracebackType

from lunar_sandbox.trajectory.models import TrajectoryStep

__all__ = [
    "TrajectoryWriter",
]

logger = structlog.get_logger(__name__)


class TrajectoryWriter:
    """Append-only JSONL writer for trajectory steps.

    Each call to write_step() serialises a TrajectoryStep as a single
    JSON line followed by a flush.  No fsync is issued (user decision);
    the OS page cache handles durability.

    Usage::

        with TrajectoryWriter(directory, episode_id) as w:
            w.write_step(step)

    Args:
        directory: Directory where JSONL files are stored.
        episode_id: Episode identifier used as the file stem.
    """

    def __init__(self, directory: Path, episode_id: str) -> None:
        self._directory = directory
        self._episode_id = episode_id
        self._path = directory / f"{episode_id}.jsonl"
        self._file: io.TextIOWrapper | None = None

    # -- lifecycle -----------------------------------------------------------

    def open(self) -> None:
        """Open the JSONL file for appending.

        Creates the parent directory tree if it does not exist.
        """
        self._directory.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "a", encoding="utf-8")  # noqa: SIM115
        logger.debug(
            "trajectory_writer_opened",
            path=str(self._path),
            episode_id=self._episode_id,
        )

    def close(self) -> None:
        """Close the JSONL file if open."""
        if self._file is not None:
            self._file.close()
            self._file = None
            logger.debug(
                "trajectory_writer_closed",
                path=str(self._path),
                episode_id=self._episode_id,
            )

    # -- writing -------------------------------------------------------------

    def write_step(self, step: TrajectoryStep) -> None:
        """Append a single trajectory step as one JSON line.

        Flushes the file buffer after writing so that a crash leaves
        every previously-written line intact and parseable.

        Args:
            step: The trajectory step to write.

        Raises:
            RuntimeError: If the writer has not been opened.
        """
        if self._file is None:
            msg = "TrajectoryWriter is not open; call open() or use as context manager"
            raise RuntimeError(msg)
        self._file.write(step.model_dump_json() + "\n")
        self._file.flush()

    # -- properties ----------------------------------------------------------

    @property
    def path(self) -> Path:
        """Return the JSONL file path."""
        return self._path

    @property
    def is_open(self) -> bool:
        """Return whether the file is currently open."""
        return self._file is not None

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> TrajectoryWriter:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

"""SQLite trajectory store for queryable episode persistence.

Cold-path persistence layer: after episodes complete, their trajectories
move from JSONL into SQLite for rich querying by episode, task, score,
action type, and time window.  WAL mode is used for concurrent read access
while a single writer ingests data.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from types import TracebackType

__all__ = [
    "TrajectoryStore",
]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_EPISODES = """\
CREATE TABLE IF NOT EXISTS episodes (
    episode_id   TEXT PRIMARY KEY,
    task_name    TEXT NOT NULL,
    outcome      TEXT NOT NULL,
    score        REAL,
    step_count   INTEGER NOT NULL DEFAULT 0,
    duration_ms  REAL NOT NULL DEFAULT 0.0,
    started_at   REAL NOT NULL,
    ended_at     REAL,
    is_complete  INTEGER NOT NULL DEFAULT 1,
    sandbox_id   TEXT DEFAULT '',
    created_at   REAL NOT NULL
);
"""

_CREATE_STEPS = """\
CREATE TABLE IF NOT EXISTS steps (
    episode_id    TEXT NOT NULL,
    step_idx      INTEGER NOT NULL,
    timestamp     REAL NOT NULL,
    action        TEXT NOT NULL,
    action_params TEXT NOT NULL,
    observation   TEXT NOT NULL,
    reward        REAL NOT NULL DEFAULT 0.0,
    duration_ms   REAL NOT NULL DEFAULT 0.0,
    cpu_time_ms   REAL NOT NULL DEFAULT 0.0,
    file_diff     TEXT,
    token_usage   INTEGER,
    cost_usd      REAL,
    source        TEXT NOT NULL DEFAULT 'api',
    state_cwd     TEXT DEFAULT '',
    state_json    TEXT DEFAULT '{}',
    PRIMARY KEY (episode_id, step_idx),
    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_episodes_task ON episodes(task_name);",
    "CREATE INDEX IF NOT EXISTS idx_episodes_score ON episodes(score);",
    "CREATE INDEX IF NOT EXISTS idx_episodes_started ON episodes(started_at);",
    "CREATE INDEX IF NOT EXISTS idx_steps_action ON steps(action);",
    "CREATE INDEX IF NOT EXISTS idx_steps_episode ON steps(episode_id);",
    "CREATE INDEX IF NOT EXISTS idx_steps_timestamp ON steps(timestamp);",
]


class TrajectoryStore:
    """SQLite-backed trajectory store with WAL mode.

    Provides schema creation, batch episode ingestion, and query methods
    covering four access patterns: by episode/task, by score range, by
    action type, and by time window.

    Usage::

        with TrajectoryStore(db_path) as store:
            store.ingest_episode(meta, steps)
            results = store.query_episodes(task_name="my-task")

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle -----------------------------------------------------------

    def open(self) -> None:
        """Open the database and ensure schema exists.

        Enables WAL journal mode and ``PRAGMA synchronous=NORMAL`` for
        safe concurrent reads with good write performance.
        """
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        self._conn = conn
        self._ensure_schema()
        logger.debug(
            "trajectory_store_opened",
            db_path=str(self._db_path),
        )

    def close(self) -> None:
        """Close the database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug(
                "trajectory_store_closed",
                db_path=str(self._db_path),
            )

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> TrajectoryStore:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- schema --------------------------------------------------------------

    def _ensure_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        assert self._conn is not None  # noqa: S101
        self._conn.execute(_CREATE_EPISODES)
        self._conn.execute(_CREATE_STEPS)
        for idx_sql in _INDEXES:
            self._conn.execute(idx_sql)

    # -- ingestion -----------------------------------------------------------

    def ingest_episode(
        self,
        episode_metadata: dict[str, Any],
        steps: list[dict[str, Any]],
    ) -> int:
        """Ingest a complete episode with its steps in a single transaction.

        Args:
            episode_metadata: Episode-level data matching the ``episodes``
                table columns (episode_id, task_name, outcome, score, etc.).
            steps: List of step dicts (matching ``TrajectoryStep.model_dump()``
                output).

        Returns:
            Number of steps ingested.
        """
        assert self._conn is not None  # noqa: S101
        import time as _time

        created_at = episode_metadata.get("created_at", _time.time())

        with self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO episodes
                   (episode_id, task_name, outcome, score, step_count,
                    duration_ms, started_at, ended_at, is_complete,
                    sandbox_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode_metadata["episode_id"],
                    episode_metadata["task_name"],
                    episode_metadata["outcome"],
                    episode_metadata.get("score"),
                    episode_metadata.get("step_count", len(steps)),
                    episode_metadata.get("duration_ms", 0.0),
                    episode_metadata["started_at"],
                    episode_metadata.get("ended_at"),
                    int(episode_metadata.get("is_complete", True)),
                    episode_metadata.get("sandbox_id", ""),
                    created_at,
                ),
            )

            step_rows = []
            for s in steps:
                # Extract state fields -- may be nested dict or flat
                state = s.get("state", {})
                if isinstance(state, dict):
                    state_cwd = state.get("cwd", "")
                    state_json = json.dumps(state)
                else:
                    state_cwd = ""
                    state_json = "{}"

                step_rows.append(
                    (
                        s["episode_id"],
                        s["step_idx"],
                        s["timestamp"],
                        s["action"],
                        json.dumps(s.get("action_params", {})),
                        json.dumps(s.get("observation", {})),
                        s.get("reward", 0.0),
                        s.get("duration_ms", 0.0),
                        s.get("cpu_time_ms", 0.0),
                        json.dumps(s.get("file_diff")) if s.get("file_diff") else None,
                        s.get("token_usage"),
                        s.get("cost_usd"),
                        s.get("source", "api"),
                        state_cwd,
                        state_json,
                    )
                )

            if step_rows:
                self._conn.executemany(
                    """INSERT OR REPLACE INTO steps
                       (episode_id, step_idx, timestamp, action, action_params,
                        observation, reward, duration_ms, cpu_time_ms, file_diff,
                        token_usage, cost_usd, source, state_cwd, state_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    step_rows,
                )

        logger.info(
            "episode_ingested",
            episode_id=episode_metadata["episode_id"],
            step_count=len(step_rows),
        )
        return len(step_rows)

    def ingest_from_jsonl(
        self,
        jsonl_path: Path,
        episode_metadata: dict[str, Any],
    ) -> int:
        """Ingest steps from a JSONL file into the store.

        Each line is independently parsed; corrupt lines (from crashed
        episodes) are skipped with a warning.

        Args:
            jsonl_path: Path to the JSONL file containing step records.
            episode_metadata: Episode-level data for the ``episodes`` table.

        Returns:
            Number of steps successfully ingested.
        """
        steps: list[dict[str, Any]] = []
        with open(jsonl_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    steps.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    logger.warning(
                        "jsonl_corrupt_line_skipped",
                        path=str(jsonl_path),
                        line_number=line_num,
                        episode_id=episode_metadata.get("episode_id"),
                    )
        return self.ingest_episode(episode_metadata, steps)

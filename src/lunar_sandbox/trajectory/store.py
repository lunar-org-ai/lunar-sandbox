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

    # -- queries -------------------------------------------------------------

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a sqlite3.Row to a plain dict."""
        return dict(row)

    def query_episodes(
        self,
        *,
        task_name: str | None = None,
        episode_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query episodes by task name and/or episode ID.

        Args:
            task_name: Filter to episodes for this task.
            episode_id: Filter to a specific episode.

        Returns:
            List of episode dicts matching filters.
        """
        assert self._conn is not None  # noqa: S101
        clauses: list[str] = []
        params: list[Any] = []
        if task_name is not None:
            clauses.append("task_name = ?")
            params.append(task_name)
        if episode_id is not None:
            clauses.append("episode_id = ?")
            params.append(episode_id)
        where = " AND ".join(clauses)
        sql = "SELECT * FROM episodes"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY started_at DESC"
        return [self._row_to_dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def query_episodes_by_score(
        self,
        *,
        min_score: float | None = None,
        max_score: float | None = None,
        task_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query episodes filtered by score range.

        Args:
            min_score: Minimum score (inclusive).
            max_score: Maximum score (inclusive).
            task_name: Optionally restrict to a specific task.

        Returns:
            List of episode dicts within the score range.
        """
        assert self._conn is not None  # noqa: S101
        clauses: list[str] = []
        params: list[Any] = []
        if min_score is not None:
            clauses.append("score >= ?")
            params.append(min_score)
        if max_score is not None:
            clauses.append("score <= ?")
            params.append(max_score)
        if task_name is not None:
            clauses.append("task_name = ?")
            params.append(task_name)
        where = " AND ".join(clauses)
        sql = "SELECT * FROM episodes"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY score DESC"
        return [self._row_to_dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def query_steps_by_action(
        self,
        action: str,
        *,
        episode_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query steps by action type, optionally scoped to specific episodes.

        JSON columns (action_params, observation, file_diff, state_json)
        are deserialized back to dicts.

        Args:
            action: Action type string to match.
            episode_ids: Optional list of episode IDs to scope the search.

        Returns:
            List of step dicts matching the action type.
        """
        assert self._conn is not None  # noqa: S101
        clauses: list[str] = ["action = ?"]
        params: list[Any] = [action]
        if episode_ids:
            placeholders = ", ".join("?" for _ in episode_ids)
            clauses.append(f"episode_id IN ({placeholders})")
            params.extend(episode_ids)
        where = " AND ".join(clauses)
        sql = f"SELECT * FROM steps WHERE {where} ORDER BY episode_id, step_idx"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._deserialize_step(r) for r in rows]

    def query_episodes_by_time(
        self,
        *,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> list[dict[str, Any]]:
        """Query episodes within a time window based on started_at.

        Args:
            start_time: Minimum started_at timestamp (inclusive).
            end_time: Maximum started_at timestamp (inclusive).

        Returns:
            List of episode dicts within the time window.
        """
        assert self._conn is not None  # noqa: S101
        clauses: list[str] = []
        params: list[Any] = []
        if start_time is not None:
            clauses.append("started_at >= ?")
            params.append(start_time)
        if end_time is not None:
            clauses.append("started_at <= ?")
            params.append(end_time)
        where = " AND ".join(clauses)
        sql = "SELECT * FROM episodes"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY started_at DESC"
        return [self._row_to_dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def query_steps(self, episode_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch steps for a set of episodes, ordered by episode and step index.

        JSON columns (action_params, observation, file_diff, state_json)
        are deserialized back to dicts.

        Args:
            episode_ids: Episode IDs to fetch steps for.

        Returns:
            List of step dicts with JSON fields deserialized.
        """
        assert self._conn is not None  # noqa: S101
        if not episode_ids:
            return []
        placeholders = ", ".join("?" for _ in episode_ids)
        sql = (
            f"SELECT * FROM steps WHERE episode_id IN ({placeholders}) "
            "ORDER BY episode_id, step_idx"
        )
        rows = self._conn.execute(sql, episode_ids).fetchall()
        return [self._deserialize_step(r) for r in rows]

    def count_episodes(self, *, task_name: str | None = None) -> int:
        """Count episodes, optionally filtered by task name.

        Args:
            task_name: If provided, count only episodes for this task.

        Returns:
            Number of matching episodes.
        """
        assert self._conn is not None  # noqa: S101
        if task_name is not None:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM episodes WHERE task_name = ?",
                (task_name,),
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM episodes").fetchone()
        return row[0]

    # -- export --------------------------------------------------------------

    def _get_export_data(
        self,
        *,
        episode_ids: list[str] | None = None,
        task_name: str | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> list[dict[str, Any]]:
        """Shared helper: filter episodes, fetch their steps, enrich with episode metadata.

        Returns a flat list of step dicts, each enriched with ``score`` and
        ``task_name`` from the parent episode.
        """
        assert self._conn is not None  # noqa: S101

        # Build episode filter
        clauses: list[str] = []
        params: list[Any] = []

        if episode_ids is not None:
            placeholders = ", ".join("?" for _ in episode_ids)
            clauses.append(f"e.episode_id IN ({placeholders})")
            params.extend(episode_ids)
        if task_name is not None:
            clauses.append("e.task_name = ?")
            params.append(task_name)
        if min_score is not None:
            clauses.append("e.score >= ?")
            params.append(min_score)
        if max_score is not None:
            clauses.append("e.score <= ?")
            params.append(max_score)
        if start_time is not None:
            clauses.append("e.started_at >= ?")
            params.append(start_time)
        if end_time is not None:
            clauses.append("e.started_at <= ?")
            params.append(end_time)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT s.*, e.score AS ep_score, e.task_name AS ep_task_name "
            "FROM steps s "
            "JOIN episodes e ON s.episode_id = e.episode_id"
            f"{where} "
            "ORDER BY s.episode_id, s.step_idx"
        )
        rows = self._conn.execute(sql, params).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            d = self._deserialize_step(row)
            # Enrich with episode-level fields
            d["score"] = d.pop("ep_score", None)
            d["task_name"] = d.pop("ep_task_name", None)
            results.append(d)

        return results

    def export_jsonl(
        self,
        output_path: Path,
        *,
        episode_ids: list[str] | None = None,
        task_name: str | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> int:
        """Export filtered steps to a JSONL file (one JSON object per line).

        Each line contains a single ``(state, action, observation, reward)``
        tuple enriched with episode-level ``score`` and ``task_name``.

        Args:
            output_path: Destination JSONL file path.
            episode_ids: Optional list of episode IDs to include.
            task_name: Filter to a specific task.
            min_score: Minimum episode score (inclusive).
            max_score: Maximum episode score (inclusive).
            start_time: Minimum episode started_at timestamp.
            end_time: Maximum episode started_at timestamp.

        Returns:
            Number of steps exported.
        """
        data = self._get_export_data(
            episode_ids=episode_ids,
            task_name=task_name,
            min_score=min_score,
            max_score=max_score,
            start_time=start_time,
            end_time=end_time,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for step in data:
                f.write(json.dumps(step, default=str) + "\n")

        logger.info(
            "jsonl_exported",
            output_path=str(output_path),
            step_count=len(data),
        )
        return len(data)

    def export_parquet(
        self,
        output_path: Path,
        *,
        episode_ids: list[str] | None = None,
        task_name: str | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> int:
        """Export filtered steps to a Parquet file with snappy compression.

        Requires ``pyarrow`` to be installed (available via the ``parquet``
        optional extra: ``pip install lunar-sandbox[parquet]``).

        The output table has a flat schema with columns: ``episode_id``,
        ``step_idx``, ``action``, ``observation`` (JSON string), ``reward``,
        ``score``, ``task_name``, ``duration_ms``, ``timestamp``.

        Args:
            output_path: Destination Parquet file path.
            episode_ids: Optional list of episode IDs to include.
            task_name: Filter to a specific task.
            min_score: Minimum episode score (inclusive).
            max_score: Maximum episode score (inclusive).
            start_time: Minimum episode started_at timestamp.
            end_time: Maximum episode started_at timestamp.

        Returns:
            Number of steps exported.

        Raises:
            ImportError: If ``pyarrow`` is not installed.
        """
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            raise ImportError(
                "pyarrow is required for Parquet export. "
                "Install it with: pip install lunar-sandbox[parquet]"
            ) from None

        data = self._get_export_data(
            episode_ids=episode_ids,
            task_name=task_name,
            min_score=min_score,
            max_score=max_score,
            start_time=start_time,
            end_time=end_time,
        )

        # Build columnar data for flat table
        columns: dict[str, list[Any]] = {
            "episode_id": [],
            "step_idx": [],
            "action": [],
            "observation": [],
            "reward": [],
            "score": [],
            "task_name": [],
            "duration_ms": [],
            "timestamp": [],
        }
        for step in data:
            columns["episode_id"].append(step.get("episode_id", ""))
            columns["step_idx"].append(step.get("step_idx", 0))
            columns["action"].append(step.get("action", ""))
            obs = step.get("observation", {})
            columns["observation"].append(
                json.dumps(obs, default=str) if isinstance(obs, dict) else str(obs)
            )
            columns["reward"].append(step.get("reward", 0.0))
            columns["score"].append(step.get("score"))
            columns["task_name"].append(step.get("task_name", ""))
            columns["duration_ms"].append(step.get("duration_ms", 0.0))
            columns["timestamp"].append(step.get("timestamp", 0.0))

        schema = pa.schema(
            [
                pa.field("episode_id", pa.string()),
                pa.field("step_idx", pa.int64()),
                pa.field("action", pa.string()),
                pa.field("observation", pa.string()),
                pa.field("reward", pa.float64()),
                pa.field("score", pa.float64()),
                pa.field("task_name", pa.string()),
                pa.field("duration_ms", pa.float64()),
                pa.field("timestamp", pa.float64()),
            ]
        )

        table = pa.Table.from_pydict(columns, schema=schema)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, str(output_path), compression="snappy")

        logger.info(
            "parquet_exported",
            output_path=str(output_path),
            step_count=len(data),
        )
        return len(data)

    # -- deserialization helpers ----------------------------------------------

    def _deserialize_step(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a step row to a dict with JSON columns deserialized."""
        d = dict(row)
        for col in ("action_params", "observation", "state_json"):
            if d.get(col) is not None:
                try:
                    d[col] = json.loads(d[col])
                except (json.JSONDecodeError, TypeError):
                    pass
        if d.get("file_diff") is not None:
            try:
                d["file_diff"] = json.loads(d["file_diff"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

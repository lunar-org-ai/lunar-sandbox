"""SQLite batch result persistence.

Provides :class:`BatchResultStore` for persisting batch evaluation runs
and their per-task results to SQLite.  Extends the same database used
by :class:`TrajectoryStore` with ``batch_runs`` and ``task_results``
tables.

Uses WAL mode and ``synchronous=NORMAL`` for safe concurrent reads,
consistent with the :class:`TrajectoryStore` pattern.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from types import TracebackType

    from lunar_sandbox.scheduler.result import BatchResult, TaskResult

__all__ = ["BatchResultStore"]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_BATCH_RUNS = """\
CREATE TABLE IF NOT EXISTS batch_runs (
    batch_id       TEXT PRIMARY KEY,
    benchmark_name TEXT DEFAULT '',
    config_json    TEXT NOT NULL,
    total_tasks    INTEGER NOT NULL DEFAULT 0,
    passed         INTEGER NOT NULL DEFAULT 0,
    failed         INTEGER NOT NULL DEFAULT 0,
    errors         INTEGER NOT NULL DEFAULT 0,
    pass_rate      REAL NOT NULL DEFAULT 0.0,
    mean_score     REAL,
    p50_ms         REAL,
    p95_ms         REAL,
    total_tokens   INTEGER NOT NULL DEFAULT 0,
    total_cost     REAL NOT NULL DEFAULT 0.0,
    duration_ms    REAL NOT NULL DEFAULT 0.0,
    started_at     REAL NOT NULL,
    ended_at       REAL,
    created_at     REAL NOT NULL
);
"""

_CREATE_TASK_RESULTS = """\
CREATE TABLE IF NOT EXISTS task_results (
    batch_id        TEXT NOT NULL,
    task_name       TEXT NOT NULL,
    episode_id      TEXT DEFAULT '',
    outcome         TEXT NOT NULL,
    score           REAL,
    error_type      TEXT,
    error_message   TEXT,
    wall_clock_ms   REAL NOT NULL DEFAULT 0.0,
    step_count      INTEGER NOT NULL DEFAULT 0,
    token_count     INTEGER NOT NULL DEFAULT 0,
    estimated_cost  REAL NOT NULL DEFAULT 0.0,
    trajectory_path TEXT DEFAULT '',
    attempt         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (batch_id, task_name),
    FOREIGN KEY (batch_id) REFERENCES batch_runs(batch_id)
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_batch_runs_benchmark ON batch_runs(benchmark_name);",
    "CREATE INDEX IF NOT EXISTS idx_batch_runs_started ON batch_runs(started_at);",
    "CREATE INDEX IF NOT EXISTS idx_task_results_batch ON task_results(batch_id);",
    "CREATE INDEX IF NOT EXISTS idx_task_results_outcome ON task_results(outcome);",
    "CREATE INDEX IF NOT EXISTS idx_task_results_task ON task_results(task_name);",
]


class BatchResultStore:
    """SQLite-backed store for batch evaluation results.

    Persists :class:`BatchResult` objects (``batch_runs`` table) and
    their per-task :class:`TaskResult` objects (``task_results`` table).

    Usage::

        with BatchResultStore(db_path) as store:
            store.save_batch(batch_result)
            batches = store.query_batches()

    Args:
        db_path: Path to the SQLite database file.  Can share the same
            DB as :class:`TrajectoryStore`.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle -----------------------------------------------------------

    def open(self) -> None:
        """Open the database and ensure batch schema exists.

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
            "batch_result_store_opened",
            db_path=str(self._db_path),
        )

    def close(self) -> None:
        """Close the database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug(
                "batch_result_store_closed",
                db_path=str(self._db_path),
            )

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> BatchResultStore:
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
        self._conn.execute(_CREATE_BATCH_RUNS)
        self._conn.execute(_CREATE_TASK_RESULTS)
        for idx_sql in _INDEXES:
            self._conn.execute(idx_sql)

    # -- write operations ----------------------------------------------------

    def save_batch(
        self,
        batch_result: BatchResult,
        benchmark_name: str = "",
    ) -> None:
        """Persist a complete batch result in a single transaction.

        Inserts one row into ``batch_runs`` and one row per task into
        ``task_results``.

        Args:
            batch_result: The batch result to persist.
            benchmark_name: Optional benchmark name to tag the run.
        """
        assert self._conn is not None  # noqa: S101
        agg = batch_result.aggregate
        now = time.time()

        with self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO batch_runs
                   (batch_id, benchmark_name, config_json, total_tasks,
                    passed, failed, errors, pass_rate, mean_score,
                    p50_ms, p95_ms, total_tokens, total_cost,
                    duration_ms, started_at, ended_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch_result.batch_id,
                    benchmark_name,
                    json.dumps(batch_result.config, default=str),
                    agg.total_tasks,
                    agg.passed,
                    agg.failed,
                    agg.errors,
                    agg.pass_rate,
                    agg.mean_score,
                    agg.p50_wall_clock_ms,
                    agg.p95_wall_clock_ms,
                    agg.total_tokens,
                    agg.total_estimated_cost_usd,
                    agg.total_batch_duration_ms,
                    batch_result.started_at,
                    batch_result.ended_at,
                    now,
                ),
            )

            task_rows = []
            for tr in batch_result.task_results:
                task_rows.append(
                    (
                        batch_result.batch_id,
                        tr.task_name,
                        tr.episode_id,
                        tr.outcome,
                        tr.score,
                        tr.error_type,
                        tr.error_message,
                        tr.wall_clock_ms,
                        tr.step_count,
                        tr.token_count,
                        tr.estimated_cost_usd,
                        tr.trajectory_path,
                        tr.attempt,
                    )
                )

            if task_rows:
                self._conn.executemany(
                    """INSERT OR REPLACE INTO task_results
                       (batch_id, task_name, episode_id, outcome, score,
                        error_type, error_message, wall_clock_ms,
                        step_count, token_count, estimated_cost,
                        trajectory_path, attempt)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    task_rows,
                )

        logger.info(
            "batch_saved",
            batch_id=batch_result.batch_id,
            task_count=len(batch_result.task_results),
        )

    def save_task_result(
        self,
        batch_id: str,
        result: TaskResult,
    ) -> None:
        """Persist a single task result (streaming as tasks complete).

        Uses ``INSERT OR REPLACE`` so calling this multiple times for
        the same ``(batch_id, task_name)`` is idempotent.

        Args:
            batch_id: The batch run this task belongs to.
            result: The task result to persist.
        """
        assert self._conn is not None  # noqa: S101

        with self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO task_results
                   (batch_id, task_name, episode_id, outcome, score,
                    error_type, error_message, wall_clock_ms,
                    step_count, token_count, estimated_cost,
                    trajectory_path, attempt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch_id,
                    result.task_name,
                    result.episode_id,
                    result.outcome,
                    result.score,
                    result.error_type,
                    result.error_message,
                    result.wall_clock_ms,
                    result.step_count,
                    result.token_count,
                    result.estimated_cost_usd,
                    result.trajectory_path,
                    result.attempt,
                ),
            )

    # -- read operations -----------------------------------------------------

    def query_batches(
        self,
        benchmark_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query batch runs, ordered by start time (most recent first).

        Args:
            benchmark_name: If provided, filter to this benchmark.
            limit: Maximum number of results. Defaults to 50.

        Returns:
            List of batch run dicts.
        """
        assert self._conn is not None  # noqa: S101
        params: list[Any] = []

        sql = "SELECT * FROM batch_runs"
        if benchmark_name is not None:
            sql += " WHERE benchmark_name = ?"
            params.append(benchmark_name)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        return [
            dict(row)
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def query_batch_results(self, batch_id: str) -> list[dict[str, Any]]:
        """Query task results for a specific batch.

        Args:
            batch_id: The batch run to query.

        Returns:
            List of task result dicts.
        """
        assert self._conn is not None  # noqa: S101
        return [
            dict(row)
            for row in self._conn.execute(
                "SELECT * FROM task_results WHERE batch_id = ? ORDER BY task_name",
                (batch_id,),
            ).fetchall()
        ]

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        """Get a single batch run by ID.

        Args:
            batch_id: The batch run identifier.

        Returns:
            Batch run dict, or ``None`` if not found.
        """
        assert self._conn is not None  # noqa: S101
        row = self._conn.execute(
            "SELECT * FROM batch_runs WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
        return dict(row) if row else None

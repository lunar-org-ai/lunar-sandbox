"""SQLite telemetry persistence.

Provides :class:`TelemetryStore` for persisting telemetry run metadata
and raw metric samples.  Follows the same WAL-mode pattern as
:class:`TrajectoryStore` and :class:`BatchResultStore`.

Tables are created alongside the existing trajectory/batch tables in
the same database.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from types import TracebackType

    from lunar_sandbox.telemetry.types import MetricSample

__all__ = ["TelemetryStore"]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_TELEMETRY_RUNS = """\
CREATE TABLE IF NOT EXISTS telemetry_runs (
    run_id                TEXT PRIMARY KEY,
    started_at            REAL NOT NULL,
    ended_at              REAL,
    total_episodes        INTEGER NOT NULL DEFAULT 0,
    throughput_eps_per_min REAL,
    cache_hit_rate        REAL,
    duration_seconds      REAL,
    created_at            REAL NOT NULL
);
"""

_CREATE_TELEMETRY_SAMPLES = """\
CREATE TABLE IF NOT EXISTS telemetry_samples (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    metric      TEXT NOT NULL,
    value       REAL NOT NULL,
    fingerprint TEXT DEFAULT '',
    timestamp   REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES telemetry_runs(run_id)
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_telem_samples_run ON telemetry_samples(run_id);",
    "CREATE INDEX IF NOT EXISTS idx_telem_samples_metric ON telemetry_samples(metric);",
    "CREATE INDEX IF NOT EXISTS idx_telem_samples_fingerprint ON telemetry_samples(fingerprint);",
    "CREATE INDEX IF NOT EXISTS idx_telem_runs_started ON telemetry_runs(started_at);",
]


class TelemetryStore:
    """SQLite-backed telemetry store with WAL mode.

    Persists telemetry run metadata (``telemetry_runs``) and raw
    metric samples (``telemetry_samples``).

    Usage::

        with TelemetryStore(db_path) as store:
            store.save_run("run-1", samples, ...)
            runs = store.query_runs()

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle -----------------------------------------------------------

    def open(self) -> None:
        """Open the database and ensure telemetry schema exists.

        Enables WAL journal mode and ``PRAGMA synchronous=NORMAL``
        for safe concurrent reads with good write performance.
        """
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        self._conn = conn
        self._ensure_schema()
        logger.debug(
            "telemetry_store_opened",
            db_path=str(self._db_path),
        )

    def close(self) -> None:
        """Close the database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug(
                "telemetry_store_closed",
                db_path=str(self._db_path),
            )

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> TelemetryStore:
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
        self._conn.execute(_CREATE_TELEMETRY_RUNS)
        self._conn.execute(_CREATE_TELEMETRY_SAMPLES)
        for idx_sql in _INDEXES:
            self._conn.execute(idx_sql)

    # -- write operations ----------------------------------------------------

    def save_run(
        self,
        run_id: str,
        samples: list[MetricSample],
        started_at: float,
        ended_at: float,
        total_episodes: int,
        throughput: float,
        cache_hit_rate: float,
    ) -> None:
        """Persist a telemetry run and its samples in a single transaction.

        Uses ``INSERT OR REPLACE`` for idempotent re-ingestion.

        Args:
            run_id: Unique run identifier (batch_id or synthetic).
            samples: Raw metric samples to persist.
            started_at: Run start time (``time.time()``).
            ended_at: Run end time (``time.time()``).
            total_episodes: Number of episodes in the run.
            throughput: Episodes per minute.
            cache_hit_rate: Cache hit rate (0.0--1.0).
        """
        assert self._conn is not None  # noqa: S101
        now = time.time()
        duration_seconds = ended_at - started_at if ended_at > started_at else 0.0

        with self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO telemetry_runs
                   (run_id, started_at, ended_at, total_episodes,
                    throughput_eps_per_min, cache_hit_rate,
                    duration_seconds, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    started_at,
                    ended_at,
                    total_episodes,
                    throughput,
                    cache_hit_rate,
                    duration_seconds,
                    now,
                ),
            )

            if samples:
                sample_rows = [
                    (
                        run_id,
                        s.metric,
                        s.value,
                        s.fingerprint,
                        s.timestamp,
                    )
                    for s in samples
                ]
                self._conn.executemany(
                    """INSERT INTO telemetry_samples
                       (run_id, metric, value, fingerprint, timestamp)
                       VALUES (?, ?, ?, ?, ?)""",
                    sample_rows,
                )

        logger.info(
            "telemetry_run_saved",
            run_id=run_id,
            sample_count=len(samples),
            total_episodes=total_episodes,
        )

    # -- read operations -----------------------------------------------------

    def query_samples(
        self,
        run_id: str,
        *,
        metric: str | None = None,
        fingerprint: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch samples for a run with optional filters.

        Args:
            run_id: The run to query.
            metric: Filter to a specific metric name.
            fingerprint: Filter to a specific fingerprint.

        Returns:
            List of sample dicts.
        """
        assert self._conn is not None  # noqa: S101
        clauses: list[str] = ["run_id = ?"]
        params: list[Any] = [run_id]
        if metric is not None:
            clauses.append("metric = ?")
            params.append(metric)
        if fingerprint is not None:
            clauses.append("fingerprint = ?")
            params.append(fingerprint)
        where = " AND ".join(clauses)
        sql = f"SELECT * FROM telemetry_samples WHERE {where} ORDER BY timestamp"
        return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

    def query_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """List recent telemetry runs ordered by started_at DESC.

        Args:
            limit: Maximum number of runs to return.

        Returns:
            List of run dicts.
        """
        assert self._conn is not None  # noqa: S101
        return [
            dict(row)
            for row in self._conn.execute(
                "SELECT * FROM telemetry_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        ]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get a single telemetry run by ID.

        Args:
            run_id: The run identifier.

        Returns:
            Run dict, or ``None`` if not found.
        """
        assert self._conn is not None  # noqa: S101
        row = self._conn.execute(
            "SELECT * FROM telemetry_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return dict(row) if row else None

    def delete_run(self, run_id: str) -> bool:
        """Delete a run and its samples.

        Args:
            run_id: The run to delete.

        Returns:
            True if the run existed and was deleted.
        """
        assert self._conn is not None  # noqa: S101
        with self._conn:
            self._conn.execute(
                "DELETE FROM telemetry_samples WHERE run_id = ?",
                (run_id,),
            )
            cursor = self._conn.execute(
                "DELETE FROM telemetry_runs WHERE run_id = ?",
                (run_id,),
            )
        return cursor.rowcount > 0

    def delete_all(self) -> int:
        """Delete all runs and samples.

        Returns:
            Number of runs deleted.
        """
        assert self._conn is not None  # noqa: S101
        with self._conn:
            self._conn.execute("DELETE FROM telemetry_samples")
            cursor = self._conn.execute("DELETE FROM telemetry_runs")
        return cursor.rowcount

    def export_samples(
        self,
        run_id: str,
        *,
        metric: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return raw samples as list of dicts for CSV/JSON export.

        Args:
            run_id: The run to export.
            metric: Optionally filter to a specific metric.

        Returns:
            List of sample dicts suitable for serialization.
        """
        assert self._conn is not None  # noqa: S101
        clauses: list[str] = ["run_id = ?"]
        params: list[Any] = [run_id]
        if metric is not None:
            clauses.append("metric = ?")
            params.append(metric)
        where = " AND ".join(clauses)
        sql = (
            f"SELECT run_id, metric, value, fingerprint, timestamp "
            f"FROM telemetry_samples WHERE {where} ORDER BY timestamp"
        )
        return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

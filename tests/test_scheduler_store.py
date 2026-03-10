"""Tests for BatchResultStore SQLite persistence.

Covers open/close lifecycle, context manager, save/query batch runs
and task results. All tests use tempfile.TemporaryDirectory for DB path.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from lunar_sandbox.scheduler.result import AggregateMetrics, BatchResult, TaskResult
from lunar_sandbox.scheduler.store import BatchResultStore


# ---------- Helpers ----------


def _make_batch_result(
    batch_id: str = "batch-test-001",
    task_results: list[TaskResult] | None = None,
) -> BatchResult:
    """Create a BatchResult with predictable data."""
    if task_results is None:
        task_results = [
            TaskResult(task_name="t1", outcome="pass", score=1.0, wall_clock_ms=100.0),
            TaskResult(task_name="t2", outcome="fail", score=0.0, wall_clock_ms=200.0),
        ]
    agg = AggregateMetrics.from_results(task_results, batch_duration_ms=300.0)
    return BatchResult(
        batch_id=batch_id,
        task_results=task_results,
        aggregate=agg,
        config={"max_workers": 8},
        started_at=time.time(),
        ended_at=time.time() + 1.0,
        jsonl_path="/tmp/test-batch.jsonl",
    )


# ---------- Lifecycle ----------


class TestStoreLifecycle:
    """BatchResultStore open/close and context manager."""

    def test_open_close(self) -> None:
        """open() creates tables, close() works without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = BatchResultStore(db_path)
            store.open()
            # Verify tables exist by querying
            assert store._conn is not None
            rows = store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_runs'"
            ).fetchall()
            assert len(rows) == 1
            store.close()
            assert store._conn is None

    def test_context_manager(self) -> None:
        """with statement opens and closes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with BatchResultStore(db_path) as store:
                assert store._conn is not None
            # After exit, connection is closed
            assert store._conn is None


# ---------- Save operations ----------


class TestSaveBatch:
    """Saving batch results to SQLite."""

    def test_save_batch_creates_batch_row(self) -> None:
        """save_batch inserts a batch_runs row."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with BatchResultStore(db_path) as store:
                batch = _make_batch_result()
                store.save_batch(batch, benchmark_name="test-bench")

                row = store.get_batch(batch.batch_id)
                assert row is not None
                assert row["batch_id"] == "batch-test-001"
                assert row["benchmark_name"] == "test-bench"
                assert row["total_tasks"] == 2
                assert row["passed"] == 1
                assert row["failed"] == 1

    def test_save_batch_task_results(self) -> None:
        """save_batch inserts task_results rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with BatchResultStore(db_path) as store:
                batch = _make_batch_result()
                store.save_batch(batch)

                results = store.query_batch_results(batch.batch_id)
                assert len(results) == 2
                names = {r["task_name"] for r in results}
                assert names == {"t1", "t2"}

    def test_save_task_result_streaming(self) -> None:
        """save_task_result inserts individual rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with BatchResultStore(db_path) as store:
                tr = TaskResult(
                    task_name="streaming-task",
                    outcome="pass",
                    score=1.0,
                    wall_clock_ms=50.0,
                    episode_id="ep-s1",
                )
                store.save_task_result("batch-stream", tr)

                results = store.query_batch_results("batch-stream")
                assert len(results) == 1
                assert results[0]["task_name"] == "streaming-task"
                assert results[0]["outcome"] == "pass"
                assert results[0]["episode_id"] == "ep-s1"


# ---------- Query operations ----------


class TestQueryBatches:
    """Querying batch runs."""

    def test_query_all(self) -> None:
        """query_batches with no filter returns all batches ordered by started_at DESC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with BatchResultStore(db_path) as store:
                batch1 = _make_batch_result("batch-1")
                batch1.started_at = 1000.0
                batch2 = _make_batch_result("batch-2")
                batch2.started_at = 2000.0

                store.save_batch(batch1)
                store.save_batch(batch2)

                batches = store.query_batches()
                assert len(batches) == 2
                # Most recent first
                assert batches[0]["batch_id"] == "batch-2"
                assert batches[1]["batch_id"] == "batch-1"

    def test_query_by_benchmark(self) -> None:
        """filter by benchmark_name returns matching batches only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with BatchResultStore(db_path) as store:
                b1 = _make_batch_result("batch-a")
                b2 = _make_batch_result("batch-b")
                store.save_batch(b1, benchmark_name="swe-bench")
                store.save_batch(b2, benchmark_name="other-bench")

                results = store.query_batches(benchmark_name="swe-bench")
                assert len(results) == 1
                assert results[0]["batch_id"] == "batch-a"

    def test_query_batch_results(self) -> None:
        """get task results for specific batch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with BatchResultStore(db_path) as store:
                batch = _make_batch_result()
                store.save_batch(batch)

                results = store.query_batch_results(batch.batch_id)
                assert len(results) == 2
                # Ordered by task_name
                assert results[0]["task_name"] == "t1"
                assert results[1]["task_name"] == "t2"


class TestGetBatch:
    """Single batch retrieval."""

    def test_get_batch(self) -> None:
        """get_batch returns the batch dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with BatchResultStore(db_path) as store:
                batch = _make_batch_result()
                store.save_batch(batch)
                got = store.get_batch(batch.batch_id)
                assert got is not None
                assert got["batch_id"] == batch.batch_id

    def test_get_batch_not_found(self) -> None:
        """Nonexistent batch_id -> None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with BatchResultStore(db_path) as store:
                assert store.get_batch("nonexistent") is None


class TestMultipleBatches:
    """Multiple batch operations."""

    def test_multiple_batches(self) -> None:
        """Save multiple batches, verify querying returns all."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with BatchResultStore(db_path) as store:
                for i in range(5):
                    batch = _make_batch_result(f"batch-{i}")
                    batch.started_at = 1000.0 + i
                    store.save_batch(batch, benchmark_name="multi-bench")

                all_batches = store.query_batches()
                assert len(all_batches) == 5

                filtered = store.query_batches(benchmark_name="multi-bench")
                assert len(filtered) == 5

                # Most recent first
                assert filtered[0]["batch_id"] == "batch-4"
                assert filtered[4]["batch_id"] == "batch-0"

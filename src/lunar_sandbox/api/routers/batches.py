"""Batch evaluation endpoints.

Provides paginated listing of batch runs and detail with per-task results.
BatchResultStore is opened on-demand (not via the engine singleton) because
the engine lifespan does not hold a BatchResultStore open permanently.
"""

from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Depends, HTTPException

from lunar_sandbox.api.deps import get_engine
from lunar_sandbox.api.pagination import PaginationParams, pagination_query
from lunar_sandbox.api.schemas import (
    BatchDetail,
    BatchSummary,
    PaginatedBatches,
    TaskResultSummary,
)

router = APIRouter(prefix="/api/batches", tags=["batches"])

logger = structlog.get_logger(__name__)


def _open_batch_store(engine):  # noqa: ANN001
    """Open an on-demand BatchResultStore from the engine config."""
    from lunar_sandbox.scheduler.store import BatchResultStore

    db_path = engine._config.trajectory_dir / "trajectories.db"
    store = BatchResultStore(db_path)
    store.open()
    return store


def _mock_batches() -> list[BatchSummary]:
    """Return mock batch data for macOS development."""
    now = time.time()
    return [
        BatchSummary(
            batch_id="mock-batch-1",
            benchmark_name="swe-bench-lite",
            total_tasks=20,
            passed=14,
            failed=4,
            errors=2,
            pass_rate=0.70,
            total_tokens=42000,
            total_cost=0.084,
            duration_ms=120000.0,
            started_at=now - 180.0,
            ended_at=now - 60.0,
        )
    ]


def _mock_batch_detail() -> BatchDetail:
    """Return mock batch detail for macOS development."""
    now = time.time()
    task_results = []
    outcomes = (
        ["passed"] * 14
        + ["failed"] * 4
        + ["error"] * 2
    )
    for i, outcome in enumerate(outcomes):
        task_results.append(
            TaskResultSummary(
                task_name=f"task_{i + 1:02d}",
                episode_id=f"ep-mock-{i + 1:04d}",
                outcome=outcome,
                score=1.0 if outcome == "passed" else 0.0,
                wall_clock_ms=float(5000 + i * 300),
                step_count=8 + (i % 5),
                token_count=2000 + i * 100,
                estimated_cost=0.004 + i * 0.0002,
            )
        )
    return BatchDetail(
        batch_id="mock-batch-1",
        benchmark_name="swe-bench-lite",
        total_tasks=20,
        passed=14,
        failed=4,
        errors=2,
        pass_rate=0.70,
        total_tokens=42000,
        total_cost=0.084,
        duration_ms=120000.0,
        started_at=now - 180.0,
        ended_at=now - 60.0,
        task_results=task_results,
    )


@router.get("", response_model=PaginatedBatches)
async def list_batches(
    pagination: PaginationParams = Depends(pagination_query),
    engine=Depends(get_engine),
) -> PaginatedBatches:
    """List batch runs with pagination."""
    # macOS mock fallback: engine pool not available
    if engine.pool is None:
        batches = _mock_batches()
        total = len(batches)
        page = batches[pagination.offset : pagination.offset + pagination.limit]
        return PaginatedBatches(
            items=page,
            total=total,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    store = _open_batch_store(engine)
    try:
        rows = store.query_batches(limit=10000)
        total = len(rows)
        page = rows[pagination.offset : pagination.offset + pagination.limit]

        items = [
            BatchSummary(
                batch_id=r["batch_id"],
                benchmark_name=r.get("benchmark_name", ""),
                total_tasks=r.get("total_tasks", 0),
                passed=r.get("passed", 0),
                failed=r.get("failed", 0),
                errors=r.get("errors", 0),
                pass_rate=r.get("pass_rate", 0.0),
                total_tokens=r.get("total_tokens", 0),
                total_cost=r.get("total_cost", 0.0),
                duration_ms=r.get("duration_ms", 0.0),
                started_at=r.get("started_at", 0.0),
                ended_at=r.get("ended_at"),
            )
            for r in page
        ]

        return PaginatedBatches(
            items=items,
            total=total,
            offset=pagination.offset,
            limit=pagination.limit,
        )
    finally:
        store.close()


@router.get("/{batch_id}", response_model=BatchDetail)
async def get_batch(
    batch_id: str,
    engine=Depends(get_engine),
) -> BatchDetail:
    """Get batch detail with per-task results."""
    # macOS mock fallback: engine pool not available
    if engine.pool is None:
        if batch_id != "mock-batch-1":
            raise HTTPException(
                status_code=404,
                detail=f"Batch '{batch_id}' not found",
            )
        return _mock_batch_detail()

    store = _open_batch_store(engine)
    try:
        batch = store.get_batch(batch_id)
        if batch is None:
            raise HTTPException(
                status_code=404,
                detail=f"Batch '{batch_id}' not found",
            )

        result_rows = store.query_batch_results(batch_id)

        task_results = [
            TaskResultSummary(
                task_name=r["task_name"],
                episode_id=r.get("episode_id", ""),
                outcome=r["outcome"],
                score=r.get("score"),
                wall_clock_ms=r.get("wall_clock_ms", 0.0),
                step_count=r.get("step_count", 0),
                token_count=r.get("token_count", 0),
                estimated_cost=r.get("estimated_cost", 0.0),
            )
            for r in result_rows
        ]

        return BatchDetail(
            batch_id=batch["batch_id"],
            benchmark_name=batch.get("benchmark_name", ""),
            total_tasks=batch.get("total_tasks", 0),
            passed=batch.get("passed", 0),
            failed=batch.get("failed", 0),
            errors=batch.get("errors", 0),
            pass_rate=batch.get("pass_rate", 0.0),
            total_tokens=batch.get("total_tokens", 0),
            total_cost=batch.get("total_cost", 0.0),
            duration_ms=batch.get("duration_ms", 0.0),
            started_at=batch.get("started_at", 0.0),
            ended_at=batch.get("ended_at"),
            task_results=task_results,
        )
    finally:
        store.close()

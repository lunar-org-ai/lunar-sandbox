"""Telemetry run endpoints.

Provides paginated listing of telemetry runs and detail with raw
metric samples.  TelemetryStore is opened on-demand (not via the
engine singleton) because the engine lifespan does not hold a
TelemetryStore open permanently.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from lunar_sandbox.api.deps import get_engine
from lunar_sandbox.api.pagination import PaginationParams, pagination_query
from lunar_sandbox.api.schemas import (
    PaginatedTelemetryRuns,
    TelemetryRunDetail,
    TelemetryRunSummary,
)

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

logger = structlog.get_logger(__name__)


def _open_telemetry_store(engine):  # noqa: ANN001
    """Open an on-demand TelemetryStore from the engine config."""
    from lunar_sandbox.telemetry.store import TelemetryStore

    db_path = engine._config.trajectory_dir / "trajectories.db"
    store = TelemetryStore(db_path)
    store.open()
    return store


@router.get("", response_model=PaginatedTelemetryRuns)
async def list_telemetry_runs(
    pagination: PaginationParams = Depends(pagination_query),
    engine=Depends(get_engine),
) -> PaginatedTelemetryRuns:
    """List telemetry runs with pagination."""
    store = _open_telemetry_store(engine)
    try:
        # Fetch more than needed for accurate total count
        runs = store.query_runs(limit=10000)
        total = len(runs)
        page = runs[pagination.offset : pagination.offset + pagination.limit]

        items = [
            TelemetryRunSummary(
                run_id=r["run_id"],
                started_at=r.get("started_at", 0.0),
                ended_at=r.get("ended_at"),
                total_episodes=r.get("total_episodes", 0),
                throughput_eps_per_min=r.get("throughput_eps_per_min"),
                cache_hit_rate=r.get("cache_hit_rate"),
            )
            for r in page
        ]

        return PaginatedTelemetryRuns(
            items=items,
            total=total,
            offset=pagination.offset,
            limit=pagination.limit,
        )
    finally:
        store.close()


@router.get("/{run_id}", response_model=TelemetryRunDetail)
async def get_telemetry_run(
    run_id: str,
    engine=Depends(get_engine),
) -> TelemetryRunDetail:
    """Get telemetry run detail with raw metric samples."""
    store = _open_telemetry_store(engine)
    try:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail=f"Telemetry run '{run_id}' not found",
            )

        samples = store.query_samples(run_id)

        return TelemetryRunDetail(
            run_id=run["run_id"],
            started_at=run.get("started_at", 0.0),
            ended_at=run.get("ended_at"),
            total_episodes=run.get("total_episodes", 0),
            throughput_eps_per_min=run.get("throughput_eps_per_min"),
            cache_hit_rate=run.get("cache_hit_rate"),
            samples=samples,
        )
    finally:
        store.close()

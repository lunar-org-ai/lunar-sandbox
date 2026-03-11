"""Run launch endpoint.

Provides a POST /api/runs endpoint that accepts a RunRequest body and
immediately returns run/episode IDs.  On macOS (where the engine pool is
unavailable), returns mock IDs so the frontend can be developed without
a running engine.
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends

from lunar_sandbox.api.deps import get_engine
from lunar_sandbox.api.schemas import RunLaunchResponse, RunRequest

router = APIRouter(prefix="/api/runs", tags=["runs"])

logger = structlog.get_logger(__name__)


@router.post("", response_model=RunLaunchResponse)
async def launch_run(
    body: RunRequest,
    background_tasks: BackgroundTasks,
    engine=Depends(get_engine),
) -> RunLaunchResponse:
    """Launch an evaluation run and return IDs immediately.

    When the engine pool is unavailable (e.g., on macOS), returns mock
    IDs so the dashboard can be developed without a running engine.
    """
    run_id = f"run-{uuid4().hex[:8]}"
    episode_id = f"ep-{uuid4().hex[:8]}"

    if engine.pool is None:
        # macOS / no engine pool -- return mock IDs immediately
        logger.info(
            "launch_run_mock",
            task_name=body.task_name,
            run_id=run_id,
            episode_id=episode_id,
        )
        return RunLaunchResponse(run_id=run_id, episode_id=episode_id)

    # Engine available -- schedule evaluation in background and return IDs
    async def _run_eval() -> None:
        try:
            await engine.eval(
                task_name=body.task_name,
                model=body.model,
                parallelism=body.parallelism,
                timeout=body.timeout,
                env_vars=body.env_vars or {},
            )
        except Exception as exc:
            logger.error("run_eval_failed", run_id=run_id, error=str(exc))

    background_tasks.add_task(_run_eval)
    logger.info(
        "launch_run",
        task_name=body.task_name,
        run_id=run_id,
        episode_id=episode_id,
    )
    return RunLaunchResponse(run_id=run_id, episode_id=episode_id)

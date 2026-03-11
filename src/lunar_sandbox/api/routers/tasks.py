"""Task listing endpoints.

Tasks are defined in YAML files, not stored in a database.  For Phase 8,
this router queries the trajectory store for distinct task names from
completed episodes, providing a "tasks that have been run" endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from lunar_sandbox.api.deps import get_engine
from lunar_sandbox.api.pagination import PaginationParams, pagination_query
from lunar_sandbox.api.schemas import PaginatedTasks, TaskSummary

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=PaginatedTasks)
async def list_tasks(
    pagination: PaginationParams = Depends(pagination_query),
    engine=Depends(get_engine),
) -> PaginatedTasks:
    """List tasks that have been evaluated (from episode history)."""
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")

    # Get distinct task names from episodes
    all_episodes = store.query_episodes()
    task_names: dict[str, int] = {}
    for ep in all_episodes:
        name = ep.get("task_name", "")
        task_names[name] = task_names.get(name, 0) + 1

    # Build task summaries sorted by name
    tasks = sorted(
        [TaskSummary(name=name) for name in task_names],
        key=lambda t: t.name,
    )

    total = len(tasks)
    page = tasks[pagination.offset : pagination.offset + pagination.limit]

    return PaginatedTasks(
        items=page,
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )


@router.get("/{task_name}", response_model=TaskSummary)
async def get_task(
    task_name: str,
    engine=Depends(get_engine),
) -> TaskSummary:
    """Get task info by name (from episode history)."""
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")

    episodes = store.query_episodes(task_name=task_name)
    if not episodes:
        raise HTTPException(
            status_code=404,
            detail=f"No episodes found for task '{task_name}'",
        )

    return TaskSummary(name=task_name)

"""Task listing and registration endpoints.

Tasks can be registered via POST and listed via GET.  The GET endpoint
reads from the ``tasks`` table in the trajectory store.
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
    """List registered tasks."""
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")

    all_tasks = store.list_tasks()
    tasks = [TaskSummary(**t) for t in all_tasks]

    total = len(tasks)
    page = tasks[pagination.offset : pagination.offset + pagination.limit]

    return PaginatedTasks(
        items=page,
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )


@router.post("", response_model=TaskSummary, status_code=201)
async def create_task(
    body: TaskSummary,
    engine=Depends(get_engine),
) -> TaskSummary:
    """Register a new task definition."""
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")

    if not body.name:
        raise HTTPException(status_code=422, detail="Task name is required")

    store.register_task(body.model_dump())
    return body


@router.get("/{task_name}", response_model=TaskSummary)
async def get_task(
    task_name: str,
    engine=Depends(get_engine),
) -> TaskSummary:
    """Get a task by name."""
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")

    all_tasks = store.list_tasks()
    for t in all_tasks:
        if t["name"] == task_name:
            return TaskSummary(**t)

    raise HTTPException(status_code=404, detail=f"Task '{task_name}' not found")


@router.delete("/{task_name}", status_code=204)
async def delete_task(
    task_name: str,
    engine=Depends(get_engine),
) -> None:
    """Delete a registered task."""
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")

    if not store.delete_task(task_name):
        raise HTTPException(status_code=404, detail=f"Task '{task_name}' not found")

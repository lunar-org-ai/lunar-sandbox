"""Episode list and detail endpoints.

Provides paginated episode listing with optional task_name filter,
and full episode detail with step data.  Data is served from the
TrajectoryStore (SQLite), which works on all platforms.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from lunar_sandbox.api.deps import get_engine
from lunar_sandbox.api.pagination import PaginationParams, pagination_query
from lunar_sandbox.api.schemas import EpisodeDetail, EpisodeSummary, PaginatedEpisodes

router = APIRouter(prefix="/api/episodes", tags=["episodes"])


@router.get("", response_model=PaginatedEpisodes)
async def list_episodes(
    pagination: PaginationParams = Depends(pagination_query),
    task_name: str | None = None,
    engine=Depends(get_engine),
) -> PaginatedEpisodes:
    """List episodes with optional task_name filter and pagination."""
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")

    episodes = store.query_episodes(task_name=task_name)
    total = len(episodes)
    page = episodes[pagination.offset : pagination.offset + pagination.limit]

    return PaginatedEpisodes(
        items=[EpisodeSummary(**ep) for ep in page],
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )


@router.get("/{episode_id}", response_model=EpisodeDetail)
async def get_episode(
    episode_id: str,
    engine=Depends(get_engine),
) -> EpisodeDetail:
    """Get full episode detail including steps."""
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")

    episodes = store.query_episodes(episode_id=episode_id)
    if not episodes:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

    steps = store.query_steps([episode_id])
    episode = episodes[0]
    return EpisodeDetail(**episode, steps=steps)

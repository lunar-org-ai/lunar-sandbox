"""Domain routers for the LunarEngine API."""

from lunar_sandbox.api.routers.batches import router as batches_router
from lunar_sandbox.api.routers.episodes import router as episodes_router
from lunar_sandbox.api.routers.runs import router as runs_router
from lunar_sandbox.api.routers.sandboxes import pool_router, router as sandboxes_router
from lunar_sandbox.api.routers.tasks import router as tasks_router
from lunar_sandbox.api.routers.telemetry import router as telemetry_router

__all__ = [
    "batches_router",
    "episodes_router",
    "pool_router",
    "runs_router",
    "sandboxes_router",
    "tasks_router",
    "telemetry_router",
]

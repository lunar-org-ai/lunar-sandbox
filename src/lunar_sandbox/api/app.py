"""FastAPI application with lifespan-managed LunarEngine singleton.

The engine is created once at startup and shared across all handlers
via the module-level ``_engine`` reference.  On macOS (where the engine
uses Linux-only kernel features), startup failure is caught gracefully
and the API continues to serve from SQLite-backed stores.

All engine-related imports are lazy (inside the lifespan function) to
avoid triggering Linux-only imports at module-load time.  This allows
``app.openapi()`` to work on any platform for schema export.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import structlog
from fastapi import FastAPI, WebSocket
from fastapi.exceptions import HTTPException

from lunar_sandbox.api.errors import generic_exception_handler, http_exception_handler
from lunar_sandbox.api.routers import (
    batches_router,
    episodes_router,
    pool_router,
    runs_router,
    sandboxes_router,
    tasks_router,
    telemetry_router,
)
from lunar_sandbox.api.schemas import HealthResponse
from lunar_sandbox.api.ws import ConnectionManager, EventHub
from lunar_sandbox.api.ws.endpoint import websocket_handler

__all__ = ["app"]

logger = structlog.get_logger(__name__)

# Module-level engine reference, set during lifespan
_engine: Any = None
_engine_started: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create and manage the LunarEngine singleton.

    On startup, creates the engine and attempts to start it.  If
    startup fails (e.g., on macOS where Linux kernel features are
    unavailable), the error is logged but the app continues to serve
    store-backed endpoints.

    On shutdown, the engine is stopped and the reference is cleared.
    """
    global _engine, _engine_started

    # Lazy import to avoid triggering Linux-only code at module load
    from lunar_sandbox.sdk import EngineConfig, LunarEngine

    engine = LunarEngine(EngineConfig())
    try:
        await engine.start()
        _engine_started = True
        logger.info("engine_started")
    except Exception as exc:
        # Graceful degradation: engine pool/scheduler may fail on macOS
        # but SQLite stores are still usable
        _engine_started = False
        logger.warning("engine_start_failed", error=str(exc))

    _engine = engine

    # WebSocket infrastructure
    ws_manager = ConnectionManager()
    event_hub = EventHub(ws_manager)
    app.state.ws_manager = ws_manager
    app.state.event_hub = event_hub

    mock_emitter_task: asyncio.Task[None] | None = None
    if not _engine_started:
        import asyncio as _aio

        from lunar_sandbox.api.ws.mock_emitter import run_mock_emitter

        mock_emitter_task = _aio.create_task(run_mock_emitter(event_hub))
        logger.info("mock_emitter_started")

    yield

    if mock_emitter_task is not None:
        mock_emitter_task.cancel()
        try:
            await mock_emitter_task
        except asyncio.CancelledError:
            pass

    await engine.stop()
    _engine = None
    _engine_started = False


app = FastAPI(
    title="LunarEngine API",
    description="REST API for the Lunar Sandbox evaluation engine",
    lifespan=lifespan,
)

# Register RFC 7807 error handlers
app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_exception_handler)  # type: ignore[arg-type]

# Include domain routers
app.include_router(batches_router)
app.include_router(episodes_router)
app.include_router(pool_router)
app.include_router(runs_router)
app.include_router(sandboxes_router)
app.include_router(tasks_router)
app.include_router(telemetry_router)


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """Return API health status.

    Reports whether the engine fully started and whether the SQLite
    stores are available for querying.
    """
    stores_available = False
    if _engine is not None:
        stores_available = _engine.trajectory_store is not None

    if _engine_started and stores_available:
        status = "ok"
    else:
        status = "degraded"

    return HealthResponse(
        status=status,
        engine_started=_engine_started,
        stores_available=stores_available,
    )


@app.websocket("/api/ws")
async def ws_route(websocket: WebSocket) -> None:
    """Multiplexed WebSocket endpoint for real-time event streaming."""
    await websocket_handler(websocket, app.state.ws_manager)

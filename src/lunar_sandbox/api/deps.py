"""Dependency injection for FastAPI route handlers.

Provides functions usable with ``Depends()`` that give route handlers
access to the engine singleton and its subsystem stores.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from lunar_sandbox.sdk.engine import LunarEngine
    from lunar_sandbox.telemetry.store import TelemetryStore
    from lunar_sandbox.trajectory.store import TrajectoryStore

__all__ = [
    "get_engine",
    "get_telemetry_store",
    "get_trajectory_store",
]


def get_engine() -> LunarEngine:
    """Return the engine singleton set during app lifespan.

    Raises:
        HTTPException: 503 if the engine has not been initialized.
    """
    from lunar_sandbox.api.app import _engine

    if _engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    return _engine


def get_trajectory_store() -> TrajectoryStore:
    """Return the trajectory store from the engine.

    Raises:
        HTTPException: 503 if the store is not available.
    """
    engine = get_engine()
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")
    return store


def get_telemetry_store() -> TelemetryStore:
    """Return an on-demand TelemetryStore.

    Opens a new TelemetryStore connection using the engine config's
    trajectory_dir.  Callers are responsible for closing it.

    Raises:
        HTTPException: 503 if the engine is not available.
    """
    from lunar_sandbox.telemetry.store import TelemetryStore

    engine = get_engine()
    db_path = engine._config.trajectory_dir / "trajectories.db"
    store = TelemetryStore(db_path)
    store.open()
    return store

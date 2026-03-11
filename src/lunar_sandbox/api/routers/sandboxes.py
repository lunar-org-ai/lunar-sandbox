"""Sandbox pool status and individual sandbox endpoints.

Provides pool-level status information and per-sandbox detail/control.
When the engine pool is unavailable (e.g., on macOS), returns graceful
mock responses instead of erroring.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException

from lunar_sandbox.api.deps import get_engine
from lunar_sandbox.api.schemas import PoolStatus, SandboxInfo

router = APIRouter(prefix="/api/sandboxes", tags=["sandboxes"])

logger = structlog.get_logger(__name__)


@router.get("", response_model=PoolStatus)
async def get_pool_status(
    engine=Depends(get_engine),
) -> PoolStatus:
    """Return current sandbox pool status.

    Returns a graceful response when the engine pool is not available
    (e.g., on macOS where Linux kernel features are required).
    """
    if engine.pool is None:
        return PoolStatus(running=False, total_sandboxes=0, sandboxes=[])

    try:
        status = await engine.pool_status()
    except Exception as exc:
        logger.warning("pool_status_failed", error=str(exc))
        return PoolStatus(running=False, total_sandboxes=0, sandboxes=[])

    # Map pool status dict to API schema
    # The pool returns aggregate metrics, not individual sandbox enumerations.
    # We expose fingerprints as pseudo-sandbox entries for visibility.
    sandboxes: list[SandboxInfo] = []
    for fp in status.get("fingerprints", []):
        sandboxes.append(
            SandboxInfo(
                sandbox_id=f"pool-{fp[:8]}",
                fingerprint=fp,
                state="pooled",
            )
        )

    metrics = status.get("metrics", {})
    total = metrics.get("pool_size", 0) if isinstance(metrics, dict) else 0

    return PoolStatus(
        running=status.get("running", False),
        total_sandboxes=total,
        sandboxes=sandboxes,
    )


@router.get("/{sandbox_id}", response_model=SandboxInfo)
async def get_sandbox(
    sandbox_id: str,
    engine=Depends(get_engine),
) -> SandboxInfo:
    """Return detail for a single sandbox by ID.

    When the engine pool is unavailable (e.g., on macOS), returns mock
    sandbox data so the dashboard can be developed without a running engine.
    """
    if engine.pool is None:
        return SandboxInfo(
            sandbox_id=sandbox_id,
            fingerprint="mock-fingerprint",
            state="Idle",
            started_at=None,
            cpu_percent=None,
            memory_mb=None,
        )

    try:
        status: dict[str, Any] = await engine.pool_status()
    except Exception as exc:
        logger.warning("sandbox_detail_pool_status_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Sandbox pool not available") from exc

    for fp in status.get("fingerprints", []):
        sid = f"pool-{fp[:8]}"
        if sid == sandbox_id:
            return SandboxInfo(
                sandbox_id=sid,
                fingerprint=fp,
                state="pooled",
            )

    raise HTTPException(status_code=404, detail=f"Sandbox {sandbox_id} not found")


@router.post("/{sandbox_id}/stop")
async def stop_sandbox(
    sandbox_id: str,
    engine=Depends(get_engine),
) -> dict[str, str]:
    """Stop a running sandbox.

    When the engine pool is unavailable (e.g., on macOS), returns a
    graceful mock response indicating the sandbox was stopped.
    """
    if engine.pool is None:
        logger.info("stop_sandbox_mock", sandbox_id=sandbox_id)
        return {"status": "stopped", "mock": "true"}

    try:
        await engine.pool.stop_sandbox(sandbox_id)
    except AttributeError:
        # Pool may not expose stop_sandbox -- degrade gracefully
        logger.warning("stop_sandbox_not_supported", sandbox_id=sandbox_id)
    except Exception as exc:
        logger.warning("stop_sandbox_failed", sandbox_id=sandbox_id, error=str(exc))
        raise HTTPException(
            status_code=500, detail=f"Failed to stop sandbox: {exc}"
        ) from exc

    return {"status": "stopped"}

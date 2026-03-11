"""Sandbox pool status endpoints.

Provides pool-level status information.  When the engine pool is
unavailable (e.g., on macOS), returns a graceful "not running" response
instead of erroring.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

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

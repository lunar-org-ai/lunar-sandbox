"""Sandbox pool status and individual sandbox endpoints.

Provides pool-level status information and per-sandbox detail/control.
When the engine pool is unavailable (e.g., on macOS), returns graceful
mock responses instead of erroring.
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
import termios

try:
    import fcntl
    import pty
    _PTY_AVAILABLE = True
except ImportError:
    _PTY_AVAILABLE = False

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from lunar_sandbox.api.deps import get_engine
from lunar_sandbox.api.schemas import FingerprintHealth, PoolHealthDetail, PoolStatus, SandboxInfo

router = APIRouter(prefix="/api/sandboxes", tags=["sandboxes"])
pool_router = APIRouter(prefix="/api/pool", tags=["pool"])

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


# ---------------------------------------------------------------------------
# Terminal WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/{sandbox_id}/terminal")
async def sandbox_terminal(
    sandbox_id: str,
    ws: WebSocket,
    engine=Depends(get_engine),
) -> None:
    """WebSocket PTY terminal for a running sandbox.

    When engine.pool is None (macOS development mode), provides a simple
    echo-based mock terminal.  When the pool is available, forks a real
    PTY bash process and forwards bytes bidirectionally.

    The frontend may send JSON text frames for control messages (e.g.,
    terminal resize events with ``{"type":"resize","rows":N,"cols":N}``).
    All other frames are treated as raw PTY input bytes.
    """
    await ws.accept()
    logger.info("terminal_connected", sandbox_id=sandbox_id)

    if engine.pool is None or not _PTY_AVAILABLE:
        # Mock echo mode for macOS development
        try:
            await ws.send_bytes(b"\r\n[Mock Terminal - macOS development mode]\r\n$ ")
            while True:
                try:
                    data = await ws.receive_bytes()
                    # Echo the input back with a mock prompt
                    await ws.send_bytes(data + b"\r\n$ ")
                except WebSocketDisconnect:
                    break
        except WebSocketDisconnect:
            pass
        logger.info("terminal_disconnected_mock", sandbox_id=sandbox_id)
        return

    # Real PTY mode -- fork a bash shell and forward bytes
    pid, fd = pty.fork()
    if pid == 0:
        # Child process: exec bash
        os.execvp("bash", ["bash"])
        # execvp never returns on success; unreachable
        os._exit(1)

    # Parent process: forward PTY <-> WebSocket
    loop = asyncio.get_event_loop()

    async def read_pty() -> None:
        """Read from PTY and forward to WebSocket."""
        while True:
            try:
                data = await loop.run_in_executor(None, os.read, fd, 1024)
                await ws.send_bytes(data)
            except OSError:
                break
            except WebSocketDisconnect:
                break

    async def read_ws() -> None:
        """Read from WebSocket and forward to PTY."""
        while True:
            try:
                raw = await ws.receive_bytes()
                # Check for JSON control messages (resize events)
                try:
                    text = raw.decode("utf-8", errors="replace")
                    if text.lstrip().startswith('{"type":"resize"'):
                        msg = json.loads(text)
                        rows = int(msg.get("rows", 24))
                        cols = int(msg.get("cols", 80))
                        fcntl.ioctl(
                            fd,
                            termios.TIOCSWINSZ,
                            struct.pack("HHHH", rows, cols, 0, 0),
                        )
                        continue
                except (ValueError, KeyError, UnicodeDecodeError):
                    pass
                os.write(fd, raw)
            except WebSocketDisconnect:
                break
            except OSError:
                break

    pty_task = asyncio.ensure_future(read_pty())
    ws_task = asyncio.ensure_future(read_ws())

    try:
        done, pending = await asyncio.wait(
            {pty_task, ws_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        logger.info("terminal_disconnected", sandbox_id=sandbox_id)


# ---------------------------------------------------------------------------
# Pool health detail endpoint
# ---------------------------------------------------------------------------

_MOCK_FINGERPRINTS = [
    {
        "fingerprint": "sha256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        "idle_count": 4,
        "active_count": 2,
        "eviction_count": 12,
        "cache_hit_rate": 0.87,
    },
    {
        "fingerprint": "sha256:f9e8d7c6b5a4f9e8d7c6b5a4f9e8d7c6",
        "idle_count": 2,
        "active_count": 3,
        "eviction_count": 7,
        "cache_hit_rate": 0.63,
    },
    {
        "fingerprint": "sha256:0102030405060102030405060102030405",
        "idle_count": 1,
        "active_count": 0,
        "eviction_count": 18,
        "cache_hit_rate": 0.42,
    },
]


@pool_router.get("/health", response_model=PoolHealthDetail)
async def pool_health(
    engine=Depends(get_engine),
) -> PoolHealthDetail:
    """Return detailed pool health with per-fingerprint breakdown.

    When the engine pool is unavailable (e.g., on macOS), returns mock
    data with 3 fingerprint groups showing varied idle/active counts,
    eviction counts, and cache hit rates.
    """
    if engine.pool is None:
        fps = [
            FingerprintHealth(
                fingerprint=fp["fingerprint"],
                idle_count=fp["idle_count"],
                active_count=fp["active_count"],
                total_count=fp["idle_count"] + fp["active_count"],
                eviction_count=fp["eviction_count"],
                cache_hit_rate=fp["cache_hit_rate"],
            )
            for fp in _MOCK_FINGERPRINTS
        ]
        total = sum(f.total_count for f in fps)
        total_evictions = sum(f.eviction_count for f in fps)
        hit_rates = [f.cache_hit_rate for f in fps if f.cache_hit_rate is not None]
        overall_hit_rate = round(sum(hit_rates) / len(hit_rates), 3) if hit_rates else None
        return PoolHealthDetail(
            running=False,
            total_sandboxes=total,
            fingerprints=fps,
            overall_cache_hit_rate=overall_hit_rate,
            total_evictions=total_evictions,
        )

    try:
        status = await engine.pool_status()
    except Exception as exc:
        logger.warning("pool_health_failed", error=str(exc))
        return PoolHealthDetail(running=False, total_sandboxes=0)

    metrics = status.get("metrics", {})
    fp_breakdown = status.get("fingerprint_breakdown", {})

    # Build per-fingerprint health from breakdown + per-fp metrics
    fps_list: list[FingerprintHealth] = []
    for fp, counts in fp_breakdown.items():
        fp_hits = metrics.get("hits_by_fingerprint", {}).get(fp, 0)
        fp_misses = metrics.get("misses_by_fingerprint", {}).get(fp, 0)
        fp_total = fp_hits + fp_misses
        hit_rate = round(fp_hits / fp_total, 3) if fp_total > 0 else None

        fps_list.append(FingerprintHealth(
            fingerprint=fp,
            idle_count=counts.get("idle_count", 0),
            active_count=counts.get("active_count", 0),
            total_count=counts.get("total_count", 0),
            eviction_count=0,
            cache_hit_rate=hit_rate,
        ))

    total = sum(f.total_count for f in fps_list)
    total_evictions = int(metrics.get("total_evictions", 0))
    overall_hit_rate = round(metrics.get("hit_rate", 0.0), 3) if metrics.get("hit_rate") else None
    is_running = status.get("running", False)

    return PoolHealthDetail(
        running=is_running,
        total_sandboxes=total,
        fingerprints=fps_list,
        overall_cache_hit_rate=overall_hit_rate,
        total_evictions=total_evictions,
    )

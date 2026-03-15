"""CUA (Computer-Using Agent) API endpoints.

Provides REST and WebSocket endpoints for CUA episode management:

- POST   /api/cua/episodes                          -- Launch a CUA episode
- GET    /api/cua/episodes                          -- List CUA episodes
- GET    /api/cua/episodes/{episode_id}             -- Episode detail
- GET    /api/cua/episodes/{episode_id}/screenshots/{filename}  -- Serve screenshot
- PATCH  /api/cua/episodes/{episode_id}/score       -- Persist manual review score
- WS     /api/cua/vnc/{episode_id}                  -- Proxy VNC traffic to container

Concurrent episode support: each launched episode receives a unique host port
via _allocate_free_port(), preventing Docker port collisions when multiple CUA
episodes run simultaneously.
"""

from __future__ import annotations

import asyncio
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from lunar_sandbox.api.deps import get_engine
from lunar_sandbox.api.pagination import PaginationParams, pagination_query
from lunar_sandbox.api.schemas import (
    CUAEpisodeInfo,
    CUALaunchRequest,
    CUALaunchResponse,
    CUAScoreRequest,
    CUAScoreResponse,
    EpisodeSummary,
    PaginatedEpisodes,
)

__all__ = ["router"]

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/cua", tags=["cua"])

# ---------------------------------------------------------------------------
# Module-level registry of active CUA episodes
# ---------------------------------------------------------------------------

# Maps episode_id -> dict with keys: sandbox, task, runner_task
_active_episodes: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _allocate_free_port() -> int:
    """Find a free host port by binding to port 0, then releasing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _parse_resolution(resolution: str) -> tuple[int, int]:
    """Parse a 'WxH' resolution string into (width, height)."""
    try:
        w, h = resolution.split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return 1280, 800


async def _placeholder_agent(obs: Any) -> dict[str, Any]:
    """Minimal placeholder agent that stops immediately.

    This is used for v3.0 episode launch where the real agent is user code
    running externally.  The agent simply waits briefly and returns stop so
    the runner's action loop terminates cleanly.
    """
    await asyncio.sleep(0.1)
    return {"action": "stop"}


# ---------------------------------------------------------------------------
# POST /api/cua/episodes -- Launch a CUA episode
# ---------------------------------------------------------------------------


@router.post("/episodes", response_model=CUALaunchResponse)
async def launch_cua_episode(
    req: CUALaunchRequest,
    engine=Depends(get_engine),
) -> CUALaunchResponse:
    """Launch a new CUA episode.

    Creates a CUASandbox, starts the desktop stack, then launches a
    CUAEpisodeRunner as a background asyncio task.  Returns immediately
    with the episode_id and WebSocket VNC URL.

    Each episode gets a unique host port (via _allocate_free_port) so
    multiple concurrent episodes do not collide on the Docker host.
    """
    # Lazy imports to keep module load fast and avoid Linux-only code at import
    from lunar_sandbox.cua.runner import CUAEpisodeRunner
    from lunar_sandbox.cua.task import (
        CUATask,
        ManualReward,
        ScreenshotReward,
        ScriptReward,
    )
    from lunar_sandbox.sandbox.cua_config import CUASandboxConfig
    from lunar_sandbox.sandbox.cua_sandbox import CUASandbox

    # -- Build reward variant ------------------------------------------------
    reward: ManualReward | ScriptReward | ScreenshotReward
    if req.reward_type == "script":
        # Write script_content to a temp file on the host, pass path to container
        script_content = req.script_content or ""
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".sh",
            prefix="cua_reward_",
            delete=False,
        )
        tmp.write(script_content)
        tmp.close()
        reward = ScriptReward(script_path="/tmp/reward_script.sh")
    elif req.reward_type == "screenshot_match":
        reward = ScreenshotReward(
            reference_image=req.reference_image_url or "",
            threshold=req.screenshot_threshold,
        )
    else:
        reward = ManualReward()

    # -- Parse resolution ----------------------------------------------------
    width, height = _parse_resolution(req.resolution)

    # -- Allocate a unique host port to avoid concurrent episode collisions --
    novnc_port = _allocate_free_port()

    # -- Build CUATask -------------------------------------------------------
    task = CUATask(
        instruction=req.instruction,
        start_url=req.start_url,
        reward=reward,
        max_steps=req.max_steps,
        time_limit=req.time_limit,
        resolution=req.resolution,
    )

    # -- Create and start CUASandbox ----------------------------------------
    config = CUASandboxConfig(
        width=width,
        height=height,
        novnc_port=novnc_port,
    )
    sandbox = CUASandbox(config)

    try:
        sandbox.create()
        sandbox.health_check()
    except Exception as exc:
        log.error("cua_sandbox_create_failed", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create CUA sandbox: {exc}",
        ) from exc

    # Determine trajectory dir from engine config (may be None)
    trajectory_dir: Path | None = None
    if hasattr(engine, "_config") and engine._config is not None:
        td = getattr(engine._config, "trajectory_dir", None)
        if td is not None:
            trajectory_dir = Path(td)

    # Generate episode_id from the runner (we pre-generate to return it now)
    import uuid
    episode_id = f"cua-ep-{uuid.uuid4().hex[:8]}"

    runner = CUAEpisodeRunner(
        task=task,
        sandbox=sandbox,
        agent=_placeholder_agent,
        episode_id=episode_id,
        trajectory_dir=trajectory_dir,
    )

    # -- Register episode in module-level registry ---------------------------
    _active_episodes[episode_id] = {
        "sandbox": sandbox,
        "task": task,
        "novnc_port": novnc_port,
        "runner_task": None,
    }

    # -- Start episode runner as background task (do NOT await) -------------
    async def _run_episode() -> None:
        try:
            result = await runner.run()
            log.info(
                "cua_episode_completed",
                episode_id=episode_id,
                outcome=result.outcome,
            )
        except Exception as exc:
            log.error("cua_episode_runner_failed", episode_id=episode_id, error=str(exc))
        finally:
            # Clean up registry and sandbox
            _active_episodes.pop(episode_id, None)
            try:
                sandbox.destroy()
            except Exception as cleanup_exc:
                log.warning(
                    "cua_sandbox_destroy_failed",
                    episode_id=episode_id,
                    error=str(cleanup_exc),
                )

    runner_task = asyncio.create_task(_run_episode())
    _active_episodes[episode_id]["runner_task"] = runner_task

    log.info(
        "cua_episode_launched",
        episode_id=episode_id,
        novnc_port=novnc_port,
    )

    return CUALaunchResponse(
        episode_id=episode_id,
        vnc_url=f"/api/cua/vnc/{episode_id}",
    )


# ---------------------------------------------------------------------------
# GET /api/cua/episodes -- List CUA episodes
# ---------------------------------------------------------------------------


@router.get("/episodes", response_model=PaginatedEpisodes)
async def list_cua_episodes(
    pagination: PaginationParams = Depends(pagination_query),
    sort_by: str = "started_at",
    sort_order: str = "desc",
    engine=Depends(get_engine),
) -> PaginatedEpisodes:
    """List CUA episodes (episode_type='cua') with pagination."""
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")

    episodes = store.query_episodes(episode_type="cua")

    reverse = sort_order.lower() != "asc"
    episodes.sort(key=lambda ep: ep.get(sort_by) or 0, reverse=reverse)

    total = len(episodes)
    page = episodes[pagination.offset : pagination.offset + pagination.limit]

    return PaginatedEpisodes(
        items=[EpisodeSummary(**ep) for ep in page],
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )


# ---------------------------------------------------------------------------
# GET /api/cua/episodes/{episode_id} -- Episode detail
# ---------------------------------------------------------------------------


@router.get("/episodes/{episode_id}", response_model=CUAEpisodeInfo)
async def get_cua_episode(
    episode_id: str,
    engine=Depends(get_engine),
) -> CUAEpisodeInfo:
    """Get CUA episode detail including review_notes."""
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")

    episodes = store.query_episodes(episode_id=episode_id)
    if not episodes:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

    ep = episodes[0]
    return CUAEpisodeInfo(
        episode_id=ep["episode_id"],
        task_name=ep["task_name"],
        outcome=ep["outcome"],
        score=ep.get("score"),
        review_notes=ep.get("review_notes"),
        step_count=ep.get("step_count", 0),
        duration_ms=ep.get("duration_ms", 0.0),
        started_at=ep.get("started_at", 0.0),
        ended_at=ep.get("ended_at"),
        episode_type=ep.get("episode_type", "cua"),
    )


# ---------------------------------------------------------------------------
# GET /api/cua/episodes/{episode_id}/screenshots/{filename} -- Serve screenshot
# ---------------------------------------------------------------------------


@router.get("/episodes/{episode_id}/screenshots/{filename}")
async def get_cua_screenshot(
    episode_id: str,
    filename: str,
    engine=Depends(get_engine),
) -> FileResponse:
    """Serve a screenshot file from the episode trajectory directory."""
    if not hasattr(engine, "_config") or engine._config is None:
        raise HTTPException(status_code=503, detail="Engine config not available")

    trajectory_dir = getattr(engine._config, "trajectory_dir", None)
    if trajectory_dir is None:
        raise HTTPException(status_code=503, detail="Trajectory directory not configured")

    screenshot_path = Path(trajectory_dir) / episode_id / "screenshots" / filename

    if not screenshot_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Screenshot {filename} not found for episode {episode_id}",
        )

    # Determine media type from extension
    suffix = screenshot_path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    elif suffix == ".png":
        media_type = "image/png"
    else:
        media_type = "application/octet-stream"

    return FileResponse(path=str(screenshot_path), media_type=media_type)


# ---------------------------------------------------------------------------
# PATCH /api/cua/episodes/{episode_id}/score -- Persist manual review score
# ---------------------------------------------------------------------------


@router.patch("/episodes/{episode_id}/score", response_model=CUAScoreResponse)
async def score_cua_episode(
    episode_id: str,
    req: CUAScoreRequest,
    engine=Depends(get_engine),
) -> CUAScoreResponse:
    """Persist a manual review score for a CUA episode.

    Also returns the next unreviewed episode ID so the reviewer UI can
    navigate forward through the review queue.
    """
    store = engine.trajectory_store
    if store is None:
        raise HTTPException(status_code=503, detail="Trajectory store not available")

    updated = store.update_episode_score(episode_id, req.score, req.notes)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

    next_ep = store.query_next_unreviewed(current_episode_id=episode_id)
    next_episode_id = next_ep["episode_id"] if next_ep else None

    return CUAScoreResponse(
        episode_id=episode_id,
        score=req.score,
        next_episode_id=next_episode_id,
    )


# ---------------------------------------------------------------------------
# WebSocket /api/cua/vnc/{episode_id} -- Proxy VNC traffic to container
# ---------------------------------------------------------------------------


@router.websocket("/vnc/{episode_id}")
async def vnc_proxy(
    websocket: WebSocket,
    episode_id: str,
) -> None:
    """Bidirectional WebSocket-to-TCP proxy for noVNC traffic.

    Connects to the container's internal websockify port (6080) via TCP
    and bridges binary WebSocket frames in both directions.  Uses
    asyncio.open_connection for non-blocking I/O.
    """
    await websocket.accept(subprotocol="binary")

    entry = _active_episodes.get(episode_id)
    if entry is None:
        await websocket.close(code=4404, reason=f"Episode {episode_id} not active")
        return

    sandbox = entry["sandbox"]
    container_name = sandbox._config.sandbox_id

    # Resolve container's internal IP via docker inspect
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format={{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        container_ip = result.stdout.strip()
    except Exception as exc:
        log.error("vnc_proxy_inspect_failed", episode_id=episode_id, error=str(exc))
        await websocket.close(code=4500, reason="Failed to resolve container IP")
        return

    if not container_ip:
        await websocket.close(code=4404, reason="Container IP not found")
        return

    # Open TCP connection to container's websockify port
    try:
        reader, writer = await asyncio.open_connection(container_ip, 6080)
    except Exception as exc:
        log.error(
            "vnc_proxy_tcp_connect_failed",
            episode_id=episode_id,
            container_ip=container_ip,
            error=str(exc),
        )
        await websocket.close(code=4500, reason="Failed to connect to VNC server")
        return

    log.info(
        "vnc_proxy_connected",
        episode_id=episode_id,
        container_ip=container_ip,
    )

    # -- Bidirectional proxy tasks -------------------------------------------

    async def browser_to_container() -> None:
        """Read bytes from WebSocket, write to TCP stream."""
        try:
            while True:
                data = await websocket.receive_bytes()
                writer.write(data)
                await writer.drain()
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            writer.close()

    async def container_to_browser() -> None:
        """Read bytes from TCP stream, send to WebSocket."""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                await websocket.send_bytes(data)
        except (WebSocketDisconnect, Exception):
            pass

    try:
        browser_task = asyncio.create_task(browser_to_container())
        container_task = asyncio.create_task(container_to_browser())

        # Wait until either direction closes
        done, pending = await asyncio.wait(
            [browser_task, container_task],
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
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        log.info("vnc_proxy_disconnected", episode_id=episode_id)

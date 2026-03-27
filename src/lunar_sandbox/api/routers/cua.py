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
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

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


class _ManualAgent:
    """Agent that keeps the sandbox alive until explicitly stopped.

    Used for dashboard-launched episodes where the user interacts via noVNC.
    The agent idles each step (sleeping briefly) and returns a no-op action.
    Call ``stop()`` to make the next agent call return ``{"action": "stop"}``.
    """

    def __init__(self) -> None:
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        self._stop_event.set()

    async def __call__(self, obs: Any) -> dict[str, Any]:
        # Wait up to 2s or until stopped — keeps the sandbox alive
        # without busy-looping.
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        if self._stop_event.is_set():
            return {"action": "stop"}
        return {"action": "screenshot"}


# ---------------------------------------------------------------------------
# POST /api/cua/episodes -- Launch a CUA episode
# ---------------------------------------------------------------------------


@router.post("/episodes", response_model=CUALaunchResponse)
async def launch_cua_episode(
    request: Request,
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

    # -- Allocate a unique host port for VNC proxy access --------------------
    host_vnc_port = _allocate_free_port()

    # -- Build CUATask -------------------------------------------------------
    task = CUATask(
        instruction=req.instruction,
        start_url=req.start_url,
        reward=reward,
        max_steps=req.max_steps,
        time_limit=req.time_limit,
        resolution=req.resolution,
    )

    # -- Generate episode_id early (needed by sandbox config) ----------------
    import uuid
    episode_id = f"cua-ep-{uuid.uuid4().hex[:8]}"

    # -- Create sandbox (Linux Docker or Windows VM) -------------------------
    sandbox: Any
    handler: Any = None
    rdp_url: str | None = None

    if req.platform == "windows":
        from lunar_sandbox.windows.action_handler import WindowsCUAActionHandler
        from lunar_sandbox.windows.config import WindowsCUAConfig

        if not req.windows_ssh_host:
            raise HTTPException(
                status_code=400,
                detail="windows_ssh_host is required when platform='windows'",
            )

        win_config = WindowsCUAConfig(
            sandbox_id=episode_id,
            ssh_host=req.windows_ssh_host,
            ssh_port=req.windows_ssh_port,
            ssh_user=req.windows_ssh_user,
            ssh_password=req.windows_ssh_password,
            ssh_key_path=req.windows_ssh_key_path,
            width=width,
            height=height,
        )

        # Use AzureWindowsCUASandbox when Azure VM fields are provided
        # (az run-command for actions, SSH for screenshots).
        # Otherwise fall back to pure SSH-based WindowsCUASandbox.
        if req.windows_azure_resource_group and req.windows_azure_vm_name:
            from lunar_sandbox.windows.azure_sandbox import AzureWindowsCUASandbox
            sandbox = AzureWindowsCUASandbox(
                win_config,
                resource_group=req.windows_azure_resource_group,
                vm_name=req.windows_azure_vm_name,
            )
        else:
            from lunar_sandbox.windows.sandbox import WindowsCUASandbox
            sandbox = WindowsCUASandbox(win_config)

        try:
            sandbox.create()
            sandbox.health_check()
        except Exception as exc:
            log.error("windows_sandbox_create_failed", error=str(exc))
            raise HTTPException(
                status_code=500,
                detail=f"Failed to connect to Windows VM: {exc}",
            ) from exc

        handler = WindowsCUAActionHandler(sandbox, win_config)
        rdp_url = win_config.rdp_url
        host_vnc_port = 0  # No VNC for Windows
    else:
        config = CUASandboxConfig(
            sandbox_id=episode_id,
            width=width,
            height=height,
            host_vnc_port=host_vnc_port,
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

    # -- Choose agent based on mode -------------------------------------------
    agent: Any
    if req.agent_mode == "model":
        from lunar_sandbox.cua.model_agent import ModelAgent
        os_hint = "windows" if req.platform == "windows" else "linux"

        try:
            if req.model_provider == "azure_openai":
                from lunar_sandbox.cua.providers.azure_openai import AzureOpenAIProvider
                if not req.azure_openai_endpoint or not req.azure_openai_deployment:
                    raise HTTPException(
                        status_code=400,
                        detail="azure_openai_endpoint and azure_openai_deployment are "
                        "required when model_provider='azure_openai'",
                    )
                provider = AzureOpenAIProvider(
                    endpoint=req.azure_openai_endpoint,
                    deployment=req.azure_openai_deployment,
                    api_key=req.azure_openai_api_key or None,
                    instruction=req.instruction,
                    screen_size=(width, height),
                    os_hint=os_hint,
                )
                agent = ModelAgent(provider=provider)
            else:
                # Default: Anthropic
                from lunar_sandbox.cua.providers.anthropic import AnthropicProvider
                provider = AnthropicProvider(
                    instruction=req.instruction,
                    screen_size=(width, height),
                    api_key=req.api_key or None,
                    os_hint=os_hint,
                )
                agent = ModelAgent(provider=provider)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc
    else:
        agent = _ManualAgent()

    # Wire EventHub for real-time CUA event streaming
    event_hub = getattr(request.app.state, "event_hub", None)

    runner = CUAEpisodeRunner(
        task=task,
        sandbox=sandbox,
        agent=agent,
        episode_id=episode_id,
        trajectory_dir=trajectory_dir,
        event_hub=event_hub,
        handler=handler,
    )

    # -- Register episode in module-level registry ---------------------------
    _active_episodes[episode_id] = {
        "sandbox": sandbox,
        "task": task,
        "host_vnc_port": host_vnc_port,
        "runner_task": None,
        "agent": agent,
        "rdp_url": rdp_url,
        "handler": handler,
        "platform": req.platform,
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
        host_vnc_port=host_vnc_port,
    )

    vnc_url = f"ws://localhost:{host_vnc_port}" if host_vnc_port else ""

    return CUALaunchResponse(
        episode_id=episode_id,
        vnc_url=vnc_url,
        rdp_url=rdp_url,
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
    if episodes:
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

    # Episode may still be running or recently completed (external episodes)
    entry = _active_episodes.get(episode_id)
    if entry is not None:
        task = entry.get("task")
        outcome = entry.get("_outcome", "running") if entry.get("_ended") else "running"
        return CUAEpisodeInfo(
            episode_id=episode_id,
            task_name=task.name if task else "",
            outcome=outcome,
            score=None,
            review_notes=None,
            step_count=entry.get("_step_count", 0),
            duration_ms=0.0,
            started_at=0.0,
            ended_at=None,
            episode_type="cua",
            platform=entry.get("platform", "linux"),
        )

    raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")


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

    # Check multiple locations (notebook may save elsewhere)
    candidates = [
        Path(trajectory_dir) / episode_id / "screenshots" / filename,
        Path("examples/trajectories") / episode_id / "screenshots" / filename,
    ]
    screenshot_path = None
    for c in candidates:
        if c.exists():
            screenshot_path = c
            break

    if screenshot_path is None:
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

    # Signal the manual agent to stop so the sandbox gets cleaned up
    entry = _active_episodes.get(episode_id)
    if entry and "agent" in entry:
        entry["agent"].stop()

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

    # Connect to x11vnc via the host-mapped port on localhost.
    # The proxy does WS-to-TCP bridging: noVNC sends RFB over WebSocket,
    # the proxy strips WS framing and forwards raw RFB to x11vnc (TCP).
    host_vnc_port = entry.get("host_vnc_port", 5900)

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", host_vnc_port)
    except Exception as exc:
        log.error(
            "vnc_proxy_tcp_connect_failed",
            episode_id=episode_id,
            port=host_vnc_port,
            error=str(exc),
        )
        await websocket.close(code=4500, reason="Failed to connect to VNC server")
        return

    log.info(
        "vnc_proxy_connected",
        episode_id=episode_id,
        port=host_vnc_port,
    )

    # -- Bidirectional proxy tasks -------------------------------------------

    async def browser_to_container() -> None:
        """Read bytes from WebSocket, write to TCP stream."""
        try:
            while True:
                data = await websocket.receive_bytes()
                writer.write(data)
                await writer.drain()
        except WebSocketDisconnect:
            log.debug("vnc_proxy_browser_disconnected", episode_id=episode_id)
        except Exception as exc:
            log.warning("vnc_proxy_browser_error", episode_id=episode_id, error=str(exc), type=type(exc).__name__)
        finally:
            writer.close()

    async def container_to_browser() -> None:
        """Read bytes from TCP stream, send to WebSocket."""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    log.debug("vnc_proxy_container_eof", episode_id=episode_id)
                    break
                await websocket.send_bytes(data)
        except WebSocketDisconnect:
            log.debug("vnc_proxy_ws_disconnected_during_relay", episode_id=episode_id)
        except Exception as exc:
            log.warning("vnc_proxy_container_error", episode_id=episode_id, error=str(exc), type=type(exc).__name__)

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


# ---------------------------------------------------------------------------
# WebSocket /api/cua/screen/{episode_id} -- Stream screenshots (Windows VMs)
# ---------------------------------------------------------------------------

_SCREEN_STREAM_FPS = 2  # Target frames per second


@router.websocket("/screen/{episode_id}")
async def screen_stream(
    websocket: WebSocket,
    episode_id: str,
) -> None:
    """Stream live screenshots from a Windows VM over WebSocket.

    Sends JSON messages with ``{"type": "frame", "data": "<base64 jpeg>"}``
    at ~2 FPS.  The handler's screenshot method is called in a thread pool
    to avoid blocking the event loop (it executes SSH commands).
    """
    await websocket.accept()

    entry = _active_episodes.get(episode_id)
    if entry is None:
        await websocket.close(code=4404, reason=f"Episode {episode_id} not active")
        return

    handler = entry.get("handler")
    is_external = entry.get("_external", False)

    log.info("screen_stream_connected", episode_id=episode_id, external=is_external)

    loop = asyncio.get_event_loop()

    if handler and not is_external:
        # In-process episode: capture live screenshots via handler
        interval = 1.0 / _SCREEN_STREAM_FPS
        try:
            while True:
                if episode_id not in _active_episodes:
                    await websocket.send_json({"type": "ended"})
                    break
                try:
                    b64_data = await loop.run_in_executor(
                        None,
                        lambda: handler.screenshot(wait_for_idle=0.1),
                    )
                    await websocket.send_json({"type": "frame", "data": b64_data})
                except Exception as exc:
                    log.warning(
                        "screen_stream_capture_error",
                        episode_id=episode_id,
                        error=str(exc),
                    )
                    await websocket.send_json({"type": "error", "message": str(exc)})
                await asyncio.sleep(interval)
        except WebSocketDisconnect:
            pass
    else:
        # External episode (notebook): watch screenshot files on disk
        import base64

        # Check multiple possible trajectory locations (notebook may run
        # from a different working directory than the API server)
        candidates = [
            Path("trajectories") / episode_id / "screenshots",
            Path("examples/trajectories") / episode_id / "screenshots",
        ]
        # Also check the engine's configured trajectory dir
        engine = getattr(websocket.app.state, "engine", None)
        if engine and hasattr(engine, "_config") and engine._config:
            cfg_td = getattr(engine._config, "trajectory_dir", None)
            if cfg_td:
                candidates.insert(0, Path(cfg_td) / episode_id / "screenshots")

        traj_dir: Path | None = None
        for c in candidates:
            if c.exists():
                traj_dir = c
                break
        if traj_dir is None:
            traj_dir = candidates[0]  # default, will be checked in the loop
        seen_files: set[str] = set()

        try:
            while True:
                if episode_id not in _active_episodes:
                    await websocket.send_json({"type": "ended"})
                    break

                # Check for new screenshot files
                if traj_dir.exists():
                    files = sorted(traj_dir.glob("step_*.jpg"))
                    for f in files:
                        if f.name not in seen_files:
                            seen_files.add(f.name)
                            b64_data = base64.b64encode(f.read_bytes()).decode("ascii")
                            await websocket.send_json({"type": "frame", "data": b64_data})

                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            pass

    log.info("screen_stream_disconnected", episode_id=episode_id)


# ---------------------------------------------------------------------------
# POST /api/cua/events -- Publish a CUA event (for external runners)
# ---------------------------------------------------------------------------


class CUAEventPayload(BaseModel):
    """Event posted by external runners (e.g. notebooks) to the dashboard."""
    type: str  # "cua_episode_start", "cua_step", "cua_episode_end"
    topic: str  # "cua:<episode_id>"
    payload: dict[str, Any]


@router.post("/events", status_code=204)
async def post_cua_event(
    request: Request,
    event: CUAEventPayload,
) -> None:
    """Publish a CUA event to the WebSocket event hub.

    Allows external episode runners (notebooks, CLI) to push events
    to the dashboard's live activity panel without running inside
    the API server process.

    Also registers external episodes in ``_active_episodes`` so the
    episode detail endpoint returns "running" instead of 404.
    """
    # Extract episode_id from topic ("cua:<episode_id>")
    episode_id = event.topic.split(":", 1)[-1] if ":" in event.topic else ""

    # Register external episode so GET /episodes/{id} works
    if episode_id and episode_id not in _active_episodes:
        _active_episodes[episode_id] = {
            "sandbox": None,
            "task": None,
            "host_vnc_port": 0,
            "runner_task": None,
            "agent": None,
            "rdp_url": None,
            "handler": None,
            "platform": event.payload.get("platform", "windows"),
            "_external": True,  # marker for externally-launched episodes
        }

    # Update platform if provided in payload
    entry = _active_episodes.get(episode_id)
    if entry and event.payload.get("platform"):
        entry["platform"] = event.payload["platform"]

    # When episode ends, update the entry but keep it for 60s
    # so the dashboard can still fetch info and screenshots.
    if event.type == "cua_episode_end" and episode_id:
        entry = _active_episodes.get(episode_id)
        if entry:
            entry["_ended"] = True
            entry["_outcome"] = event.payload.get("outcome", "completed")
            entry["_step_count"] = event.payload.get("step_count", 0)

            async def _cleanup_later(eid: str) -> None:
                await asyncio.sleep(60)
                _active_episodes.pop(eid, None)

            asyncio.ensure_future(_cleanup_later(episode_id))

    event_hub = getattr(request.app.state, "event_hub", None)
    if event_hub is not None:
        event_hub.publish_event(event.type, event.topic, event.payload)

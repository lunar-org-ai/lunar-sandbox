"""Run launch endpoint.

Provides a POST /api/runs endpoint that accepts a RunRequest body and
immediately returns run/episode IDs.  Creates an episode record in the
trajectory store and schedules execution in a Docker sandbox.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends

from lunar_sandbox.api.deps import get_engine
from lunar_sandbox.api.schemas import RunLaunchResponse, RunRequest

router = APIRouter(prefix="/api/runs", tags=["runs"])

logger = structlog.get_logger(__name__)


@router.post("", response_model=RunLaunchResponse)
async def launch_run(
    body: RunRequest,
    background_tasks: BackgroundTasks,
    engine=Depends(get_engine),
) -> RunLaunchResponse:
    """Launch an evaluation run and return IDs immediately."""
    run_id = f"run-{uuid4().hex[:8]}"
    episode_id = f"ep-{uuid4().hex[:8]}"

    # Always create episode record so the dashboard can show it
    store = engine.trajectory_store
    if store is not None:
        now = time.time()
        store.ingest_episode(
            episode_metadata={
                "episode_id": episode_id,
                "task_name": body.task_name,
                "outcome": "running",
                "score": None,
                "step_count": 0,
                "duration_ms": 0.0,
                "started_at": now,
                "ended_at": None,
                "is_complete": 0,
                "sandbox_id": "",
            },
            steps=[],
        )

    if engine.pool is not None:
        background_tasks.add_task(
            _execute_in_sandbox,
            engine=engine,
            episode_id=episode_id,
            run_id=run_id,
            task_name=body.task_name,
            env_vars=body.env_vars or {},
            timeout=body.timeout or 1800,
        )

    logger.info(
        "launch_run",
        task_name=body.task_name,
        run_id=run_id,
        episode_id=episode_id,
        has_pool=engine.pool is not None,
    )
    return RunLaunchResponse(run_id=run_id, episode_id=episode_id)


async def _execute_in_sandbox(
    *,
    engine: Any,
    episode_id: str,
    run_id: str,
    task_name: str,
    env_vars: dict[str, str],
    timeout: int,
) -> None:
    """Execute a task in a Docker sandbox and update the episode record.

    Steps:
        1. Load task definition from the tasks table.
        2. Acquire a sandbox from the pool.
        3. Inject task instructions as a file.
        4. Run the test_command (if any) to score.
        5. Update the episode record with results.
        6. Release the sandbox.
    """
    store = engine.trajectory_store
    sandbox = None
    started_at = time.time()
    steps: list[dict[str, Any]] = []

    try:
        # 1. Load task from tasks table
        task = _get_task(store, task_name)
        if task is None:
            _update_episode(store, episode_id, task_name, started_at, "error", None, 0,
                            steps, sandbox_id="")
            logger.error("task_not_found", task_name=task_name, run_id=run_id)
            return

        # 2. Acquire a sandbox
        fingerprint = f"task:{task_name}"
        sandbox = await engine.pool.acquire(fingerprint)
        sandbox_id = getattr(
            getattr(sandbox, "config", None), "sandbox_id", ""
        )
        logger.info("sandbox_acquired", sandbox_id=sandbox_id, run_id=run_id)

        # 3. Inject task: write instructions to /workspace/TASK.md
        instructions = task.get("instructions", "")
        if instructions:
            result = await asyncio.to_thread(
                sandbox.execute,
                f"cat > /workspace/TASK.md << 'LUNAR_EOF'\n{instructions}\nLUNAR_EOF",
                timeout=10.0,
            )
            steps.append(_make_step(episode_id, len(steps), "inject_instructions", result))

        # 3b. Install dependencies detected from test_command
        test_command = task.get("test_command", "")
        deps = _detect_deps(test_command)
        if deps:
            install_cmd = f"pip install -q {' '.join(deps)}"
            result = await asyncio.to_thread(
                sandbox.execute, install_cmd, timeout=120.0,
            )
            steps.append(_make_step(episode_id, len(steps), "install_deps", result))
            if result.get("exit_code") != 0:
                logger.warning(
                    "deps_install_failed",
                    deps=deps,
                    stderr=result.get("stderr", "")[:200],
                )

        # 4. Set environment variables and run test command
        score: float | None = None
        outcome = "completed"

        if test_command:
            # Build command with env vars
            env_prefix = " ".join(f"{k}={v}" for k, v in env_vars.items())
            full_cmd = f"{env_prefix} {test_command}" if env_prefix else test_command

            result = await asyncio.to_thread(
                sandbox.execute, full_cmd, timeout=float(timeout),
            )
            steps.append(_make_step(episode_id, len(steps), "test_command", result))

            if result.get("timed_out"):
                outcome = "timeout"
                score = 0.0
            elif result.get("exit_code") == 0:
                outcome = "completed"
                score = 1.0
            else:
                outcome = "failed"
                score = 0.0
        else:
            # No test command — just mark as completed
            outcome = "completed"
            score = None

        # 5. Update episode record
        _update_episode(store, episode_id, task_name, started_at, outcome, score,
                        len(steps), steps, sandbox_id=sandbox_id)

        logger.info(
            "run_completed",
            run_id=run_id,
            episode_id=episode_id,
            outcome=outcome,
            score=score,
            step_count=len(steps),
        )

    except Exception as exc:
        logger.error("run_eval_failed", run_id=run_id, error=str(exc))
        _update_episode(store, episode_id, task_name, started_at, "error", None,
                        len(steps), steps, sandbox_id="")

    finally:
        # 6. Release the sandbox back to the pool
        if sandbox is not None:
            try:
                await engine.pool.release(sandbox)
            except Exception:
                pass


def _get_task(store: Any, task_name: str) -> dict[str, Any] | None:
    """Look up a task by name from the trajectory store."""
    if store is None:
        return None
    tasks = store.list_tasks()
    for t in tasks:
        if t["name"] == task_name:
            return t
    return None


def _update_episode(
    store: Any,
    episode_id: str,
    task_name: str,
    started_at: float,
    outcome: str,
    score: float | None,
    step_count: int,
    steps: list[dict[str, Any]],
    sandbox_id: str = "",
) -> None:
    """Update an existing episode record with execution results."""
    if store is None:
        return
    ended_at = time.time()
    duration_ms = (ended_at - started_at) * 1000
    is_complete = 1 if outcome in ("completed", "failed", "timeout") else 0

    store.ingest_episode(
        episode_metadata={
            "episode_id": episode_id,
            "task_name": task_name,
            "outcome": outcome,
            "score": score,
            "step_count": step_count,
            "duration_ms": duration_ms,
            "started_at": started_at,
            "ended_at": ended_at,
            "is_complete": is_complete,
            "sandbox_id": sandbox_id,
        },
        steps=steps,
    )


def _detect_deps(test_command: str) -> list[str]:
    """Detect Python packages needed by the test command."""
    deps: list[str] = []
    if "pytest" in test_command:
        deps.append("pytest")
    if "unittest" in test_command and "pytest" not in deps:
        deps.append("pytest")
    return deps


def _make_step(
    episode_id: str,
    step_idx: int,
    action: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Create a step dict from an execution result."""
    return {
        "episode_id": episode_id,
        "step_idx": step_idx,
        "timestamp": time.time(),
        "action": action,
        "action_params": {},
        "observation": {
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "exit_code": result.get("exit_code"),
        },
        "duration_ms": 0.0,
        "reward": None,
        "source": "shell",
        "sandbox_id": "",
        "state": {},
        "file_diff": None,
        "cpu_time_ms": None,
    }

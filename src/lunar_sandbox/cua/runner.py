"""CUAEpisodeRunner: async episode orchestrator for Computer-Using Agent tasks.

This module is the CUA equivalent of :mod:`lunar_sandbox.episode.runner` for
coding tasks.  Instead of dispatching to ActionClient over a Unix socket, it:

1. Captures a pre-action screenshot via :class:`CUAActionHandler`.
2. Constructs a :class:`CUAObservation` and passes it to the agent callable.
3. Executes the returned action dict through :meth:`CUAActionHandler.execute_action`.
4. Streams each step to a JSONL file via :class:`TrajectoryWriter`.
5. Ingests the completed trajectory into SQLite via :class:`TrajectoryStore`.

The runner accepts any ``(CUAObservation) -> dict`` callable as the agent,
whether sync or async.  Sync callables are automatically wrapped with
``asyncio.to_thread`` so the event loop never blocks on user code.

Typical usage::

    from lunar_sandbox.cua import CUAEpisodeRunner, CUATask
    from lunar_sandbox.sandbox.cua_sandbox import CUASandbox

    task = CUATask(
        name="open-calc",
        instruction="Open the calculator application.",
        max_steps=10,
    )
    sandbox = CUASandbox(config)
    sandbox.create()

    def my_agent(obs):
        # Minimal agent that always stops immediately
        return {"action": "stop"}

    runner = CUAEpisodeRunner(task, sandbox, my_agent, trajectory_dir=Path("traces"))
    result = runner.run_sync()
    print(result.outcome)  # "completed"
"""

from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import structlog

from lunar_sandbox.actions.cua_handler import CUAActionHandler
from lunar_sandbox.cua.observation import CUAObservation
from lunar_sandbox.cua.task import CUATask
from lunar_sandbox.sandbox.cua_errors import ActionFailed, ActionTimeout
from lunar_sandbox.sandbox.cua_sandbox import CUASandbox
from lunar_sandbox.trajectory.models import StepState, TrajectoryStep
from lunar_sandbox.trajectory.store import TrajectoryStore
from lunar_sandbox.trajectory.writer import TrajectoryWriter

__all__ = ["CUAEpisodeRunner", "CUAEpisodeResult"]

log = structlog.get_logger(__name__)


@dataclass
class CUAEpisodeResult:
    """Summary of a completed CUA episode.

    Attributes:
        episode_id: Unique identifier for the episode.
        task_name: Name of the task that was evaluated.
        outcome: Terminal outcome of the episode. One of:
            ``"completed"`` -- agent returned a stop/done action,
            ``"timeout"`` -- time_limit elapsed before the agent finished,
            ``"max_steps"`` -- max_steps reached before the agent finished,
            ``"agent_error"`` -- agent returned invalid output (ValueError),
            ``"infra_error"`` -- unexpected sandbox/infrastructure error.
        step_count: Number of steps executed (including the terminal step).
        duration_ms: Total wall-clock duration of the episode in milliseconds.
        error_message: Human-readable error string for ``agent_error`` and
            ``infra_error`` outcomes; ``None`` for successful terminations.
        jsonl_path: Absolute path to the JSONL trajectory file, or empty
            string if no trajectory directory was configured.
        score: Reward score in [0.0, 1.0] from :class:`CUARewardEvaluator`,
            or ``None`` if reward evaluation was skipped (no trajectory dir),
            evaluation raised an exception, or the task uses manual reward.
    """

    episode_id: str
    task_name: str
    outcome: str
    step_count: int = 0
    duration_ms: float = 0.0
    error_message: str | None = None
    jsonl_path: str = ""
    score: float | None = None  # reward score from evaluator


class CUAEpisodeRunner:
    """Async episode runner for CUA (Computer-Using Agent) tasks.

    Orchestrates the full episode lifecycle:

    1. Creates the episode directory and opens the JSONL writer.
    2. If :attr:`CUATask.start_url` is set, launches Chromium inside the
       sandbox before the agent loop begins.
    3. At each step: captures a pre-action screenshot, builds a
       :class:`CUAObservation`, invokes the agent, and executes the
       returned action via :class:`CUAActionHandler`.
    4. Writes each step to JSONL for crash-safe persistence.
    5. After the episode ends, ingests the JSONL into SQLite.

    Termination conditions (whichever triggers first):

    - Agent returns ``{"action": "stop"}`` or ``{"action": "done"}``.
    - :attr:`CUATask.max_steps` steps have been executed.
    - :attr:`CUATask.time_limit` seconds have elapsed.
    - Agent returns invalid output (raises :class:`ValueError`, outcome
      becomes ``"agent_error"``).

    Args:
        task: Task definition specifying the instruction, limits, and reward.
        sandbox: A :class:`CUASandbox` that is already in ``RUNNING`` state.
        agent: Any callable with signature ``(CUAObservation) -> dict``.
            Async callables are awaited directly; sync callables are wrapped
            with ``asyncio.to_thread``.
        episode_id: Optional episode identifier. Auto-generated as
            ``"cua-ep-{8 hex chars}"`` if not provided.
        trajectory_dir: Root directory for JSONL and screenshot storage.
            If ``None``, no files are written and SQLite ingestion is skipped.
    """

    def __init__(
        self,
        task: CUATask,
        sandbox: CUASandbox,
        agent: Callable,
        episode_id: str | None = None,
        trajectory_dir: Path | None = None,
        event_hub: Any | None = None,
    ) -> None:
        self._task = task
        self._sandbox = sandbox
        self._agent = agent
        self._episode_id = episode_id or f"cua-ep-{uuid4().hex[:8]}"
        self._trajectory_dir = trajectory_dir
        self._event_hub = event_hub
        self._handler = CUAActionHandler(sandbox, sandbox._cua_config)
        self._agent_is_async = asyncio.iscoroutinefunction(agent) or asyncio.iscoroutinefunction(getattr(agent, '__call__', None))
        self._log = log.bind(episode_id=self._episode_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> CUAEpisodeResult:
        """Run the CUA episode asynchronously.

        Returns:
            :class:`CUAEpisodeResult` with the episode outcome and metadata.
        """
        # -- 1. Set up episode directory ------------------------------------
        episode_dir: Path | None = (
            self._trajectory_dir / self._episode_id if self._trajectory_dir else None
        )
        screenshots_dir: Path | None = (
            episode_dir / "screenshots" if episode_dir else None
        )
        if screenshots_dir is not None:
            screenshots_dir.mkdir(parents=True, exist_ok=True)

        # -- 2. Open trajectory writer -------------------------------------
        writer: TrajectoryWriter | None = None
        if episode_dir is not None:
            writer = TrajectoryWriter(episode_dir, self._episode_id)
            writer.open()

        # -- 3. Launch start_url if provided --------------------------------
        if self._task.start_url:
            self._log.info("cua_episode_launching_url", url=self._task.start_url)
            self._sandbox.execute(
                f"chromium-browser-wrapper {self._task.start_url} &",
                timeout=10,
            )
            await asyncio.sleep(2)  # Give Chromium time to load

        # -- 4. Publish episode start event ---------------------------------
        self._publish("cua_episode_start", {
            "episode_id": self._episode_id,
            "instruction": self._task.instruction,
        })

        # -- 5. Main action loop -------------------------------------------
        start_time = time.monotonic()
        start_ts = time.time()
        deadline = start_time + self._task.time_limit
        step_idx = 0
        outcome = "completed"
        error_message: str | None = None
        duration_ms = 0.0
        score: float | None = None

        # Parse display resolution from task (e.g. "1280x800")
        try:
            w, h = (int(x) for x in self._task.resolution.split("x"))
        except (ValueError, TypeError):
            w, h = 1280, 800

        try:
            while step_idx < self._task.max_steps:
                # Check time limit
                if time.monotonic() >= deadline:
                    outcome = "timeout"
                    break

                # a. Capture pre-action screenshot
                screenshot_filename = f"step_{step_idx:03d}.{self._task.screenshot_format}"
                screenshot_rel_path = f"screenshots/{screenshot_filename}"

                self._log.debug("cua_episode_screenshot", step=step_idx)
                b64_screenshot = self._handler.screenshot(wait_for_idle=0.1)

                if screenshots_dir is not None:
                    raw_bytes = base64.b64decode(b64_screenshot)
                    (screenshots_dir / screenshot_filename).write_bytes(raw_bytes)

                # b. Get cursor position
                try:
                    cursor_pos = self._handler.cursor_position()
                except Exception:
                    cursor_pos = None

                # c. Build observation
                observation = CUAObservation(
                    screenshot_path=screenshot_rel_path,
                    screenshot_b64=b64_screenshot,
                    screen_size=(w, h),
                    cursor_position=cursor_pos,
                    timestamp=time.time(),
                )

                # d. Call agent (async or sync)
                self._log.debug("cua_episode_calling_agent", step=step_idx)
                if self._agent_is_async:
                    action_dict = await self._agent(observation)
                else:
                    action_dict = await asyncio.to_thread(self._agent, observation)

                # e. Publish agent reasoning + action via WebSocket
                reasoning = getattr(self._agent, "last_reasoning", None)
                self._publish("cua_step", {
                    "episode_id": self._episode_id,
                    "step": step_idx,
                    "action": action_dict.get("action", "unknown") if isinstance(action_dict, dict) else "unknown",
                    "action_params": {k: v for k, v in action_dict.items() if k != "action"} if isinstance(action_dict, dict) else {},
                    "reasoning": reasoning,
                })

                # f. Validate action dict
                if not isinstance(action_dict, dict) or "action" not in action_dict:
                    raise ValueError(
                        f"Agent must return a dict with 'action' key, "
                        f"got: {type(action_dict)}"
                    )

                # f. Check for stop/done action
                action_name = action_dict.get("action", "")
                if action_name in ("stop", "done"):
                    outcome = "completed"
                    # Record final step before breaking
                    self._write_step(writer, step_idx, observation, action_dict, 0.0, reasoning=reasoning)
                    step_idx += 1
                    self._log.info("cua_episode_agent_stopped", step=step_idx)
                    break

                # g. Execute action via handler
                action_start = time.time()
                try:
                    self._handler.execute_action(action_dict)
                except ValueError:
                    # Invalid/unrecognised action -- re-raise to terminate immediately
                    raise
                except (ActionTimeout, ActionFailed) as exc:
                    # Container-level action error -- record with error in observation
                    self._log.warning(
                        "cua_episode_action_error",
                        step=step_idx,
                        action=action_name,
                        error=str(exc),
                    )
                    observation = CUAObservation(
                        screenshot_path=screenshot_rel_path,
                        screen_size=(w, h),
                        cursor_position=cursor_pos,
                        error_message=str(exc),
                        timestamp=time.time(),
                    )
                action_duration_ms = (time.time() - action_start) * 1000

                # h. Write trajectory step
                self._write_step(writer, step_idx, observation, action_dict, action_duration_ms, reasoning=reasoning)
                step_idx += 1
                self._log.debug("cua_episode_step_complete", step=step_idx)

            else:
                # Loop exhausted without break -- max_steps reached
                outcome = "max_steps"
                self._log.info("cua_episode_max_steps_reached", step_count=step_idx)

        except ValueError as exc:
            outcome = "agent_error"
            error_message = str(exc)
            self._log.error("cua_episode_agent_error", error=str(exc))

        except Exception as exc:
            outcome = "infra_error"
            error_message = str(exc)
            self._log.error("cua_episode_infra_error", error=str(exc))

        finally:
            duration_ms = (time.monotonic() - start_time) * 1000

            # Close writer
            if writer is not None:
                writer.close()

            # Evaluate reward score
            if episode_dir is not None:
                try:
                    from lunar_sandbox.cua.reward import CUARewardEvaluator
                    evaluator = CUARewardEvaluator()
                    score = evaluator.evaluate(
                        self._task,
                        self._sandbox,
                        episode_dir,
                        step_idx,
                    )
                    self._log.info("cua_episode_reward", score=score)
                except Exception as exc:
                    self._log.warning("cua_episode_reward_error", error=str(exc))
                    score = None

            # Ingest into SQLite
            if episode_dir is not None and self._trajectory_dir is not None:
                self._ingest_trajectory(
                    episode_dir,
                    step_count=step_idx,
                    outcome=outcome,
                    duration_ms=duration_ms,
                    started_at=start_ts,
                    score=score,
                )

        self._publish("cua_episode_end", {
            "episode_id": self._episode_id,
            "outcome": outcome,
            "step_count": step_idx,
            "duration_ms": round(duration_ms, 1),
            "error": error_message,
        })

        self._log.info(
            "cua_episode_complete",
            outcome=outcome,
            step_count=step_idx,
            duration_ms=round(duration_ms, 1),
        )

        return CUAEpisodeResult(
            episode_id=self._episode_id,
            task_name=self._task.name,
            outcome=outcome,
            step_count=step_idx,
            duration_ms=duration_ms,
            error_message=error_message,
            jsonl_path=str(writer.path) if writer is not None else "",
            score=score,
        )

    def run_sync(self) -> CUAEpisodeResult:
        """Synchronous wrapper around :meth:`run`.

        Calls ``asyncio.run(self.run())`` so that the caller does not need
        to manage an event loop.  Do not use this inside an already-running
        event loop; call ``await runner.run()`` instead.

        Returns:
            :class:`CUAEpisodeResult` with the episode outcome and metadata.
        """
        return asyncio.run(self.run())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """Publish a real-time event if an EventHub is configured."""
        if self._event_hub is not None:
            topic = f"cua:{self._episode_id}"
            self._event_hub.publish_event(event_type, topic, payload)

    def _write_step(
        self,
        writer: TrajectoryWriter | None,
        step_idx: int,
        observation: CUAObservation,
        action_dict: dict[str, Any],
        duration_ms: float,
        reasoning: str | None = None,
    ) -> None:
        """Serialise a single episode step to the JSONL writer.

        A no-op when ``writer`` is ``None`` (no trajectory directory configured).

        Args:
            writer: Open :class:`TrajectoryWriter` instance, or ``None``.
            step_idx: Zero-based index of this step within the episode.
            observation: The :class:`CUAObservation` captured before the action.
            action_dict: Full action dict returned by the agent.
            duration_ms: Wall-clock execution time of the action in milliseconds.
            reasoning: Model reasoning text for this step, if available.
        """
        if writer is None:
            return

        action_name = action_dict.get("action", "unknown")
        # Build action_params without the "action" key itself
        action_params = {k: v for k, v in action_dict.items() if k != "action"}
        if reasoning:
            action_params["reasoning"] = reasoning

        step = TrajectoryStep(
            episode_id=self._episode_id,
            step_idx=step_idx,
            timestamp=time.time(),
            state=StepState(),  # CUA steps don't track cwd/open_files
            action=action_name,
            action_params=action_params,
            observation=observation.model_dump(exclude={"screenshot_b64"}),
            duration_ms=duration_ms,
            source="cua",
            sandbox_id=self._sandbox._config.sandbox_id,
        )
        writer.write_step(step)

    def _ingest_trajectory(
        self,
        episode_dir: Path,
        *,
        step_count: int,
        outcome: str,
        duration_ms: float,
        started_at: float,
        score: float | None = None,
    ) -> None:
        """Ingest the JSONL trajectory file into the SQLite store.

        If the JSONL file does not exist (e.g. the episode produced no steps),
        this method is a no-op.  Ingestion errors are logged as warnings and
        suppressed so that they never mask the primary episode result.

        Args:
            episode_dir: Directory containing the JSONL file.
            step_count: Total number of steps recorded.
            outcome: Terminal outcome string for the episodes table.
            duration_ms: Total episode wall-clock duration in milliseconds.
            started_at: Episode start time as a Unix timestamp.
            score: Reward score from evaluator, or None if not available.
        """
        assert self._trajectory_dir is not None  # guarded at call site

        jsonl_path = episode_dir / f"{self._episode_id}.jsonl"
        if not jsonl_path.exists():
            self._log.debug("cua_trajectory_no_jsonl", path=str(jsonl_path))
            return

        try:
            db_path = self._trajectory_dir / "trajectories.db"
            store = TrajectoryStore(db_path)
            store.open()
            try:
                store.ingest_from_jsonl(
                    jsonl_path,
                    {
                        "episode_id": self._episode_id,
                        "task_name": self._task.name,
                        "outcome": outcome,
                        "score": score,
                        "step_count": step_count,
                        "duration_ms": duration_ms,
                        "started_at": started_at,
                        "ended_at": time.time(),
                        "is_complete": int(
                            outcome in ("completed", "timeout", "max_steps")
                        ),
                        "sandbox_id": self._sandbox._config.sandbox_id,
                        "episode_type": "cua",
                    },
                )
                self._log.info("cua_trajectory_ingested", db_path=str(db_path))
            finally:
                store.close()
        except Exception as exc:
            self._log.warning("cua_trajectory_ingestion_failed", error=str(exc))

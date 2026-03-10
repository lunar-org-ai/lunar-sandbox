"""Episode runner: orchestrates the full episode lifecycle.

Wires together sandbox allocation, task injection, agent action loop,
scoring, and sandbox reset into a single ``EpisodeRunner.run()`` call.

State machine flow::

    CREATED -> ALLOCATING -> INJECTING -> RUNNING -> SCORING -> RESETTING -> FINISHED

Infrastructure errors abort immediately with ``INFRA_ERROR`` outcome.
Agent errors are caught and recorded as ``AGENT_ERROR``.
"""

from __future__ import annotations

import time
from typing import Any, Protocol
from uuid import uuid4

import structlog

from lunar_sandbox.actions.client import ActionClient
from lunar_sandbox.actions.types import ActionResponse, ActionStatus, TraceEvent
from lunar_sandbox.episode.result import EpisodeResult
from lunar_sandbox.episode.scoring import run_scoring
from lunar_sandbox.episode.state import EpisodeOutcome, EpisodePhase, EpisodeState
from lunar_sandbox.sandbox.errors import InfraError

__all__ = ["EpisodeRunner"]

log = structlog.get_logger(__name__)


class AgentAdapter(Protocol):
    """Protocol for agent adapters that drive the action loop."""

    async def act(
        self, observation: ActionResponse | None
    ) -> tuple[str, dict[str, Any]]:
        """Return the next (action, params) to execute.

        Args:
            observation: The response from the previous action, or None
                on the first call.

        Returns:
            A tuple of (action_type_string, params_dict).
        """
        ...


class EpisodeRunner:
    """Orchestrates the full episode lifecycle.

    Coordinates sandbox allocation, task injection (repo clone + setup),
    agent action loop, scoring, and sandbox reset.

    Args:
        sandbox: A sandbox instance (must be in RUNNING state).
        task: A :class:`~lunar_sandbox.task.schema.TaskDefinition`.
        episode_id: Unique episode identifier (auto-generated if not provided).
        agent_adapter: Optional agent adapter that drives the action loop.
            When None, the caller drives actions manually via
            :meth:`execute_action`.
    """

    def __init__(
        self,
        sandbox: Any,
        task: Any,
        episode_id: str | None = None,
        agent_adapter: AgentAdapter | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._task = task
        self._episode_id = episode_id or f"ep-{uuid4().hex[:8]}"
        self._agent_adapter = agent_adapter
        self._state = EpisodeState()
        self._client: ActionClient | None = None
        self._trace_events: list[TraceEvent] = []
        self._seq: int = 0
        self._deadline: float | None = None
        self._log = log.bind(episode_id=self._episode_id)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def episode_id(self) -> str:
        """Unique episode identifier."""
        return self._episode_id

    @property
    def state(self) -> EpisodeState:
        """Current episode state."""
        return self._state

    @property
    def client(self) -> ActionClient | None:
        """The ActionClient, if connected."""
        return self._client

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self) -> EpisodeResult:
        """Execute the full episode lifecycle.

        Orchestrates: allocate -> inject -> run -> score -> reset -> finish.

        Returns:
            An :class:`EpisodeResult` with outcome, score, and trace.
        """
        try:
            # ---- 1. ALLOCATING ----
            await self._phase_allocate()

            # ---- 2. INJECTING ----
            await self._phase_inject()

            # ---- 3. RUNNING ----
            await self._phase_run()

            # ---- 4. SCORING ----
            await self._phase_score()

            # ---- 5. RESETTING ----
            await self._phase_reset()

            # ---- 6. FINISHED ----
            if not self._state.is_terminal():
                self._state.finish(
                    EpisodeOutcome.COMPLETED,
                    score=self._state.score,
                )

        except InfraError as exc:
            self._log.error("episode_infra_error", error=str(exc))
            if not self._state.is_terminal():
                self._state.finish(
                    EpisodeOutcome.INFRA_ERROR,
                    error_message=str(exc),
                )

        except Exception as exc:
            self._log.error("episode_unexpected_error", error=str(exc))
            if not self._state.is_terminal():
                self._state.finish(
                    EpisodeOutcome.AGENT_ERROR,
                    error_message=str(exc),
                )

        finally:
            # Ensure client is disconnected
            if self._client is not None:
                try:
                    await self._client.disconnect()
                except Exception:
                    pass
                self._client = None

        task_name = getattr(self._task, "name", "")
        sandbox_id = getattr(
            getattr(self._sandbox, "config", None), "sandbox_id", ""
        )

        self._log.info(
            "episode_finished",
            outcome=self._state.outcome.value if self._state.outcome else "unknown",
            score=self._state.score,
            steps=self._state.step_count,
            duration_ms=self._state.elapsed_ms(),
        )

        return EpisodeResult.from_state(
            self._state,
            episode_id=self._episode_id,
            task_name=task_name,
            sandbox_id=sandbox_id,
            trace_events=[te.model_dump() for te in self._trace_events],
        )

    # ------------------------------------------------------------------
    # Lifecycle phases
    # ------------------------------------------------------------------

    async def _phase_allocate(self) -> None:
        """Verify sandbox is in RUNNING state."""
        self._state.transition(EpisodePhase.ALLOCATING)
        self._log.info("phase_transition", phase="allocating")

        # Check sandbox state -- it must already be RUNNING
        sandbox_state = getattr(self._sandbox, "state", None)
        if sandbox_state is None:
            raise InfraError("Sandbox has no state attribute")

        state_value = (
            sandbox_state.value
            if hasattr(sandbox_state, "value")
            else str(sandbox_state)
        )
        if state_value != "running":
            raise InfraError(
                f"Sandbox is in state '{state_value}', expected 'running'"
            )

    async def _phase_inject(self) -> None:
        """Set up the task in the sandbox.

        Steps:
            a. Copy repo into sandbox merged_dir.
            b. Run setup_commands sequentially.
            c. Start action executor inside sandbox.
            d. Connect ActionClient to executor socket.
        """
        self._state.transition(EpisodePhase.INJECTING)
        self._log.info("phase_transition", phase="injecting")

        # a. Copy repo into merged_dir
        # Phase 2 uses a simple approach: copy repo files directly.
        # Phase 4 (Pool Management) will optimize with seed layer integration.
        repo = getattr(self._task, "repo", None)
        if repo is not None:
            repo_path = getattr(repo, "path", None)
            if repo_path is not None:
                layers = getattr(self._sandbox, "layers", None)
                if layers is not None:
                    merged_dir = getattr(layers, "merged_dir", None)
                    if merged_dir is not None:
                        self._log.debug(
                            "inject_repo",
                            repo_path=repo_path,
                            target=str(merged_dir),
                        )

        # b. Run setup_commands
        setup_commands = getattr(self._task, "setup_commands", [])
        for cmd in setup_commands:
            self._log.debug("inject_setup_command", command=cmd)
            try:
                result = self._sandbox.execute(cmd, timeout=120.0)
                exit_code = result.get("exit_code")
                if exit_code is not None and exit_code != 0:
                    self._log.warning(
                        "setup_command_failed",
                        command=cmd,
                        exit_code=exit_code,
                        stderr=result.get("stderr", ""),
                    )
            except Exception as exc:
                raise InfraError(
                    f"Setup command failed: {cmd!r}: {exc}"
                ) from exc

        # c. Start action executor inside sandbox (placeholder for Phase 2).
        # In a real deployment, this would fork the executor as a subprocess
        # inside the sandbox namespace. For now, the caller is expected to
        # have started the executor or provide a client directly.

        # d. Connect ActionClient
        # If the sandbox exposes a socket path, connect to it.
        socket_path = self._resolve_socket_path()
        if socket_path is not None:
            self._client = ActionClient(socket_path)
            try:
                await self._client.connect(timeout=5.0)
                self._log.info("client_connected", socket_path=socket_path)
            except ConnectionError as exc:
                raise InfraError(
                    f"Failed to connect to executor: {exc}"
                ) from exc

    async def _phase_run(self) -> None:
        """Run the agent action loop."""
        self._state.transition(EpisodePhase.RUNNING)
        self._log.info("phase_transition", phase="running")

        # Set episode deadline
        timeout = getattr(self._task, "timeout", 1800)
        max_steps = getattr(self._task, "max_steps", 200)
        self._deadline = time.monotonic() + timeout

        if self._agent_adapter is None:
            # Manual mode: caller drives actions via execute_action()
            self._log.info("running_manual_mode")
            return

        # Agent-driven loop
        observation: ActionResponse | None = None
        try:
            while True:
                # Check deadline
                if time.monotonic() >= self._deadline:
                    self._log.info("episode_timeout")
                    self._state.transition(EpisodePhase.SCORING)
                    self._log.info("phase_transition", phase="scoring")
                    if not self._state.is_terminal():
                        self._state.finish(
                            EpisodeOutcome.TIMEOUT,
                            score=self._state.score,
                        )
                    return

                # Check step limit
                if self._state.step_count >= max_steps:
                    self._log.info(
                        "step_limit_reached", max_steps=max_steps
                    )
                    # Auto-submit: transition to scoring
                    return

                # Get next action from agent
                action, params = await self._agent_adapter.act(observation)
                self._log.debug(
                    "action_dispatched",
                    action=action,
                    step=self._state.step_count,
                )

                # Dispatch via client
                if self._client is None:
                    raise InfraError("No ActionClient connected for agent loop")

                start_ts = time.time()
                response = await self._client.send_action(action, params)
                duration_ms = (time.time() - start_ts) * 1000

                # Record trace
                self._record_trace_event(
                    action=action,
                    params=params,
                    response=response,
                    duration_ms=duration_ms,
                    source="api",
                )

                self._state.increment_step()
                observation = response

                # Check for submit action
                if action == "submit":
                    self._log.info("agent_submitted")
                    return

        except ConnectionError as exc:
            raise InfraError(
                f"Lost connection to executor: {exc}"
            ) from exc

    async def _phase_score(self) -> None:
        """Run scoring using the action client for command execution."""
        if self._state.is_terminal():
            return

        self._state.transition(EpisodePhase.SCORING)
        self._log.info("phase_transition", phase="scoring")

        if self._client is None:
            self._log.warning("scoring_skipped_no_client")
            return

        # Build sandbox_execute_fn as closure over the connected client
        client = self._client

        async def sandbox_execute_fn(
            command: str, timeout: float = 30.0
        ) -> dict[str, Any]:
            resp = await client.execute_command(command, timeout=timeout)
            return {
                "exit_code": resp.exit_code or 0,
                "stdout": resp.stdout,
                "stderr": resp.stderr,
            }

        try:
            score, method = await run_scoring(sandbox_execute_fn, self._task)
            self._state.score = score
            self._log.info(
                "scoring_complete", score=score, method=method
            )
        except InfraError:
            raise
        except Exception as exc:
            self._log.warning(
                "scoring_failed", error=str(exc)
            )
            # Scoring failure is noted but doesn't change outcome category
            self._state.score = None
            self._state.error_message = f"Scoring failed: {exc}"

    async def _phase_reset(self) -> None:
        """Reset the sandbox for next use."""
        if self._state.is_terminal():
            return

        self._state.transition(EpisodePhase.RESETTING)
        self._log.info("phase_transition", phase="resetting")

        # Disconnect client first
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

        # Reset sandbox
        try:
            reset_ok = self._sandbox.reset()
            if not reset_ok:
                self._log.warning("sandbox_reset_returned_false")
        except Exception as exc:
            self._log.warning(
                "sandbox_reset_failed", error=str(exc)
            )
            # Reset failure is logged but doesn't change outcome

    # ------------------------------------------------------------------
    # Public action methods (manual mode)
    # ------------------------------------------------------------------

    async def execute_action(
        self, action: str, params: dict[str, Any]
    ) -> ActionResponse:
        """Execute an action in manual mode (no agent adapter).

        Sends the action via the connected client, records a trace event,
        increments the step counter, and returns the response.

        Automatically handles deadline expiration and step limit.

        Args:
            action: Action type string (e.g. ``"execute_command"``).
            params: Action-specific parameters.

        Returns:
            The :class:`ActionResponse` from the executor.
        """
        # Check deadline
        if self._deadline is not None and time.monotonic() >= self._deadline:
            return ActionResponse(
                status=ActionStatus.TIMEOUT,
                stderr="Episode deadline expired",
            )

        # Check step limit
        max_steps = getattr(self._task, "max_steps", 200)
        if self._state.step_count >= max_steps:
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr=f"Step limit reached ({max_steps})",
            )

        if self._client is None:
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr="No ActionClient connected",
            )

        start_ts = time.time()
        response = await self._client.send_action(action, params)
        duration_ms = (time.time() - start_ts) * 1000

        self._record_trace_event(
            action=action,
            params=params,
            response=response,
            duration_ms=duration_ms,
            source="api",
        )

        self._state.increment_step()
        return response

    async def execute_shell(
        self, command: str, timeout: float = 30.0
    ) -> dict[str, Any]:
        """Execute a raw shell command directly on the sandbox.

        Calls ``sandbox.execute()`` and records a TraceEvent with
        ``source="shell"``, ensuring shell commands produce the same
        trace schema as API actions.

        Args:
            command: Shell command string to execute.
            timeout: Maximum seconds to wait.

        Returns:
            The raw result dict from ``sandbox.execute()``.
        """
        start_ts = time.time()
        result = self._sandbox.execute(command, timeout=timeout)
        duration_ms = (time.time() - start_ts) * 1000

        trace_event = self._wrap_shell_trace(command, result, duration_ms)
        self._trace_events.append(trace_event)
        self._state.increment_step()

        return result

    # ------------------------------------------------------------------
    # Trace recording
    # ------------------------------------------------------------------

    def _record_trace_event(
        self,
        action: str,
        params: dict[str, Any],
        response: ActionResponse,
        duration_ms: float | None = None,
        source: str = "api",
    ) -> None:
        """Create and store a trace event from an action response.

        Args:
            action: Action type string.
            params: Action parameters.
            response: The ActionResponse received.
            duration_ms: Wall-clock duration in milliseconds.
            source: Origin of the action ("api" or "shell").
        """
        self._seq += 1

        output: dict[str, Any] = {}
        if response.output is not None:
            if isinstance(response.output, dict):
                output = response.output
            else:
                output = {"value": response.output}

        if response.stdout:
            output["stdout"] = response.stdout
        if response.stderr:
            output["stderr"] = response.stderr
        if response.exit_code is not None:
            output["exit_code"] = response.exit_code
        if response.cwd:
            output["cwd"] = response.cwd

        event = TraceEvent(
            seq=self._seq,
            ts=time.time(),
            action=action,
            params=params,
            status=response.status.value if hasattr(response.status, "value") else str(response.status),
            output=output,
            duration_ms=duration_ms if duration_ms is not None else response.duration_ms,
            source=source,
            episode_id=self._episode_id,
            sandbox_id=getattr(
                getattr(self._sandbox, "config", None), "sandbox_id", ""
            ),
        )

        self._trace_events.append(event)

    def _wrap_shell_trace(
        self,
        command: str,
        result: dict[str, Any],
        duration_ms: float = 0.0,
    ) -> TraceEvent:
        """Wrap a raw sandbox.execute() result into a TraceEvent.

        Maps result dict fields (stdout, stderr, exit_code, cwd) into
        the TraceEvent schema with ``source="shell"`` and
        ``action="execute_command"``.

        Args:
            command: The shell command that was executed.
            result: Raw result dict from sandbox.execute().
            duration_ms: Wall-clock duration in milliseconds.

        Returns:
            A fully populated :class:`TraceEvent`.
        """
        self._seq += 1

        exit_code = result.get("exit_code")
        timed_out = result.get("timed_out", False)

        if timed_out:
            status = "timeout"
        elif exit_code == 0:
            status = "success"
        else:
            status = "error"

        output: dict[str, Any] = {}
        if "stdout" in result:
            output["stdout"] = result["stdout"]
        if "stderr" in result:
            output["stderr"] = result["stderr"]
        if exit_code is not None:
            output["exit_code"] = exit_code
        if "cwd" in result:
            output["cwd"] = result["cwd"]

        return TraceEvent(
            seq=self._seq,
            ts=time.time(),
            action="execute_command",
            params={"command": command},
            status=status,
            output=output,
            duration_ms=duration_ms,
            source="shell",
            episode_id=self._episode_id,
            sandbox_id=getattr(
                getattr(self._sandbox, "config", None), "sandbox_id", ""
            ),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_socket_path(self) -> str | None:
        """Determine the executor socket path from the sandbox.

        Returns the socket path if determinable, otherwise None.
        """
        # Check if sandbox exposes layers with a merged_dir
        layers = getattr(self._sandbox, "layers", None)
        if layers is not None:
            merged_dir = getattr(layers, "merged_dir", None)
            if merged_dir is not None:
                from lunar_sandbox.actions.executor import SOCKET_PATH

                return str(merged_dir / SOCKET_PATH.lstrip("/"))
        return None

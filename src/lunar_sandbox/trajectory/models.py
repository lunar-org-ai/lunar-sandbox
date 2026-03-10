"""Trajectory data models for structured step capture.

Defines the (state, action, observation, reward) schema used for recording
agent trajectories. Each step in an episode is captured as a TrajectoryStep
with minimal state context provided by StepStateTracker.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "StepState",
    "TrajectoryStep",
    "StepStateTracker",
]


class StepState(BaseModel):
    """Minimal state captured at each trajectory step.

    Attributes:
        cwd: Current working directory inside the sandbox.
        open_files: List of files currently open or recently accessed.
        recent_actions: Last N actions taken (sliding window).
    """

    cwd: str = ""
    open_files: list[str] = Field(default_factory=list)
    recent_actions: list[str] = Field(default_factory=list)


class TrajectoryStep(BaseModel):
    """Single step in a trajectory: (state, action, observation, reward).

    Each step records the full context needed for offline analysis,
    imitation learning, or reward modelling. Fields with defaults are
    optional and populated when available.

    Attributes:
        episode_id: ID of the containing episode.
        step_idx: Zero-based step index within the episode.
        timestamp: Unix timestamp (seconds since epoch).
        state: Minimal state snapshot at step start.
        action: ActionType value string (e.g. "execute_command").
        action_params: Action-specific parameters.
        observation: Action output/result as structured dict.
        reward: Sparse reward (0.0 except final scored step).
        duration_ms: Wall-clock execution time in milliseconds.
        cpu_time_ms: CPU time in milliseconds (host-side, best-effort).
        file_diff: OverlayFS changes during this step, if captured.
        token_usage: Tokens consumed by agent for this step (optional).
        cost_usd: Cost in USD for this step (optional).
        source: Origin of the action ("api" or "shell").
        sandbox_id: ID of the sandbox that executed the action.
    """

    episode_id: str
    step_idx: int
    timestamp: float
    state: StepState
    action: str
    action_params: dict[str, Any]
    observation: dict[str, Any]
    reward: float = 0.0
    duration_ms: float = 0.0
    cpu_time_ms: float = 0.0
    file_diff: dict[str, Any] | None = None
    token_usage: int | None = None
    cost_usd: float | None = None
    source: str = "api"
    sandbox_id: str = ""


class StepStateTracker:
    """Tracks minimal state across trajectory steps.

    Maintains a sliding window of recent actions using a bounded deque.
    Create one per episode and call record_action() after each step.

    Args:
        history_size: Maximum number of recent actions to track.
    """

    def __init__(self, history_size: int = 5) -> None:
        self._recent_actions: deque[str] = deque(maxlen=history_size)

    def record_action(self, action: str) -> None:
        """Append an action to the recent actions window.

        Args:
            action: Action type string to record.
        """
        self._recent_actions.append(action)

    def get_state(
        self, cwd: str = "", open_files: list[str] | None = None
    ) -> StepState:
        """Return a snapshot of the current tracked state.

        Args:
            cwd: Current working directory to include in the snapshot.
            open_files: List of currently open files (None treated as empty).

        Returns:
            StepState with current cwd, open_files, and recent actions.
        """
        return StepState(
            cwd=cwd,
            open_files=open_files or [],
            recent_actions=list(self._recent_actions),
        )

    def reset(self) -> None:
        """Clear the recent actions deque (for new episodes)."""
        self._recent_actions.clear()

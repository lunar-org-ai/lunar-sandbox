"""Episode lifecycle state machine.

Defines the finite-state machine controlling episode phases
(CREATED -> ALLOCATING -> INJECTING -> RUNNING -> SCORING -> RESETTING -> FINISHED)
and terminal outcome states (completed, timeout, infra_error, agent_error, cancelled).

State machine::

    CREATED -> ALLOCATING -> INJECTING -> RUNNING -> SCORING -> RESETTING -> FINISHED
    any active phase -> FINISHED  (abort on error/cancellation)
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field


__all__ = [
    "EpisodeOutcome",
    "EpisodePhase",
    "EpisodeState",
    "VALID_TRANSITIONS",
]


class EpisodeOutcome(str, enum.Enum):
    """Terminal outcome states for an episode.

    These represent *why* the episode ended, not *where* it ended.
    """

    COMPLETED = "completed"
    """Agent submitted work and it was scored."""

    TIMEOUT = "timeout"
    """Episode exceeded its time limit; auto-scored at deadline."""

    INFRA_ERROR = "infra_error"
    """Infrastructure failure; not scored, not agent's fault."""

    AGENT_ERROR = "agent_error"
    """Agent crashed or violated protocol."""

    CANCELLED = "cancelled"
    """Episode was externally stopped (e.g., user abort)."""


class EpisodePhase(str, enum.Enum):
    """Internal lifecycle phases for an episode."""

    CREATED = "created"
    ALLOCATING = "allocating"
    INJECTING = "injecting"
    RUNNING = "running"
    SCORING = "scoring"
    RESETTING = "resetting"
    FINISHED = "finished"


VALID_TRANSITIONS: dict[EpisodePhase, set[EpisodePhase]] = {
    EpisodePhase.CREATED: {EpisodePhase.ALLOCATING},
    EpisodePhase.ALLOCATING: {EpisodePhase.INJECTING, EpisodePhase.FINISHED},
    EpisodePhase.INJECTING: {EpisodePhase.RUNNING, EpisodePhase.FINISHED},
    EpisodePhase.RUNNING: {EpisodePhase.SCORING, EpisodePhase.FINISHED},
    EpisodePhase.SCORING: {EpisodePhase.RESETTING, EpisodePhase.FINISHED},
    EpisodePhase.RESETTING: {EpisodePhase.FINISHED},
}


@dataclass
class EpisodeState:
    """Mutable state for an episode, with FSM transition guards.

    Usage::

        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        state.transition(EpisodePhase.INJECTING)
        state.transition(EpisodePhase.RUNNING)
        state.increment_step()
        state.transition(EpisodePhase.SCORING)
        state.transition(EpisodePhase.RESETTING)
        state.finish(EpisodeOutcome.COMPLETED, score=1.0)
    """

    phase: EpisodePhase = EpisodePhase.CREATED
    outcome: EpisodeOutcome | None = None
    step_count: int = 0
    score: float | None = None
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None
    error_message: str | None = None

    def transition(self, target: EpisodePhase) -> None:
        """Transition to a new phase, enforcing the valid-transitions graph.

        Args:
            target: The phase to transition to.

        Raises:
            RuntimeError: If the transition is not allowed from the
                current phase.
        """
        allowed = VALID_TRANSITIONS.get(self.phase)
        if allowed is None or target not in allowed:
            raise RuntimeError(
                f"Invalid episode transition: {self.phase.value} -> {target.value}"
            )
        self.phase = target

    def finish(
        self,
        outcome: EpisodeOutcome,
        score: float | None = None,
        error_message: str | None = None,
    ) -> None:
        """Terminate the episode with a final outcome.

        Can be called from any active (non-FINISHED) phase, allowing
        abort from any point in the lifecycle.

        Args:
            outcome: Why the episode ended.
            score: Final score (None for infra_error / cancelled).
            error_message: Human-readable error description.

        Raises:
            RuntimeError: If the episode is already finished.
        """
        if self.phase == EpisodePhase.FINISHED:
            raise RuntimeError("Episode is already finished")
        # Use transition() to validate FINISHED is reachable
        self.transition(EpisodePhase.FINISHED)
        self.outcome = outcome
        self.score = score
        self.error_message = error_message
        self.ended_at = time.monotonic()

    def increment_step(self) -> int:
        """Increment the step counter and return the new count."""
        self.step_count += 1
        return self.step_count

    def elapsed_ms(self) -> float:
        """Return elapsed time in milliseconds.

        If the episode is finished, returns the total duration.
        Otherwise, returns the time elapsed since start.
        """
        end = self.ended_at if self.ended_at is not None else time.monotonic()
        return (end - self.started_at) * 1000

    def is_terminal(self) -> bool:
        """Return True if the episode has reached a terminal state."""
        return self.phase == EpisodePhase.FINISHED

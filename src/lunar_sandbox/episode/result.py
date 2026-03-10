"""Episode result schema.

Provides :class:`EpisodeResult` -- the structured output of a single
episode run.  Separates infrastructure errors from agent failures so
that infra problems are never counted against the agent's score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lunar_sandbox.episode.state import EpisodeOutcome

if TYPE_CHECKING:
    from lunar_sandbox.episode.state import EpisodeState

__all__ = ["EpisodeResult"]


@dataclass
class EpisodeResult:
    """Structured result of a single episode evaluation.

    The key design decision: ``error_type`` explicitly distinguishes
    infrastructure errors (``"infra_error"``) from agent errors
    (``"agent_error"``).  This ensures infra failures are never
    confused with agent failures in aggregate scoring.
    """

    episode_id: str
    task_name: str
    outcome: EpisodeOutcome
    score: float | None = None
    duration_ms: float = 0.0
    step_count: int = 0
    error_type: str | None = None
    error_message: str | None = None
    trace_events: list[Any] = field(default_factory=list)
    sandbox_id: str = ""
    fingerprint: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    jsonl_path: str = ""

    def is_success(self) -> bool:
        """Return True if the episode completed successfully with a positive score."""
        return (
            self.outcome == EpisodeOutcome.COMPLETED
            and self.score is not None
            and self.score > 0.0
        )

    def is_infra_error(self) -> bool:
        """Return True if the episode failed due to infrastructure."""
        return self.outcome == EpisodeOutcome.INFRA_ERROR

    def is_agent_error(self) -> bool:
        """Return True if the episode failed due to agent error."""
        return self.outcome == EpisodeOutcome.AGENT_ERROR

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary for JSON output."""
        return {
            "episode_id": self.episode_id,
            "task_name": self.task_name,
            "outcome": self.outcome.value,
            "score": self.score,
            "duration_ms": self.duration_ms,
            "step_count": self.step_count,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "trace_events": self.trace_events,
            "sandbox_id": self.sandbox_id,
            "fingerprint": self.fingerprint,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "jsonl_path": self.jsonl_path,
        }

    @classmethod
    def from_state(
        cls,
        state: EpisodeState,
        *,
        episode_id: str,
        task_name: str,
        sandbox_id: str = "",
        fingerprint: str = "",
        trace_events: list[Any] | None = None,
        jsonl_path: str = "",
    ) -> EpisodeResult:
        """Construct an :class:`EpisodeResult` from an :class:`EpisodeState`.

        Maps the state's outcome to ``error_type`` automatically:
        - INFRA_ERROR -> error_type="infra_error"
        - AGENT_ERROR -> error_type="agent_error"
        - Others -> error_type=None

        Args:
            state: The completed episode state.
            episode_id: Unique identifier for the episode.
            task_name: Name of the task that was evaluated.
            sandbox_id: Identifier of the sandbox used.
            fingerprint: Content fingerprint of the sandbox.
            trace_events: List of trace event dicts.
            jsonl_path: Path to the JSONL trajectory file (empty when
                no trajectory was captured).

        Returns:
            A fully populated :class:`EpisodeResult`.
        """
        # Derive error_type from outcome
        error_type: str | None = None
        if state.outcome == EpisodeOutcome.INFRA_ERROR:
            error_type = "infra_error"
        elif state.outcome == EpisodeOutcome.AGENT_ERROR:
            error_type = "agent_error"

        return cls(
            episode_id=episode_id,
            task_name=task_name,
            outcome=state.outcome if state.outcome is not None else EpisodeOutcome.CANCELLED,
            score=state.score,
            duration_ms=state.elapsed_ms(),
            step_count=state.step_count,
            error_type=error_type,
            error_message=state.error_message,
            trace_events=trace_events if trace_events is not None else [],
            sandbox_id=sandbox_id,
            fingerprint=fingerprint,
            started_at=state.started_at,
            ended_at=state.ended_at if state.ended_at is not None else 0.0,
            jsonl_path=jsonl_path,
        )

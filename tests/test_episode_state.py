"""Unit tests for episode lifecycle state machine and result.

Tests EpisodePhase, EpisodeOutcome, EpisodeState FSM transitions
(valid and invalid), and EpisodeResult construction and serialization.
"""

from __future__ import annotations

import time

import pytest

from lunar_sandbox.episode.result import EpisodeResult
from lunar_sandbox.episode.state import (
    EpisodeOutcome,
    EpisodePhase,
    EpisodeState,
)


class TestEpisodeState:
    """Tests for EpisodeState FSM."""

    def test_initial_state(self) -> None:
        """phase=CREATED, outcome=None, step_count=0."""
        state = EpisodeState()
        assert state.phase == EpisodePhase.CREATED
        assert state.outcome is None
        assert state.step_count == 0
        assert state.score is None
        assert state.ended_at is None

    def test_happy_path_transitions(self) -> None:
        """CREATED->ALLOCATING->INJECTING->RUNNING->SCORING->RESETTING->FINISHED."""
        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        assert state.phase == EpisodePhase.ALLOCATING

        state.transition(EpisodePhase.INJECTING)
        assert state.phase == EpisodePhase.INJECTING

        state.transition(EpisodePhase.RUNNING)
        assert state.phase == EpisodePhase.RUNNING

        state.transition(EpisodePhase.SCORING)
        assert state.phase == EpisodePhase.SCORING

        state.transition(EpisodePhase.RESETTING)
        assert state.phase == EpisodePhase.RESETTING

        state.transition(EpisodePhase.FINISHED)
        assert state.phase == EpisodePhase.FINISHED

    def test_invalid_transition_skip(self) -> None:
        """CREATED->RUNNING raises RuntimeError (skips ALLOCATING)."""
        state = EpisodeState()
        with pytest.raises(RuntimeError, match="Invalid episode transition"):
            state.transition(EpisodePhase.RUNNING)

    def test_invalid_transition_backward(self) -> None:
        """RUNNING->INJECTING raises RuntimeError (backward)."""
        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        state.transition(EpisodePhase.INJECTING)
        state.transition(EpisodePhase.RUNNING)

        with pytest.raises(RuntimeError, match="Invalid episode transition"):
            state.transition(EpisodePhase.INJECTING)

    def test_abort_from_allocating(self) -> None:
        """Transition to FINISHED with INFRA_ERROR from ALLOCATING."""
        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        state.finish(EpisodeOutcome.INFRA_ERROR, error_message="No sandbox available")

        assert state.phase == EpisodePhase.FINISHED
        assert state.outcome == EpisodeOutcome.INFRA_ERROR
        assert state.error_message == "No sandbox available"

    def test_abort_from_injecting(self) -> None:
        """Transition to FINISHED with AGENT_ERROR from INJECTING."""
        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        state.transition(EpisodePhase.INJECTING)
        state.finish(EpisodeOutcome.AGENT_ERROR, error_message="Agent crashed")

        assert state.phase == EpisodePhase.FINISHED
        assert state.outcome == EpisodeOutcome.AGENT_ERROR

    def test_abort_from_running(self) -> None:
        """Transition to FINISHED from RUNNING."""
        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        state.transition(EpisodePhase.INJECTING)
        state.transition(EpisodePhase.RUNNING)
        state.finish(EpisodeOutcome.TIMEOUT)

        assert state.phase == EpisodePhase.FINISHED
        assert state.outcome == EpisodeOutcome.TIMEOUT

    def test_finish_sets_fields(self) -> None:
        """outcome, score, ended_at, phase all set correctly."""
        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        state.transition(EpisodePhase.INJECTING)
        state.transition(EpisodePhase.RUNNING)
        state.transition(EpisodePhase.SCORING)
        state.transition(EpisodePhase.RESETTING)
        state.finish(EpisodeOutcome.COMPLETED, score=0.95)

        assert state.phase == EpisodePhase.FINISHED
        assert state.outcome == EpisodeOutcome.COMPLETED
        assert state.score == 0.95
        assert state.ended_at is not None

    def test_finish_already_finished(self) -> None:
        """Finishing an already finished episode raises RuntimeError."""
        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        state.finish(EpisodeOutcome.CANCELLED)

        with pytest.raises(RuntimeError, match="already finished"):
            state.finish(EpisodeOutcome.CANCELLED)

    def test_increment_step(self) -> None:
        """step_count increments correctly."""
        state = EpisodeState()
        assert state.step_count == 0

        result = state.increment_step()
        assert result == 1
        assert state.step_count == 1

        result = state.increment_step()
        assert result == 2
        assert state.step_count == 2

    def test_elapsed_ms(self) -> None:
        """Returns positive float."""
        state = EpisodeState()
        # Elapsed should be non-negative.
        elapsed = state.elapsed_ms()
        assert elapsed >= 0.0
        assert isinstance(elapsed, float)

    def test_elapsed_ms_after_finish(self) -> None:
        """Elapsed is fixed after finish."""
        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        state.finish(EpisodeOutcome.CANCELLED)
        elapsed1 = state.elapsed_ms()
        time.sleep(0.01)
        elapsed2 = state.elapsed_ms()
        # After finish, elapsed should be the same (uses ended_at).
        assert elapsed1 == elapsed2

    def test_is_terminal(self) -> None:
        """True only after finish()."""
        state = EpisodeState()
        assert state.is_terminal() is False

        state.transition(EpisodePhase.ALLOCATING)
        assert state.is_terminal() is False

        state.finish(EpisodeOutcome.INFRA_ERROR)
        assert state.is_terminal() is True


class TestEpisodeResult:
    """Tests for EpisodeResult."""

    def _make_finished_state(
        self,
        outcome: EpisodeOutcome = EpisodeOutcome.COMPLETED,
        score: float | None = 1.0,
    ) -> EpisodeState:
        """Helper: create a finished EpisodeState."""
        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        state.transition(EpisodePhase.INJECTING)
        state.transition(EpisodePhase.RUNNING)
        state.increment_step()
        state.increment_step()
        state.transition(EpisodePhase.SCORING)
        state.transition(EpisodePhase.RESETTING)
        state.finish(outcome, score=score)
        return state

    def test_episode_result_from_state(self) -> None:
        """Constructs correctly from EpisodeState."""
        state = self._make_finished_state()
        result = EpisodeResult.from_state(
            state,
            episode_id="ep-001",
            task_name="test-task",
            sandbox_id="sb-001",
            fingerprint="abc123",
        )
        assert result.episode_id == "ep-001"
        assert result.task_name == "test-task"
        assert result.outcome == EpisodeOutcome.COMPLETED
        assert result.score == 1.0
        assert result.step_count == 2
        assert result.sandbox_id == "sb-001"
        assert result.fingerprint == "abc123"
        assert result.duration_ms > 0

    def test_episode_result_is_success(self) -> None:
        """score > 0 and COMPLETED."""
        state = self._make_finished_state(EpisodeOutcome.COMPLETED, score=0.8)
        result = EpisodeResult.from_state(state, episode_id="ep", task_name="t")
        assert result.is_success() is True

    def test_episode_result_is_success_zero_score(self) -> None:
        """score == 0 with COMPLETED is NOT success."""
        state = self._make_finished_state(EpisodeOutcome.COMPLETED, score=0.0)
        result = EpisodeResult.from_state(state, episode_id="ep", task_name="t")
        assert result.is_success() is False

    def test_episode_result_is_infra_error(self) -> None:
        """INFRA_ERROR outcome."""
        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        state.finish(EpisodeOutcome.INFRA_ERROR, error_message="disk full")
        result = EpisodeResult.from_state(state, episode_id="ep", task_name="t")
        assert result.is_infra_error() is True
        assert result.error_type == "infra_error"

    def test_episode_result_is_agent_error(self) -> None:
        """AGENT_ERROR outcome."""
        state = EpisodeState()
        state.transition(EpisodePhase.ALLOCATING)
        state.transition(EpisodePhase.INJECTING)
        state.finish(EpisodeOutcome.AGENT_ERROR, error_message="agent crashed")
        result = EpisodeResult.from_state(state, episode_id="ep", task_name="t")
        assert result.is_agent_error() is True
        assert result.error_type == "agent_error"

    def test_episode_result_to_dict(self) -> None:
        """Serializes to dict with correct keys."""
        state = self._make_finished_state()
        result = EpisodeResult.from_state(
            state,
            episode_id="ep-001",
            task_name="test-task",
        )
        d = result.to_dict()
        assert d["episode_id"] == "ep-001"
        assert d["task_name"] == "test-task"
        assert d["outcome"] == "completed"
        assert d["score"] == 1.0
        assert d["step_count"] == 2
        assert isinstance(d["duration_ms"], float)
        assert "trace_events" in d
        assert "error_type" in d
        assert "error_message" in d

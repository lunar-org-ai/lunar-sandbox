"""Unit tests for trajectory data models.

Tests StepState defaults and values, TrajectoryStep required/optional fields
and serialization roundtrip, StepStateTracker sliding window, and TraceEvent
new fields and backward compatibility.
"""

from __future__ import annotations

import json

from lunar_sandbox.actions.types import TraceEvent
from lunar_sandbox.trajectory.models import StepState, StepStateTracker, TrajectoryStep


class TestStepState:
    """Tests for StepState Pydantic model."""

    def test_step_state_defaults(self) -> None:
        """StepState() has empty cwd and empty lists."""
        s = StepState()
        assert s.cwd == ""
        assert s.open_files == []
        assert s.recent_actions == []

    def test_step_state_with_values(self) -> None:
        """StepState with populated fields validates correctly."""
        s = StepState(
            cwd="/home/user",
            open_files=["a.py", "b.py"],
            recent_actions=["execute_command", "read_file"],
        )
        assert s.cwd == "/home/user"
        assert s.open_files == ["a.py", "b.py"]
        assert s.recent_actions == ["execute_command", "read_file"]


class TestTrajectoryStep:
    """Tests for TrajectoryStep Pydantic model."""

    def _make_step(self, **overrides) -> TrajectoryStep:
        """Create a minimal valid TrajectoryStep with optional overrides."""
        defaults = {
            "episode_id": "ep-test",
            "step_idx": 0,
            "timestamp": 1700000000.0,
            "state": StepState(),
            "action": "execute_command",
            "action_params": {"command": "ls"},
            "observation": {"stdout": "file.txt"},
        }
        defaults.update(overrides)
        return TrajectoryStep(**defaults)

    def test_trajectory_step_required_fields(self) -> None:
        """TrajectoryStep requires episode_id, step_idx, timestamp, state, action, action_params, observation."""
        step = self._make_step()
        assert step.episode_id == "ep-test"
        assert step.step_idx == 0
        assert step.timestamp == 1700000000.0
        assert isinstance(step.state, StepState)
        assert step.action == "execute_command"
        assert step.action_params == {"command": "ls"}
        assert step.observation == {"stdout": "file.txt"}

    def test_trajectory_step_optional_defaults(self) -> None:
        """reward=0.0, token_usage=None, cost_usd=None, file_diff=None by default."""
        step = self._make_step()
        assert step.reward == 0.0
        assert step.token_usage is None
        assert step.cost_usd is None
        assert step.file_diff is None

    def test_trajectory_step_serialization_roundtrip(self) -> None:
        """model_dump_json() -> json.loads() -> model_validate() produces identical step."""
        original = self._make_step(
            reward=0.5,
            token_usage=100,
            cost_usd=0.01,
            file_diff={"created": ["new.py"]},
        )
        json_str = original.model_dump_json()
        parsed = json.loads(json_str)
        restored = TrajectoryStep.model_validate(parsed)
        assert restored == original
        assert restored.reward == 0.5
        assert restored.token_usage == 100
        assert restored.cost_usd == 0.01
        assert restored.file_diff == {"created": ["new.py"]}


class TestStepStateTracker:
    """Tests for StepStateTracker sliding window."""

    def test_step_state_tracker_sliding_window(self) -> None:
        """After recording 7 actions, only last 5 are kept (default maxlen=5)."""
        tracker = StepStateTracker()
        for i in range(7):
            tracker.record_action(f"action_{i}")
        state = tracker.get_state()
        assert state.recent_actions == [
            "action_2",
            "action_3",
            "action_4",
            "action_5",
            "action_6",
        ]

    def test_step_state_tracker_get_state(self) -> None:
        """get_state returns StepState with correct cwd, open_files, recent_actions."""
        tracker = StepStateTracker()
        tracker.record_action("read_file")
        tracker.record_action("write_file")
        state = tracker.get_state(cwd="/work", open_files=["main.py"])
        assert state.cwd == "/work"
        assert state.open_files == ["main.py"]
        assert state.recent_actions == ["read_file", "write_file"]

    def test_step_state_tracker_reset(self) -> None:
        """reset() clears the deque."""
        tracker = StepStateTracker()
        tracker.record_action("a")
        tracker.record_action("b")
        tracker.reset()
        state = tracker.get_state()
        assert state.recent_actions == []

    def test_step_state_tracker_custom_history_size(self) -> None:
        """maxlen respects custom value."""
        tracker = StepStateTracker(history_size=3)
        for i in range(5):
            tracker.record_action(f"a{i}")
        state = tracker.get_state()
        assert state.recent_actions == ["a2", "a3", "a4"]


class TestTraceEventFields:
    """Tests for TraceEvent new fields added in Phase 3."""

    def test_trace_event_new_fields(self) -> None:
        """TraceEvent has token_usage, cost_usd, cpu_time_ms with correct defaults."""
        event = TraceEvent(
            seq=1,
            ts=1700000000.0,
            action="execute_command",
            params={"command": "ls"},
            status="success",
            output={"stdout": "file.txt"},
            duration_ms=100.0,
            token_usage=500,
            cost_usd=0.02,
            cpu_time_ms=50.0,
        )
        assert event.token_usage == 500
        assert event.cost_usd == 0.02
        assert event.cpu_time_ms == 50.0

    def test_trace_event_backward_compat(self) -> None:
        """Creating TraceEvent without new fields still works (defaults apply)."""
        event = TraceEvent(
            seq=1,
            ts=1700000000.0,
            action="execute_command",
            params={"command": "ls"},
            status="success",
            output={"stdout": "ok"},
            duration_ms=10.0,
        )
        assert event.token_usage is None
        assert event.cost_usd is None
        assert event.cpu_time_ms == 0.0

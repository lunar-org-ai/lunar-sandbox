"""Tests for CUA observation model."""

from lunar_sandbox.cua.observation import CUAObservation
from lunar_sandbox.trajectory.models import TrajectoryStep


class TestCUAObservation:
    def test_defaults(self):
        obs = CUAObservation()
        assert obs.screenshot_path == ""
        assert obs.screen_size == (1280, 800)
        assert obs.cursor_position is None
        assert obs.action_result is None
        assert obs.error_message is None

    def test_full_observation(self):
        obs = CUAObservation(
            screenshot_path="screenshots/step_001.jpg",
            screen_size=(1920, 1080),
            cursor_position=(640, 400),
            action_result={"type": "left_click", "status": "ok"},
            timestamp=1234567890.0,
        )
        d = obs.model_dump()
        assert d["screenshot_path"] == "screenshots/step_001.jpg"
        assert d["screen_size"] == (1920, 1080)
        assert d["cursor_position"] == (640, 400)

    def test_compatible_with_trajectory_step(self):
        """CUAObservation.model_dump() must work as TrajectoryStep.observation."""
        obs = CUAObservation(
            screenshot_path="screenshots/step_000.jpg",
            screen_size=(1280, 800),
        )
        step = TrajectoryStep(
            episode_id="test-ep",
            step_idx=0,
            timestamp=1234567890.0,
            state={"cwd": "", "open_files": [], "recent_actions": []},
            action="screenshot",
            action_params={},
            observation=obs.model_dump(),
        )
        assert step.observation["screenshot_path"] == "screenshots/step_000.jpg"

    def test_json_roundtrip(self):
        obs = CUAObservation(
            screenshot_path="screenshots/step_005.jpg",
            cursor_position=(100, 200),
        )
        json_str = obs.model_dump_json()
        restored = CUAObservation.model_validate_json(json_str)
        assert restored.screenshot_path == "screenshots/step_005.jpg"
        assert restored.cursor_position == (100, 200)

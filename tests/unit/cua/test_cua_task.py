"""Tests for CUA task definition and reward discriminated union."""

import pytest
from lunar_sandbox.cua.task import (
    CUATask,
    ManualReward,
    ScreenshotReward,
    ScriptReward,
)


class TestCUATaskDefaults:
    def test_minimal_task(self):
        task = CUATask(instruction="Click the button")
        assert task.instruction == "Click the button"
        assert task.start_url is None
        assert task.max_steps == 100
        assert task.time_limit == 300.0
        assert task.resolution == "1280x800"
        assert task.screenshot_format == "jpg"
        assert task.reward.type == "manual"

    def test_with_start_url(self):
        task = CUATask(instruction="Fill form", start_url="https://example.com")
        assert task.start_url == "https://example.com"

    def test_no_setup_commands_field(self):
        """CUATask must NOT have setup_commands (deferred from Phase 16)."""
        assert not hasattr(CUATask.model_fields, "setup_commands")


class TestRewardVariants:
    def test_manual_reward_default(self):
        task = CUATask(instruction="test")
        assert isinstance(task.reward, ManualReward)
        assert task.reward.type == "manual"

    def test_script_reward(self):
        task = CUATask(
            instruction="test",
            reward=ScriptReward(script_path="/check.sh", timeout=60.0),
        )
        assert task.reward.type == "script"
        assert task.reward.script_path == "/check.sh"
        assert task.reward.timeout == 60.0

    def test_screenshot_reward(self):
        task = CUATask(
            instruction="test",
            reward=ScreenshotReward(reference_image="ref.png", threshold=0.9),
        )
        assert task.reward.type == "screenshot_match"
        assert task.reward.reference_image == "ref.png"
        assert task.reward.threshold == 0.9

    def test_json_roundtrip_manual(self):
        task = CUATask(instruction="test")
        json_str = task.model_dump_json()
        restored = CUATask.model_validate_json(json_str)
        assert restored.reward.type == "manual"

    def test_json_roundtrip_script(self):
        task = CUATask(
            instruction="test",
            reward=ScriptReward(script_path="/x.sh"),
        )
        json_str = task.model_dump_json()
        restored = CUATask.model_validate_json(json_str)
        assert restored.reward.type == "script"
        assert restored.reward.script_path == "/x.sh"

    def test_json_roundtrip_screenshot(self):
        task = CUATask(
            instruction="test",
            reward=ScreenshotReward(reference_image="r.png", threshold=0.85),
        )
        json_str = task.model_dump_json()
        restored = CUATask.model_validate_json(json_str)
        assert restored.reward.type == "screenshot_match"
        assert restored.reward.threshold == 0.85

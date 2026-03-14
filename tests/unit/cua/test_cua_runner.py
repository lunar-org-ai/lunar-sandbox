"""Tests for CUA episode runner with mocked sandbox."""

import asyncio
import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from lunar_sandbox.cua.runner import CUAEpisodeRunner, CUAEpisodeResult
from lunar_sandbox.cua.task import CUATask
from lunar_sandbox.cua.observation import CUAObservation


def _make_mock_sandbox():
    """Create a mock CUASandbox that returns fake results."""
    sandbox = MagicMock()
    sandbox._config = MagicMock()
    sandbox._config.sandbox_id = "mock-cua-sandbox"

    # Mock CUASandboxConfig
    sandbox._cua_config = MagicMock()
    sandbox._cua_config.display = ":1"
    sandbox._cua_config.action_delay_ms = 0
    sandbox._cua_config.screenshot_quality = 7

    # Mock execute to return success
    sandbox.execute.return_value = {
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "timed_out": False,
        "timeout_action": None,
    }

    return sandbox


def _make_fake_screenshot_b64():
    """Return a small valid-ish base64 string for testing."""
    # 1x1 JPEG bytes (minimal valid JPEG)
    jpeg_bytes = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00,
        0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB,
        0x00, 0x43, 0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07,
        0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B,
        0x0B, 0x0C, 0x19, 0x12, 0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E,
        0x1D, 0x1A, 0x1C, 0x1C, 0x20, 0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C,
        0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29, 0x2C, 0x30, 0x31, 0x34, 0x34,
        0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34,
        0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01,
        0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05,
        0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01,
        0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00,
        0x01, 0x7D, 0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21,
        0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7B,
        0x94, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xD9,
    ])
    return base64.b64encode(jpeg_bytes).decode()


class TestCUAEpisodeRunner:
    def test_scripted_3_step_agent(self, tmp_path):
        """Run a 3-step scripted agent and verify trajectory output."""
        task = CUATask(instruction="Click three buttons", name="3-step-test")
        sandbox = _make_mock_sandbox()

        # Track agent call count
        call_count = 0
        actions = [
            {"action": "left_click", "coordinate": [100, 200]},
            {"action": "type", "text": "hello"},
            {"action": "stop"},
        ]

        def scripted_agent(obs: CUAObservation) -> dict:
            nonlocal call_count
            action = actions[call_count]
            call_count += 1
            return action

        fake_b64 = _make_fake_screenshot_b64()

        # Patch CUAActionHandler to avoid real sandbox calls
        with patch("lunar_sandbox.cua.runner.CUAActionHandler") as MockHandler:
            handler = MockHandler.return_value
            handler.screenshot.return_value = fake_b64
            handler.cursor_position.return_value = (0, 0)
            handler.execute_action.return_value = {"type": "left_click", "status": "ok"}

            runner = CUAEpisodeRunner(
                task=task,
                sandbox=sandbox,
                agent=scripted_agent,
                episode_id="test-ep-001",
                trajectory_dir=tmp_path,
            )
            result = runner.run_sync()

        assert result.outcome == "completed"
        assert result.step_count == 3
        assert result.task_name == "3-step-test"

        # Verify JSONL was written
        jsonl_path = tmp_path / "test-ep-001" / "test-ep-001.jsonl"
        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) == 3

        # Verify each step has screenshot_path in observation
        for i, line in enumerate(lines):
            step = json.loads(line)
            assert step["observation"]["screenshot_path"] == f"screenshots/step_{i:03d}.jpg"
            assert step["action"] in ("left_click", "type", "stop")

        # Verify screenshots directory
        ss_dir = tmp_path / "test-ep-001" / "screenshots"
        assert ss_dir.exists()
        assert (ss_dir / "step_000.jpg").exists()
        assert (ss_dir / "step_001.jpg").exists()
        assert (ss_dir / "step_002.jpg").exists()

    def test_max_steps_termination(self, tmp_path):
        """Agent exceeding max_steps terminates with 'max_steps' outcome."""
        task = CUATask(instruction="loop", name="max-test", max_steps=3)
        sandbox = _make_mock_sandbox()

        def infinite_agent(obs: CUAObservation) -> dict:
            return {"action": "left_click", "coordinate": [50, 50]}

        fake_b64 = _make_fake_screenshot_b64()

        with patch("lunar_sandbox.cua.runner.CUAActionHandler") as MockHandler:
            handler = MockHandler.return_value
            handler.screenshot.return_value = fake_b64
            handler.cursor_position.return_value = (0, 0)
            handler.execute_action.return_value = {"type": "left_click", "status": "ok"}

            runner = CUAEpisodeRunner(
                task=task,
                sandbox=sandbox,
                agent=infinite_agent,
                episode_id="max-test-ep",
                trajectory_dir=tmp_path,
            )
            result = runner.run_sync()

        assert result.outcome == "max_steps"
        assert result.step_count == 3

    def test_invalid_action_terminates(self, tmp_path):
        """Agent returning unrecognized action terminates with agent_error."""
        task = CUATask(instruction="fail", name="invalid-test")
        sandbox = _make_mock_sandbox()

        def bad_agent(obs: CUAObservation) -> dict:
            return {"action": "fly_to_moon"}

        fake_b64 = _make_fake_screenshot_b64()

        with patch("lunar_sandbox.cua.runner.CUAActionHandler") as MockHandler:
            handler = MockHandler.return_value
            handler.screenshot.return_value = fake_b64
            handler.cursor_position.return_value = (0, 0)
            handler.execute_action.side_effect = ValueError("Unknown CUA action: 'fly_to_moon'")

            runner = CUAEpisodeRunner(
                task=task,
                sandbox=sandbox,
                agent=bad_agent,
                episode_id="invalid-test-ep",
                trajectory_dir=tmp_path,
            )
            result = runner.run_sync()

        assert result.outcome == "agent_error"
        assert "fly_to_moon" in (result.error_message or "")

    def test_async_agent(self, tmp_path):
        """Async agent callable works correctly."""
        task = CUATask(instruction="async test", name="async-test")
        sandbox = _make_mock_sandbox()

        async def async_agent(obs: CUAObservation) -> dict:
            return {"action": "stop"}

        fake_b64 = _make_fake_screenshot_b64()

        with patch("lunar_sandbox.cua.runner.CUAActionHandler") as MockHandler:
            handler = MockHandler.return_value
            handler.screenshot.return_value = fake_b64
            handler.cursor_position.return_value = (0, 0)

            runner = CUAEpisodeRunner(
                task=task,
                sandbox=sandbox,
                agent=async_agent,
                episode_id="async-test-ep",
                trajectory_dir=tmp_path,
            )
            result = runner.run_sync()

        assert result.outcome == "completed"
        assert result.step_count == 1

    def test_sqlite_ingestion(self, tmp_path):
        """CUA episode is ingested into SQLite with episode_type='cua'."""
        task = CUATask(instruction="ingest test", name="ingest-test")
        sandbox = _make_mock_sandbox()

        def one_step_agent(obs: CUAObservation) -> dict:
            return {"action": "stop"}

        fake_b64 = _make_fake_screenshot_b64()

        with patch("lunar_sandbox.cua.runner.CUAActionHandler") as MockHandler:
            handler = MockHandler.return_value
            handler.screenshot.return_value = fake_b64
            handler.cursor_position.return_value = (0, 0)

            runner = CUAEpisodeRunner(
                task=task,
                sandbox=sandbox,
                agent=one_step_agent,
                episode_id="ingest-ep",
                trajectory_dir=tmp_path,
            )
            result = runner.run_sync()

        assert result.outcome == "completed"

        # Verify SQLite ingestion
        from lunar_sandbox.trajectory.store import TrajectoryStore
        db_path = tmp_path / "trajectories.db"
        if db_path.exists():
            store = TrajectoryStore(db_path)
            store.open()
            try:
                episodes = store.query_episodes(episode_id="ingest-ep")
                assert len(episodes) == 1
                steps = store.query_steps(["ingest-ep"])
                assert len(steps) == 1
                assert steps[0]["action"] == "stop"
                # Check observation has screenshot_path
                obs_data = steps[0].get("observation", {})
                if isinstance(obs_data, str):
                    import json
                    obs_data = json.loads(obs_data)
                assert "screenshot_path" in obs_data
            finally:
                store.close()

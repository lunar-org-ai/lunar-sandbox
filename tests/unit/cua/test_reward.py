"""Tests for CUA reward signal evaluation."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from lunar_sandbox.cua.reward import CUARewardEvaluator
from lunar_sandbox.cua.task import (
    CUATask,
    ManualReward,
    ScreenshotReward,
    ScriptReward,
)


def _make_mock_sandbox(
    stdout: str = "",
    exit_code: int = 0,
    timed_out: bool = False,
) -> MagicMock:
    """Create a mock CUASandbox with configurable execute() return."""
    sandbox = MagicMock()
    sandbox.execute.return_value = {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": "",
        "timed_out": timed_out,
        "timeout_action": None,
    }
    return sandbox


class TestScriptReward:
    def test_score_from_json_stdout(self):
        """Script returning valid JSON with score 0.9 yields 0.9."""
        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="test",
            reward=ScriptReward(script_path="/check.sh", timeout=10.0),
        )
        sandbox = _make_mock_sandbox(stdout=json.dumps({"score": 0.9}))

        score = evaluator.evaluate(task, sandbox, None, 0)
        assert score == 0.9

    def test_score_with_reason_metadata(self):
        """Script returning score with reason metadata works."""
        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="test",
            reward=ScriptReward(script_path="/check.sh"),
        )
        sandbox = _make_mock_sandbox(
            stdout=json.dumps({"score": 0.75, "reason": "partial match"})
        )

        score = evaluator.evaluate(task, sandbox, None, 0)
        assert score == 0.75

    def test_score_clamped_to_unit_interval(self):
        """Score > 1.0 is clamped to 1.0, score < 0.0 is clamped to 0.0."""
        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="test",
            reward=ScriptReward(script_path="/check.sh"),
        )

        # Score > 1.0
        sandbox = _make_mock_sandbox(stdout=json.dumps({"score": 1.5}))
        assert evaluator.evaluate(task, sandbox, None, 0) == 1.0

        # Score < 0.0
        sandbox = _make_mock_sandbox(stdout=json.dumps({"score": -0.5}))
        assert evaluator.evaluate(task, sandbox, None, 0) == 0.0

    def test_timeout_returns_zero(self):
        """Script timeout produces score 0.0 (locked decision)."""
        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="test",
            reward=ScriptReward(script_path="/slow.sh", timeout=5.0),
        )
        sandbox = _make_mock_sandbox(timed_out=True)

        score = evaluator.evaluate(task, sandbox, None, 0)
        assert score == 0.0

    def test_nonzero_exit_code_returns_zero(self):
        """Script with non-zero exit code produces score 0.0."""
        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="test",
            reward=ScriptReward(script_path="/fail.sh"),
        )
        sandbox = _make_mock_sandbox(exit_code=1)

        score = evaluator.evaluate(task, sandbox, None, 0)
        assert score == 0.0

    def test_invalid_json_returns_zero(self):
        """Script producing invalid JSON returns 0.0."""
        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="test",
            reward=ScriptReward(script_path="/bad.sh"),
        )
        sandbox = _make_mock_sandbox(stdout="not json at all")

        score = evaluator.evaluate(task, sandbox, None, 0)
        assert score == 0.0

    def test_missing_score_key_returns_zero(self):
        """Script returning JSON without 'score' key returns 0.0."""
        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="test",
            reward=ScriptReward(script_path="/no_score.sh"),
        )
        sandbox = _make_mock_sandbox(stdout=json.dumps({"result": "ok"}))

        score = evaluator.evaluate(task, sandbox, None, 0)
        assert score == 0.0

    def test_task_context_written_via_base64(self):
        """Task context is written to container using base64 encoding."""
        evaluator = CUARewardEvaluator()
        task = CUATask(
            name="my-task",
            instruction="Click the button with 'quotes'",
            start_url="https://example.com",
            reward=ScriptReward(script_path="/check.sh"),
        )
        sandbox = _make_mock_sandbox(stdout=json.dumps({"score": 1.0}))

        evaluator.evaluate(task, sandbox, None, 0)

        # First execute call should be the base64 write
        first_call = sandbox.execute.call_args_list[0]
        cmd = first_call[0][0]
        assert "base64" in cmd, "Must use base64 encoding for task_context.json"
        assert "/tmp/task_context.json" in cmd


class TestScreenshotReward:
    def test_identical_images_score_one(self, tmp_path):
        """Pixel-identical screenshot and reference yield score 1.0."""
        pytest.importorskip("skimage")
        pytest.importorskip("PIL")

        import numpy as np
        from PIL import Image

        # Create identical test images
        img = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)
        pil_img = Image.fromarray(img)

        # Save as episode screenshot
        episode_dir = tmp_path / "ep-1"
        ss_dir = episode_dir / "screenshots"
        ss_dir.mkdir(parents=True)
        pil_img.save(ss_dir / "step_000.png")

        # Save as reference
        ref_path = tmp_path / "reference.png"
        pil_img.save(ref_path)

        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="match",
            reward=ScreenshotReward(
                reference_image=str(ref_path),
                threshold=0.95,
            ),
        )
        sandbox = MagicMock()

        score = evaluator.evaluate(task, sandbox, episode_dir, 1)
        assert score == 1.0

    def test_different_images_score_zero(self, tmp_path):
        """Very different images produce SSIM below threshold -> score 0.0."""
        pytest.importorskip("skimage")
        pytest.importorskip("PIL")

        import numpy as np
        from PIL import Image

        # Create very different images (black vs white)
        black = np.zeros((100, 100, 3), dtype=np.uint8)
        white = np.full((100, 100, 3), 255, dtype=np.uint8)

        episode_dir = tmp_path / "ep-2"
        ss_dir = episode_dir / "screenshots"
        ss_dir.mkdir(parents=True)
        Image.fromarray(black).save(ss_dir / "step_000.png")

        ref_path = tmp_path / "reference_white.png"
        Image.fromarray(white).save(ref_path)

        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="match",
            reward=ScreenshotReward(
                reference_image=str(ref_path),
                threshold=0.95,
            ),
        )
        sandbox = MagicMock()

        score = evaluator.evaluate(task, sandbox, episode_dir, 1)
        assert score == 0.0

    def test_crop_region(self, tmp_path):
        """Crop region extracts sub-image for comparison."""
        pytest.importorskip("skimage")
        pytest.importorskip("PIL")

        import numpy as np
        from PIL import Image

        # Same image content in the crop region
        img = np.random.randint(0, 256, (200, 200, 3), dtype=np.uint8)

        episode_dir = tmp_path / "ep-crop"
        ss_dir = episode_dir / "screenshots"
        ss_dir.mkdir(parents=True)
        Image.fromarray(img).save(ss_dir / "step_000.png")

        ref_path = tmp_path / "reference_crop.png"
        Image.fromarray(img).save(ref_path)

        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="match region",
            reward=ScreenshotReward(
                reference_image=str(ref_path),
                threshold=0.95,
                crop_region=(50, 50, 100, 100),
            ),
        )
        sandbox = MagicMock()

        score = evaluator.evaluate(task, sandbox, episode_dir, 1)
        assert score == 1.0

    def test_step_index_selection(self, tmp_path):
        """step_index selects the correct screenshot for comparison."""
        pytest.importorskip("skimage")
        pytest.importorskip("PIL")

        import numpy as np
        from PIL import Image

        episode_dir = tmp_path / "ep-idx"
        ss_dir = episode_dir / "screenshots"
        ss_dir.mkdir(parents=True)

        # step_000 = black (different from reference)
        black = np.zeros((100, 100, 3), dtype=np.uint8)
        Image.fromarray(black).save(ss_dir / "step_000.png")

        # step_001 = same as reference (should match)
        matching = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)
        Image.fromarray(matching).save(ss_dir / "step_001.png")

        ref_path = tmp_path / "reference_idx.png"
        Image.fromarray(matching).save(ref_path)

        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="match step 1",
            reward=ScreenshotReward(
                reference_image=str(ref_path),
                threshold=0.95,
                step_index=1,
            ),
        )
        sandbox = MagicMock()

        score = evaluator.evaluate(task, sandbox, episode_dir, 2)
        assert score == 1.0

    def test_missing_reference_returns_zero(self, tmp_path):
        """Missing reference image returns 0.0."""
        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="match",
            reward=ScreenshotReward(
                reference_image="/nonexistent/ref.png",
                threshold=0.95,
            ),
        )
        sandbox = MagicMock()

        episode_dir = tmp_path / "ep-noref"
        ss_dir = episode_dir / "screenshots"
        ss_dir.mkdir(parents=True)
        (ss_dir / "step_000.png").write_bytes(b"fake")

        score = evaluator.evaluate(task, sandbox, episode_dir, 1)
        assert score == 0.0

    def test_no_episode_dir_returns_zero(self):
        """No episode_dir returns 0.0."""
        evaluator = CUARewardEvaluator()
        task = CUATask(
            instruction="match",
            reward=ScreenshotReward(reference_image="ref.png"),
        )
        score = evaluator.evaluate(task, MagicMock(), None, 1)
        assert score == 0.0


class TestManualReward:
    def test_manual_returns_none(self):
        """ManualReward produces None (pending human review)."""
        evaluator = CUARewardEvaluator()
        task = CUATask(instruction="test")  # default ManualReward
        score = evaluator.evaluate(task, MagicMock(), None, 0)
        assert score is None

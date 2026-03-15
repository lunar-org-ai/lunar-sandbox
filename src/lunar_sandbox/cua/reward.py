"""CUA reward signal evaluation.

Computes episode scores by dispatching on task.reward.type:

- ``script``: Executes a validation script inside the container,
  parses JSON stdout for a ``"score"`` field, clamps to [0.0, 1.0].
- ``screenshot_match``: Computes SSIM between an episode screenshot
  and a reference image on the host (FastAPI worker). Returns 1.0
  if SSIM >= threshold, else 0.0.
- ``manual``: Returns None (score set later by human reviewer).

SSIM computation uses scikit-image (``skimage.metrics.structural_similarity``)
with ``channel_axis=2`` and ``data_range=255`` for RGB uint8 images.
scikit-image is a host-side dependency only -- NOT installed in the Docker image.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from lunar_sandbox.cua.task import CUATask, ScriptReward, ScreenshotReward
    from lunar_sandbox.sandbox.cua_sandbox import CUASandbox

__all__ = ["CUARewardEvaluator"]

log = structlog.get_logger(__name__)

_TASK_CONTEXT_PATH = "/tmp/task_context.json"


class CUARewardEvaluator:
    """Compute episode reward score by dispatching on task.reward.type."""

    def evaluate(
        self,
        task: CUATask,
        sandbox: CUASandbox,
        episode_dir: Path | None,
        step_count: int,
    ) -> float | None:
        """Evaluate reward for a completed CUA episode.

        Args:
            task: The task definition with reward configuration.
            sandbox: The CUA sandbox (for script execution).
            episode_dir: Path to episode directory containing screenshots/.
                Required for screenshot_match; ignored for script/manual.
            step_count: Total number of steps in the episode.

        Returns:
            Float score in [0.0, 1.0] for script/screenshot_match,
            None for manual (awaiting human review).
        """
        reward = task.reward
        if reward.type == "script":
            return self._script_reward(reward, task, sandbox)
        elif reward.type == "screenshot_match":
            return self._screenshot_reward(reward, task, episode_dir, step_count)
        else:
            # ManualReward -- return None so score column stays NULL
            log.info("reward_manual_pending", task=task.name)
            return None

    def _script_reward(
        self,
        reward: ScriptReward,
        task: CUATask,
        sandbox: CUASandbox,
    ) -> float:
        """Execute validation script inside container and parse score."""
        # 1. Write task context into container via base64 to avoid quoting hazards
        context_data = {
            "task_name": task.name,
            "instruction": task.instruction,
            "start_url": task.start_url,
        }
        context_json = json.dumps(context_data)
        b64_content = base64.b64encode(context_json.encode()).decode()
        sandbox.execute(
            f"echo {b64_content} | base64 -d > {_TASK_CONTEXT_PATH}",
            timeout=5,
        )

        # 2. Run validation script with configurable timeout
        log.info("script_reward_executing", script=reward.script_path, timeout=reward.timeout)
        result = sandbox.execute(reward.script_path, timeout=reward.timeout)

        # 3. Handle timeout
        if result.get("timed_out"):
            log.warning("script_reward_timeout", script=reward.script_path, timeout=reward.timeout)
            return 0.0

        # 4. Handle non-zero exit code
        if result.get("exit_code") != 0:
            log.warning(
                "script_reward_nonzero_exit",
                script=reward.script_path,
                exit_code=result.get("exit_code"),
                stderr=result.get("stderr", ""),
            )
            return 0.0

        # 5. Parse JSON stdout and extract score
        try:
            stdout = result.get("stdout", "").strip()
            data = json.loads(stdout)
            score = float(data["score"])
            clamped = max(0.0, min(1.0, score))
            log.info("script_reward_result", score=clamped, raw_score=score,
                     reason=data.get("reason"))
            return clamped
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            log.warning("script_reward_parse_error", error=str(exc),
                        stdout=result.get("stdout", "")[:200])
            return 0.0

    def _screenshot_reward(
        self,
        reward: ScreenshotReward,
        task: CUATask,
        episode_dir: Path | None,
        step_count: int,
    ) -> float:
        """Compare episode screenshot against reference using SSIM."""
        if episode_dir is None:
            log.warning("screenshot_reward_no_episode_dir")
            return 0.0

        if step_count <= 0:
            log.warning("screenshot_reward_no_steps")
            return 0.0

        # 1. Determine which screenshot to compare
        step_idx = reward.step_index
        if step_idx < 0:
            step_idx = step_count - 1

        # 2. Locate the episode screenshot
        screenshots_dir = episode_dir / "screenshots"
        if not screenshots_dir.exists():
            log.warning("screenshot_reward_no_screenshots_dir",
                        path=str(screenshots_dir))
            return 0.0

        screenshot_files = sorted(screenshots_dir.glob("step_*"))
        if not screenshot_files:
            log.warning("screenshot_reward_no_screenshot_files")
            return 0.0

        step_idx = min(step_idx, len(screenshot_files) - 1)
        screenshot_path = screenshot_files[step_idx]

        # 3. Load reference image
        reference_path = Path(reward.reference_image)
        if not reference_path.exists():
            log.warning("screenshot_reward_missing_reference",
                        path=str(reference_path))
            return 0.0

        # 4. Compute SSIM (imports deferred to avoid import cost when unused)
        try:
            import numpy as np
            from PIL import Image
            from skimage.metrics import structural_similarity

            episode_img = np.array(Image.open(screenshot_path).convert("RGB"))
            reference_img = np.array(Image.open(reference_path).convert("RGB"))

            # 5. Apply optional crop region (x, y, width, height)
            if reward.crop_region is not None:
                x, y, w, h = reward.crop_region
                episode_img = episode_img[y:y + h, x:x + w]
                reference_img = reference_img[y:y + h, x:x + w]

            # 6. Resize episode to match reference if dimensions differ
            if episode_img.shape != reference_img.shape:
                ep_pil = Image.fromarray(episode_img).resize(
                    (reference_img.shape[1], reference_img.shape[0]),
                    Image.LANCZOS,
                )
                episode_img = np.array(ep_pil)

            # 7. Compute SSIM
            ssim_score = float(structural_similarity(
                episode_img,
                reference_img,
                channel_axis=2,   # RGB axis; do NOT use multichannel (deprecated)
                data_range=255,   # Required for uint8; do NOT omit
            ))

            log.info("screenshot_reward_ssim",
                     ssim=round(ssim_score, 4),
                     threshold=reward.threshold,
                     step_idx=step_idx)

            return 1.0 if ssim_score >= reward.threshold else 0.0

        except ImportError as exc:
            log.error("screenshot_reward_import_error",
                      error=str(exc),
                      hint="Install scikit-image: pip install 'scikit-image>=0.19'")
            return 0.0
        except Exception as exc:
            log.error("screenshot_reward_error", error=str(exc))
            return 0.0

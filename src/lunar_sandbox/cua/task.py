"""CUA task definition schema.

A CUATask specifies what a Computer-Using Agent episode evaluates:
the natural-language instruction, an optional browser start URL, the
reward mechanism, and resource limits (max steps, time limit).

The ``start_url`` field determines the episode mode:
- If ``start_url`` is provided, the agent opens Chromium at that URL
  before the episode begins.
- If ``start_url`` is None, the agent starts with a clean desktop
  (no browser pre-loaded).

There is no explicit ``mode`` field -- the single CUATask type is
flexible enough to cover both browser and desktop tasks through the
presence or absence of ``start_url``.

Reward types are a discriminated union keyed on the ``type`` literal:
- ``"script"``         -- ScriptReward: validation script runs inside container
- ``"screenshot_match"`` -- ScreenshotReward: SSIM comparison against reference image
- ``"manual"``         -- ManualReward: human reviewer assigns reward (default)
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

__all__ = [
    "CUATask",
    "ScriptReward",
    "ScreenshotReward",
    "ManualReward",
    "RewardVariant",
]


class ScriptReward(BaseModel):
    """Reward computed by running a validation script inside the container.

    The script is executed after the episode ends and should exit 0 for
    success (reward = 1.0) or non-zero for failure (reward = 0.0).

    Attributes:
        type: Discriminator literal, always ``"script"``.
        script_path: Absolute path to the script inside the container.
        timeout: Maximum seconds to wait for the script to complete.
    """

    type: Literal["script"] = "script"
    script_path: str
    timeout: float = 30.0


class ScreenshotReward(BaseModel):
    """Reward computed by comparing the final screenshot to a reference image.

    SSIM (structural similarity) is computed on the host (FastAPI worker)
    to keep scipy out of the Docker image.  Reward is 1.0 if the similarity
    meets or exceeds ``threshold``, otherwise 0.0.

    Attributes:
        type: Discriminator literal, always ``"screenshot_match"``.
        reference_image: Path or identifier of the reference image.
        threshold: Minimum SSIM score to count as success (0.0 - 1.0).
    """

    type: Literal["screenshot_match"] = "screenshot_match"
    reference_image: str
    threshold: float = 0.95


class ManualReward(BaseModel):
    """Reward assigned manually by a human reviewer.

    This is the default reward type when no automated scoring is available.
    The reward value is set externally after episode review.

    Attributes:
        type: Discriminator literal, always ``"manual"``.
    """

    type: Literal["manual"] = "manual"


RewardVariant = Annotated[
    Union[ScriptReward, ScreenshotReward, ManualReward],
    Field(discriminator="type"),
]
"""Discriminated union of all reward variant types.

Pydantic uses the ``type`` field to select the correct model during
deserialization.  Use this as a type annotation on fields that accept
any reward kind.
"""


class CUATask(BaseModel):
    """Task definition for a Computer-Using Agent episode.

    Specifies the instruction, optional browser start URL, reward mechanism,
    and resource limits for a single evaluation episode.

    Attributes:
        name: Human-readable task name (optional, defaults to empty string).
        instruction: Natural-language instruction given to the agent.
        start_url: If provided, Chromium opens at this URL before the episode.
            If None, the agent starts with a clean desktop (no browser).
        reward: How the episode is scored. Defaults to ManualReward.
        max_steps: Maximum number of agent steps before the episode is
            terminated. Either max_steps or time_limit can end the episode.
        time_limit: Maximum wall-clock seconds for the episode. Either limit
            can terminate the episode, whichever triggers first.
        resolution: Display resolution string, e.g. ``"1280x800"``.
        screenshot_format: Image format for screenshots (``"jpg"`` by default;
            use ``"png"`` for pixel-perfect comparison tasks).
    """

    name: str = ""
    instruction: str
    start_url: str | None = None
    reward: RewardVariant = Field(default_factory=ManualReward)
    max_steps: int = 100
    time_limit: float = 300.0
    resolution: str = "1280x800"
    screenshot_format: str = "jpg"

"""CUA observation model for per-step agent input capture.

A CUAObservation captures everything the agent sees at each step of a
Computer-Using Agent episode. Instances are serialised to a plain dict
via ``model_dump()`` and stored in ``TrajectoryStep.observation``.

Screenshot paths are stored relative to the episode directory so that
episode archives remain portable when moved or copied.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

__all__ = [
    "CUAObservation",
]


class CUAObservation(BaseModel):
    """Observation captured at each CUA episode step.

    Stored in ``TrajectoryStep.observation`` via ``model_dump()``.
    Screenshot paths are relative to the episode directory for portability.

    Attributes:
        screenshot_path: Relative path to the captured screenshot,
            e.g. ``"screenshots/step_001.jpg"``. Empty string if no
            screenshot was captured for this step.
        screen_size: Display resolution as ``(width, height)`` in pixels.
            Matches the container's configured resolution.
        cursor_position: Cursor location as ``(x, y)`` in pixels, or None
            if the cursor position could not be determined.
        action_result: Structured result returned by the previous action,
            passed back to the agent as feedback. None if not available.
        error_message: Error text from the previous action, if any.
            None when the previous action succeeded.
        timestamp: Unix timestamp (seconds since epoch) when the
            observation was captured.
    """

    screenshot_path: str = ""
    screen_size: tuple[int, int] = (1280, 800)
    cursor_position: tuple[int, int] | None = None
    action_result: dict[str, Any] | None = None
    error_message: str | None = None
    timestamp: float = 0.0

"""Windows CUA action handler: translates Anthropic computer_20251124 action
dicts into PowerShell commands executed on a Windows VM via SSH.

Same interface as :class:`CUAActionHandler` but uses the PowerShell
``cua_helper.ps1`` script instead of xdotool/maim.

Usage::

    from lunar_sandbox.windows.action_handler import WindowsCUAActionHandler

    handler = WindowsCUAActionHandler(sandbox, config)

    # Typed convenience methods
    handler.mouse_move(100, 200)
    handler.left_click(300, 400)
    handler.type_text("hello world")
    b64 = handler.screenshot()

    # Anthropic agent loop passthrough
    result = handler.execute_action({"action": "left_click", "coordinate": [300, 400]})
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import structlog

from lunar_sandbox.actions.types import ACTION_TIMEOUTS, ActionType
from lunar_sandbox.sandbox.cua_errors import ActionFailed, ActionTimeout
from lunar_sandbox.windows.config import WindowsCUAConfig
from lunar_sandbox.windows.sandbox import WindowsCUASandbox

__all__ = ["WindowsCUAActionHandler"]

log = structlog.get_logger(__name__)


class WindowsCUAActionHandler:
    """Translates CUA action requests into PowerShell commands over SSH.

    Holds a reference to a :class:`WindowsCUASandbox` and executes
    commands via ``sandbox.execute_helper()``.

    Attributes:
        _sandbox: Underlying Windows sandbox for command execution.
        _config: Windows CUA configuration.
        _action_delay_ms: Milliseconds to sleep after actions.
        _screenshot_quality: JPEG quality (1-100).
    """

    __slots__ = (
        "_sandbox",
        "_config",
        "_action_delay_ms",
        "_screenshot_quality",
    )

    def __init__(self, sandbox: WindowsCUASandbox, config: WindowsCUAConfig) -> None:
        self._sandbox = sandbox
        self._config = config
        self._action_delay_ms: int = config.action_delay_ms
        self._screenshot_quality: int = config.screenshot_quality

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _exec_helper(
        self,
        action: str,
        timeout: float | None = None,
        *,
        action_type: str = "",
        **params: Any,
    ) -> dict[str, Any]:
        """Execute a CUA helper action and check for errors.

        Args:
            action: Helper action name.
            timeout: Maximum seconds to wait.
            action_type: Human-readable name for error messages.
            **params: Action-specific parameters.

        Returns:
            Result dict from the helper.

        Raises:
            ActionTimeout: If the command exceeded the timeout.
            ActionFailed: If the command returned non-zero exit code.
        """
        result = self._sandbox.execute_helper(action, timeout=timeout, **params)

        if result["timed_out"]:
            raise ActionTimeout(
                f"Action '{action_type}' timed out after {timeout}s",
                action_type=action_type,
                timeout_seconds=timeout or 0.0,
            )

        if result["exit_code"] != 0:
            raise ActionFailed(
                f"Action '{action_type}' failed (exit {result['exit_code']}): "
                f"{result['stderr'].strip()}",
                action_type=action_type,
                exit_code=result["exit_code"],
                stderr=result["stderr"],
            )

        return result

    def _delay(self) -> None:
        """Sleep for action_delay_ms to allow the Windows desktop to process."""
        if self._action_delay_ms > 0:
            time.sleep(self._action_delay_ms / 1000.0)

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------

    def screenshot(
        self,
        *,
        save_path: str | None = None,
        wait_for_idle: float = 0.3,
    ) -> str:
        """Capture a JPEG screenshot and return it as a base64 string.

        Args:
            save_path: Optional host-side path to also write the image.
            wait_for_idle: Seconds to sleep before capturing (default
                0.3s -- slightly longer than Linux to account for
                Windows rendering latency).

        Returns:
            Base64-encoded JPEG screenshot string.
        """
        if wait_for_idle > 0:
            time.sleep(wait_for_idle)

        log.debug("windows_cua_action", action="screenshot")

        result = self._exec_helper(
            "screenshot",
            timeout=ACTION_TIMEOUTS[ActionType.SCREENSHOT] + 5,  # Extra time for SSH overhead
            action_type="screenshot",
            Quality=self._screenshot_quality,
        )

        b64_str: str = result["stdout"].strip()

        if save_path is not None:
            raw_bytes = base64.b64decode(b64_str)
            Path(save_path).write_bytes(raw_bytes)

        return b64_str

    # ------------------------------------------------------------------
    # Mouse actions
    # ------------------------------------------------------------------

    def mouse_move(self, x: int, y: int) -> None:
        """Move the mouse cursor to the given coordinates."""
        log.debug("windows_cua_action", action="mouse_move", x=x, y=y)
        self._exec_helper(
            "mouse_move",
            timeout=ACTION_TIMEOUTS[ActionType.MOUSE_MOVE] + 5,
            action_type="mouse_move",
            X=x, Y=y,
        )
        self._delay()

    def left_click(self, x: int, y: int) -> None:
        """Move to coordinates and left-click."""
        log.debug("windows_cua_action", action="left_click", x=x, y=y)
        self._exec_helper(
            "left_click",
            timeout=ACTION_TIMEOUTS[ActionType.LEFT_CLICK] + 5,
            action_type="left_click",
            X=x, Y=y,
        )
        self._delay()

    def right_click(self, x: int, y: int) -> None:
        """Move to coordinates and right-click."""
        log.debug("windows_cua_action", action="right_click", x=x, y=y)
        self._exec_helper(
            "right_click",
            timeout=ACTION_TIMEOUTS[ActionType.RIGHT_CLICK] + 5,
            action_type="right_click",
            X=x, Y=y,
        )
        self._delay()

    def double_click(self, x: int, y: int) -> None:
        """Move to coordinates and double-click."""
        log.debug("windows_cua_action", action="double_click", x=x, y=y)
        self._exec_helper(
            "double_click",
            timeout=ACTION_TIMEOUTS[ActionType.DOUBLE_CLICK] + 5,
            action_type="double_click",
            X=x, Y=y,
        )
        self._delay()

    def middle_click(self, x: int, y: int) -> None:
        """Move to coordinates and middle-click."""
        log.debug("windows_cua_action", action="middle_click", x=x, y=y)
        self._exec_helper(
            "middle_click",
            timeout=ACTION_TIMEOUTS[ActionType.MIDDLE_CLICK] + 5,
            action_type="middle_click",
            X=x, Y=y,
        )
        self._delay()

    def click(self, x: int, y: int, button: str = "left") -> None:
        """Move to coordinates and click the given mouse button."""
        action_map = {
            "left": self.left_click,
            "right": self.right_click,
            "middle": self.middle_click,
        }
        fn = action_map.get(button)
        if fn is None:
            raise ValueError(f"Unknown button: {button!r}")
        fn(x, y)

    def mouse_click(self, button: str = "left") -> None:
        """Click at the CURRENT cursor position (no movement)."""
        pos = self.cursor_position()
        self.click(pos[0], pos[1], button)

    def scroll(self, x: int, y: int, direction: str, clicks: int = 3) -> None:
        """Scroll at the given coordinates."""
        log.debug("windows_cua_action", action="scroll", x=x, y=y, direction=direction)
        self._exec_helper(
            "scroll",
            timeout=ACTION_TIMEOUTS[ActionType.SCROLL] + 5,
            action_type="scroll",
            X=x, Y=y, Direction=direction, Clicks=clicks,
        )
        self._delay()

    def left_click_drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
    ) -> None:
        """Drag from start coordinates to end coordinates."""
        log.debug(
            "windows_cua_action",
            action="left_click_drag",
            start=(start_x, start_y),
            end=(end_x, end_y),
        )
        self._exec_helper(
            "left_click_drag",
            timeout=ACTION_TIMEOUTS[ActionType.LEFT_CLICK_DRAG] + 5,
            action_type="left_click_drag",
            X=start_x, Y=start_y, EndX=end_x, EndY=end_y,
        )
        self._delay()

    # ------------------------------------------------------------------
    # Keyboard actions
    # ------------------------------------------------------------------

    def type_text(self, text: str) -> None:
        """Type a string of text."""
        log.debug("windows_cua_action", action="type_text", length=len(text))
        self._exec_helper(
            "type",
            timeout=ACTION_TIMEOUTS[ActionType.TYPE] + 10,
            action_type="type_text",
            Text=text,
        )
        self._delay()

    def key_combo(self, keys: str) -> None:
        """Press a key or key combination (e.g. ``"ctrl+c"``, ``"Return"``)."""
        log.debug("windows_cua_action", action="key_combo", keys=keys)
        self._exec_helper(
            "key",
            timeout=ACTION_TIMEOUTS[ActionType.KEY] + 5,
            action_type="key_combo",
            Keys=keys,
        )
        self._delay()

    hotkey = key_combo

    # ------------------------------------------------------------------
    # Query actions
    # ------------------------------------------------------------------

    def cursor_position(self) -> tuple[int, int]:
        """Return the current mouse cursor position as (x, y)."""
        log.debug("windows_cua_action", action="cursor_position")
        result = self._exec_helper(
            "cursor_position",
            timeout=ACTION_TIMEOUTS[ActionType.CURSOR_POSITION] + 5,
            action_type="cursor_position",
        )

        x: int | None = None
        y: int | None = None
        for line in result["stdout"].splitlines():
            if line.startswith("X="):
                x = int(line.split("=", 1)[1])
            elif line.startswith("Y="):
                y = int(line.split("=", 1)[1])

        if x is None or y is None:
            raise ValueError(
                f"Could not parse cursor position from output: {result['stdout']!r}"
            )

        return (x, y)

    # ------------------------------------------------------------------
    # Anthropic agent loop passthrough
    # ------------------------------------------------------------------

    def execute_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Execute an action dict in the Anthropic computer_20251124 format.

        Same interface as :meth:`CUAActionHandler.execute_action`.

        Args:
            action: Action dict with an ``"action"`` key.

        Returns:
            For ``screenshot``: ``{"type": "screenshot", "data": <base64>}``
            For ``cursor_position``: ``{"type": "cursor_position", "coordinate": [x, y]}``
            For all others: ``{"type": <action_name>, "status": "ok"}``
        """
        action_name = action.get("action", "")
        log.debug("windows_cua_execute_action", action=action_name)

        if action_name == "screenshot":
            b64 = self.screenshot()
            return {"type": "screenshot", "data": b64}

        elif action_name == "mouse_move":
            x, y = action["coordinate"]
            self.mouse_move(x, y)

        elif action_name == "left_click":
            x, y = action["coordinate"]
            self.left_click(x, y)

        elif action_name == "right_click":
            x, y = action["coordinate"]
            self.right_click(x, y)

        elif action_name == "double_click":
            x, y = action["coordinate"]
            self.double_click(x, y)

        elif action_name == "middle_click":
            x, y = action["coordinate"]
            self.middle_click(x, y)

        elif action_name == "left_click_drag":
            sx, sy = action["start_coordinate"]
            ex, ey = action["coordinate"]
            self.left_click_drag(sx, sy, ex, ey)

        elif action_name == "type":
            self.type_text(action["text"])

        elif action_name == "key":
            self.key_combo(action["text"])

        elif action_name == "scroll":
            x, y = action["coordinate"]
            direction = action.get("direction", "down")
            clicks = int(action.get("amount", 3))
            self.scroll(x, y, direction, clicks)

        elif action_name == "cursor_position":
            pos_x, pos_y = self.cursor_position()
            return {"type": "cursor_position", "coordinate": [pos_x, pos_y]}

        else:
            raise ValueError(
                f"Unknown CUA action: {action_name!r}. "
                f"Supported: screenshot, mouse_move, left_click, right_click, "
                f"double_click, middle_click, left_click_drag, type, key, "
                f"scroll, cursor_position"
            )

        return {"type": action_name, "status": "ok"}

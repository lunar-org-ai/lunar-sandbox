"""CUA action handler: translates Anthropic computer_20251124 action dicts
into xdotool/maim shell commands executed inside a DockerSandbox.

Provides both typed convenience methods (``click()``, ``type_text()``,
``screenshot()``) and a raw ``execute_action(action_dict)`` passthrough
that is compatible with the Anthropic agent loop.

Usage::

    from lunar_sandbox.actions.cua_handler import CUAActionHandler
    from lunar_sandbox.sandbox.cua_config import CUASandboxConfig

    handler = CUAActionHandler(sandbox, config)

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
import shlex
import time
from pathlib import Path
from typing import Any

import structlog

from lunar_sandbox.actions.types import ACTION_TIMEOUTS, ActionType
from lunar_sandbox.sandbox.cua_config import CUASandboxConfig
from lunar_sandbox.sandbox.cua_errors import ActionFailed, ActionTimeout
from lunar_sandbox.sandbox.docker_sandbox import DockerSandbox

__all__ = ["CUAActionHandler"]

log = structlog.get_logger(__name__)


class CUAActionHandler:
    """Translates CUA action requests into xdotool/maim shell commands.

    Holds a reference to a :class:`~lunar_sandbox.sandbox.docker_sandbox.DockerSandbox`
    and executes commands via ``sandbox.execute()``.  All actions raise
    :class:`~lunar_sandbox.sandbox.cua_errors.ActionTimeout` or
    :class:`~lunar_sandbox.sandbox.cua_errors.ActionFailed` on failure.

    Attributes:
        _sandbox: Underlying Docker sandbox for command execution.
        _config: CUA sandbox configuration (display, quality, delays).
        _action_delay_ms: Milliseconds to sleep after mouse/keyboard actions.
        _screenshot_quality: JPEG quality for maim (1-10).
        _display: X11 display identifier (e.g. ``":1"``).
    """

    __slots__ = (
        "_sandbox",
        "_config",
        "_action_delay_ms",
        "_screenshot_quality",
        "_display",
    )

    def __init__(self, sandbox: DockerSandbox, config: CUASandboxConfig) -> None:
        """Initialise the handler.

        Args:
            sandbox: Running DockerSandbox (or CUASandbox) to execute against.
            config: CUA configuration providing display, quality, and timing.
        """
        self._sandbox = sandbox
        self._config = config
        self._action_delay_ms: int = config.action_delay_ms
        self._screenshot_quality: int = config.screenshot_quality
        self._display: str = config.display

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _exec(self, command: str, timeout: float | None = None, *, action_type: str = "") -> dict[str, Any]:
        """Execute a shell command in the sandbox and check for errors.

        Args:
            command: Shell command string to execute inside the container.
            timeout: Maximum seconds to wait (None = no timeout).
            action_type: Human-readable action name for error messages.

        Returns:
            Result dict from ``sandbox.execute()``.

        Raises:
            ActionTimeout: If the command exceeded the timeout.
            ActionFailed: If the command returned non-zero exit code.
        """
        result = self._sandbox.execute(command, timeout=timeout)

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
        """Sleep for action_delay_ms to allow X11 to process the event."""
        if self._action_delay_ms > 0:
            time.sleep(self._action_delay_ms / 1000.0)

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------

    def screenshot(
        self,
        *,
        save_path: str | None = None,
        wait_for_idle: float = 0.1,
    ) -> str:
        """Capture a JPEG screenshot and return it as a base64 string.

        Args:
            save_path: Optional host-side path to also write the decoded
                image bytes.  Uses ``pathlib``, not docker exec.
            wait_for_idle: Seconds to sleep before capturing, allowing the
                screen to settle after recent actions.  Default 0.1s provides
                a small stabilisation delay; set to 0 for maximum speed.

        Returns:
            Base64-encoded JPEG screenshot string.

        Raises:
            ActionTimeout: If maim exceeds its timeout.
            ActionFailed: If maim returns non-zero exit code.
        """
        if wait_for_idle > 0:
            time.sleep(wait_for_idle)

        log.debug("cua_action", action="screenshot", wait_for_idle=wait_for_idle)

        cmd = f"maim -f jpg -m {self._screenshot_quality} | base64 -w 0"
        result = self._exec(
            cmd,
            timeout=ACTION_TIMEOUTS[ActionType.SCREENSHOT],
            action_type="screenshot",
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
        """Move the mouse cursor to the given coordinates.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
        """
        log.debug("cua_action", action="mouse_move", x=x, y=y)
        self._exec(
            f"xdotool mousemove --sync {x} {y}",
            timeout=ACTION_TIMEOUTS[ActionType.MOUSE_MOVE],
            action_type="mouse_move",
        )
        self._delay()

    def click(self, x: int, y: int, button: str = "left") -> None:
        """Move to coordinates and click the given mouse button.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
            button: Button name (``"left"``, ``"middle"``, ``"right"``).
        """
        button_num = _button_num(button)
        log.debug("cua_action", action="click", x=x, y=y, button=button)
        self._exec(
            f"xdotool mousemove --sync {x} {y} click {button_num}",
            timeout=ACTION_TIMEOUTS[ActionType.LEFT_CLICK],
            action_type="click",
        )
        self._delay()

    def left_click(self, x: int, y: int) -> None:
        """Move to coordinates and left-click.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
        """
        log.debug("cua_action", action="left_click", x=x, y=y)
        self._exec(
            f"xdotool mousemove --sync {x} {y} click 1",
            timeout=ACTION_TIMEOUTS[ActionType.LEFT_CLICK],
            action_type="left_click",
        )
        self._delay()

    def right_click(self, x: int, y: int) -> None:
        """Move to coordinates and right-click.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
        """
        log.debug("cua_action", action="right_click", x=x, y=y)
        self._exec(
            f"xdotool mousemove --sync {x} {y} click 3",
            timeout=ACTION_TIMEOUTS[ActionType.RIGHT_CLICK],
            action_type="right_click",
        )
        self._delay()

    def double_click(self, x: int, y: int) -> None:
        """Move to coordinates and double-click.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
        """
        log.debug("cua_action", action="double_click", x=x, y=y)
        self._exec(
            f"xdotool mousemove --sync {x} {y} click --repeat 2 --delay 50 1",
            timeout=ACTION_TIMEOUTS[ActionType.DOUBLE_CLICK],
            action_type="double_click",
        )
        self._delay()

    def middle_click(self, x: int, y: int) -> None:
        """Move to coordinates and middle-click.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
        """
        log.debug("cua_action", action="middle_click", x=x, y=y)
        self._exec(
            f"xdotool mousemove --sync {x} {y} click 2",
            timeout=ACTION_TIMEOUTS[ActionType.MIDDLE_CLICK],
            action_type="middle_click",
        )
        self._delay()

    def mouse_click(self, button: str = "left") -> None:
        """Click at the CURRENT cursor position (no movement).

        Use this for fine-grained control when you have already positioned
        the cursor with ``mouse_move()``.

        Args:
            button: Button name (``"left"``, ``"middle"``, ``"right"``).
        """
        button_num = _button_num(button)
        log.debug("cua_action", action="mouse_click", button=button)
        self._exec(
            f"xdotool click {button_num}",
            timeout=ACTION_TIMEOUTS[ActionType.LEFT_CLICK],
            action_type="mouse_click",
        )
        self._delay()

    def scroll(self, x: int, y: int, direction: str, clicks: int = 3) -> None:
        """Scroll at the given coordinates.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
            direction: ``"up"`` or ``"down"``.
            clicks: Number of scroll clicks (default 3).
        """
        button = 4 if direction == "up" else 5
        log.debug("cua_action", action="scroll", x=x, y=y, direction=direction, clicks=clicks)
        self._exec(
            f"xdotool mousemove --sync {x} {y} click --repeat {clicks} {button}",
            timeout=ACTION_TIMEOUTS[ActionType.SCROLL],
            action_type="scroll",
        )
        self._delay()

    def left_click_drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
    ) -> None:
        """Drag from start coordinates to end coordinates with left button held.

        Performs a mousedown-move-mouseup sequence, with a short sleep
        between the move steps to allow the window manager to register the
        drag gesture.

        Args:
            start_x: Drag start X coordinate.
            start_y: Drag start Y coordinate.
            end_x: Drag end X coordinate.
            end_y: Drag end Y coordinate.
        """
        log.debug(
            "cua_action",
            action="left_click_drag",
            start=(start_x, start_y),
            end=(end_x, end_y),
        )
        cmd = (
            f"xdotool mousemove --sync {start_x} {start_y} "
            f"mousedown 1 "
            f"sleep 0.1 "
            f"mousemove --sync {end_x} {end_y} "
            f"mouseup 1"
        )
        self._exec(
            cmd,
            timeout=ACTION_TIMEOUTS[ActionType.LEFT_CLICK_DRAG],
            action_type="left_click_drag",
        )
        self._delay()

    # ------------------------------------------------------------------
    # Keyboard actions
    # ------------------------------------------------------------------

    def type_text(self, text: str) -> None:
        """Type a string of text using xdotool type.

        Uses ``shlex.quote()`` for shell safety and the ``--`` separator
        to prevent xdotool from interpreting text starting with ``-`` as flags.

        Args:
            text: Text to type.
        """
        quoted = shlex.quote(text)
        log.debug("cua_action", action="type_text", length=len(text))
        self._exec(
            f"xdotool type --delay {self._action_delay_ms} -- {quoted}",
            timeout=ACTION_TIMEOUTS[ActionType.TYPE],
            action_type="type_text",
        )
        self._delay()

    def key_combo(self, keys: str) -> None:
        """Press a key or key combination using xdotool key.

        Accepts xdotool key syntax, e.g. ``"ctrl+c"``, ``"Return"``,
        ``"super+d"``.

        Args:
            keys: Key or modifier+key string.
        """
        log.debug("cua_action", action="key_combo", keys=keys)
        self._exec(
            f"xdotool key -- {keys}",
            timeout=ACTION_TIMEOUTS[ActionType.KEY],
            action_type="key_combo",
        )
        self._delay()

    # Alias: hotkey is an alternate name for key_combo
    hotkey = key_combo

    # ------------------------------------------------------------------
    # Query actions
    # ------------------------------------------------------------------

    def cursor_position(self) -> tuple[int, int]:
        """Return the current mouse cursor position.

        Returns:
            ``(x, y)`` pixel coordinates.

        Raises:
            ActionTimeout: If xdotool exceeds its timeout.
            ActionFailed: If xdotool returns non-zero exit code.
            ValueError: If output cannot be parsed.
        """
        log.debug("cua_action", action="cursor_position")
        result = self._exec(
            "xdotool getmouselocation --shell",
            timeout=ACTION_TIMEOUTS[ActionType.CURSOR_POSITION],
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

        This passthrough method allows the Anthropic agent loop to send
        action dicts directly to the handler without needing to know which
        typed method to call.

        Supported action types:
            - ``screenshot``
            - ``mouse_move``
            - ``left_click``
            - ``right_click``
            - ``double_click``
            - ``middle_click``
            - ``left_click_drag``
            - ``type``
            - ``key``
            - ``scroll``
            - ``cursor_position``

        Args:
            action: Action dict with at minimum an ``"action"`` key.

        Returns:
            For ``screenshot``: ``{"type": "screenshot", "data": <base64>}``
            For ``cursor_position``: ``{"type": "cursor_position", "coordinate": [x, y]}``
            For all others: ``{"type": <action_name>, "status": "ok"}``

        Raises:
            ValueError: If the action type is not recognised.
        """
        action_name = action.get("action", "")
        log.debug("cua_execute_action", action=action_name)

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


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _button_num(button: str) -> int:
    """Map a button name to an xdotool button number.

    Args:
        button: One of ``"left"``, ``"middle"``, ``"right"``.

    Returns:
        xdotool button number (1, 2, or 3).

    Raises:
        ValueError: If button name is not recognised.
    """
    mapping = {"left": 1, "middle": 2, "right": 3}
    if button not in mapping:
        raise ValueError(
            f"Unknown button: {button!r}. Expected one of: {list(mapping)}"
        )
    return mapping[button]

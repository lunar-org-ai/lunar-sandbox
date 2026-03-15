"""Model-driven CUA agent using Claude's computer-use capability.

Calls the Anthropic Messages API directly via httpx — no SDK dependency.
The agent sends each screenshot to Claude and receives computer-use tool
calls (click, type, key, scroll, etc.) which map directly to the action
dict format expected by CUAActionHandler.

Requires ANTHROPIC_API_KEY in environment.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from lunar_sandbox.cua.observation import CUAObservation

__all__ = ["ModelAgent"]

log = structlog.get_logger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-sonnet-4-20250514"


class ModelAgent:
    """CUA agent that uses a multimodal Claude model to decide actions.

    Each call sends the current screenshot to Claude with the task
    instruction and conversation history. Claude responds with
    computer-use tool calls that are translated into action dicts.

    Args:
        instruction: The task instruction shown to the model.
        screen_size: Display resolution as (width, height).
        model: Anthropic model ID to use.
        api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
    """

    def __init__(
        self,
        instruction: str,
        screen_size: tuple[int, int] = (1280, 800),
        model: str = _DEFAULT_MODEL,
        api_key: str | None = None,
    ) -> None:
        self._instruction = instruction
        self._screen_size = screen_size
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required. Set it as an environment "
                "variable or pass api_key to ModelAgent."
            )
        self._messages: list[dict[str, Any]] = []
        self._client = httpx.AsyncClient(timeout=60.0)

    async def __call__(self, obs: CUAObservation) -> dict[str, Any]:
        """Process an observation and return the next action.

        Args:
            obs: Current observation with screenshot_b64 data.

        Returns:
            Action dict compatible with CUAActionHandler.execute_action().
        """
        # Build the user message with the screenshot
        content: list[dict[str, Any]] = []

        if obs.screenshot_b64:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": obs.screenshot_b64,
                },
            })

        if obs.error_message:
            content.append({
                "type": "text",
                "text": f"Error from previous action: {obs.error_message}",
            })

        if not content:
            content.append({"type": "text", "text": "What should I do next?"})

        self._messages.append({"role": "user", "content": content})

        # Call Claude API
        response = await self._call_api()

        # Parse the response
        action = self._parse_response(response)

        # Add assistant response to conversation history
        self._messages.append({
            "role": "assistant",
            "content": response.get("content", []),
        })

        log.debug("model_agent_action", action=action.get("action"))
        return action

    async def _call_api(self) -> dict[str, Any]:
        """Make a raw HTTP call to the Anthropic Messages API."""
        w, h = self._screen_size

        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "system": (
                f"You are a computer-use agent. Your task: {self._instruction}\n\n"
                f"The screen resolution is {w}x{h}. "
                "Use the computer tool to interact with the desktop. "
                "When the task is complete, respond with a text message "
                "containing the word DONE (do not use the computer tool)."
            ),
            "tools": [
                {
                    "type": "computer_20250124",
                    "name": "computer",
                    "display_width_px": w,
                    "display_height_px": h,
                    "display_number": 1,
                },
            ],
            "messages": self._messages,
        }

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2025-01-24",
            "content-type": "application/json",
            "anthropic-beta": "computer-use-2025-01-24",
        }

        resp = await self._client.post(_API_URL, json=payload, headers=headers)

        if resp.status_code != 200:
            log.error(
                "model_agent_api_error",
                status=resp.status_code,
                body=resp.text[:500],
            )
            raise RuntimeError(
                f"Anthropic API returned {resp.status_code}: {resp.text[:200]}"
            )

        return resp.json()

    def _parse_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Extract an action dict from the Claude API response.

        Looks for a computer-use tool_use block. If Claude responds with
        only text (no tool call), treats it as a stop signal.
        """
        for block in response.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "computer":
                inp = block.get("input", {})
                action_type = inp.get("action", "")

                # Map Claude's computer-use actions to our action dict format
                action: dict[str, Any] = {"action": action_type}

                if "coordinate" in inp:
                    action["coordinate"] = inp["coordinate"]
                if "start_coordinate" in inp:
                    action["start_coordinate"] = inp["start_coordinate"]
                if "text" in inp:
                    action["text"] = inp["text"]
                if "direction" in inp:
                    action["direction"] = inp["direction"]
                if "amount" in inp:
                    action["amount"] = inp["amount"]

                return action

            elif block.get("type") == "text":
                text = block.get("text", "")
                if "DONE" in text.upper():
                    return {"action": "done"}

        # If stop_reason is end_turn with no tool use, treat as done
        if response.get("stop_reason") == "end_turn":
            return {"action": "done"}

        return {"action": "screenshot"}

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

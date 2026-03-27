"""Anthropic model provider for CUA agents.

Calls the Anthropic Messages API directly via httpx with the
``computer_20250124`` tool type. No SDK dependency.

Usage::

    provider = AnthropicProvider(
        api_key="<your-api-key>",
        instruction="Open the calculator and compute 42 * 17",
        screen_size=(1280, 800),
        os_hint="linux",
    )
    response = await provider(observation)
    print(response.action)  # {"action": "left_click", "coordinate": [300, 400]}
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from lunar_sandbox.cua.observation import CUAObservation
from lunar_sandbox.cua.providers.base import ModelResponse

__all__ = ["AnthropicProvider"]

log = structlog.get_logger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-sonnet-4-20250514"

# System prompts per OS
_LINUX_SYSTEM_PROMPT = (
    "You are a computer-use agent. Your task: {instruction}\n\n"
    "The screen resolution is {w}x{h}. "
    "You are controlling a Linux desktop with Openbox window manager. "
    "To open applications, RIGHT-CLICK on the desktop to get the Openbox menu, "
    "then navigate the menu to find and launch applications. "
    "Available apps include: Chromium (web browser), LXTerminal, "
    "Mousepad (text editor), PCManFM (file manager), and Galculator (calculator). "
    "Use the computer tool to interact with the desktop. "
    "Be precise with coordinates when clicking. "
    "When the task is complete, respond with a text message "
    "containing the word DONE (do not use the computer tool)."
)

_WINDOWS_SYSTEM_PROMPT = (
    "You are a computer-use agent. Your task: {instruction}\n\n"
    "The screen resolution is {w}x{h}. "
    "You are controlling a Windows desktop. "
    "You can open applications via the Start menu (click bottom-left corner), "
    "the taskbar, or by using keyboard shortcuts (Win+R for Run dialog). "
    "Available apps include: Microsoft Edge (web browser), Notepad, "
    "File Explorer, Calculator, and any installed Windows applications. "
    "Use the computer tool to interact with the desktop. "
    "Be precise with coordinates when clicking. "
    "When the task is complete, respond with a text message "
    "containing the word DONE (do not use the computer tool)."
)


class AnthropicProvider:
    """CUA model provider using the Anthropic Messages API.

    Manages conversation history and translates Claude's computer-use
    tool calls into standardised action dicts.

    Args:
        instruction: Task instruction shown to the model.
        screen_size: Display resolution as (width, height).
        model: Anthropic model ID.
        api_key: API key. Falls back to ``ANTHROPIC_API_KEY`` env var.
        os_hint: Target OS (``"linux"`` or ``"windows"``).
        api_url: Override API endpoint URL (e.g. for proxies).
    """

    def __init__(
        self,
        instruction: str,
        screen_size: tuple[int, int] = (1280, 800),
        model: str = _DEFAULT_MODEL,
        api_key: str | None = None,
        os_hint: str = "linux",
        api_url: str = _API_URL,
    ) -> None:
        self._instruction = instruction
        self._screen_size = screen_size
        self._model = model
        self._os_hint = os_hint
        self._api_url = api_url
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required. Set it as an environment "
                "variable or pass api_key to AnthropicProvider."
            )
        self._messages: list[dict[str, Any]] = []
        self._pending_tool_use_id: str | None = None
        self._client = httpx.AsyncClient(timeout=60.0)

    async def __call__(self, obs: CUAObservation) -> ModelResponse:
        """Process an observation and return the next action."""
        content: list[dict[str, Any]] = []

        if self._pending_tool_use_id:
            tool_result_content: list[dict[str, Any]] = []
            if obs.screenshot_b64:
                tool_result_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": obs.screenshot_b64,
                    },
                })
            if obs.error_message:
                tool_result_content.append({
                    "type": "text",
                    "text": f"Error: {obs.error_message}",
                })
            if not tool_result_content:
                tool_result_content.append({"type": "text", "text": "Action executed."})

            content.append({
                "type": "tool_result",
                "tool_use_id": self._pending_tool_use_id,
                "content": tool_result_content,
            })
            self._pending_tool_use_id = None
        else:
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

        response = await self._call_api()

        self._messages.append({
            "role": "assistant",
            "content": response.get("content", []),
        })

        action, reasoning = self._parse_response(response)

        log.debug("anthropic_provider_action", action=action.get("action"))
        return ModelResponse(action=action, reasoning=reasoning, raw_response=response)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _call_api(self) -> dict[str, Any]:
        w, h = self._screen_size

        template = _WINDOWS_SYSTEM_PROMPT if self._os_hint == "windows" else _LINUX_SYSTEM_PROMPT
        system_prompt = template.format(instruction=self._instruction, w=w, h=h)

        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "system": system_prompt,
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
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "anthropic-beta": "computer-use-2025-01-24",
        }

        resp = await self._client.post(self._api_url, json=payload, headers=headers)

        if resp.status_code != 200:
            log.error(
                "anthropic_api_error",
                status=resp.status_code,
                body=resp.text[:500],
            )
            raise RuntimeError(
                f"Anthropic API returned {resp.status_code}: {resp.text[:200]}"
            )

        return resp.json()

    def _parse_response(self, response: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """Parse Claude's response into (action_dict, reasoning)."""
        reasoning_parts = []
        for block in response.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                reasoning_parts.append(block["text"])
        reasoning = "\n".join(reasoning_parts) if reasoning_parts else None

        for block in response.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "computer":
                self._pending_tool_use_id = block.get("id")
                inp = block.get("input", {})
                action_type = inp.get("action", "")

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

                return action, reasoning

            elif block.get("type") == "text":
                text = block.get("text", "")
                if "DONE" in text.upper():
                    return {"action": "done"}, reasoning

        if response.get("stop_reason") == "end_turn":
            return {"action": "done"}, reasoning

        return {"action": "screenshot"}, reasoning

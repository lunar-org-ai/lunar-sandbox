"""Azure OpenAI model provider for CUA agents.

Calls the Azure OpenAI Responses API with the ``computer_use_preview``
tool type. Uses httpx directly -- no SDK dependency.

Requires an Azure OpenAI resource with a deployment that supports
computer use (e.g. ``computer-use-preview``).

Usage::

    provider = AzureOpenAIProvider(
        endpoint="https://my-resource.openai.azure.com",
        deployment="computer-use-preview",
        api_key="...",
        instruction="Open the calculator and compute 42 * 17",
        screen_size=(1280, 800),
        os_hint="windows",
    )
    response = await provider(observation)
    print(response.action)  # {"action": "left_click", "coordinate": [300, 400]}

Azure OpenAI Responses API reference:
    https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/computer-use
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from lunar_sandbox.cua.observation import CUAObservation
from lunar_sandbox.cua.providers.base import ModelResponse

__all__ = ["AzureOpenAIProvider"]

log = structlog.get_logger(__name__)

_DEFAULT_API_VERSION = "2025-03-01-preview"

# gpt-5.4+ uses the /openai/v1/ path with tool type "computer" (GA).
# Older models used /openai/responses with "computer_use_preview" (deprecated).
_V1_MODELS = {"gpt-5.4", "gpt-5.3", "gpt-5.2", "gpt-5.1", "gpt-5"}

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
    "containing the word DONE."
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
    "containing the word DONE."
)


class AzureOpenAIProvider:
    """CUA model provider using Azure OpenAI Responses API.

    Uses the ``computer_use_preview`` tool type available in Azure OpenAI
    to control a computer. The Responses API maintains server-side
    conversation state via ``previous_response_id``.

    Args:
        endpoint: Azure OpenAI resource endpoint URL
            (e.g. ``https://my-resource.openai.azure.com``).
        deployment: Deployment name (e.g. ``gpt-4o-cua``). The deployment
            must use a model that supports the ``computer_use_preview``
            tool (gpt-4.1, gpt-4o 2024-11-20+).
        api_key: Azure OpenAI API key. Falls back to
            ``AZURE_OPENAI_API_KEY`` env var.
        instruction: Task instruction shown to the model.
        screen_size: Display resolution as (width, height).
        os_hint: Target OS (``"linux"`` or ``"windows"``).
        api_version: Azure API version string.
        model: Model name for the ``model`` field in the API request.
            Defaults to the deployment name.
    """

    def __init__(
        self,
        endpoint: str,
        deployment: str,
        instruction: str,
        screen_size: tuple[int, int] = (1280, 800),
        api_key: str | None = None,
        os_hint: str = "windows",
        api_version: str = _DEFAULT_API_VERSION,
        model: str | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._deployment = deployment
        self._instruction = instruction
        self._screen_size = screen_size
        self._os_hint = os_hint
        self._api_version = api_version
        self._model = model or deployment
        self._api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "AZURE_OPENAI_API_KEY is required. Set it as an environment "
                "variable or pass api_key to AzureOpenAIProvider."
            )

        # Responses API state
        self._previous_response_id: str | None = None
        self._pending_call_id: str | None = None

        self._client = httpx.AsyncClient(timeout=90.0)

    async def __call__(self, obs: CUAObservation) -> ModelResponse:
        """Process an observation and return the next action."""
        w, h = self._screen_size

        # Build the input for this turn
        input_items: list[dict[str, Any]] = []

        if self._pending_call_id:
            # Send computer_call_output with the new screenshot
            output: dict[str, Any] = {"type": "computer_call_output", "call_id": self._pending_call_id}
            if obs.screenshot_b64:
                output["output"] = {
                    "type": "computer_screenshot",
                    "image_url": f"data:image/jpeg;base64,{obs.screenshot_b64}",
                }
            if obs.error_message:
                output["output"] = {"type": "text", "text": f"Error: {obs.error_message}"}
            input_items.append(output)
            self._pending_call_id = None
        else:
            # First turn: send instruction + initial screenshot
            template = _WINDOWS_SYSTEM_PROMPT if self._os_hint == "windows" else _LINUX_SYSTEM_PROMPT
            system_text = template.format(instruction=self._instruction, w=w, h=h)
            input_items.append({"type": "message", "role": "user", "content": system_text})
            if obs.screenshot_b64:
                input_items.append({
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": f"data:image/jpeg;base64,{obs.screenshot_b64}",
                        },
                        {"type": "input_text", "text": "This is the current screen. What action should I take?"},
                    ],
                })

        # Build request payload — tool format depends on model generation
        if self._is_v1_model():
            # gpt-5.x: GA "computer" tool (no display params)
            tools = [{"type": "computer"}]
        else:
            # Older: preview tool with display dimensions
            environment = "windows" if self._os_hint == "windows" else "linux"
            tools = [{
                "type": "computer_use_preview",
                "display_width": w,
                "display_height": h,
                "environment": environment,
            }]

        payload: dict[str, Any] = {
            "model": self._model,
            "input": input_items,
            "tools": tools,
            "truncation": "auto",
        }

        if self._is_v1_model():
            payload["reasoning"] = {"summary": "concise"}
            # Ask the model to explain its actions in commentary messages
            if "instructions" not in payload:
                payload["instructions"] = (
                    "Before each action, briefly explain what you see on screen "
                    "and what you plan to do next in a short message."
                )

        if self._previous_response_id:
            payload["previous_response_id"] = self._previous_response_id

        # Call the API
        response = await self._call_api(payload)

        # Track response ID for conversation continuity
        self._previous_response_id = response.get("id")

        # Parse the response
        action, reasoning = self._parse_response(response)

        log.debug("azure_openai_provider_action", action=action.get("action"))
        return ModelResponse(action=action, reasoning=reasoning, raw_response=response)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _is_v1_model(self) -> bool:
        """Check if the deployment uses a model that requires the /v1/ API path."""
        # Match if the deployment name or model name contains a v1-era model prefix
        name = self._deployment.lower()
        return any(m in name for m in ("gpt-5", "gpt5"))

    async def _call_api(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Make a request to the Azure OpenAI Responses API."""
        if self._is_v1_model():
            # gpt-5.x uses /openai/v1/responses (no api-version query param)
            url = f"{self._endpoint}/openai/v1/responses"
        else:
            # Older models use /openai/responses with api-version
            url = f"{self._endpoint}/openai/responses?api-version={self._api_version}"

        headers = {
            "api-key": self._api_key,
            "content-type": "application/json",
        }

        resp = await self._client.post(url, json=payload, headers=headers)

        if resp.status_code != 200:
            log.error(
                "azure_openai_api_error",
                status=resp.status_code,
                body=resp.text[:500],
            )
            raise RuntimeError(
                f"Azure OpenAI API returned {resp.status_code}: {resp.text[:200]}"
            )

        return resp.json()

    def _parse_response(self, response: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """Parse Azure OpenAI response into (action_dict, reasoning).

        The Responses API returns output items that can be:
        - ``computer_call``: A computer-use action to execute.
        - ``message``: Text output from the model.

        Computer call actions from Azure OpenAI:
        - click(x, y, button)
        - double_click(x, y)
        - drag(startX, startY, endX, endY)
        - keypress(keys)
        - type(text)
        - screenshot()
        - scroll(x, y, direction, amount)
        - wait()
        - move(x, y)
        """
        reasoning_parts = []

        for item in response.get("output", []):
            item_type = item.get("type", "")

            if item_type == "reasoning":
                # gpt-5.x reasoning summaries
                for summary in item.get("summary", []):
                    text = summary.get("text", "").strip()
                    if text:
                        reasoning_parts.append(text)

            elif item_type == "message":
                # Extract text content — commentary and final answers
                for content_block in item.get("content", []):
                    if content_block.get("type") == "output_text":
                        text = content_block.get("text", "").strip()
                        if text:
                            reasoning_parts.append(text)
                        if text and "DONE" in text.upper():
                            reasoning = "\n".join(reasoning_parts) if reasoning_parts else None
                            return {"action": "done"}, reasoning

            elif item_type == "computer_call":
                self._pending_call_id = item.get("call_id")

                # gpt-5.x returns batched actions[] array;
                # older models return a single action dict.
                actions_list = item.get("actions")
                if actions_list and isinstance(actions_list, list):
                    # Batched format — take the first action
                    action_data = actions_list[0]
                else:
                    action_data = item.get("action", {})

                azure_action_type = action_data.get("type", "")
                reasoning = "\n".join(reasoning_parts) if reasoning_parts else None
                action = self._map_azure_action(azure_action_type, action_data)
                return action, reasoning

        reasoning = "\n".join(reasoning_parts) if reasoning_parts else None

        # No computer_call found. Only treat as "done" if the model
        # explicitly said DONE in its message text. Otherwise request
        # another screenshot — the model may just be providing commentary
        # before acting (status=="completed" means the API call finished,
        # NOT that the task is done).
        if reasoning and "DONE" in reasoning.upper():
            return {"action": "done"}, reasoning

        # Ask for another screenshot to prompt the model to act
        return {"action": "screenshot"}, reasoning

    def _map_azure_action(self, action_type: str, data: dict[str, Any]) -> dict[str, Any]:
        """Map Azure OpenAI action format to our standard action dict.

        Azure format uses different field names (x/y vs coordinate,
        separate action types for single/double click, etc.).

        Args:
            action_type: Azure action type string.
            data: Full action data dict from the API.

        Returns:
            Standardised action dict for CUAActionHandler.
        """
        if action_type == "click":
            x = data.get("x", 0)
            y = data.get("y", 0)
            button = data.get("button", "left")
            if button == "left":
                return {"action": "left_click", "coordinate": [x, y]}
            elif button == "right":
                return {"action": "right_click", "coordinate": [x, y]}
            elif button == "middle":
                return {"action": "middle_click", "coordinate": [x, y]}
            return {"action": "left_click", "coordinate": [x, y]}

        elif action_type == "double_click":
            x = data.get("x", 0)
            y = data.get("y", 0)
            return {"action": "double_click", "coordinate": [x, y]}

        elif action_type == "move":
            x = data.get("x", 0)
            y = data.get("y", 0)
            return {"action": "mouse_move", "coordinate": [x, y]}

        elif action_type == "drag":
            return {
                "action": "left_click_drag",
                "start_coordinate": [data.get("startX", 0), data.get("startY", 0)],
                "coordinate": [data.get("endX", 0), data.get("endY", 0)],
            }

        elif action_type == "type":
            return {"action": "type", "text": data.get("text", "")}

        elif action_type == "keypress":
            # Azure sends keys as a list, join with + for our format
            keys = data.get("keys", [])
            if isinstance(keys, list):
                keys_str = "+".join(keys)
            else:
                keys_str = str(keys)
            return {"action": "key", "text": keys_str}

        elif action_type == "scroll":
            x = data.get("x", 0)
            y = data.get("y", 0)
            # gpt-5.x uses scroll_x/scroll_y; older uses direction/amount
            scroll_y = data.get("scroll_y")
            if scroll_y is not None:
                direction = "down" if scroll_y > 0 else "up"
                amount = max(1, abs(scroll_y) // 40)  # ~40px per scroll click
            else:
                direction = data.get("direction", "down")
                amount = data.get("amount", 3)
            return {
                "action": "scroll",
                "coordinate": [x, y],
                "direction": direction,
                "amount": amount,
            }

        elif action_type == "screenshot":
            return {"action": "screenshot"}

        elif action_type == "wait":
            # No direct equivalent -- take a screenshot to observe
            return {"action": "screenshot"}

        else:
            log.warning("azure_openai_unknown_action", action_type=action_type)
            return {"action": "screenshot"}

"""Model-driven CUA agent with pluggable model providers.

Accepts any :class:`ModelProvider` (Anthropic, Azure OpenAI, etc.)
and translates model responses into action dicts for the CUA action
handler.

No SDK dependencies -- all providers use httpx directly.

Usage::

    # Default (Anthropic)
    agent = ModelAgent(
        instruction="Open the calculator",
        screen_size=(1280, 800),
    )

    # Explicit Anthropic provider
    from lunar_sandbox.cua.providers import AnthropicProvider
    provider = AnthropicProvider(instruction="...", screen_size=(1280, 800))
    agent = ModelAgent(provider=provider)

    # Azure OpenAI provider
    from lunar_sandbox.cua.providers import AzureOpenAIProvider
    provider = AzureOpenAIProvider(
        endpoint="https://my-resource.openai.azure.com",
        deployment="computer-use-preview",
        instruction="...",
        screen_size=(1280, 800),
    )
    agent = ModelAgent(provider=provider)
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from lunar_sandbox.cua.observation import CUAObservation

__all__ = ["ModelAgent"]

log = structlog.get_logger(__name__)


class ModelAgent:
    """CUA agent that uses a model provider to decide actions.

    Can be used with any :class:`ModelProvider` implementation. If no
    provider is passed, creates an :class:`AnthropicProvider` from the
    legacy constructor arguments for backward compatibility.

    Args:
        provider: A :class:`ModelProvider` instance. If provided, all
            other arguments are ignored.
        instruction: Task instruction (used to create default provider).
        screen_size: Display resolution (used to create default provider).
        model: Model ID (used to create default Anthropic provider).
        api_key: API key (used to create default Anthropic provider).
        os_hint: Target OS (used to create default provider).
    """

    def __init__(
        self,
        provider: Any | None = None,
        *,
        instruction: str = "",
        screen_size: tuple[int, int] = (1280, 800),
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        os_hint: str = "linux",
    ) -> None:
        if provider is not None:
            self._provider = provider
        else:
            # Backward compatibility: create AnthropicProvider from args
            from lunar_sandbox.cua.providers.anthropic import AnthropicProvider

            self._provider = AnthropicProvider(
                instruction=instruction,
                screen_size=screen_size,
                model=model,
                api_key=api_key,
                os_hint=os_hint,
            )

        self.last_reasoning: str | None = None

    async def __call__(self, obs: CUAObservation) -> dict[str, Any]:
        """Process an observation and return the next action.

        Args:
            obs: Current observation with screenshot_b64 data.

        Returns:
            Action dict compatible with CUAActionHandler.execute_action().
        """
        response = await self._provider(obs)

        self.last_reasoning = response.reasoning

        log.debug("model_agent_action", action=response.action.get("action"))
        return response.action

    async def close(self) -> None:
        """Close the underlying provider's HTTP client."""
        await self._provider.close()

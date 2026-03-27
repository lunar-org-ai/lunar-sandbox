"""Base protocol for CUA model providers.

Defines the :class:`ModelProvider` protocol that all model providers
(Anthropic, Azure OpenAI, etc.) implement. The protocol decouples the
:class:`ModelAgent` from any specific API so that providers can be
swapped without changing agent logic.

A provider:
1. Receives a :class:`CUAObservation` (screenshot + metadata).
2. Calls the model API with the observation and conversation history.
3. Returns a :class:`ModelResponse` containing an action dict and
   optional reasoning text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from lunar_sandbox.cua.observation import CUAObservation

__all__ = ["ModelProvider", "ModelResponse"]


@dataclass
class ModelResponse:
    """Response from a model provider.

    Attributes:
        action: Action dict compatible with ``CUAActionHandler.execute_action()``.
            Must contain at minimum an ``"action"`` key with the action name.
            Example: ``{"action": "left_click", "coordinate": [300, 400]}``
        reasoning: Optional text reasoning/thinking from the model.
            Stored in trajectory for debugging and analysis.
        raw_response: The raw API response dict, for debugging.
            Not stored in trajectory.
    """

    action: dict[str, Any]
    reasoning: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ModelProvider(Protocol):
    """Protocol for CUA model providers.

    Each provider wraps a specific AI model API and handles:
    - Conversation history management
    - API request construction (model-specific format)
    - Response parsing into standardised action dicts
    - OS-aware system prompts (Linux vs Windows)

    Providers are stateful: they maintain conversation history across
    calls so the model can reason about previous actions.

    Implementations must be async-compatible (the ``__call__`` method
    is async).
    """

    async def __call__(self, obs: CUAObservation) -> ModelResponse:
        """Process an observation and return the next action.

        Args:
            obs: Current observation with screenshot_b64 data.

        Returns:
            :class:`ModelResponse` with the action dict and reasoning.
        """
        ...

    async def close(self) -> None:
        """Close underlying HTTP client and release resources."""
        ...

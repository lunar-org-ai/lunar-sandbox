"""Model providers for CUA agents.

Each provider wraps a specific AI model API (Anthropic, Azure OpenAI, etc.)
and translates observations into actions using that model's computer-use
capability.

All providers implement the :class:`ModelProvider` protocol and use httpx
directly -- no SDK dependencies.

Usage::

    from lunar_sandbox.cua.providers import AnthropicProvider, AzureOpenAIProvider

    # Anthropic (default)
    provider = AnthropicProvider(
        api_key="<your-api-key>",
        instruction="Open the calculator",
        screen_size=(1280, 800),
    )

    # Azure OpenAI
    provider = AzureOpenAIProvider(
        endpoint="https://my-resource.openai.azure.com",
        deployment="computer-use-preview",
        api_key="...",
        instruction="Open the calculator",
        screen_size=(1280, 800),
    )

    # Use with ModelAgent
    from lunar_sandbox.cua.model_agent import ModelAgent
    agent = ModelAgent(provider=provider)
"""

from lunar_sandbox.cua.providers.anthropic import AnthropicProvider
from lunar_sandbox.cua.providers.azure_openai import AzureOpenAIProvider
from lunar_sandbox.cua.providers.base import ModelProvider, ModelResponse

__all__ = [
    "ModelProvider",
    "ModelResponse",
    "AnthropicProvider",
    "AzureOpenAIProvider",
]

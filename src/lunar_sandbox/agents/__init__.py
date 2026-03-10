"""Built-in agents for testing and smoke-testing.

Provides simple agent implementations for pipeline validation:

- :class:`EchoAgent`: Submits immediately (simplest possible agent).
- :class:`RandomAgent`: Takes random actions before submitting.

Usage::

    from lunar_sandbox.agents import EchoAgent, RandomAgent
"""

from lunar_sandbox.agents.echo import EchoAgent
from lunar_sandbox.agents.random_agent import RandomAgent

__all__ = [
    "EchoAgent",
    "RandomAgent",
]

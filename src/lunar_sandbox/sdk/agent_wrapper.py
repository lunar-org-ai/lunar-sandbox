"""Agent wrapper for converting plain callables to AgentAdapter.

Provides :class:`CallableAgentAdapter` and :func:`normalize_agent` for
bridging simple user functions into the :class:`AgentAdapter` protocol
expected by the episode runner and scheduler.

The SDK accepts three agent forms:
  1. An :class:`AgentAdapter` Protocol instance (passed through).
  2. A plain callable ``(task, observation) -> (action, params)``.
  3. A class implementing :class:`AgentAdapter` (instantiated per task).
"""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from lunar_sandbox.actions.types import ActionResponse
    from lunar_sandbox.episode.runner import AgentAdapter

__all__ = ["CallableAgentAdapter", "normalize_agent"]


class CallableAgentAdapter:
    """Wraps a simple callable as an AgentAdapter Protocol implementation.

    The callable signature is ``(task, observation) -> (action_type, params)``.
    Both sync and async callables are supported: if the result of calling
    ``fn(task, obs)`` has an ``__await__`` method, it is awaited.

    Args:
        fn: A callable ``(task, observation) -> (action_type, params)``.
        task: The task object passed as the first argument to ``fn``.
    """

    __slots__ = ("_fn", "_task")

    def __init__(self, fn: Callable[..., Any], task: Any = None) -> None:
        self._fn = fn
        self._task = task

    async def act(
        self, observation: ActionResponse | None
    ) -> tuple[str, dict[str, Any]]:
        """Return the next (action_type, params) by calling the wrapped function.

        Args:
            observation: The response from the previous action, or ``None``
                on the first call.

        Returns:
            A tuple of ``(action_type_string, params_dict)``.
        """
        result = self._fn(self._task, observation)
        if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
            result = await result
        return result


def _is_agent_adapter(obj: Any) -> bool:
    """Check if an object satisfies the AgentAdapter Protocol.

    Checks for an ``act`` method that is callable -- this matches the
    structural typing of the AgentAdapter Protocol without requiring
    explicit inheritance.
    """
    return hasattr(obj, "act") and callable(getattr(obj, "act"))


def normalize_agent(
    agent: Any,
) -> Callable[..., Any]:
    """Normalize an agent into an agent_factory callable for the scheduler.

    Handles three forms:

    1. **AgentAdapter instance** -- returns a factory that always returns
       this instance (suitable for single-task usage).
    2. **Class** (with an ``act`` method or without) -- returns a factory
       that instantiates the class per task: ``lambda task: cls(task)``.
    3. **Callable** (function/lambda) -- returns a factory that wraps it
       in :class:`CallableAgentAdapter`: ``lambda task: CallableAgentAdapter(fn, task)``.

    Args:
        agent: An AgentAdapter instance, a class, or a callable.

    Returns:
        A callable ``(task) -> AgentAdapter`` suitable for the scheduler.

    Raises:
        TypeError: If *agent* cannot be normalized to an agent factory.
    """
    # Case 1: Already an AgentAdapter instance (has .act method, not a class)
    if not inspect.isclass(agent) and _is_agent_adapter(agent):
        return lambda task: agent

    # Case 2: A class (either AgentAdapter subclass or plain class)
    if inspect.isclass(agent):
        return lambda task: agent(task)

    # Case 3: A plain callable (function, lambda)
    if callable(agent):
        return lambda task: CallableAgentAdapter(agent, task)

    msg = (
        f"Cannot normalize agent of type {type(agent).__name__}. "
        "Expected an AgentAdapter instance, a class, or a callable."
    )
    raise TypeError(msg)

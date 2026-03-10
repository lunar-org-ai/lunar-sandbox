"""Built-in echo agent for pipeline testing.

The simplest possible agent: it submits immediately on the first
``act()`` call without performing any actions.  Useful for verifying
the end-to-end evaluation pipeline (sandbox, executor, scoring)
without any agent-side complexity.

Usage::

    from lunar_sandbox.agents import EchoAgent

    result = await engine.run("tasks/hello.yaml", EchoAgent)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lunar_sandbox.actions.types import ActionResponse

__all__ = ["EchoAgent"]


class EchoAgent:
    """Agent that immediately submits without performing any actions.

    Implements the :class:`~lunar_sandbox.episode.runner.AgentAdapter`
    Protocol.  On the first ``act()`` call (observation is ``None``),
    returns ``("submit", {})``.

    Args:
        task: Task object (ignored; accepted to match the agent factory
            pattern ``cls(task)``).
    """

    __slots__ = ()

    def __init__(self, task: Any = None) -> None:
        pass  # Task ignored -- echo agent doesn't use it

    async def act(
        self, observation: ActionResponse | None
    ) -> tuple[str, dict[str, Any]]:
        """Return a submit action immediately.

        Args:
            observation: Previous action response (ignored).

        Returns:
            ``("submit", {})`` -- always submits.
        """
        return ("submit", {})

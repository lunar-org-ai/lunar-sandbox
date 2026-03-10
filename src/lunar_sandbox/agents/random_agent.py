"""Built-in random agent for smoke testing.

Performs a configurable number of random actions (shell commands, file
reads) before submitting.  Useful for stress-testing the sandbox
infrastructure, verifying action dispatch, and exercising the
trajectory recording pipeline.

Usage::

    from lunar_sandbox.agents import RandomAgent

    result = await engine.run("tasks/hello.yaml", RandomAgent)
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lunar_sandbox.actions.types import ActionResponse

__all__ = ["RandomAgent"]

# Pools of random actions to choose from
_COMMANDS = [
    "ls",
    "pwd",
    "echo hello",
    "whoami",
    "date",
    "ls -la",
    "cat /etc/hostname",
    "uname -a",
]

_FILES_TO_READ = [
    "README.md",
    "setup.py",
    "pyproject.toml",
    "Makefile",
    "setup.cfg",
]


class RandomAgent:
    """Agent that takes random actions before submitting.

    On each ``act()`` call, randomly chooses between:

    - ``execute_command``: runs a simple shell command from a built-in list.
    - ``read_file``: reads a common project file.
    - ``submit``: after ``max_steps`` random actions.

    Implements the :class:`~lunar_sandbox.episode.runner.AgentAdapter`
    Protocol.

    Args:
        task: Task object (accepted to match the agent factory pattern;
            currently unused).
        max_steps: Number of random actions before submitting.
            Defaults to 5.
    """

    __slots__ = ("_task", "_max_steps", "_step_count")

    def __init__(self, task: Any = None, max_steps: int = 5) -> None:
        self._task = task
        self._max_steps = max_steps
        self._step_count = 0

    async def act(
        self, observation: ActionResponse | None
    ) -> tuple[str, dict[str, Any]]:
        """Return a random action or submit after reaching max_steps.

        Args:
            observation: Previous action response (ignored for action
                selection in this simple agent).

        Returns:
            A tuple of ``(action_type, params)``.
        """
        # Submit after max_steps random actions
        if self._step_count >= self._max_steps:
            return ("submit", {})

        self._step_count += 1

        # Randomly choose between execute_command and read_file
        action_type = random.choice(["execute_command", "read_file"])

        if action_type == "execute_command":
            command = random.choice(_COMMANDS)
            return ("execute_command", {"command": command})
        else:
            file_path = random.choice(_FILES_TO_READ)
            return ("read_file", {"path": file_path})

"""Dynamic agent loading from ``module:ClassName`` specs.

Provides :func:`load_agent_class` for importing agent classes at
runtime, :func:`get_default_agent` for the built-in fallback, and
:func:`make_agent_factory` for creating agent factory callables.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

import typer

__all__ = ["load_agent_class", "get_default_agent", "make_agent_factory"]


def load_agent_class(spec: str) -> type:
    """Load an agent class from a ``module.path:ClassName`` string.

    Args:
        spec: Import specification in ``module:ClassName`` format.

    Returns:
        The agent class object.

    Raises:
        typer.BadParameter: If the spec is malformed, the module
            cannot be imported, or the class is not found.
    """
    if ":" not in spec:
        raise typer.BadParameter(
            f"Agent spec must be 'module.path:ClassName', got: {spec!r}"
        )

    module_path, class_name = spec.rsplit(":", 1)

    if not module_path or not class_name:
        raise typer.BadParameter(
            f"Agent spec must be 'module.path:ClassName', got: {spec!r}"
        )

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise typer.BadParameter(
            f"Cannot import module {module_path!r}: {exc}"
        ) from exc

    try:
        cls = getattr(module, class_name)
    except AttributeError as exc:
        raise typer.BadParameter(
            f"Module {module_path!r} has no class {class_name!r}: {exc}"
        ) from exc

    return cls


def get_default_agent() -> type:
    """Return the default agent class for when ``--agent`` is not specified.

    Falls back to a minimal no-op agent if the ``lunar_sandbox.agents``
    module does not exist yet.

    Returns:
        The default agent class.
    """
    try:
        from lunar_sandbox.agents import EchoAgent

        return EchoAgent
    except ImportError:
        # Agents module not yet created -- return a minimal stub
        return _StubAgent


class _StubAgent:
    """Minimal stub agent used when no agent module is available.

    Acts as a no-op agent that immediately submits, ensuring the CLI
    infrastructure works even before real agent implementations exist.
    """

    def __init__(self, task: Any = None) -> None:
        self._task = task

    async def act(
        self, observation: Any = None
    ) -> tuple[str, dict[str, Any]]:
        """Return a submit action immediately."""
        return ("submit", {})


def make_agent_factory(agent_spec: str | None) -> Callable:
    """Create an agent factory callable from an optional spec string.

    When ``agent_spec`` is None, uses the default agent. When it is
    a ``module:Class`` string, loads the class dynamically.

    Args:
        agent_spec: Optional ``module.path:ClassName`` string.

    Returns:
        A callable that accepts a task and returns an agent instance.
    """
    if agent_spec is None:
        cls = get_default_agent()
    else:
        cls = load_agent_class(agent_spec)

    def factory(task: Any) -> Any:
        return cls(task)

    return factory

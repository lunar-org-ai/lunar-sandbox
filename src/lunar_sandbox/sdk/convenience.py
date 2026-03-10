"""Convenience one-liner functions for quick evaluation.

Provides :func:`run_task` and :func:`run_batch` (plus sync wrappers)
that handle the full :class:`LunarEngine` lifecycle internally.  For
repeated evaluations, use :class:`LunarEngine` directly to amortize
startup cost.

Usage::

    from lunar_sandbox.sdk import run_task

    result = await run_task("tasks/my-task.yaml", my_agent)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from lunar_sandbox.sdk.config import EngineConfig

if TYPE_CHECKING:
    from lunar_sandbox.scheduler.result import BatchResult, TaskResult

__all__ = ["run_batch", "run_batch_sync", "run_task", "run_task_sync"]


async def run_task(
    task: Any,
    agent: Any,
    config: EngineConfig | None = None,
    **kwargs: Any,
) -> TaskResult:
    """Run a single task with automatic engine lifecycle.

    Creates a :class:`LunarEngine`, starts it, runs the task, stops
    the engine, and returns the result.  Uses ``try/finally`` to ensure
    cleanup even on errors.

    Args:
        task: Task definition, YAML path, or task name string.
        agent: An AgentAdapter instance, a class, or a callable.
        config: Optional engine configuration.
        **kwargs: Passed through to :meth:`LunarEngine.run`.

    Returns:
        A :class:`~lunar_sandbox.scheduler.result.TaskResult`.
    """
    from lunar_sandbox.sdk.engine import LunarEngine

    engine = LunarEngine(config)
    try:
        await engine.start()
        return await engine.run(task, agent, **kwargs)
    finally:
        await engine.stop()


def run_task_sync(
    task: Any,
    agent: Any,
    config: EngineConfig | None = None,
    **kwargs: Any,
) -> TaskResult:
    """Synchronous wrapper for :func:`run_task`.

    Uses ``asyncio.run()`` per codebase convention.
    """
    return asyncio.run(run_task(task, agent, config=config, **kwargs))


async def run_batch(
    benchmark: Any,
    agent_factory: Any,
    config: EngineConfig | None = None,
    on_task_complete: Callable[..., None] | None = None,
    **kwargs: Any,
) -> BatchResult:
    """Run a batch evaluation with automatic engine lifecycle.

    Creates a :class:`LunarEngine`, starts it, runs the batch, stops
    the engine, and returns the result.  Uses ``try/finally`` to ensure
    cleanup even on errors.

    Args:
        benchmark: Benchmark YAML path, or list of TaskDefinitions.
        agent_factory: An agent factory callable, class, or instance.
        config: Optional engine configuration.
        on_task_complete: Optional callback invoked after each task.
        **kwargs: Passed through to :meth:`LunarEngine.eval`.

    Returns:
        A :class:`~lunar_sandbox.scheduler.result.BatchResult`.
    """
    from lunar_sandbox.sdk.engine import LunarEngine

    engine = LunarEngine(config)
    try:
        await engine.start()
        return await engine.eval(
            benchmark,
            agent_factory,
            on_task_complete=on_task_complete,
            **kwargs,
        )
    finally:
        await engine.stop()


def run_batch_sync(
    benchmark: Any,
    agent_factory: Any,
    config: EngineConfig | None = None,
    on_task_complete: Callable[..., None] | None = None,
    **kwargs: Any,
) -> BatchResult:
    """Synchronous wrapper for :func:`run_batch`.

    Uses ``asyncio.run()`` per codebase convention.
    """
    return asyncio.run(
        run_batch(
            benchmark,
            agent_factory,
            config=config,
            on_task_complete=on_task_complete,
            **kwargs,
        )
    )

"""Lunar Sandbox SDK -- programmatic interface to the evaluation engine.

Public API::

    from lunar_sandbox.sdk import (
        LunarEngine,
        EngineConfig,
        CallableAgentAdapter,
        normalize_agent,
        run_task,
        run_task_sync,
        run_batch,
        run_batch_sync,
    )
"""

from lunar_sandbox.sdk.agent_wrapper import CallableAgentAdapter, normalize_agent
from lunar_sandbox.sdk.config import EngineConfig
from lunar_sandbox.sdk.engine import LunarEngine

# Convenience functions are imported lazily to avoid circular imports
# during module initialization -- they depend on LunarEngine which is
# defined above.  We re-export them here for a flat public API.
from lunar_sandbox.sdk.convenience import (
    run_batch,
    run_batch_sync,
    run_task,
    run_task_sync,
)

__all__ = [
    "CallableAgentAdapter",
    "EngineConfig",
    "LunarEngine",
    "normalize_agent",
    "run_batch",
    "run_batch_sync",
    "run_task",
    "run_task_sync",
]

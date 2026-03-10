"""Action type definitions and Pydantic models for the sandbox action API.

Defines the schema foundation for all action requests, responses, trace
events, and per-action timeout defaults. Every other module in the actions
package depends on these types.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "ActionType",
    "ActionStatus",
    "ActionRequest",
    "ActionResponse",
    "FileDiff",
    "TraceEvent",
    "ACTION_TIMEOUTS",
]


class ActionType(str, Enum):
    """Supported sandbox action types.

    Core actions (execute_command, read_file, write_file, submit) are
    the fundamental primitives. The remaining actions are convenience
    wrappers built on top.
    """

    EXECUTE_COMMAND = "execute_command"
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    SUBMIT = "submit"
    LIST_FILES = "list_files"
    SEARCH_CODE = "search_code"
    RUN_TESTS = "run_tests"
    GET_LOGS = "get_logs"


class ActionStatus(str, Enum):
    """Outcome status of an action execution."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ActionRequest(BaseModel):
    """Action-level request (not the JSON-RPC envelope).

    Attributes:
        action: The type of action to execute.
        params: Action-specific parameters (command, path, content, etc.).
        timeout: Optional per-request timeout override in seconds.
            When None, the per-action default from ACTION_TIMEOUTS is used.
    """

    action: ActionType
    params: dict[str, Any]
    timeout: float | None = None


class FileDiff(BaseModel):
    """OverlayFS upper layer changes detected after an action.

    Tracks which files were created, modified, or deleted relative
    to the base layer during action execution.
    """

    created: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)


class ActionResponse(BaseModel):
    """Structured response from an action execution.

    Provides rich output including exit codes, stdio streams, timing,
    filesystem side effects, and resource usage metrics.

    Attributes:
        status: Outcome status (success, error, timeout).
        output: Action-specific structured output (varies by action type).
        exit_code: Process exit code (for command execution actions).
        stdout: Captured standard output.
        stderr: Captured standard error.
        cwd: Working directory at time of execution.
        duration_ms: Wall-clock execution time in milliseconds.
        side_effects: Files created/modified/deleted during the action.
        resource_usage: Cgroup resource metrics (memory peak, CPU time, etc.).
    """

    status: ActionStatus
    output: Any = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    cwd: str = ""
    duration_ms: float = 0.0
    side_effects: FileDiff | None = None
    resource_usage: dict[str, Any] = Field(default_factory=dict)


class TraceEvent(BaseModel):
    """Single event in an episode trace log.

    Schema is identical regardless of whether the action originated
    from the structured API or a raw shell command, ensuring uniform
    trace analysis.

    Attributes:
        seq: Sequence number within the episode (0-indexed).
        ts: Unix timestamp (seconds since epoch, float for sub-second).
        action: Action type string (matches ActionType values).
        params: Action parameters as submitted.
        status: Outcome status string (matches ActionStatus values).
        output: Structured output from the action.
        duration_ms: Wall-clock execution time in milliseconds.
        source: Origin of the action ("api" or "shell").
        episode_id: ID of the containing episode.
        sandbox_id: ID of the sandbox that executed the action.
        token_usage: Tokens consumed by agent for this action (optional).
        cost_usd: Cost in USD for this action (optional).
        cpu_time_ms: CPU time in milliseconds, host-side best-effort.
    """

    seq: int
    ts: float
    action: str
    params: dict[str, Any]
    status: str
    output: dict[str, Any]
    duration_ms: float
    source: str = "api"
    episode_id: str = ""
    sandbox_id: str = ""
    token_usage: int | None = None
    cost_usd: float | None = None
    cpu_time_ms: float = 0.0


# Per-action timeout defaults in seconds.
# These are used when ActionRequest.timeout is None.
ACTION_TIMEOUTS: dict[ActionType, float] = {
    ActionType.EXECUTE_COMMAND: 300.0,
    ActionType.READ_FILE: 10.0,
    ActionType.WRITE_FILE: 10.0,
    ActionType.SUBMIT: 5.0,
    ActionType.LIST_FILES: 30.0,
    ActionType.SEARCH_CODE: 60.0,
    ActionType.RUN_TESTS: 300.0,
    ActionType.GET_LOGS: 10.0,
}

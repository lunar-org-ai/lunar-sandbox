"""Action types, protocol, and execution models for the sandbox API.

Public API::

    from lunar_sandbox.actions import (
        # Types
        ActionType, ActionStatus, ActionRequest, ActionResponse,
        TraceEvent, FileDiff, ACTION_TIMEOUTS,
        # Protocol
        send_message, recv_message, make_request, make_response, make_error,
        # Handlers
        ActionHandlers, handle_action,
        # Executor & Client
        ActionExecutor, SOCKET_PATH, ActionClient,
        # Diff
        inspect_upper_layer, snapshot_upper_state, diff_snapshots,
    )
"""

from lunar_sandbox.actions.client import ActionClient
from lunar_sandbox.actions.diff import (
    diff_snapshots,
    inspect_upper_layer,
    snapshot_upper_state,
)
from lunar_sandbox.actions.executor import SOCKET_PATH, ActionExecutor
from lunar_sandbox.actions.handlers import ActionHandlers, handle_action
from lunar_sandbox.actions.protocol import (
    make_error,
    make_request,
    make_response,
    recv_message,
    send_message,
)
from lunar_sandbox.actions.types import (
    ACTION_TIMEOUTS,
    ActionRequest,
    ActionResponse,
    ActionStatus,
    ActionType,
    FileDiff,
    TraceEvent,
)

__all__ = [
    # Types
    "ActionType",
    "ActionStatus",
    "ActionRequest",
    "ActionResponse",
    "FileDiff",
    "TraceEvent",
    "ACTION_TIMEOUTS",
    # Protocol
    "send_message",
    "recv_message",
    "make_request",
    "make_response",
    "make_error",
    # Handlers
    "ActionHandlers",
    "handle_action",
    # Executor & Client
    "ActionExecutor",
    "SOCKET_PATH",
    "ActionClient",
    # Diff
    "inspect_upper_layer",
    "snapshot_upper_state",
    "diff_snapshots",
]

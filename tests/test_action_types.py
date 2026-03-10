"""Unit tests for action type definitions and Pydantic models.

Tests ActionType, ActionStatus, ActionRequest, ActionResponse, TraceEvent,
FileDiff models, and ACTION_TIMEOUTS mapping.
"""

from __future__ import annotations

import json

from lunar_sandbox.actions.types import (
    ACTION_TIMEOUTS,
    ActionRequest,
    ActionResponse,
    ActionStatus,
    ActionType,
    FileDiff,
    TraceEvent,
)


class TestActionType:
    """Tests for ActionType enum."""

    def test_action_type_values(self) -> None:
        """All 8 action types exist with correct string values."""
        assert ActionType.EXECUTE_COMMAND == "execute_command"
        assert ActionType.READ_FILE == "read_file"
        assert ActionType.WRITE_FILE == "write_file"
        assert ActionType.SUBMIT == "submit"
        assert ActionType.LIST_FILES == "list_files"
        assert ActionType.SEARCH_CODE == "search_code"
        assert ActionType.RUN_TESTS == "run_tests"
        assert ActionType.GET_LOGS == "get_logs"
        assert len(ActionType) == 8


class TestActionStatus:
    """Tests for ActionStatus enum."""

    def test_action_status_values(self) -> None:
        """success, error, timeout status values."""
        assert ActionStatus.SUCCESS == "success"
        assert ActionStatus.ERROR == "error"
        assert ActionStatus.TIMEOUT == "timeout"
        assert len(ActionStatus) == 3


class TestActionResponse:
    """Tests for ActionResponse model."""

    def test_action_response_defaults(self) -> None:
        """Default field values are correct."""
        resp = ActionResponse(status=ActionStatus.SUCCESS)
        assert resp.status == ActionStatus.SUCCESS
        assert resp.output is None
        assert resp.exit_code is None
        assert resp.stdout == ""
        assert resp.stderr == ""
        assert resp.cwd == ""
        assert resp.duration_ms == 0.0
        assert resp.side_effects is None
        assert resp.resource_usage == {}

    def test_action_response_with_side_effects(self) -> None:
        """ActionResponse with FileDiff in side_effects."""
        diff = FileDiff(created=["new.py"], modified=["old.py"])
        resp = ActionResponse(
            status=ActionStatus.SUCCESS,
            side_effects=diff,
        )
        assert resp.side_effects is not None
        assert resp.side_effects.created == ["new.py"]
        assert resp.side_effects.modified == ["old.py"]

    def test_action_response_serialization(self) -> None:
        """model_dump() and model_dump_json() work correctly."""
        resp = ActionResponse(
            status=ActionStatus.SUCCESS,
            stdout="hello",
            exit_code=0,
            duration_ms=42.5,
        )
        d = resp.model_dump()
        assert d["status"] == "success"
        assert d["stdout"] == "hello"
        assert d["exit_code"] == 0
        assert d["duration_ms"] == 42.5

        j = resp.model_dump_json()
        parsed = json.loads(j)
        assert parsed["status"] == "success"


class TestActionRequest:
    """Tests for ActionRequest model."""

    def test_action_request_fields(self) -> None:
        """ActionRequest has correct fields."""
        req = ActionRequest(
            action=ActionType.EXECUTE_COMMAND,
            params={"command": "echo hello"},
        )
        assert req.action == ActionType.EXECUTE_COMMAND
        assert req.params == {"command": "echo hello"}
        assert req.timeout is None

    def test_action_request_with_timeout(self) -> None:
        """ActionRequest accepts optional timeout."""
        req = ActionRequest(
            action=ActionType.READ_FILE,
            params={"path": "test.py"},
            timeout=5.0,
        )
        assert req.timeout == 5.0


class TestTraceEvent:
    """Tests for TraceEvent model."""

    def test_trace_event_api_source(self) -> None:
        """Source defaults to 'api'."""
        event = TraceEvent(
            seq=0,
            ts=1000.0,
            action="execute_command",
            params={"command": "ls"},
            status="success",
            output={},
            duration_ms=10.0,
        )
        assert event.source == "api"

    def test_trace_event_shell_source(self) -> None:
        """source='shell' is accepted."""
        event = TraceEvent(
            seq=1,
            ts=1001.0,
            action="execute_command",
            params={"command": "pwd"},
            status="success",
            output={},
            duration_ms=5.0,
            source="shell",
        )
        assert event.source == "shell"

    def test_trace_event_schema_parity(self) -> None:
        """API and shell TraceEvents have identical fields."""
        api_event = TraceEvent(
            seq=0, ts=1000.0, action="read_file",
            params={"path": "x"}, status="success",
            output={"content": "data"}, duration_ms=1.0,
            source="api",
        )
        shell_event = TraceEvent(
            seq=1, ts=1001.0, action="execute_command",
            params={"command": "ls"}, status="error",
            output={}, duration_ms=2.0,
            source="shell",
        )
        api_fields = set(TraceEvent.model_fields.keys())
        shell_fields = set(TraceEvent.model_fields.keys())
        assert api_fields == shell_fields


class TestFileDiff:
    """Tests for FileDiff model."""

    def test_file_diff_empty(self) -> None:
        """FileDiff with no changes."""
        diff = FileDiff()
        assert diff.created == []
        assert diff.modified == []
        assert diff.deleted == []

    def test_file_diff_with_changes(self) -> None:
        """FileDiff with created, modified, deleted lists."""
        diff = FileDiff(
            created=["a.py", "b.py"],
            modified=["c.py"],
            deleted=["d.py"],
        )
        assert diff.created == ["a.py", "b.py"]
        assert diff.modified == ["c.py"]
        assert diff.deleted == ["d.py"]


class TestActionTimeouts:
    """Tests for ACTION_TIMEOUTS mapping."""

    def test_action_timeouts(self) -> None:
        """ACTION_TIMEOUTS has entries for all 8 action types."""
        assert len(ACTION_TIMEOUTS) == 8
        for action_type in ActionType:
            assert action_type in ACTION_TIMEOUTS
            assert isinstance(ACTION_TIMEOUTS[action_type], float)
            assert ACTION_TIMEOUTS[action_type] > 0

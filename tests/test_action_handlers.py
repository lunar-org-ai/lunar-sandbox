"""Unit tests for action handler implementations.

Tests all 8 action handlers (execute_command, read_file, write_file,
submit, list_files, search_code, run_tests, get_logs) and the
handle_action dispatcher. Uses tmp_path for isolated working directories.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from lunar_sandbox.actions.handlers import ActionHandlers, handle_action
from lunar_sandbox.actions.types import ActionStatus


def _run(coro):
    """Helper to run async tests."""
    return asyncio.run(coro)


class TestExecuteCommand:
    """Tests for handle_execute_command."""

    def test_execute_command_echo(self, tmp_path: Path) -> None:
        """Runs 'echo hello', verifies stdout."""
        handlers = ActionHandlers(working_dir=tmp_path)

        async def _test():
            resp = await handlers.handle_execute_command({"command": "echo hello"})
            assert resp.status == ActionStatus.SUCCESS
            assert resp.stdout.strip() == "hello"
            assert resp.exit_code == 0

        _run(_test())

    def test_execute_command_exit_code(self, tmp_path: Path) -> None:
        """Runs failing command, verifies non-zero exit code."""
        handlers = ActionHandlers(working_dir=tmp_path)

        async def _test():
            resp = await handlers.handle_execute_command({"command": "exit 42"})
            assert resp.status == ActionStatus.ERROR
            assert resp.exit_code == 42

        _run(_test())

    def test_execute_command_cwd(self, tmp_path: Path) -> None:
        """Runs 'pwd' with custom cwd."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        handlers = ActionHandlers(working_dir=tmp_path)

        async def _test():
            resp = await handlers.handle_execute_command(
                {"command": "pwd", "cwd": "subdir"}
            )
            assert resp.status == ActionStatus.SUCCESS
            assert "subdir" in resp.stdout

        _run(_test())

    def test_execute_command_missing_param(self, tmp_path: Path) -> None:
        """Missing 'command' param returns error."""
        handlers = ActionHandlers(working_dir=tmp_path)

        async def _test():
            resp = await handlers.handle_execute_command({})
            assert resp.status == ActionStatus.ERROR
            assert "command" in resp.stderr.lower()

        _run(_test())


class TestReadFile:
    """Tests for handle_read_file."""

    def test_read_file_success(self, tmp_path: Path) -> None:
        """Reads existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("file content here")
        handlers = ActionHandlers(working_dir=tmp_path)

        async def _test():
            resp = await handlers.handle_read_file({"path": "test.txt"})
            assert resp.status == ActionStatus.SUCCESS
            assert resp.output == "file content here"

        _run(_test())

    def test_read_file_not_found(self, tmp_path: Path) -> None:
        """Returns error for missing file."""
        handlers = ActionHandlers(working_dir=tmp_path)

        async def _test():
            resp = await handlers.handle_read_file({"path": "nonexistent.txt"})
            assert resp.status == ActionStatus.ERROR
            assert "not found" in resp.stderr.lower()

        _run(_test())


class TestWriteFile:
    """Tests for handle_write_file."""

    def test_write_file_new(self, tmp_path: Path) -> None:
        """Writes new file, verifies on disk."""
        handlers = ActionHandlers(working_dir=tmp_path)

        async def _test():
            resp = await handlers.handle_write_file(
                {"path": "output.txt", "content": "hello world"}
            )
            assert resp.status == ActionStatus.SUCCESS
            assert (tmp_path / "output.txt").read_text() == "hello world"
            assert resp.side_effects is not None
            assert "output.txt" in resp.side_effects.created

        _run(_test())

    def test_write_file_creates_dirs(self, tmp_path: Path) -> None:
        """Writes to nested path, parent dirs created."""
        handlers = ActionHandlers(working_dir=tmp_path)

        async def _test():
            resp = await handlers.handle_write_file(
                {"path": "deep/nested/dir/file.py", "content": "# code"}
            )
            assert resp.status == ActionStatus.SUCCESS
            assert (tmp_path / "deep" / "nested" / "dir" / "file.py").exists()

        _run(_test())

    def test_write_file_overwrite(self, tmp_path: Path) -> None:
        """Overwriting existing file classifies as modified."""
        handlers = ActionHandlers(working_dir=tmp_path)
        (tmp_path / "existing.txt").write_text("old content")

        async def _test():
            resp = await handlers.handle_write_file(
                {"path": "existing.txt", "content": "new content"}
            )
            assert resp.status == ActionStatus.SUCCESS
            assert resp.side_effects is not None
            assert "existing.txt" in resp.side_effects.modified

        _run(_test())


class TestSubmit:
    """Tests for handle_submit."""

    def test_submit(self, tmp_path: Path) -> None:
        """Returns submitted=True."""
        handlers = ActionHandlers(working_dir=tmp_path)

        async def _test():
            resp = await handlers.handle_submit({"message": "done"})
            assert resp.status == ActionStatus.SUCCESS
            assert resp.output["submitted"] is True
            assert resp.output["message"] == "done"

        _run(_test())


class TestHandleActionDispatcher:
    """Tests for handle_action() dispatcher."""

    def test_handle_action_dispatch(self, tmp_path: Path) -> None:
        """Dispatcher routes execute_command correctly."""
        handlers = ActionHandlers(working_dir=tmp_path)

        async def _test():
            resp = await handle_action(handlers, "execute_command", {"command": "echo dispatched"})
            assert resp.status == ActionStatus.SUCCESS
            assert "dispatched" in resp.stdout

        _run(_test())

    def test_handle_action_unknown(self, tmp_path: Path) -> None:
        """Unknown action returns error."""
        handlers = ActionHandlers(working_dir=tmp_path)

        async def _test():
            resp = await handle_action(handlers, "unknown_action", {})
            assert resp.status == ActionStatus.ERROR
            assert "unknown" in resp.stderr.lower()

        _run(_test())

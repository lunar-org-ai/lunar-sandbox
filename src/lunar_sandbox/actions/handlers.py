"""Action handler implementations for the sandbox action API.

Provides ``ActionHandlers`` with methods for all 8 action types:
- **Core actions:** execute_command, read_file, write_file, submit
- **Convenience wrappers:** list_files, search_code, run_tests, get_logs

The top-level ``handle_action`` dispatcher routes an action type string
to the appropriate handler method and catches unexpected exceptions.

All handlers return structured ``ActionResponse`` instances -- never raw
dicts or unhandled exceptions.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Any

import structlog

from lunar_sandbox.actions.diff import diff_snapshots, snapshot_upper_state
from lunar_sandbox.actions.types import ActionResponse, ActionStatus, FileDiff

__all__ = [
    "ActionHandlers",
    "handle_action",
]

log = structlog.get_logger(__name__)


class ActionHandlers:
    """Container for action handler methods with shared sandbox context.

    Args:
        working_dir: Path to the sandbox merged directory (overlayfs mount
            point or a plain directory for testing).
        upper_dir: Optional path to the OverlayFS upper (writable) layer.
            When set, ``execute_command`` and ``write_file`` will record
            filesystem side effects via upper-layer snapshots.
    """

    def __init__(
        self,
        working_dir: Path,
        upper_dir: Path | None = None,
    ) -> None:
        self.working_dir = working_dir
        self.upper_dir = upper_dir

    # ------------------------------------------------------------------
    # Core actions
    # ------------------------------------------------------------------

    async def handle_execute_command(self, params: dict[str, Any]) -> ActionResponse:
        """Execute a shell command inside the sandbox working directory.

        Params:
            command (str): Shell command to execute (required).
            cwd (str): Working directory override, relative to working_dir.
            timeout (float): Per-invocation timeout in seconds.
        """
        command = params.get("command")
        if not command:
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr="Missing required parameter: command",
            )

        cwd_param = params.get("cwd")
        if cwd_param:
            cwd = self.working_dir / cwd_param
        else:
            cwd = self.working_dir

        timeout = params.get("timeout")
        cwd_str = str(cwd)

        # Snapshot before (for side effects).
        before_snap: set[str] | None = None
        if self.upper_dir is not None:
            before_snap = snapshot_upper_state(self.upper_dir)

        log.debug("execute_command.start", command=command, cwd=cwd_str)
        t0 = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd_str,
            )

            if timeout is not None:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            else:
                stdout_bytes, stderr_bytes = await proc.communicate()

        except asyncio.TimeoutError:
            # Kill the timed-out process.
            duration_ms = (time.monotonic() - t0) * 1000
            try:
                proc.kill()  # type: ignore[possibly-undefined]
                await proc.wait()  # type: ignore[possibly-undefined]
            except (ProcessLookupError, OSError):
                pass
            log.warning("execute_command.timeout", command=command, duration_ms=duration_ms)
            return ActionResponse(
                status=ActionStatus.TIMEOUT,
                stdout="",
                stderr="Command timed out",
                exit_code=-1,
                cwd=cwd_str,
                duration_ms=duration_ms,
            )
        except OSError as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr=f"Failed to execute command: {exc}",
                cwd=cwd_str,
                duration_ms=duration_ms,
            )

        duration_ms = (time.monotonic() - t0) * 1000
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        exit_code = proc.returncode or 0
        status = ActionStatus.SUCCESS if exit_code == 0 else ActionStatus.ERROR

        # Compute side effects.
        side_effects: FileDiff | None = None
        if self.upper_dir is not None and before_snap is not None:
            after_snap = snapshot_upper_state(self.upper_dir)
            side_effects = diff_snapshots(before_snap, after_snap, self.upper_dir)

        log.debug(
            "execute_command.done",
            command=command,
            exit_code=exit_code,
            duration_ms=round(duration_ms, 2),
        )

        return ActionResponse(
            status=status,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            cwd=cwd_str,
            duration_ms=duration_ms,
            side_effects=side_effects,
        )

    async def handle_read_file(self, params: dict[str, Any]) -> ActionResponse:
        """Read a file from the sandbox filesystem.

        Params:
            path (str): File path relative to working_dir (required).
        """
        file_path = params.get("path")
        if not file_path:
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr="Missing required parameter: path",
            )

        t0 = time.monotonic()
        resolved = self.working_dir / file_path

        try:
            content = resolved.read_text(encoding="utf-8")
        except FileNotFoundError:
            duration_ms = (time.monotonic() - t0) * 1000
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr=f"File not found: {file_path}",
                duration_ms=duration_ms,
            )
        except PermissionError:
            duration_ms = (time.monotonic() - t0) * 1000
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr=f"Permission denied: {file_path}",
                duration_ms=duration_ms,
            )
        except OSError as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr=f"Error reading file: {exc}",
                duration_ms=duration_ms,
            )

        duration_ms = (time.monotonic() - t0) * 1000
        return ActionResponse(
            status=ActionStatus.SUCCESS,
            output=content,
            duration_ms=duration_ms,
        )

    async def handle_write_file(self, params: dict[str, Any]) -> ActionResponse:
        """Write content to a file in the sandbox filesystem.

        Params:
            path (str): File path relative to working_dir (required).
            content (str): Content to write (required).
        """
        file_path = params.get("path")
        content = params.get("content")

        if not file_path:
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr="Missing required parameter: path",
            )
        if content is None:
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr="Missing required parameter: content",
            )

        t0 = time.monotonic()
        resolved = self.working_dir / file_path

        try:
            existed = resolved.exists()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
        except PermissionError:
            duration_ms = (time.monotonic() - t0) * 1000
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr=f"Permission denied: {file_path}",
                duration_ms=duration_ms,
            )
        except OSError as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr=f"Error writing file: {exc}",
                duration_ms=duration_ms,
            )

        duration_ms = (time.monotonic() - t0) * 1000

        # Classify as created or modified based on prior existence.
        if existed:
            side_effects = FileDiff(modified=[file_path])
        else:
            side_effects = FileDiff(created=[file_path])

        return ActionResponse(
            status=ActionStatus.SUCCESS,
            output=f"Wrote {len(content)} bytes to {file_path}",
            duration_ms=duration_ms,
            side_effects=side_effects,
        )

    async def handle_submit(self, params: dict[str, Any]) -> ActionResponse:
        """Signal episode completion.

        Params:
            message (str): Optional submission message.
        """
        t0 = time.monotonic()
        message = params.get("message", "")

        duration_ms = (time.monotonic() - t0) * 1000
        return ActionResponse(
            status=ActionStatus.SUCCESS,
            output={"submitted": True, "message": message},
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    async def handle_list_files(self, params: dict[str, Any]) -> ActionResponse:
        """List files in a directory. Delegates to execute_command.

        Params:
            path (str): Directory to list (defaults to ".").
        """
        target = params.get("path", ".")
        return await self.handle_execute_command(
            {"command": f"find {_shell_quote(target)} -type f", "cwd": params.get("cwd")},
        )

    async def handle_search_code(self, params: dict[str, Any]) -> ActionResponse:
        """Search for a pattern in source files. Delegates to execute_command.

        Uses ``grep -rn`` as a universal fallback. If ``rg`` (ripgrep) is
        available, it is preferred for speed.

        Params:
            pattern (str): Search pattern (required).
            path (str): Directory scope (defaults to ".").
        """
        pattern = params.get("pattern")
        if not pattern:
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr="Missing required parameter: pattern",
            )

        target = params.get("path", ".")

        # Prefer ripgrep if available.
        if shutil.which("rg"):
            cmd = f"rg -n {_shell_quote(pattern)} {_shell_quote(target)}"
        else:
            cmd = f"grep -rn {_shell_quote(pattern)} {_shell_quote(target)}"

        return await self.handle_execute_command(
            {"command": cmd, "cwd": params.get("cwd")},
        )

    async def handle_run_tests(self, params: dict[str, Any]) -> ActionResponse:
        """Run a test command. Delegates to execute_command.

        Params:
            test_command (str): Full test command to execute (required).
        """
        test_command = params.get("test_command")
        if not test_command:
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr="Missing required parameter: test_command",
            )

        return await self.handle_execute_command(
            {"command": test_command, "cwd": params.get("cwd")},
        )

    async def handle_get_logs(self, params: dict[str, Any]) -> ActionResponse:
        """Read a log file. Delegates to read_file.

        Params:
            log_path (str): Path to the log file (required).
        """
        log_path = params.get("log_path")
        if not log_path:
            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr="Missing required parameter: log_path",
            )

        return await self.handle_read_file({"path": log_path})


# ------------------------------------------------------------------
# Dispatcher
# ------------------------------------------------------------------

#: Maps action type strings to their handler method names.
_ACTION_DISPATCH: dict[str, str] = {
    "execute_command": "handle_execute_command",
    "read_file": "handle_read_file",
    "write_file": "handle_write_file",
    "submit": "handle_submit",
    "list_files": "handle_list_files",
    "search_code": "handle_search_code",
    "run_tests": "handle_run_tests",
    "get_logs": "handle_get_logs",
}


async def handle_action(
    handlers: ActionHandlers,
    action_type: str,
    params: dict[str, Any],
) -> ActionResponse:
    """Dispatch an action to the appropriate handler method.

    Args:
        handlers: The ``ActionHandlers`` instance with sandbox context.
        action_type: Action type string (e.g. ``"execute_command"``).
        params: Action-specific parameters.

    Returns:
        ``ActionResponse`` -- always returns a response, never raises.
    """
    method_name = _ACTION_DISPATCH.get(action_type)
    if method_name is None:
        return ActionResponse(
            status=ActionStatus.ERROR,
            stderr=f"Unknown action: {action_type}",
        )

    try:
        method = getattr(handlers, method_name)
        return await method(params)
    except Exception as exc:
        log.error(
            "handle_action.unexpected_error",
            action_type=action_type,
            error=str(exc),
            exc_info=True,
        )
        return ActionResponse(
            status=ActionStatus.ERROR,
            stderr=f"Unexpected error in {action_type}: {exc}",
        )


def _shell_quote(value: str) -> str:
    """Minimal shell quoting: wrap in single quotes, escape internal quotes."""
    return "'" + value.replace("'", "'\\''") + "'"

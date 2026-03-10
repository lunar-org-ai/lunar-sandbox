"""Host-side action client for communicating with the in-sandbox executor.

Connects to the :class:`~lunar_sandbox.actions.executor.ActionExecutor` over
a Unix domain socket, sends JSON-RPC 2.0 requests, and returns structured
:class:`~lunar_sandbox.actions.types.ActionResponse` instances.

Provides both a low-level :meth:`send_action` and high-level convenience
methods for each action type (execute_command, read_file, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from lunar_sandbox.actions.protocol import (
    make_request,
    recv_message,
    send_message,
)
from lunar_sandbox.actions.types import ActionResponse, ActionStatus

__all__ = [
    "ActionClient",
]

_log = logging.getLogger(__name__)


class ActionClient:
    """Host-side client for sending actions to the sandbox executor.

    Communicates over a Unix domain socket using JSON-RPC 2.0 with
    newline-delimited framing. The client maintains a persistent
    connection and auto-increments request IDs for correlation.

    Args:
        socket_path: Path to the executor's Unix domain socket.
    """

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id: int = 0

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(
        self,
        timeout: float = 5.0,
        retry_interval: float = 0.1,
    ) -> None:
        """Connect to the executor, retrying until the socket is available.

        Polls for socket file existence and attempts connection, which
        handles the race condition when the executor is still starting.

        Args:
            timeout: Maximum time in seconds to wait for a connection.
            retry_interval: Seconds between connection attempts.

        Raises:
            ConnectionError: If the connection cannot be established
                within the timeout period.
        """

        async def _try_connect() -> None:
            while True:
                if os.path.exists(self._socket_path):
                    try:
                        self._reader, self._writer = (
                            await asyncio.open_unix_connection(self._socket_path)
                        )
                        return
                    except (ConnectionRefusedError, FileNotFoundError, OSError):
                        pass
                await asyncio.sleep(retry_interval)

        try:
            await asyncio.wait_for(_try_connect(), timeout=timeout)
        except asyncio.TimeoutError:
            raise ConnectionError(
                f"Could not connect to executor at {self._socket_path} "
                f"within {timeout}s"
            ) from None

        _log.info("client_connected socket_path=%s", self._socket_path)

    async def disconnect(self) -> None:
        """Close the connection to the executor."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (ConnectionError, OSError, BrokenPipeError):
                pass
            self._writer = None
            self._reader = None

        _log.info("client_disconnected socket_path=%s", self._socket_path)

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> ActionClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.disconnect()

    # ------------------------------------------------------------------
    # Core send/receive
    # ------------------------------------------------------------------

    async def send_action(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float | None = None,
    ) -> ActionResponse:
        """Send an action request and wait for the response.

        Builds a JSON-RPC 2.0 request, sends it over the socket,
        reads the response, and returns a validated ``ActionResponse``.

        Args:
            action: Action type string (e.g. ``"execute_command"``).
            params: Action-specific parameters.
            timeout: Optional per-request timeout in seconds.

        Returns:
            Structured ``ActionResponse`` for every call -- never raises
            for action-level errors (those become error status responses).

        Raises:
            ConnectionError: If the connection to the executor is lost
                (infrastructure error, not action error).
        """
        if self._reader is None or self._writer is None:
            raise ConnectionError("Not connected to executor")

        self._request_id += 1
        request_id = self._request_id
        request = make_request(action, params, request_id)

        async def _roundtrip() -> ActionResponse:
            assert self._writer is not None
            assert self._reader is not None

            await send_message(self._writer, request)
            response = await recv_message(self._reader)

            # Validate response ID matches.
            resp_id = response.get("id")
            if resp_id != request_id:
                return ActionResponse(
                    status=ActionStatus.ERROR,
                    stderr=(
                        f"Response ID mismatch: expected {request_id}, "
                        f"got {resp_id}"
                    ),
                )

            # JSON-RPC error response.
            if "error" in response:
                error_obj = response["error"]
                error_msg = (
                    f"JSON-RPC error {error_obj.get('code')}: "
                    f"{error_obj.get('message', 'unknown')}"
                )
                return ActionResponse(
                    status=ActionStatus.ERROR,
                    stderr=error_msg,
                )

            # Success response.
            if "result" in response:
                return ActionResponse.model_validate(response["result"])

            return ActionResponse(
                status=ActionStatus.ERROR,
                stderr="Malformed JSON-RPC response: missing result and error",
            )

        if timeout is not None:
            try:
                return await asyncio.wait_for(_roundtrip(), timeout=timeout)
            except asyncio.TimeoutError:
                return ActionResponse(
                    status=ActionStatus.TIMEOUT,
                    stderr=f"Action '{action}' timed out after {timeout}s",
                )
        else:
            return await _roundtrip()

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    async def execute_command(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float | None = None,
    ) -> ActionResponse:
        """Execute a shell command in the sandbox."""
        params: dict[str, Any] = {"command": command}
        if cwd is not None:
            params["cwd"] = cwd
        return await self.send_action("execute_command", params, timeout=timeout)

    async def read_file(
        self,
        path: str,
        timeout: float | None = None,
    ) -> ActionResponse:
        """Read a file from the sandbox filesystem."""
        return await self.send_action("read_file", {"path": path}, timeout=timeout)

    async def write_file(
        self,
        path: str,
        content: str,
        timeout: float | None = None,
    ) -> ActionResponse:
        """Write content to a file in the sandbox filesystem."""
        return await self.send_action(
            "write_file", {"path": path, "content": content}, timeout=timeout
        )

    async def submit(
        self,
        message: str = "",
        timeout: float | None = None,
    ) -> ActionResponse:
        """Signal episode completion."""
        return await self.send_action(
            "submit", {"message": message}, timeout=timeout
        )

    async def list_files(
        self,
        path: str = ".",
        timeout: float | None = None,
    ) -> ActionResponse:
        """List files in a sandbox directory."""
        return await self.send_action(
            "list_files", {"path": path}, timeout=timeout
        )

    async def search_code(
        self,
        pattern: str,
        path: str = ".",
        timeout: float | None = None,
    ) -> ActionResponse:
        """Search for a pattern in sandbox source files."""
        return await self.send_action(
            "search_code", {"pattern": pattern, "path": path}, timeout=timeout
        )

    async def run_tests(
        self,
        test_command: str,
        timeout: float | None = None,
    ) -> ActionResponse:
        """Run a test command in the sandbox."""
        return await self.send_action(
            "run_tests", {"test_command": test_command}, timeout=timeout
        )

    async def get_logs(
        self,
        log_path: str,
        timeout: float | None = None,
    ) -> ActionResponse:
        """Read a log file from the sandbox."""
        return await self.send_action(
            "get_logs", {"log_path": log_path}, timeout=timeout
        )

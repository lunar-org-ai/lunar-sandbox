"""Persistent action executor: Unix socket server running inside the sandbox.

Listens on a well-known Unix socket path, receives JSON-RPC 2.0 requests,
dispatches them to :func:`~lunar_sandbox.actions.handlers.handle_action`,
and returns structured responses. Designed to run as a long-lived process
inside each sandbox instance.

Wire protocol: newline-delimited JSON-RPC 2.0 (see :mod:`protocol`).
"""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
from pathlib import Path
from typing import Any

from lunar_sandbox.actions.handlers import ActionHandlers, handle_action
from lunar_sandbox.actions.protocol import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_PARSE_ERROR,
    make_error,
    make_response,
    recv_message,
    send_message,
)
from lunar_sandbox.sandbox.errors import ProtocolError

__all__ = [
    "ActionExecutor",
    "SOCKET_PATH",
]

_log = logging.getLogger(__name__)

#: Well-known socket path inside the sandbox filesystem.
SOCKET_PATH: str = "/tmp/lunar-action.sock"


class ActionExecutor:
    """Unix socket server for in-sandbox action handling.

    Accepts JSON-RPC 2.0 requests over a Unix domain socket, dispatches
    each to the appropriate :class:`~lunar_sandbox.actions.handlers.ActionHandlers`
    method, and sends back structured responses.

    Args:
        socket_path: Path for the Unix domain socket (default: ``SOCKET_PATH``).
        working_dir: Sandbox working directory passed to handlers.
        upper_dir: Optional OverlayFS upper layer for side-effect tracking.
    """

    def __init__(
        self,
        socket_path: str = SOCKET_PATH,
        working_dir: Path | None = None,
        upper_dir: Path | None = None,
    ) -> None:
        self._socket_path = socket_path
        self._working_dir = working_dir or Path.cwd()
        self._upper_dir = upper_dir
        self._handlers: ActionHandlers | None = None
        self._server: asyncio.Server | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start listening on the Unix socket.

        Removes a stale socket file if one exists from a previous crash,
        creates :class:`ActionHandlers`, and starts the async server.
        """
        # Clean up stale socket from a previous crash.
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass

        self._handlers = ActionHandlers(
            working_dir=self._working_dir,
            upper_dir=self._upper_dir,
        )

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self._socket_path,
        )

        _log.info("executor_started socket_path=%s", self._socket_path)

    async def stop(self) -> None:
        """Stop the server and clean up the socket file."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass

        _log.info("executor_stopped socket_path=%s", self._socket_path)

    async def run_forever(self) -> None:
        """Start the executor and serve until cancelled.

        Intended as the main entry-point when the executor is launched
        as a standalone process inside the sandbox.
        """
        await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> ActionExecutor:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # Client handling
    # ------------------------------------------------------------------

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single client connection.

        Reads JSON-RPC 2.0 requests in a loop, dispatches each to the
        appropriate handler, and sends back responses. The loop continues
        until the client disconnects or the connection breaks.
        """
        try:
            while True:
                try:
                    msg = await recv_message(reader)
                except ConnectionError:
                    # Client disconnected -- normal lifecycle.
                    break
                except ProtocolError:
                    # Malformed JSON -- send parse error, keep connection.
                    error_resp = make_error(
                        JSONRPC_PARSE_ERROR,
                        "Parse error: invalid JSON",
                        request_id=None,
                    )
                    await send_message(writer, error_resp)
                    continue

                # Validate minimal JSON-RPC 2.0 structure.
                request_id = msg.get("id")
                method = msg.get("method")
                jsonrpc_version = msg.get("jsonrpc")

                if jsonrpc_version != "2.0" or not method or request_id is None:
                    error_resp = make_error(
                        JSONRPC_INVALID_REQUEST,
                        "Invalid JSON-RPC 2.0 request",
                        request_id=request_id,
                    )
                    await send_message(writer, error_resp)
                    continue

                params: dict[str, Any] = msg.get("params", {})

                try:
                    assert self._handlers is not None
                    response = await handle_action(self._handlers, method, params)
                    rpc_response = make_response(response.model_dump(), request_id)
                    await send_message(writer, rpc_response)
                except ConnectionError:
                    # Write failed -- client gone.
                    break
                except Exception:
                    _log.error(
                        "executor: unexpected error handling %s:\n%s",
                        method,
                        traceback.format_exc(),
                    )
                    error_resp = make_error(
                        JSONRPC_INTERNAL_ERROR,
                        "Internal error",
                        request_id=request_id,
                    )
                    try:
                        await send_message(writer, error_resp)
                    except ConnectionError:
                        break
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, OSError, BrokenPipeError):
                pass


if __name__ == "__main__":
    import sys

    socket_path = sys.argv[1] if len(sys.argv) > 1 else SOCKET_PATH
    working_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()
    executor = ActionExecutor(socket_path=socket_path, working_dir=working_dir)
    asyncio.run(executor.run_forever())

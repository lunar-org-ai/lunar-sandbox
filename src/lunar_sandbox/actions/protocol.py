"""JSON-RPC 2.0 protocol layer for sandbox Unix socket communication.

Implements newline-delimited JSON-RPC 2.0 message framing over asyncio
streams. Provides pure message construction functions and async transport
helpers for send/receive over StreamReader/StreamWriter pairs.

Wire format: each message is a single JSON object followed by ``\\n``.
No embedded newlines within a message (compact JSON encoding).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from lunar_sandbox.sandbox.errors import ProtocolError

__all__ = [
    "send_message",
    "recv_message",
    "make_request",
    "make_response",
    "make_error",
    "JSONRPC_PARSE_ERROR",
    "JSONRPC_INVALID_REQUEST",
    "JSONRPC_METHOD_NOT_FOUND",
    "JSONRPC_INVALID_PARAMS",
    "JSONRPC_INTERNAL_ERROR",
]

_log = logging.getLogger(__name__)

# Standard JSON-RPC 2.0 error codes.
JSONRPC_PARSE_ERROR: int = -32700
JSONRPC_INVALID_REQUEST: int = -32600
JSONRPC_METHOD_NOT_FOUND: int = -32601
JSONRPC_INVALID_PARAMS: int = -32602
JSONRPC_INTERNAL_ERROR: int = -32603


# ---------------------------------------------------------------------------
# Message construction (pure, synchronous)
# ---------------------------------------------------------------------------


def make_request(method: str, params: dict[str, Any], request_id: int) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 request message.

    Args:
        method: The RPC method name (maps to an ActionType value).
        params: Method parameters.
        request_id: Unique request identifier for correlating responses.

    Returns:
        A dict representing a valid JSON-RPC 2.0 request object.
    """
    return {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": request_id,
    }


def make_response(result: dict[str, Any], request_id: int) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response message.

    Args:
        result: The result payload.
        request_id: The id from the original request.

    Returns:
        A dict representing a valid JSON-RPC 2.0 response object.
    """
    return {
        "jsonrpc": "2.0",
        "result": result,
        "id": request_id,
    }


def make_error(
    code: int,
    message: str,
    request_id: int | None,
    data: Any = None,
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response message.

    Args:
        code: JSON-RPC error code (standard or application-defined).
        message: Human-readable error description.
        request_id: The id from the original request, or None for
            parse errors where the id could not be determined.
        data: Optional additional error context.

    Returns:
        A dict representing a valid JSON-RPC 2.0 error response object.
    """
    error_obj: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error_obj["data"] = data
    return {
        "jsonrpc": "2.0",
        "error": error_obj,
        "id": request_id,
    }


# ---------------------------------------------------------------------------
# Async transport (asyncio.StreamReader / StreamWriter)
# ---------------------------------------------------------------------------


async def send_message(writer: asyncio.StreamWriter, msg: dict[str, Any]) -> None:
    """Serialize and send a JSON-RPC message over a stream.

    Encodes the message as compact JSON (no embedded newlines) followed
    by a newline delimiter, then flushes the write buffer.

    Args:
        writer: The asyncio stream to write to.
        msg: A JSON-RPC 2.0 message dict.
    """
    line = json.dumps(msg, separators=(",", ":")) + "\n"
    writer.write(line.encode("utf-8"))
    await writer.drain()


async def recv_message(reader: asyncio.StreamReader) -> dict[str, Any]:
    """Read and parse a JSON-RPC message from a stream.

    Reads one newline-delimited line and parses it as JSON.

    Args:
        reader: The asyncio stream to read from.

    Returns:
        The parsed JSON-RPC 2.0 message as a dict.

    Raises:
        ConnectionError: When the stream is closed (empty read).
        ProtocolError: When the received data is not valid JSON.
    """
    raw = await reader.readline()
    if not raw:
        raise ConnectionError("Connection closed: empty read from stream")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        _log.warning("Failed to parse JSON-RPC message: %r", raw[:200])
        raise ProtocolError(
            f"Invalid JSON in protocol message: {exc}",
            raw_data=raw,
        ) from exc

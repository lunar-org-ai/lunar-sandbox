"""Unit tests for JSON-RPC 2.0 protocol layer.

Tests message construction functions (make_request, make_response, make_error),
error code constants, and async send/recv transport helpers.
"""

from __future__ import annotations

import asyncio

import pytest

from lunar_sandbox.actions.protocol import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    make_error,
    make_request,
    make_response,
    recv_message,
    send_message,
)
from lunar_sandbox.sandbox.errors import ProtocolError


class TestMakeRequest:
    """Tests for make_request()."""

    def test_make_request(self) -> None:
        """Correct JSON-RPC 2.0 format with jsonrpc, method, params, id."""
        msg = make_request("execute_command", {"command": "ls"}, 1)
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "execute_command"
        assert msg["params"] == {"command": "ls"}
        assert msg["id"] == 1


class TestMakeResponse:
    """Tests for make_response()."""

    def test_make_response(self) -> None:
        """Correct format with jsonrpc, result, id."""
        msg = make_response({"status": "success", "output": "hello"}, 42)
        assert msg["jsonrpc"] == "2.0"
        assert msg["result"] == {"status": "success", "output": "hello"}
        assert msg["id"] == 42


class TestMakeError:
    """Tests for make_error()."""

    def test_make_error(self) -> None:
        """Correct format with error object containing code and message."""
        msg = make_error(-32600, "Invalid request", 5)
        assert msg["jsonrpc"] == "2.0"
        assert msg["error"]["code"] == -32600
        assert msg["error"]["message"] == "Invalid request"
        assert msg["id"] == 5
        assert "data" not in msg["error"]

    def test_make_error_with_data(self) -> None:
        """Error response includes optional data field."""
        msg = make_error(
            -32603, "Internal error", 7,
            data={"detail": "stack trace here"},
        )
        assert msg["error"]["data"] == {"detail": "stack trace here"}

    def test_make_error_null_id(self) -> None:
        """Error with None id (for parse errors)."""
        msg = make_error(-32700, "Parse error", None)
        assert msg["id"] is None


class TestErrorCodes:
    """Tests for JSON-RPC 2.0 error code constants."""

    def test_error_codes(self) -> None:
        """All 5 error codes have correct values."""
        assert JSONRPC_PARSE_ERROR == -32700
        assert JSONRPC_INVALID_REQUEST == -32600
        assert JSONRPC_METHOD_NOT_FOUND == -32601
        assert JSONRPC_INVALID_PARAMS == -32602
        assert JSONRPC_INTERNAL_ERROR == -32603


class TestAsyncTransport:
    """Tests for async send_message/recv_message."""

    def test_send_recv_roundtrip(self) -> None:
        """Async roundtrip using in-memory stream pair."""

        async def _roundtrip() -> None:
            # Create an in-memory pipe using asyncio streams.
            reader = asyncio.StreamReader()
            # Create a mock writer that writes to the reader.
            transport = _MockTransport(reader)
            protocol = asyncio.StreamReaderProtocol(reader)
            writer = asyncio.StreamWriter(transport, protocol, reader, asyncio.get_event_loop())

            original = make_request("read_file", {"path": "test.py"}, 99)
            await send_message(writer, original)
            received = await recv_message(reader)

            assert received["jsonrpc"] == "2.0"
            assert received["method"] == "read_file"
            assert received["params"] == {"path": "test.py"}
            assert received["id"] == 99

        asyncio.run(_roundtrip())

    def test_recv_empty_connection(self) -> None:
        """recv_message raises ConnectionError on empty read."""

        async def _empty_recv() -> None:
            reader = asyncio.StreamReader()
            reader.feed_eof()
            with pytest.raises(ConnectionError, match="Connection closed"):
                await recv_message(reader)

        asyncio.run(_empty_recv())

    def test_recv_invalid_json(self) -> None:
        """recv_message raises ProtocolError on malformed JSON."""

        async def _invalid_json() -> None:
            reader = asyncio.StreamReader()
            reader.feed_data(b"this is not json\n")
            with pytest.raises(ProtocolError, match="Invalid JSON"):
                await recv_message(reader)

        asyncio.run(_invalid_json())


class _MockTransport:
    """Minimal transport mock that feeds data into a StreamReader."""

    def __init__(self, reader: asyncio.StreamReader) -> None:
        self._reader = reader
        self._closing = False

    def write(self, data: bytes) -> None:
        self._reader.feed_data(data)

    def is_closing(self) -> bool:
        return self._closing

    def close(self) -> None:
        self._closing = True

    def get_extra_info(self, name: str, default: object = None) -> object:
        return default

    def set_write_buffer_limits(self, high: int = 0, low: int = 0) -> None:
        pass

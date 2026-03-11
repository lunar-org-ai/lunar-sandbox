"""Unit tests for WebSocket ConnectionManager and Connection.

Tests hierarchical topic matching, queue overflow (drop-oldest),
manager fan-out, and subscribe/unsubscribe lifecycle.
"""

from __future__ import annotations

import asyncio

import pytest

from lunar_sandbox.api.ws.manager import Connection, ConnectionManager


class _FakeWebSocket:
    """Minimal stand-in for ``fastapi.WebSocket`` -- only needs identity."""

    pass


# ---------------------------------------------------------------------------
# Connection topic matching
# ---------------------------------------------------------------------------


class TestConnectionMatching:
    """Hierarchical topic matching on a single Connection."""

    def test_exact_match(self) -> None:
        """Subscribing to 'sandbox:1' matches topic 'sandbox:1'."""
        conn = Connection(_FakeWebSocket())  # type: ignore[arg-type]
        conn.topics.add("sandbox:1")
        assert conn.matches("sandbox:1") is True

    def test_hierarchical_match(self) -> None:
        """Subscribing to 'sandbox:1' matches 'sandbox:1:episode:5'."""
        conn = Connection(_FakeWebSocket())  # type: ignore[arg-type]
        conn.topics.add("sandbox:1")
        assert conn.matches("sandbox:1:episode:5") is True

    def test_no_false_prefix(self) -> None:
        """Subscribing to 'sandbox:1' does NOT match 'sandbox:10'."""
        conn = Connection(_FakeWebSocket())  # type: ignore[arg-type]
        conn.topics.add("sandbox:1")
        assert conn.matches("sandbox:10") is False

    def test_no_match(self) -> None:
        """Subscribing to 'sandbox:1' does NOT match 'sandbox:2'."""
        conn = Connection(_FakeWebSocket())  # type: ignore[arg-type]
        conn.topics.add("sandbox:1")
        assert conn.matches("sandbox:2") is False


# ---------------------------------------------------------------------------
# Connection queue behaviour
# ---------------------------------------------------------------------------


class TestConnectionQueue:
    """Per-connection bounded queue with drop-oldest overflow."""

    def test_enqueue_and_drain(self) -> None:
        """Enqueued message can be retrieved via get_nowait."""
        conn = Connection(_FakeWebSocket(), maxsize=3)  # type: ignore[arg-type]
        conn.enqueue("msg-1")
        assert conn.queue.get_nowait() == "msg-1"

    def test_enqueue_drop_oldest(self) -> None:
        """When queue is full, enqueuing drops the oldest message."""
        conn = Connection(_FakeWebSocket(), maxsize=3)  # type: ignore[arg-type]
        conn.enqueue("msg-1")
        conn.enqueue("msg-2")
        conn.enqueue("msg-3")
        # Queue is full (3/3)
        conn.enqueue("msg-4")
        # msg-1 should have been dropped; remaining: msg-2, msg-3, msg-4
        items = []
        while not conn.queue.empty():
            items.append(conn.queue.get_nowait())
        assert items == ["msg-2", "msg-3", "msg-4"]


# ---------------------------------------------------------------------------
# ConnectionManager pub/sub
# ---------------------------------------------------------------------------


class TestManagerPublish:
    """ConnectionManager fan-out and topic filtering."""

    def test_publish_fan_out(self) -> None:
        """Two connections on the same topic both receive the message."""
        mgr = ConnectionManager()
        ws1, ws2 = _FakeWebSocket(), _FakeWebSocket()
        c1 = Connection(ws1, maxsize=10)  # type: ignore[arg-type]
        c2 = Connection(ws2, maxsize=10)  # type: ignore[arg-type]
        c1.topics.add("sandbox:1")
        c2.topics.add("sandbox:1")
        mgr.add(c1)
        mgr.add(c2)

        mgr.publish("sandbox:1", '{"data": 1}')

        assert c1.queue.get_nowait() == '{"data": 1}'
        assert c2.queue.get_nowait() == '{"data": 1}'

    def test_publish_filtered(self) -> None:
        """Only the connection subscribed to the matching topic receives."""
        mgr = ConnectionManager()
        ws1, ws2 = _FakeWebSocket(), _FakeWebSocket()
        c1 = Connection(ws1, maxsize=10)  # type: ignore[arg-type]
        c2 = Connection(ws2, maxsize=10)  # type: ignore[arg-type]
        c1.topics.add("sandbox:1")
        c2.topics.add("sandbox:2")
        mgr.add(c1)
        mgr.add(c2)

        mgr.publish("sandbox:1", '{"data": 1}')

        assert c1.queue.get_nowait() == '{"data": 1}'
        assert c2.queue.empty()

    def test_subscribe_unsubscribe(self) -> None:
        """After unsubscribe, connection no longer matches the topic."""
        mgr = ConnectionManager()
        ws = _FakeWebSocket()
        conn = Connection(ws, maxsize=10)  # type: ignore[arg-type]
        mgr.add(conn)

        mgr.subscribe(ws, "sandbox:1")  # type: ignore[arg-type]
        assert conn.matches("sandbox:1") is True

        mgr.unsubscribe(ws, "sandbox:1")  # type: ignore[arg-type]
        assert conn.matches("sandbox:1") is False

        # Publish after unsubscribe should not deliver
        mgr.publish("sandbox:1", '{"data": 1}')
        assert conn.queue.empty()

    def test_connection_count(self) -> None:
        """connection_count reflects the number of tracked connections."""
        mgr = ConnectionManager()
        assert mgr.connection_count == 0

        ws = _FakeWebSocket()
        conn = Connection(ws, maxsize=10)  # type: ignore[arg-type]
        mgr.add(conn)
        assert mgr.connection_count == 1

        mgr.remove(ws)  # type: ignore[arg-type]
        assert mgr.connection_count == 0

    def test_remove_missing_no_error(self) -> None:
        """Removing a non-existent connection does not raise."""
        mgr = ConnectionManager()
        ws = _FakeWebSocket()
        mgr.remove(ws)  # type: ignore[arg-type]  # should not raise

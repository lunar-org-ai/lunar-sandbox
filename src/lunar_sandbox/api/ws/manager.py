"""ConnectionManager: tracks WebSocket connections, subscriptions, and queues.

Each connection gets a bounded ``asyncio.Queue`` for outbound messages and
a set of topic subscriptions.  The manager fans out published messages to
all connections whose subscriptions match the event topic.

Topic matching is hierarchical:  subscribing to ``sandbox:1`` matches
``sandbox:1`` and ``sandbox:1:episode:5`` but NOT ``sandbox:10``.
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import WebSocket

__all__ = ["Connection", "ConnectionManager", "QUEUE_MAX_SIZE"]

logger = structlog.get_logger(__name__)

QUEUE_MAX_SIZE = 500


class Connection:
    """A single WebSocket connection with its send queue and subscriptions."""

    __slots__ = ("ws", "queue", "topics")

    def __init__(self, ws: WebSocket, *, maxsize: int = QUEUE_MAX_SIZE) -> None:
        self.ws = ws
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=maxsize)
        self.topics: set[str] = set()

    def matches(self, topic: str) -> bool:
        """Check if this connection is subscribed to *topic*.

        Hierarchical matching: subscription ``sandbox:1`` matches topic
        ``sandbox:1:episode:5`` (child) but NOT ``sandbox:10`` (different
        entity sharing a prefix).
        """
        for sub in self.topics:
            if topic == sub or topic.startswith(sub + ":"):
                return True
        return False

    def enqueue(self, message: str) -> None:
        """Add *message* to the send queue, dropping the oldest if full."""
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            # Drop oldest (FIFO front) to make room
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self.queue.put_nowait(message)
            except asyncio.QueueFull:
                pass  # Should never happen after get_nowait


class ConnectionManager:
    """Manages all active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: dict[int, Connection] = {}

    # -- connection lifecycle ------------------------------------------------

    def add(self, conn: Connection) -> None:
        """Register a new connection."""
        self._connections[id(conn.ws)] = conn

    def remove(self, ws: WebSocket) -> None:
        """Remove a connection (no error if already gone)."""
        self._connections.pop(id(ws), None)

    # -- subscriptions -------------------------------------------------------

    def subscribe(self, ws: WebSocket, topic: str) -> None:
        """Subscribe *ws* to *topic*."""
        conn = self._connections.get(id(ws))
        if conn:
            conn.topics.add(topic)

    def unsubscribe(self, ws: WebSocket, topic: str) -> None:
        """Unsubscribe *ws* from *topic* (no error if not subscribed)."""
        conn = self._connections.get(id(ws))
        if conn:
            conn.topics.discard(topic)

    # -- publishing ----------------------------------------------------------

    def publish(self, topic: str, message: str) -> None:
        """Fan out *message* to all connections subscribed to *topic*."""
        for conn in self._connections.values():
            if conn.matches(topic):
                conn.enqueue(message)

    # -- introspection -------------------------------------------------------

    @property
    def connection_count(self) -> int:
        """Number of active connections."""
        return len(self._connections)

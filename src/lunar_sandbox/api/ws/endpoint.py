"""WebSocket route handler with dual-task reader/writer pattern.

The handler accepts a connection, then runs two concurrent tasks:

* **reader** -- processes ``subscribe`` / ``unsubscribe`` messages
  from the client.
* **writer** -- drains the per-connection queue and pushes messages
  to the client.

When either task finishes (client disconnects or send error), the
other is cancelled and the connection is cleaned up.
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from lunar_sandbox.api.ws.manager import Connection, ConnectionManager

__all__ = ["websocket_handler"]

logger = structlog.get_logger(__name__)


async def websocket_handler(ws: WebSocket, manager: ConnectionManager) -> None:
    """Handle a single WebSocket connection lifecycle."""
    await ws.accept()
    conn = Connection(ws)
    manager.add(conn)
    connection_id = id(ws)
    logger.info("ws_connected", connection_id=connection_id)

    async def reader() -> None:
        """Read subscribe/unsubscribe messages from the client."""
        try:
            while True:
                data = await ws.receive_json()
                if "subscribe" in data:
                    topic = data["subscribe"]
                    manager.subscribe(ws, topic)
                    logger.info("ws_subscribed", connection_id=connection_id, topic=topic)
                elif "unsubscribe" in data:
                    topic = data["unsubscribe"]
                    manager.unsubscribe(ws, topic)
                    logger.info("ws_unsubscribed", connection_id=connection_id, topic=topic)
        except WebSocketDisconnect:
            pass

    async def writer() -> None:
        """Drain send queue and push messages to the client."""
        try:
            while True:
                message = await conn.queue.get()
                await ws.send_text(message)
        except Exception:
            pass

    try:
        done, pending = await asyncio.wait(
            [asyncio.create_task(reader()), asyncio.create_task(writer())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        manager.remove(ws)
        logger.info("ws_disconnected", connection_id=connection_id)

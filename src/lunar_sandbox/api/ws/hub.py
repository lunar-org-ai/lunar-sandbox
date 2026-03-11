"""EventHub: typed event publishing over the ConnectionManager.

Decouples event producers (engine hooks, mock emitter) from raw
WebSocket details.  Callers pass structured data; the hub serializes
a ``WsEnvelope`` and delegates fan-out to the manager.
"""

from __future__ import annotations

import time
from typing import Any

from lunar_sandbox.api.schemas import WsEnvelope
from lunar_sandbox.api.ws.manager import ConnectionManager

__all__ = ["EventHub"]


class EventHub:
    """Publish typed events to all matching WebSocket connections."""

    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager

    def publish_event(self, type: str, topic: str, payload: dict[str, Any]) -> None:
        """Create a ``WsEnvelope``, serialize it, and publish to *topic*."""
        envelope = WsEnvelope(
            type=type,
            topic=topic,
            timestamp=time.time(),
            payload=payload,
        )
        self._manager.publish(topic, envelope.model_dump_json())

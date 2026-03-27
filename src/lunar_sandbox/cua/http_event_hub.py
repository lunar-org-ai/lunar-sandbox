"""Lightweight event hub that POSTs events to a running API server.

Used by notebooks and CLI scripts to push CUA events to the dashboard's
live activity panel without running inside the API server process.

Usage::

    hub = HttpEventHub("http://localhost:8000")
    runner = CUAEpisodeRunner(
        task=task,
        sandbox=sandbox,
        agent=agent,
        event_hub=hub,
        ...
    )
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

__all__ = ["HttpEventHub"]

log = structlog.get_logger(__name__)


class HttpEventHub:
    """Publishes CUA events to the API server via HTTP POST.

    Drop-in replacement for the in-process ``EventHub`` used by the
    API server.  Events are sent to ``POST /api/cua/events`` which
    forwards them to the WebSocket event hub.

    Args:
        api_base: Base URL of the running API server
            (e.g. ``"http://localhost:8000"``).
    """

    def __init__(self, api_base: str = "http://localhost:8000") -> None:
        self._url = f"{api_base.rstrip('/')}/api/cua/events"
        self._client = httpx.Client(timeout=5.0)

    def publish_event(self, type: str, topic: str, payload: dict[str, Any]) -> None:
        """POST an event to the API server's event endpoint."""
        try:
            self._client.post(
                self._url,
                json={"type": type, "topic": topic, "payload": payload},
            )
        except Exception as exc:
            # Non-fatal: dashboard just won't see this event
            log.debug("http_event_hub_post_failed", error=str(exc))

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

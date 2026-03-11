"""Mock event emitter for macOS development.

When the engine cannot start (Linux-only kernel features), this
emitter publishes synthetic trace events on a timer so the entire
WebSocket pipeline can be developed and tested without a running engine.
"""

from __future__ import annotations

import asyncio
import random

import structlog

from lunar_sandbox.api.ws.hub import EventHub

__all__ = ["run_mock_emitter"]

logger = structlog.get_logger(__name__)


async def run_mock_emitter(hub: EventHub, interval: float = 2.0) -> None:
    """Publish synthetic trace events every *interval* seconds."""
    logger.info("mock_emitter_running", interval=interval)
    step_idx = 0
    try:
        while True:
            await asyncio.sleep(interval)
            hub.publish_event(
                type="trace_event",
                topic="sandbox:mock:episode:demo",
                payload={
                    "step_idx": step_idx,
                    "action_type": "shell",
                    "command": "echo hello",
                    "status": "completed",
                    "duration_ms": random.randint(50, 500),
                },
            )
            step_idx += 1
    except asyncio.CancelledError:
        logger.info("mock_emitter_stopped", steps_emitted=step_idx)

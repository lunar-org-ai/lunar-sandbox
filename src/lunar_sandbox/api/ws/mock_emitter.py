"""Mock event emitter for macOS development.

When the engine cannot start (Linux-only kernel features), this
emitter publishes synthetic trace events and sandbox_status events on
a timer so the entire WebSocket pipeline can be developed and tested
without a running engine.

Emission schedule:
- Every 2 seconds (even ticks): trace_event on sandbox:mock:episode:demo
- Every 4 seconds (multiples of 2): sandbox_status for one of 3 mock sandboxes
"""

from __future__ import annotations

import asyncio
import random

import structlog

from lunar_sandbox.api.ws.hub import EventHub

__all__ = ["run_mock_emitter"]

logger = structlog.get_logger(__name__)

_MOCK_SANDBOX_IDS = ["sbx-a1b2", "sbx-c3d4", "sbx-e5f6"]
_SANDBOX_STATES = ["Running", "Idle", "Starting", "Finished", "Error"]


async def run_mock_emitter(hub: EventHub, interval: float = 2.0) -> None:
    """Publish synthetic trace and sandbox_status events on a timer.

    Emits a ``trace_event`` every *interval* seconds (default 2s).
    Every other tick (every 4s) also emits a ``sandbox_status`` event
    for one of three rotating mock sandbox IDs.
    """
    logger.info("mock_emitter_running", interval=interval)
    step_idx = 0
    tick = 0
    try:
        while True:
            await asyncio.sleep(interval)

            # Trace event every tick
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

            # Sandbox status event every other tick (every 4s)
            if tick % 2 == 1:
                sandbox_id = _MOCK_SANDBOX_IDS[tick // 2 % len(_MOCK_SANDBOX_IDS)]
                hub.publish_event(
                    type="sandbox_status",
                    topic="sandbox",
                    payload={
                        "sandbox_id": sandbox_id,
                        "state": random.choice(_SANDBOX_STATES),
                        "cpu_percent": round(random.uniform(0, 100), 1),
                        "memory_mb": round(random.uniform(50, 512), 1),
                    },
                )

            tick += 1
    except asyncio.CancelledError:
        logger.info("mock_emitter_stopped", steps_emitted=step_idx)

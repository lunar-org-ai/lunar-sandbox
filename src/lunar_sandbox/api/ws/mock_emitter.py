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
import time

import structlog

from lunar_sandbox.api.ws.hub import EventHub

__all__ = ["run_mock_emitter"]

logger = structlog.get_logger(__name__)

_MOCK_SANDBOX_IDS = ["sbx-a1b2", "sbx-c3d4", "sbx-e5f6"]
_SANDBOX_STATES = ["Running", "Idle", "Starting", "Finished", "Error"]

# 8 canonical action types for diverse timeline display
_ACTION_TYPES = [
    "execute_command",
    "read_file",
    "write_file",
    "submit",
    "list_files",
    "search_code",
    "run_tests",
    "get_logs",
]

# Mock params per action type
_ACTION_PARAMS: dict[str, dict] = {
    "execute_command": {"command": "echo hello"},
    "read_file": {"path": "/src/main.py"},
    "write_file": {"path": "/src/utils.py", "content": "..."},
    "submit": {"answer": "42"},
    "list_files": {"directory": "/src"},
    "search_code": {"query": "def main", "path": "."},
    "run_tests": {"test_command": "pytest tests/"},
    "get_logs": {"container_id": "abc123"},
}


async def run_mock_emitter(hub: EventHub, interval: float = 2.0) -> None:
    """Publish synthetic trace and sandbox_status events on a timer.

    Emits a ``trace_event`` every *interval* seconds (default 2s).
    Every other tick (every 4s) also emits a ``sandbox_status`` event
    for one of three rotating mock sandbox IDs.

    Action types cycle through 8 canonical types to provide visual variety
    in the trace timeline. Duration varies widely (10-2000ms) to produce
    diverse bar widths. Status is mostly "completed" with occasional
    "error" (every 7th step) and "timeout" (every 11th step).
    """
    logger.info("mock_emitter_running", interval=interval)
    step_idx = 0
    tick = 0
    try:
        while True:
            await asyncio.sleep(interval)

            # Cycle through action types for visual variety
            action_type = _ACTION_TYPES[step_idx % len(_ACTION_TYPES)]
            params = _ACTION_PARAMS[action_type]

            # Vary duration widely to show diverse bar widths in timeline
            duration_ms = random.randint(10, 2000)

            # Status variation: error every 7th step, timeout every 11th
            if step_idx % 11 == 10:
                status = "timeout"
                exit_code = 1
            elif step_idx % 7 == 6:
                status = "error"
                exit_code = 1
            else:
                status = "completed"
                exit_code = 0

            output = {
                "stdout": f"mock output for step {step_idx}",
                "exit_code": exit_code,
            }

            # Trace event every tick
            hub.publish_event(
                type="trace_event",
                topic="sandbox:mock:episode:demo",
                payload={
                    "step_idx": step_idx,
                    "action_type": action_type,
                    "status": status,
                    "duration_ms": duration_ms,
                    "ts": time.time(),
                    "params": params,
                    "output": output,
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

"""Mock event emitter for macOS development.

When the engine cannot start (Linux-only kernel features), this
emitter publishes synthetic trace events, sandbox_status events,
batch_progress events, and telemetry_metric events on a timer so
the entire WebSocket pipeline can be developed and tested without a
running engine.

Emission schedule:
- Every 2 seconds (even ticks): trace_event on sandbox:mock:episode:demo
- Every 4 seconds (tick % 2 == 1): sandbox_status for one of 3 mock sandboxes
- Every 4 seconds (tick % 2 == 1): batch_progress on batch:mock-batch-1
- Every 6 seconds (tick % 3 == 2): telemetry_metric on telemetry:mock-run-1
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

# Batch progress state
MOCK_BATCH_ID = "mock-batch-1"
MOCK_BATCH_TOTAL = 20


async def run_mock_emitter(hub: EventHub, interval: float = 2.0) -> None:
    """Publish synthetic trace, sandbox_status, batch_progress, and
    telemetry_metric events on a timer.

    Emits a ``trace_event`` every *interval* seconds (default 2s).
    Every other tick (every 4s) also emits a ``sandbox_status`` event
    for one of three rotating mock sandbox IDs, plus a ``batch_progress``
    event on topic ``batch:mock-batch-1``.
    Every third tick (every 6s) emits a ``telemetry_metric`` event on
    topic ``telemetry:mock-run-1``.

    Action types cycle through 8 canonical types to provide visual variety
    in the trace timeline. Duration varies widely (10-2000ms) to produce
    diverse bar widths. Status is mostly "completed" with occasional
    "error" (every 7th step) and "timeout" (every 11th step).

    Batch progress:
    - Increments completed count by 1 every 4s
    - Roughly 70/20/10 pass/fail/error distribution
    - Tracks cumulative total_cost and total_tokens for live cost tracking
    - Resets on cycle completion (passed + failed + errors >= MOCK_BATCH_TOTAL)
    """
    logger.info("mock_emitter_running", interval=interval)
    step_idx = 0
    tick = 0

    # Batch progress tracking state
    batch_passed = 0
    batch_failed = 0
    batch_errors = 0
    batch_total_cost: float = 0.0
    batch_total_tokens: int = 0
    batch_start_time = time.time()

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

            # Sandbox status event + batch_progress every other tick (every 4s)
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

                # Check if batch cycle is complete; reset if so
                completed = batch_passed + batch_failed + batch_errors
                if completed >= MOCK_BATCH_TOTAL:
                    batch_passed = 0
                    batch_failed = 0
                    batch_errors = 0
                    batch_total_cost = 0.0
                    batch_total_tokens = 0
                    batch_start_time = time.time()
                    completed = 0

                # Advance batch by one episode with 70/20/10 distribution
                roll = random.random()
                if roll < 0.70:
                    batch_passed += 1
                elif roll < 0.90:
                    batch_failed += 1
                else:
                    batch_errors += 1

                # Accumulate cost and token state
                episode_cost = round(random.uniform(0.001, 0.01), 6)
                episode_tokens = random.randint(500, 2000)
                batch_total_cost = round(batch_total_cost + episode_cost, 6)
                batch_total_tokens += episode_tokens

                new_completed = batch_passed + batch_failed + batch_errors
                elapsed_ms = (time.time() - batch_start_time) * 1000

                hub.publish_event(
                    type="batch_progress",
                    topic=f"batch:{MOCK_BATCH_ID}",
                    payload={
                        "batch_id": MOCK_BATCH_ID,
                        "total_tasks": MOCK_BATCH_TOTAL,
                        "passed": batch_passed,
                        "failed": batch_failed,
                        "errors": batch_errors,
                        "in_progress": random.randint(1, 2),
                        "elapsed_ms": round(elapsed_ms, 1),
                        "total_cost": batch_total_cost,
                        "total_tokens": batch_total_tokens,
                    },
                )

            # Telemetry metric event every 6 seconds (tick % 3 == 2)
            if tick % 3 == 2:
                hub.publish_event(
                    type="telemetry_metric",
                    topic="telemetry:mock-run-1",
                    payload={
                        "run_id": "mock-run-1",
                        "samples": [
                            {
                                "metric": "allocate_latency",
                                "value": round(random.uniform(80, 250), 1),
                                "unit": "ms",
                            },
                            {
                                "metric": "reset_latency",
                                "value": round(random.uniform(30, 90), 1),
                                "unit": "ms",
                            },
                            {
                                "metric": "episode_duration",
                                "value": round(random.uniform(4000, 12000), 0),
                                "unit": "ms",
                            },
                            {
                                "metric": "cache_hit_rate",
                                "value": round(random.uniform(0.6, 0.95), 3),
                                "unit": "ratio",
                            },
                        ],
                    },
                )

            tick += 1
    except asyncio.CancelledError:
        logger.info("mock_emitter_stopped", steps_emitted=step_idx)

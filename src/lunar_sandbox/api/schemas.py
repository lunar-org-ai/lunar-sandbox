"""Pydantic response models for the API layer.

Separate from internal engine types (which use dataclasses).  This
decouples the API response shapes from internal implementation,
allowing the API to evolve independently.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lunar_sandbox.api.pagination import PaginatedResponse

__all__ = [
    "EpisodeDetail",
    "EpisodeSummary",
    "HealthResponse",
    "PaginatedEpisodes",
    "PaginatedTasks",
    "PaginatedTelemetryRuns",
    "PoolStatus",
    "SandboxInfo",
    "TaskSummary",
    "TelemetryRunDetail",
    "TelemetryRunSummary",
    "WsEnvelope",
]


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------


class EpisodeSummary(BaseModel):
    """Summary of a single evaluation episode."""

    episode_id: str
    task_name: str
    outcome: str
    score: float | None = None
    step_count: int = 0
    duration_ms: float = 0.0
    started_at: float = 0.0
    ended_at: float | None = None


class EpisodeDetail(EpisodeSummary):
    """Full episode detail including sandbox info and step data."""

    sandbox_id: str = ""
    is_complete: int = 1
    steps: list[dict[str, Any]] = []


class PaginatedEpisodes(PaginatedResponse):
    """Paginated list of episode summaries."""

    items: list[EpisodeSummary]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


class TaskSummary(BaseModel):
    """Summary of a task definition."""

    name: str
    runtime: str = "python3.12"
    timeout: int = 1800
    max_steps: int = 200
    instructions: str = ""
    test_command: str = ""


class PaginatedTasks(PaginatedResponse):
    """Paginated list of task summaries."""

    items: list[TaskSummary]


# ---------------------------------------------------------------------------
# Sandboxes
# ---------------------------------------------------------------------------


class SandboxInfo(BaseModel):
    """Information about a single sandbox instance."""

    sandbox_id: str
    fingerprint: str
    state: str


class PoolStatus(BaseModel):
    """Current sandbox pool status."""

    running: bool
    total_sandboxes: int
    sandboxes: list[SandboxInfo] = []


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


class TelemetryRunSummary(BaseModel):
    """Summary of a telemetry collection run."""

    run_id: str
    started_at: float = 0.0
    ended_at: float | None = None
    total_episodes: int = 0
    throughput_eps_per_min: float | None = None
    cache_hit_rate: float | None = None


class PaginatedTelemetryRuns(PaginatedResponse):
    """Paginated list of telemetry run summaries."""

    items: list[TelemetryRunSummary]


class TelemetryRunDetail(TelemetryRunSummary):
    """Telemetry run detail with raw metric samples."""

    samples: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Health check response."""

    status: str  # "ok" or "degraded"
    engine_started: bool
    stores_available: bool


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


class WsEnvelope(BaseModel):
    """WebSocket message envelope.

    Every message sent over the WebSocket connection is wrapped in this
    envelope.  The ``payload`` dict reuses the same shapes as REST
    responses so the codegen pipeline produces TypeScript types for both.
    """

    type: str
    """Event type, e.g. ``"trace_event"``, ``"sandbox_status"``."""

    topic: str
    """Hierarchical topic, e.g. ``"sandbox:abc123:episode:ep456"``."""

    timestamp: float
    """Unix timestamp (seconds since epoch)."""

    payload: dict[str, Any]
    """Event data — reuses existing schema shapes."""

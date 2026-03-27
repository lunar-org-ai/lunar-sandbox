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
    "BatchDetail",
    "BatchSummary",
    "CUAEpisodeInfo",
    "CUALaunchRequest",
    "CUALaunchResponse",
    "CUAScoreRequest",
    "CUAScoreResponse",
    "EpisodeDetail",
    "EpisodeSummary",
    "FingerprintHealth",
    "HealthResponse",
    "PaginatedBatches",
    "PaginatedEpisodes",
    "PaginatedTasks",
    "PaginatedTelemetryRuns",
    "PoolHealthDetail",
    "PoolStatus",
    "RunLaunchResponse",
    "RunRequest",
    "SandboxInfo",
    "TaskResultSummary",
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
    cost_usd: float | None = None
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
    started_at: float | None = None
    cpu_percent: float | None = None
    memory_mb: float | None = None


class PoolStatus(BaseModel):
    """Current sandbox pool status."""

    running: bool
    total_sandboxes: int
    sandboxes: list[SandboxInfo] = []


class FingerprintHealth(BaseModel):
    """Health metrics for a single fingerprint group."""

    fingerprint: str
    idle_count: int = 0
    active_count: int = 0
    total_count: int = 0
    eviction_count: int = 0
    cache_hit_rate: float | None = None


class PoolHealthDetail(BaseModel):
    """Detailed pool health with per-fingerprint breakdown."""

    running: bool
    total_sandboxes: int
    fingerprints: list[FingerprintHealth] = []
    overall_cache_hit_rate: float | None = None
    total_evictions: int = 0


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
# Runs
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    """Request body for launching an evaluation run."""

    task_name: str
    model: str | None = None
    parallelism: int = 1
    timeout: int | None = None
    env_vars: dict[str, str] | None = None
    cpu_cores: int | None = None
    memory_mb: int | None = None


class RunLaunchResponse(BaseModel):
    """Response returned after a run is successfully launched."""

    run_id: str
    episode_id: str


# ---------------------------------------------------------------------------
# Batches
# ---------------------------------------------------------------------------


class TaskResultSummary(BaseModel):
    """Summary of a single task result within a batch."""

    task_name: str
    episode_id: str = ""
    outcome: str
    score: float | None = None
    wall_clock_ms: float = 0.0
    step_count: int = 0
    token_count: int = 0
    estimated_cost: float = 0.0


class BatchSummary(BaseModel):
    """Summary of a batch evaluation run."""

    batch_id: str
    benchmark_name: str = ""
    total_tasks: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    pass_rate: float = 0.0
    total_tokens: int = 0
    total_cost: float = 0.0
    duration_ms: float = 0.0
    started_at: float = 0.0
    ended_at: float | None = None


class BatchDetail(BatchSummary):
    """Full batch detail including per-task results."""

    task_results: list[TaskResultSummary] = []


class PaginatedBatches(PaginatedResponse):
    """Paginated list of batch summaries."""

    items: list[BatchSummary]


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
    """Event data -- reuses existing schema shapes."""


# ---------------------------------------------------------------------------
# CUA
# ---------------------------------------------------------------------------


class CUALaunchRequest(BaseModel):
    """Request body for launching a CUA episode."""

    instruction: str
    reward_type: str = "manual"  # "manual", "script", "screenshot_match"
    agent_mode: str = "manual"  # "manual" (keep alive for user) or "model" (AI-driven)
    api_key: str | None = None  # Anthropic API key (falls back to ANTHROPIC_API_KEY env var)
    # Model provider: "anthropic" (default) or "azure_openai"
    model_provider: str = "anthropic"
    # Azure OpenAI settings (used when model_provider="azure_openai")
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_key: str | None = None
    start_url: str | None = None
    resolution: str = "1280x800"
    max_steps: int = 1000
    time_limit: float = 300.0
    # Script reward fields
    script_content: str | None = None
    # Screenshot match fields
    reference_image_url: str | None = None
    screenshot_threshold: float = 0.95
    # Platform selection: "linux" (Docker, default) or "windows" (VM)
    platform: str = "linux"
    # Windows Azure VM settings (used when platform="windows")
    windows_ssh_host: str | None = None
    windows_ssh_port: int = 22
    windows_ssh_user: str = "lunar"
    windows_ssh_password: str | None = None
    windows_ssh_key_path: str | None = None
    # Azure VM execution via az run-command (no SSH for actions).
    # When set, uses AzureWindowsCUASandbox instead of SSH-based sandbox.
    windows_azure_resource_group: str | None = None
    windows_azure_vm_name: str | None = None


class CUALaunchResponse(BaseModel):
    """Response after CUA episode launch."""

    episode_id: str
    vnc_url: str  # WebSocket URL for live VNC (Linux) or empty string (Windows)
    rdp_url: str | None = None  # RDP URL for live viewing (Windows only)


class CUAScoreRequest(BaseModel):
    """Request body for scoring a CUA episode."""

    score: float
    notes: str | None = None


class CUAScoreResponse(BaseModel):
    """Response after scoring."""

    episode_id: str
    score: float
    next_episode_id: str | None = None  # next unreviewed episode


class CUAEpisodeInfo(BaseModel):
    """CUA episode with review info."""

    episode_id: str
    task_name: str
    outcome: str
    score: float | None = None
    review_notes: str | None = None
    step_count: int = 0
    duration_ms: float = 0.0
    started_at: float = 0.0
    ended_at: float | None = None
    episode_type: str = "cua"
    platform: str | None = None  # "linux" or "windows"

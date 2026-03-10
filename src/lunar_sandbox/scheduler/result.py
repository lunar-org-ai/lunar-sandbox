"""Batch evaluation result types.

Provides :class:`TaskResult`, :class:`AggregateMetrics`, and
:class:`BatchResult` -- the structured output of batch evaluation runs.

:class:`TaskResult` wraps the per-task outcome with timing, cost, and
error context.  Factory classmethods construct results from
:class:`EpisodeResult`, timeouts, and unexpected exceptions.

:class:`AggregateMetrics` computes pass rate, P50/P95 timing, cost
totals, and error breakdown from a list of :class:`TaskResult` objects.

:class:`BatchResult` is structured data only -- Phase 6 CLI handles
formatting and display.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lunar_sandbox.episode.result import EpisodeResult

__all__ = ["AggregateMetrics", "BatchResult", "TaskResult"]


@dataclass
class TaskResult:
    """Result of a single task evaluation within a batch.

    Extends :class:`EpisodeResult` with batch-specific fields: timing
    breakdown, cost data, retry info, and error classification.

    Attributes:
        task_name: Name of the evaluated task.
        outcome: One of ``"pass"``, ``"fail"``, ``"error"``.
        score: Numeric score (None if scoring was not reached).
        error_type: Error classification when outcome is ``"error"``.
        error_message: Human-readable error description.
        last_agent_action: Last action the agent attempted before failure.
        wall_clock_ms: Total wall-clock time for the task in milliseconds.
        time_to_first_action_ms: Time to first agent action (not yet
            instrumented; defaults to None).
        scoring_time_ms: Time spent in the scoring phase (not yet
            instrumented; defaults to None).
        step_count: Number of agent steps executed.
        token_count: Total tokens consumed (defaults to 0; AgentAdapter
            does not yet return metadata).
        estimated_cost_usd: Estimated cost in USD (defaults to 0.0).
        trajectory_path: Path to the JSONL trajectory file.
        episode_id: Unique episode identifier.
        attempt: Retry attempt number (1-based).
    """

    task_name: str
    outcome: str  # "pass", "fail", "error"
    score: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    last_agent_action: str | None = None

    # Timing breakdown
    wall_clock_ms: float = 0.0
    time_to_first_action_ms: float | None = None
    scoring_time_ms: float | None = None

    # Step count & cost
    step_count: int = 0
    token_count: int = 0
    estimated_cost_usd: float = 0.0

    # Trajectory reference
    trajectory_path: str = ""
    episode_id: str = ""

    # Retry info
    attempt: int = 1

    def is_pass(self) -> bool:
        """Return True if the task passed."""
        return self.outcome == "pass"

    def is_infra_error(self) -> bool:
        """Return True if the task failed due to infrastructure.

        Infrastructure errors are retryable: sandbox crashes, timeouts,
        pool exhaustion, and generic infra failures.
        """
        return self.outcome == "error" and self.error_type in (
            "sandbox_crash",
            "timeout",
            "pool_exhausted",
            "infra_error",
        )

    def is_error(self) -> bool:
        """Return True if the task ended with any error."""
        return self.outcome == "error"

    def to_dict(self) -> dict[str, Any]:
        """Serialize all fields for JSONL output."""
        return {
            "task_name": self.task_name,
            "outcome": self.outcome,
            "score": self.score,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "last_agent_action": self.last_agent_action,
            "wall_clock_ms": self.wall_clock_ms,
            "time_to_first_action_ms": self.time_to_first_action_ms,
            "scoring_time_ms": self.scoring_time_ms,
            "step_count": self.step_count,
            "token_count": self.token_count,
            "estimated_cost_usd": self.estimated_cost_usd,
            "trajectory_path": self.trajectory_path,
            "episode_id": self.episode_id,
            "attempt": self.attempt,
        }

    # -- factory classmethods ------------------------------------------------

    @classmethod
    def from_episode(
        cls,
        task_name: str,
        episode_result: EpisodeResult,
        start_time_mono: float,
    ) -> TaskResult:
        """Construct from a completed :class:`EpisodeResult`.

        Maps :class:`EpisodeOutcome` values to task-level outcomes:

        - COMPLETED with score > 0 -> ``"pass"``
        - COMPLETED with score <= 0 or None -> ``"fail"``
        - INFRA_ERROR -> ``"error"`` with error_type ``"infra_error"``
        - TIMEOUT -> ``"error"`` with error_type ``"timeout"``
        - AGENT_ERROR -> ``"error"`` with error_type ``"agent_error"``
        - CANCELLED -> ``"error"`` with error_type ``"cancelled"``

        Args:
            task_name: Name of the task.
            episode_result: The completed episode result.
            start_time_mono: ``time.monotonic()`` value at task start.

        Returns:
            A populated :class:`TaskResult`.
        """
        from lunar_sandbox.episode.state import EpisodeOutcome

        wall_clock_ms = (time.monotonic() - start_time_mono) * 1000

        outcome_val = episode_result.outcome

        # Map EpisodeOutcome to task outcome + error_type
        if outcome_val == EpisodeOutcome.COMPLETED:
            if episode_result.score is not None and episode_result.score > 0:
                outcome = "pass"
            else:
                outcome = "fail"
            error_type = None
            error_message = None
        elif outcome_val == EpisodeOutcome.INFRA_ERROR:
            outcome = "error"
            error_type = "infra_error"
            error_message = episode_result.error_message
        elif outcome_val == EpisodeOutcome.TIMEOUT:
            outcome = "error"
            error_type = "timeout"
            error_message = episode_result.error_message
        elif outcome_val == EpisodeOutcome.AGENT_ERROR:
            outcome = "error"
            error_type = "agent_error"
            error_message = episode_result.error_message
        elif outcome_val == EpisodeOutcome.CANCELLED:
            outcome = "error"
            error_type = "cancelled"
            error_message = episode_result.error_message
        else:
            outcome = "error"
            error_type = "unknown"
            error_message = f"Unexpected outcome: {outcome_val}"

        return cls(
            task_name=task_name,
            outcome=outcome,
            score=episode_result.score,
            error_type=error_type,
            error_message=error_message,
            wall_clock_ms=wall_clock_ms,
            step_count=episode_result.step_count,
            trajectory_path=episode_result.jsonl_path,
            episode_id=episode_result.episode_id,
        )

    @classmethod
    def from_timeout(
        cls,
        task_name: str,
        start_time_mono: float,
    ) -> TaskResult:
        """Construct a timeout error result.

        Args:
            task_name: Name of the task that timed out.
            start_time_mono: ``time.monotonic()`` value at task start.

        Returns:
            A :class:`TaskResult` with outcome ``"error"`` and
            error_type ``"timeout"``.
        """
        wall_clock_ms = (time.monotonic() - start_time_mono) * 1000
        return cls(
            task_name=task_name,
            outcome="error",
            error_type="timeout",
            error_message="Task exceeded timeout",
            wall_clock_ms=wall_clock_ms,
        )

    @classmethod
    def from_error(
        cls,
        task_name: str,
        exc: Exception,
        start_time_mono: float = 0.0,
    ) -> TaskResult:
        """Construct an infrastructure error result from an exception.

        Args:
            task_name: Name of the task that failed.
            exc: The exception that caused the failure.
            start_time_mono: ``time.monotonic()`` value at task start.
                Defaults to ``0.0`` if timing is not available.

        Returns:
            A :class:`TaskResult` with outcome ``"error"`` and
            error_type ``"infra_error"``.
        """
        wall_clock_ms = (
            (time.monotonic() - start_time_mono) * 1000
            if start_time_mono > 0
            else 0.0
        )
        return cls(
            task_name=task_name,
            outcome="error",
            error_type="infra_error",
            error_message=str(exc),
            wall_clock_ms=wall_clock_ms,
        )

    @classmethod
    def cancelled(cls, task_name: str) -> TaskResult:
        """Construct a cancellation result.

        Args:
            task_name: Name of the task that was cancelled.

        Returns:
            A :class:`TaskResult` with outcome ``"error"`` and
            error_type ``"cancelled"``.
        """
        return cls(
            task_name=task_name,
            outcome="error",
            error_type="cancelled",
            error_message="Task cancelled (batch fail-fast or shutdown)",
        )


@dataclass
class AggregateMetrics:
    """Aggregate metrics computed from a list of :class:`TaskResult` objects.

    Attributes:
        total_tasks: Total number of tasks in the batch.
        passed: Number of tasks that passed.
        failed: Number of tasks that failed (outcome ``"fail"``).
        errors: Number of tasks with errors (outcome ``"error"``).
        pass_rate: Fraction of tasks that passed (0.0--1.0).
        mean_score: Mean score across tasks with scores, or None.
        p50_wall_clock_ms: Median wall-clock time, or None.
        p95_wall_clock_ms: 95th percentile wall-clock time, or None.
        total_tokens: Sum of token counts across all tasks.
        total_estimated_cost_usd: Sum of estimated costs.
        total_batch_duration_ms: Total batch wall-clock duration.
        errors_by_type: Count of errors grouped by error_type.
    """

    total_tasks: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    pass_rate: float = 0.0
    mean_score: float | None = None

    # Timing percentiles
    p50_wall_clock_ms: float | None = None
    p95_wall_clock_ms: float | None = None

    # Cost totals
    total_tokens: int = 0
    total_estimated_cost_usd: float = 0.0
    total_batch_duration_ms: float = 0.0

    # Error breakdown
    errors_by_type: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_results(
        cls,
        results: list[TaskResult],
        batch_duration_ms: float,
    ) -> AggregateMetrics:
        """Compute aggregate metrics from a list of task results.

        Guards :func:`statistics.quantiles` with a ``len >= 2`` check
        (it requires at least two data points).  For a single data
        point, P50 and P95 are both set to that value.

        Args:
            results: List of :class:`TaskResult` objects.
            batch_duration_ms: Total batch wall-clock duration in ms.

        Returns:
            Populated :class:`AggregateMetrics`.
        """
        total = len(results)
        passed = sum(1 for r in results if r.is_pass())
        failed = sum(1 for r in results if r.outcome == "fail")
        errors = sum(1 for r in results if r.is_error())

        # Timing percentiles (only from tasks with positive wall clock)
        timings = [r.wall_clock_ms for r in results if r.wall_clock_ms > 0]
        p50: float | None = None
        p95: float | None = None
        if len(timings) >= 2:
            percentiles = statistics.quantiles(timings, n=100)
            p50 = percentiles[49]  # P50
            p95 = percentiles[94]  # P95
        elif len(timings) == 1:
            p50 = timings[0]
            p95 = timings[0]

        # Scores (only from tasks with scores)
        scores = [r.score for r in results if r.score is not None]
        mean_score = statistics.mean(scores) if scores else None

        # Error breakdown
        errors_by_type: dict[str, int] = {}
        for r in results:
            if r.error_type:
                errors_by_type[r.error_type] = (
                    errors_by_type.get(r.error_type, 0) + 1
                )

        return cls(
            total_tasks=total,
            passed=passed,
            failed=failed,
            errors=errors,
            pass_rate=passed / total if total > 0 else 0.0,
            mean_score=mean_score,
            p50_wall_clock_ms=p50,
            p95_wall_clock_ms=p95,
            total_tokens=sum(r.token_count for r in results),
            total_estimated_cost_usd=sum(r.estimated_cost_usd for r in results),
            total_batch_duration_ms=batch_duration_ms,
            errors_by_type=errors_by_type,
        )


@dataclass
class BatchResult:
    """Complete result of a batch evaluation run.

    Structured data only -- no text summary method.
    Phase 6 CLI handles formatting and display.

    Attributes:
        batch_id: Unique identifier for the batch run.
        task_results: Per-task results in execution order.
        aggregate: Computed aggregate metrics.
        config: Serialized :class:`BatchConfig` as a dictionary.
        started_at: Batch start timestamp (``time.time()``).
        ended_at: Batch end timestamp (``time.time()``).
        jsonl_path: Path to the streaming JSONL results file.
    """

    batch_id: str
    task_results: list[TaskResult]
    aggregate: AggregateMetrics
    config: dict[str, Any]
    started_at: float = 0.0
    ended_at: float = 0.0
    jsonl_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire batch result including nested types."""
        return {
            "batch_id": self.batch_id,
            "task_results": [r.to_dict() for r in self.task_results],
            "aggregate": {
                "total_tasks": self.aggregate.total_tasks,
                "passed": self.aggregate.passed,
                "failed": self.aggregate.failed,
                "errors": self.aggregate.errors,
                "pass_rate": self.aggregate.pass_rate,
                "mean_score": self.aggregate.mean_score,
                "p50_wall_clock_ms": self.aggregate.p50_wall_clock_ms,
                "p95_wall_clock_ms": self.aggregate.p95_wall_clock_ms,
                "total_tokens": self.aggregate.total_tokens,
                "total_estimated_cost_usd": self.aggregate.total_estimated_cost_usd,
                "total_batch_duration_ms": self.aggregate.total_batch_duration_ms,
                "errors_by_type": self.aggregate.errors_by_type,
            },
            "config": self.config,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "jsonl_path": self.jsonl_path,
        }

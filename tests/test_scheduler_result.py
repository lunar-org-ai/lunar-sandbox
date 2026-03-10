"""Tests for TaskResult, AggregateMetrics, and BatchResult.

Covers outcome mapping from EpisodeResult, factory classmethods,
AggregateMetrics P50/P95 edge cases, and nested serialization.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from lunar_sandbox.episode.result import EpisodeResult
from lunar_sandbox.episode.state import EpisodeOutcome
from lunar_sandbox.scheduler.result import AggregateMetrics, BatchResult, TaskResult


# ---------- TaskResult basic properties ----------


class TestTaskResultOutcome:
    """TaskResult outcome helpers."""

    def test_is_pass(self) -> None:
        r = TaskResult(task_name="t1", outcome="pass", score=1.0)
        assert r.is_pass() is True
        assert r.is_error() is False

    def test_is_error(self) -> None:
        r = TaskResult(task_name="t1", outcome="error", error_type="timeout")
        assert r.is_error() is True
        assert r.is_pass() is False

    def test_is_infra_error_sandbox_crash(self) -> None:
        r = TaskResult(task_name="t1", outcome="error", error_type="sandbox_crash")
        assert r.is_infra_error() is True

    def test_is_infra_error_timeout(self) -> None:
        r = TaskResult(task_name="t1", outcome="error", error_type="timeout")
        assert r.is_infra_error() is True

    def test_is_infra_error_pool_exhausted(self) -> None:
        r = TaskResult(task_name="t1", outcome="error", error_type="pool_exhausted")
        assert r.is_infra_error() is True

    def test_is_infra_error_infra_error(self) -> None:
        r = TaskResult(task_name="t1", outcome="error", error_type="infra_error")
        assert r.is_infra_error() is True

    def test_is_infra_error_agent_wrong_answer_false(self) -> None:
        """Agent errors are NOT infra errors (not retryable)."""
        r = TaskResult(task_name="t1", outcome="error", error_type="agent_wrong_answer")
        assert r.is_infra_error() is False

    def test_is_infra_error_agent_error_false(self) -> None:
        r = TaskResult(task_name="t1", outcome="error", error_type="agent_error")
        assert r.is_infra_error() is False


# ---------- TaskResult.to_dict ----------


class TestTaskResultToDict:
    """TaskResult.to_dict() serializes all fields."""

    def test_to_dict_all_fields(self) -> None:
        r = TaskResult(
            task_name="my-task",
            outcome="pass",
            score=0.85,
            error_type=None,
            error_message=None,
            last_agent_action="submit",
            wall_clock_ms=1234.5,
            time_to_first_action_ms=100.0,
            scoring_time_ms=50.0,
            step_count=10,
            token_count=5000,
            estimated_cost_usd=0.05,
            trajectory_path="/tmp/traj.jsonl",
            episode_id="ep-abc",
            attempt=1,
        )
        d = r.to_dict()
        assert d["task_name"] == "my-task"
        assert d["outcome"] == "pass"
        assert d["score"] == 0.85
        assert d["error_type"] is None
        assert d["error_message"] is None
        assert d["last_agent_action"] == "submit"
        assert d["wall_clock_ms"] == 1234.5
        assert d["time_to_first_action_ms"] == 100.0
        assert d["scoring_time_ms"] == 50.0
        assert d["step_count"] == 10
        assert d["token_count"] == 5000
        assert d["estimated_cost_usd"] == 0.05
        assert d["trajectory_path"] == "/tmp/traj.jsonl"
        assert d["episode_id"] == "ep-abc"
        assert d["attempt"] == 1


# ---------- TaskResult.from_episode ----------


class TestTaskResultFromEpisode:
    """TaskResult.from_episode() maps EpisodeOutcome correctly."""

    def _make_episode_result(
        self,
        outcome: EpisodeOutcome,
        score: float | None = None,
        error_message: str | None = None,
        step_count: int = 0,
    ) -> EpisodeResult:
        return EpisodeResult(
            episode_id="ep-test",
            task_name="test-task",
            outcome=outcome,
            score=score,
            step_count=step_count,
            error_message=error_message,
            jsonl_path="/tmp/test.jsonl",
        )

    def test_completed_pass(self) -> None:
        """COMPLETED + score > 0 -> outcome='pass'."""
        ep = self._make_episode_result(EpisodeOutcome.COMPLETED, score=1.0, step_count=5)
        start = time.monotonic()
        r = TaskResult.from_episode("t1", ep, start)
        assert r.outcome == "pass"
        assert r.score == 1.0
        assert r.error_type is None
        assert r.step_count == 5
        assert r.wall_clock_ms >= 0

    def test_completed_fail_score_zero(self) -> None:
        """COMPLETED + score = 0 -> outcome='fail'."""
        ep = self._make_episode_result(EpisodeOutcome.COMPLETED, score=0.0)
        r = TaskResult.from_episode("t1", ep, time.monotonic())
        assert r.outcome == "fail"
        assert r.error_type is None

    def test_completed_fail_score_none(self) -> None:
        """COMPLETED + score = None -> outcome='fail'."""
        ep = self._make_episode_result(EpisodeOutcome.COMPLETED, score=None)
        r = TaskResult.from_episode("t1", ep, time.monotonic())
        assert r.outcome == "fail"

    def test_infra_error(self) -> None:
        """INFRA_ERROR -> outcome='error', error_type='infra_error'."""
        ep = self._make_episode_result(
            EpisodeOutcome.INFRA_ERROR, error_message="sandbox crashed"
        )
        r = TaskResult.from_episode("t1", ep, time.monotonic())
        assert r.outcome == "error"
        assert r.error_type == "infra_error"
        assert r.error_message == "sandbox crashed"

    def test_timeout(self) -> None:
        """TIMEOUT -> outcome='error', error_type='timeout'."""
        ep = self._make_episode_result(
            EpisodeOutcome.TIMEOUT, error_message="timed out"
        )
        r = TaskResult.from_episode("t1", ep, time.monotonic())
        assert r.outcome == "error"
        assert r.error_type == "timeout"

    def test_agent_error(self) -> None:
        """AGENT_ERROR -> outcome='error', error_type='agent_error'."""
        ep = self._make_episode_result(
            EpisodeOutcome.AGENT_ERROR, error_message="agent crashed"
        )
        r = TaskResult.from_episode("t1", ep, time.monotonic())
        assert r.outcome == "error"
        assert r.error_type == "agent_error"

    def test_cancelled(self) -> None:
        """CANCELLED -> outcome='error', error_type='cancelled'."""
        ep = self._make_episode_result(
            EpisodeOutcome.CANCELLED, error_message="user abort"
        )
        r = TaskResult.from_episode("t1", ep, time.monotonic())
        assert r.outcome == "error"
        assert r.error_type == "cancelled"


# ---------- TaskResult factory classmethods ----------


class TestTaskResultFactories:
    """Factory classmethods for common error scenarios."""

    def test_from_timeout(self) -> None:
        start = time.monotonic()
        r = TaskResult.from_timeout("slow-task", start)
        assert r.outcome == "error"
        assert r.error_type == "timeout"
        assert r.error_message == "Task exceeded timeout"
        assert r.wall_clock_ms >= 0

    def test_from_error(self) -> None:
        exc = RuntimeError("something broke")
        start = time.monotonic()
        r = TaskResult.from_error("broken-task", exc, start)
        assert r.outcome == "error"
        assert r.error_type == "infra_error"
        assert "something broke" in r.error_message

    def test_from_error_no_start_time(self) -> None:
        """from_error with default start_time=0.0 yields 0.0 wall_clock_ms."""
        exc = RuntimeError("no timing")
        r = TaskResult.from_error("task", exc)
        assert r.wall_clock_ms == 0.0

    def test_cancelled(self) -> None:
        r = TaskResult.cancelled("cancelled-task")
        assert r.outcome == "error"
        assert r.error_type == "cancelled"
        assert "cancelled" in r.error_message.lower()
        assert r.wall_clock_ms == 0.0


# ---------- AggregateMetrics ----------


class TestAggregateMetricsFromResults:
    """AggregateMetrics.from_results() edge cases."""

    def test_multiple_results(self) -> None:
        """3+ results -> correct pass_rate, mean_score, P50/P95."""
        results = [
            TaskResult(task_name="t1", outcome="pass", score=1.0, wall_clock_ms=100.0),
            TaskResult(task_name="t2", outcome="fail", score=0.0, wall_clock_ms=200.0),
            TaskResult(task_name="t3", outcome="pass", score=0.8, wall_clock_ms=300.0),
            TaskResult(task_name="t4", outcome="error", error_type="timeout", wall_clock_ms=400.0),
        ]
        agg = AggregateMetrics.from_results(results, batch_duration_ms=500.0)

        assert agg.total_tasks == 4
        assert agg.passed == 2
        assert agg.failed == 1
        assert agg.errors == 1
        assert agg.pass_rate == 0.5  # 2/4

        # mean_score: (1.0 + 0.0 + 0.8) / 3 = 0.6
        assert agg.mean_score is not None
        assert abs(agg.mean_score - 0.6) < 0.001

        # P50 and P95 should be computed (4 data points)
        assert agg.p50_wall_clock_ms is not None
        assert agg.p95_wall_clock_ms is not None
        assert agg.p50_wall_clock_ms > 0
        assert agg.p95_wall_clock_ms >= agg.p50_wall_clock_ms

        assert agg.total_batch_duration_ms == 500.0

    def test_single_result(self) -> None:
        """1 result -> P50 and P95 both equal to the single timing value."""
        results = [
            TaskResult(task_name="t1", outcome="pass", score=1.0, wall_clock_ms=150.0),
        ]
        agg = AggregateMetrics.from_results(results, batch_duration_ms=200.0)

        assert agg.total_tasks == 1
        assert agg.passed == 1
        assert agg.pass_rate == 1.0
        assert agg.p50_wall_clock_ms == 150.0
        assert agg.p95_wall_clock_ms == 150.0

    def test_empty_results(self) -> None:
        """0 results -> all zeros/None, no crash."""
        agg = AggregateMetrics.from_results([], batch_duration_ms=0.0)

        assert agg.total_tasks == 0
        assert agg.passed == 0
        assert agg.failed == 0
        assert agg.errors == 0
        assert agg.pass_rate == 0.0
        assert agg.mean_score is None
        assert agg.p50_wall_clock_ms is None
        assert agg.p95_wall_clock_ms is None
        assert agg.total_tokens == 0
        assert agg.total_estimated_cost_usd == 0.0

    def test_error_breakdown(self) -> None:
        """Results with various error_types -> correct counts."""
        results = [
            TaskResult(task_name="t1", outcome="error", error_type="timeout"),
            TaskResult(task_name="t2", outcome="error", error_type="timeout"),
            TaskResult(task_name="t3", outcome="error", error_type="infra_error"),
            TaskResult(task_name="t4", outcome="error", error_type="agent_error"),
            TaskResult(task_name="t5", outcome="pass", score=1.0),
        ]
        agg = AggregateMetrics.from_results(results, batch_duration_ms=100.0)

        assert agg.errors_by_type == {
            "timeout": 2,
            "infra_error": 1,
            "agent_error": 1,
        }
        assert agg.errors == 4
        assert agg.passed == 1

    def test_zero_timing_excluded(self) -> None:
        """wall_clock_ms=0 excluded from percentile computation."""
        results = [
            TaskResult(task_name="t1", outcome="error", error_type="cancelled", wall_clock_ms=0.0),
            TaskResult(task_name="t2", outcome="pass", score=1.0, wall_clock_ms=200.0),
            TaskResult(task_name="t3", outcome="pass", score=1.0, wall_clock_ms=300.0),
        ]
        agg = AggregateMetrics.from_results(results, batch_duration_ms=400.0)

        # Only 2 timings (200, 300), so P50/P95 should be computed
        assert agg.p50_wall_clock_ms is not None
        assert agg.p95_wall_clock_ms is not None

    def test_token_and_cost_totals(self) -> None:
        results = [
            TaskResult(task_name="t1", outcome="pass", token_count=1000, estimated_cost_usd=0.05),
            TaskResult(task_name="t2", outcome="pass", token_count=2000, estimated_cost_usd=0.10),
        ]
        agg = AggregateMetrics.from_results(results, batch_duration_ms=100.0)

        assert agg.total_tokens == 3000
        assert abs(agg.total_estimated_cost_usd - 0.15) < 0.001


# ---------- BatchResult ----------


class TestBatchResultToDict:
    """BatchResult.to_dict() serializes nested types."""

    def test_to_dict(self) -> None:
        results = [
            TaskResult(task_name="t1", outcome="pass", score=1.0, wall_clock_ms=100.0),
            TaskResult(task_name="t2", outcome="fail", score=0.0, wall_clock_ms=200.0),
        ]
        agg = AggregateMetrics.from_results(results, batch_duration_ms=300.0)
        batch = BatchResult(
            batch_id="batch-abc123",
            task_results=results,
            aggregate=agg,
            config={"max_workers": 8},
            started_at=1000.0,
            ended_at=1001.0,
            jsonl_path="/tmp/batch.jsonl",
        )
        d = batch.to_dict()

        assert d["batch_id"] == "batch-abc123"
        assert len(d["task_results"]) == 2
        assert d["task_results"][0]["task_name"] == "t1"
        assert d["task_results"][1]["task_name"] == "t2"

        # Aggregate nested
        assert d["aggregate"]["total_tasks"] == 2
        assert d["aggregate"]["passed"] == 1
        assert d["aggregate"]["failed"] == 1
        assert d["aggregate"]["pass_rate"] == 0.5

        assert d["config"] == {"max_workers": 8}
        assert d["started_at"] == 1000.0
        assert d["ended_at"] == 1001.0
        assert d["jsonl_path"] == "/tmp/batch.jsonl"

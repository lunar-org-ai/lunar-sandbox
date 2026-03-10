"""Integration tests for EpisodeRunner + trajectory streaming + SQLite ingestion.

Tests that EpisodeRunner correctly creates JSONL files, streams trajectory steps
during execution (shell and agent modes), ingests to SQLite after completion,
and backfills reward with episode score.

Uses asyncio.run() in test bodies (no pytest-asyncio). Uses unittest.mock for
sandbox, agent adapter, and client.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from lunar_sandbox.actions.types import ActionResponse, ActionStatus
from lunar_sandbox.episode.runner import EpisodeRunner
from lunar_sandbox.episode.state import EpisodeOutcome, EpisodePhase
from lunar_sandbox.sandbox.errors import InfraError


def _make_sandbox(state_value: str = "running") -> MagicMock:
    """Create a mock sandbox with configurable state."""
    sandbox = MagicMock()
    sandbox.state = SimpleNamespace(value=state_value)
    sandbox.config = SimpleNamespace(sandbox_id="sbx-test")
    sandbox.execute = MagicMock(
        return_value={
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "cwd": "/work",
        }
    )
    sandbox.reset = MagicMock(return_value=True)
    sandbox.layers = None  # No layers -> no socket -> manual mode
    return sandbox


def _make_task(name: str = "test-task") -> SimpleNamespace:
    """Create a mock task object."""
    return SimpleNamespace(
        name=name,
        repo=None,
        setup_commands=[],
        timeout=1800,
        max_steps=200,
        test_command=None,
        scoring_script=None,
        scoring_parser=None,
    )


class TestRunnerNoTrajectory:
    """Tests for EpisodeRunner without trajectory_dir."""

    def test_runner_no_trajectory_dir(self) -> None:
        """EpisodeRunner without trajectory_dir works as before."""
        sandbox = _make_sandbox()
        task = _make_task()

        async def _run():
            runner = EpisodeRunner(sandbox, task, episode_id="ep-no-traj")
            result = await runner.run()
            return result

        result = asyncio.run(_run())
        assert result.episode_id == "ep-no-traj"
        assert result.jsonl_path == ""


class TestRunnerWithTrajectory:
    """Tests for EpisodeRunner with trajectory_dir enabled."""

    def test_runner_with_trajectory_dir_creates_jsonl(self) -> None:
        """EpisodeRunner with trajectory_dir creates JSONL file."""
        with tempfile.TemporaryDirectory() as tmp:
            traj_dir = Path(tmp) / "trajectories"
            sandbox = _make_sandbox()
            task = _make_task()

            async def _run():
                runner = EpisodeRunner(
                    sandbox, task, episode_id="ep-jsonl",
                    trajectory_dir=traj_dir,
                )
                result = await runner.run()
                return result

            result = asyncio.run(_run())
            jsonl_path = Path(result.jsonl_path)
            assert jsonl_path.exists()
            assert jsonl_path.name == "ep-jsonl.jsonl"

    def test_runner_shell_writes_trajectory_steps(self) -> None:
        """Manually set up writer + state_tracker, call execute_shell() twice,
        assert JSONL has 2 lines with action=execute_command, file_diff=null."""
        with tempfile.TemporaryDirectory() as tmp:
            traj_dir = Path(tmp) / "trajectories"
            sandbox = _make_sandbox()
            task = _make_task()

            async def _run():
                runner = EpisodeRunner(
                    sandbox, task, episode_id="ep-shell",
                    trajectory_dir=traj_dir,
                )
                # Manually open writer (run() does this, but we want manual mode)
                # We run through run() phases but use manual mode (no agent_adapter)
                # Then execute shell commands after
                result = await runner.run()
                return runner, result

            # Instead of going through full run(), let's directly test execute_shell
            # by setting up the writer manually
            async def _run_shell():
                runner = EpisodeRunner(
                    sandbox, task, episode_id="ep-shell",
                    trajectory_dir=traj_dir,
                )
                # Open writer manually (normally run() does this)
                from lunar_sandbox.trajectory import StepStateTracker, TrajectoryWriter

                runner._writer = TrajectoryWriter(traj_dir, "ep-shell")
                runner._state_tracker = StepStateTracker()
                runner._writer.open()

                # Advance state to RUNNING so execute_shell works
                from lunar_sandbox.episode.state import EpisodePhase
                runner._state.transition(EpisodePhase.ALLOCATING)
                runner._state.transition(EpisodePhase.INJECTING)
                runner._state.transition(EpisodePhase.RUNNING)

                # Execute two shell commands
                r1 = await runner.execute_shell("echo hello")
                r2 = await runner.execute_shell("echo world")

                runner._writer.close()
                return runner

            runner = asyncio.run(_run_shell())

            # Verify JSONL has 2 lines
            jsonl_path = traj_dir / "ep-shell.jsonl"
            assert jsonl_path.exists()
            lines = jsonl_path.read_text().strip().split("\n")
            assert len(lines) == 2
            for line in lines:
                parsed = json.loads(line)
                assert parsed["action"] == "execute_command"
                assert parsed["file_diff"] is None
                assert parsed["source"] == "shell"

    def test_runner_agent_mode_writes_trajectory_steps(self) -> None:
        """Mock AgentAdapter that sends actions, verify JSONL lines."""
        with tempfile.TemporaryDirectory() as tmp:
            traj_dir = Path(tmp) / "trajectories"
            sandbox = _make_sandbox()
            task = _make_task()

            # Create mock agent adapter
            call_count = 0

            async def mock_act(observation):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    return ("execute_command", {"command": f"echo {call_count}"})
                return ("submit", {})

            agent = MagicMock()
            agent.act = mock_act

            # Create mock client
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()
            mock_client.send_action = AsyncMock(
                return_value=ActionResponse(
                    status=ActionStatus.SUCCESS,
                    stdout="output",
                    cwd="/work",
                )
            )

            async def _run():
                runner = EpisodeRunner(
                    sandbox, task, episode_id="ep-agent",
                    agent_adapter=agent,
                    trajectory_dir=traj_dir,
                )
                # Inject mock client before run
                runner._client = mock_client

                # Patch lifecycle phases to advance FSM without real sandbox
                async def mock_allocate():
                    runner._state.transition(EpisodePhase.ALLOCATING)
                async def mock_inject():
                    runner._state.transition(EpisodePhase.INJECTING)
                async def mock_score():
                    if not runner._state.is_terminal():
                        runner._state.transition(EpisodePhase.SCORING)
                async def mock_reset():
                    if not runner._state.is_terminal():
                        runner._state.transition(EpisodePhase.RESETTING)

                runner._phase_allocate = mock_allocate
                runner._phase_inject = mock_inject
                runner._phase_score = mock_score
                runner._phase_reset = mock_reset

                result = await runner.run()
                return result

            result = asyncio.run(_run())

            # Verify JSONL has lines from agent actions
            jsonl_path = traj_dir / "ep-agent.jsonl"
            assert jsonl_path.exists()
            lines = jsonl_path.read_text().strip().split("\n")
            # 2 execute_command + 1 submit = 3 steps
            assert len(lines) == 3
            for line in lines:
                parsed = json.loads(line)
                assert parsed["episode_id"] == "ep-agent"

    def test_runner_result_has_jsonl_path(self) -> None:
        """jsonl_path set when trajectory active."""
        with tempfile.TemporaryDirectory() as tmp:
            traj_dir = Path(tmp) / "trajectories"
            sandbox = _make_sandbox()
            task = _make_task()

            async def _run():
                runner = EpisodeRunner(
                    sandbox, task, episode_id="ep-path",
                    trajectory_dir=traj_dir,
                )
                result = await runner.run()
                return result

            result = asyncio.run(_run())
            assert result.jsonl_path != ""
            assert "ep-path.jsonl" in result.jsonl_path

    def test_runner_result_no_jsonl_path_when_disabled(self) -> None:
        """jsonl_path empty when trajectory_dir None."""
        sandbox = _make_sandbox()
        task = _make_task()

        async def _run():
            runner = EpisodeRunner(sandbox, task, episode_id="ep-nop")
            result = await runner.run()
            return result

        result = asyncio.run(_run())
        assert result.jsonl_path == ""


class TestRunnerIngestion:
    """Tests for SQLite ingestion after episode completes."""

    def test_runner_ingests_to_sqlite_after_episode(self) -> None:
        """After run() with trajectory_dir, trajectories.db exists with data."""
        with tempfile.TemporaryDirectory() as tmp:
            traj_dir = Path(tmp) / "trajectories"
            sandbox = _make_sandbox()
            task = _make_task()

            # Create mock agent that does 2 actions then submits
            call_count = 0

            async def mock_act(observation):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    return ("execute_command", {"command": f"echo {call_count}"})
                return ("submit", {})

            agent = MagicMock()
            agent.act = mock_act

            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()
            mock_client.send_action = AsyncMock(
                return_value=ActionResponse(
                    status=ActionStatus.SUCCESS,
                    stdout="output",
                    cwd="/work",
                )
            )

            async def _run():
                runner = EpisodeRunner(
                    sandbox, task, episode_id="ep-ingest",
                    agent_adapter=agent,
                    trajectory_dir=traj_dir,
                )
                runner._client = mock_client

                async def mock_allocate():
                    runner._state.transition(EpisodePhase.ALLOCATING)
                async def mock_inject():
                    runner._state.transition(EpisodePhase.INJECTING)
                async def mock_score():
                    if not runner._state.is_terminal():
                        runner._state.transition(EpisodePhase.SCORING)
                async def mock_reset():
                    if not runner._state.is_terminal():
                        runner._state.transition(EpisodePhase.RESETTING)

                runner._phase_allocate = mock_allocate
                runner._phase_inject = mock_inject
                runner._phase_score = mock_score
                runner._phase_reset = mock_reset
                result = await runner.run()
                return result

            result = asyncio.run(_run())

            # Verify SQLite database was created
            db_path = traj_dir / "trajectories.db"
            assert db_path.exists()

            # Verify data is in the database
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            eps = conn.execute(
                "SELECT * FROM episodes WHERE episode_id = ?", ("ep-ingest",)
            ).fetchall()
            assert len(eps) == 1

            steps = conn.execute(
                "SELECT * FROM steps WHERE episode_id = ? ORDER BY step_idx",
                ("ep-ingest",),
            ).fetchall()
            assert len(steps) == 3  # 2 execute + 1 submit
            conn.close()

    def test_runner_reward_backfill(self) -> None:
        """Final step in SQLite has reward=score, earlier steps have reward=0.0."""
        with tempfile.TemporaryDirectory() as tmp:
            traj_dir = Path(tmp) / "trajectories"
            sandbox = _make_sandbox()
            task = _make_task()

            call_count = 0

            async def mock_act(observation):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    return ("execute_command", {"command": f"echo {call_count}"})
                return ("submit", {})

            agent = MagicMock()
            agent.act = mock_act

            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()
            mock_client.send_action = AsyncMock(
                return_value=ActionResponse(
                    status=ActionStatus.SUCCESS,
                    stdout="output",
                    cwd="/work",
                )
            )

            async def _run():
                runner = EpisodeRunner(
                    sandbox, task, episode_id="ep-reward",
                    agent_adapter=agent,
                    trajectory_dir=traj_dir,
                )
                runner._client = mock_client

                async def mock_allocate():
                    runner._state.transition(EpisodePhase.ALLOCATING)
                async def mock_inject():
                    runner._state.transition(EpisodePhase.INJECTING)
                async def mock_score():
                    if not runner._state.is_terminal():
                        runner._state.transition(EpisodePhase.SCORING)
                    runner._state.score = 0.85
                async def mock_reset():
                    if not runner._state.is_terminal():
                        runner._state.transition(EpisodePhase.RESETTING)

                runner._phase_allocate = mock_allocate
                runner._phase_inject = mock_inject
                runner._phase_score = mock_score
                runner._phase_reset = mock_reset
                result = await runner.run()
                return result

            result = asyncio.run(_run())
            assert result.score == 0.85

            # Verify reward backfill in SQLite
            db_path = traj_dir / "trajectories.db"
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            steps = conn.execute(
                "SELECT step_idx, reward FROM steps WHERE episode_id = ? ORDER BY step_idx",
                ("ep-reward",),
            ).fetchall()
            assert len(steps) == 3
            # Earlier steps have reward 0.0
            assert steps[0]["reward"] == 0.0
            assert steps[1]["reward"] == 0.0
            # Final step has reward = score
            assert steps[2]["reward"] == 0.85
            conn.close()

    def test_runner_incomplete_episode_ingested(self) -> None:
        """Force InfraError, verify episode ingested with is_complete=0."""
        with tempfile.TemporaryDirectory() as tmp:
            traj_dir = Path(tmp) / "trajectories"
            sandbox = _make_sandbox()
            task = _make_task()

            async def _run():
                runner = EpisodeRunner(
                    sandbox, task, episode_id="ep-fail",
                    trajectory_dir=traj_dir,
                )
                # Patch _phase_allocate to transition then raise InfraError
                async def raise_infra():
                    runner._state.transition(EpisodePhase.ALLOCATING)
                    raise InfraError("forced test failure")
                runner._phase_allocate = raise_infra
                result = await runner.run()
                return result

            result = asyncio.run(_run())
            assert result.outcome == EpisodeOutcome.INFRA_ERROR

            # Verify ingestion happened (even if no steps)
            db_path = traj_dir / "trajectories.db"
            assert db_path.exists()
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            eps = conn.execute(
                "SELECT * FROM episodes WHERE episode_id = ?", ("ep-fail",)
            ).fetchall()
            assert len(eps) == 1
            assert eps[0]["is_complete"] == 0
            conn.close()

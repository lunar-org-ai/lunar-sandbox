"""Tests for LunarEngine, agent wrapper, normalize_agent, and convenience functions.

Verifies engine instantiation, agent normalization (instances, classes,
callables), CallableAgentAdapter (sync/async), and convenience one-liners.
All subsystems are mocked to run on macOS without Linux sandbox deps.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from lunar_sandbox.agents.echo import EchoAgent
from lunar_sandbox.sdk.agent_wrapper import CallableAgentAdapter, normalize_agent
from lunar_sandbox.sdk.config import EngineConfig
from lunar_sandbox.sdk.engine import LunarEngine


# ---------- LunarEngine instantiation ----------


class TestLunarEngineInit:
    """LunarEngine can be created with default or custom config."""

    def test_default_config(self) -> None:
        engine = LunarEngine()
        assert engine._config.max_workers == 0
        assert engine._config.task_timeout == 1800.0
        assert engine._started is False

    def test_custom_config(self) -> None:
        cfg = EngineConfig(max_workers=4, task_timeout=60.0)
        engine = LunarEngine(cfg)
        assert engine._config.max_workers == 4
        assert engine._config.task_timeout == 60.0

    def test_none_config_uses_defaults(self) -> None:
        engine = LunarEngine(None)
        assert engine._config.max_workers == 0

    def test_properties_before_start(self) -> None:
        engine = LunarEngine()
        assert engine.pool is None
        assert engine.trajectory_store is None
        assert engine.batch_store is None


# ---------- normalize_agent ----------


class TestNormalizeAgent:
    """normalize_agent converts various agent forms to factory callables."""

    def test_with_callable(self) -> None:
        fn = lambda task, obs: ("submit", {})
        factory = normalize_agent(fn)
        adapter = factory("some_task")
        assert isinstance(adapter, CallableAgentAdapter)

    def test_with_class(self) -> None:
        factory = normalize_agent(EchoAgent)
        agent = factory("some_task")
        assert isinstance(agent, EchoAgent)

    def test_with_instance(self) -> None:
        instance = EchoAgent()
        factory = normalize_agent(instance)
        # Factory always returns the same instance
        result = factory("any_task")
        assert result is instance

    def test_with_non_agent_raises(self) -> None:
        try:
            normalize_agent(42)
            assert False, "Should have raised TypeError"
        except TypeError as exc:
            assert "Cannot normalize agent" in str(exc)

    def test_class_factory_creates_new_instances(self) -> None:
        factory = normalize_agent(EchoAgent)
        a1 = factory("task1")
        a2 = factory("task2")
        assert a1 is not a2


# ---------- CallableAgentAdapter ----------


class TestCallableAgentAdapter:
    """CallableAgentAdapter wraps sync/async callables as AgentAdapter."""

    def test_sync_callable(self) -> None:
        def my_agent(task: Any, obs: Any) -> tuple[str, dict]:
            return ("submit", {})

        adapter = CallableAgentAdapter(my_agent, task=None)
        result = asyncio.run(adapter.act(None))
        assert result == ("submit", {})

    def test_async_callable(self) -> None:
        async def my_async_agent(task: Any, obs: Any) -> tuple[str, dict]:
            return ("execute_command", {"command": "ls"})

        adapter = CallableAgentAdapter(my_async_agent, task=None)
        result = asyncio.run(adapter.act(None))
        assert result == ("execute_command", {"command": "ls"})

    def test_passes_task_and_observation(self) -> None:
        calls = []

        def tracking_agent(task: Any, obs: Any) -> tuple[str, dict]:
            calls.append((task, obs))
            return ("submit", {})

        adapter = CallableAgentAdapter(tracking_agent, task="my_task")
        asyncio.run(adapter.act("some_observation"))
        assert len(calls) == 1
        assert calls[0] == ("my_task", "some_observation")

    def test_lambda_callable(self) -> None:
        adapter = CallableAgentAdapter(lambda t, o: ("submit", {}), task=None)
        result = asyncio.run(adapter.act(None))
        assert result == ("submit", {})


# ---------- LunarEngine lifecycle (mocked) ----------


def _engine_patches():
    """Return context managers that patch the lazy imports in engine.start().

    Because start() does ``from lunar_sandbox.pool.pool import SandboxPool``
    inside the method body, we must patch at the source module level.
    """
    return (
        patch("lunar_sandbox.pool.pool.SandboxPool"),
        patch("lunar_sandbox.scheduler.scheduler.BatchScheduler"),
        patch("lunar_sandbox.trajectory.store.TrajectoryStore"),
        patch("lunar_sandbox.scheduler.store.BatchResultStore"),
    )


class TestLunarEngineLifecycle:
    """LunarEngine start/stop with mocked subsystems."""

    def test_start_and_stop(self) -> None:
        async def _test() -> None:
            with (
                patch("lunar_sandbox.pool.pool.SandboxPool") as MockPool,
                patch("lunar_sandbox.scheduler.scheduler.BatchScheduler"),
                patch("lunar_sandbox.trajectory.store.TrajectoryStore") as MockTrajStore,
                patch("lunar_sandbox.scheduler.store.BatchResultStore") as MockBatchStore,
            ):
                mock_pool_instance = AsyncMock()
                MockPool.return_value = mock_pool_instance

                mock_traj = MagicMock()
                MockTrajStore.return_value = mock_traj

                mock_batch_store = MagicMock()
                MockBatchStore.return_value = mock_batch_store

                engine = LunarEngine()
                await engine.start()
                assert engine._started is True
                assert engine.pool is mock_pool_instance
                mock_pool_instance.start.assert_awaited_once()

                await engine.stop()
                assert engine._started is False
                mock_pool_instance.shutdown.assert_awaited_once()
                mock_traj.close.assert_called_once()

        asyncio.run(_test())

    def test_double_start_is_noop(self) -> None:
        async def _test() -> None:
            with (
                patch("lunar_sandbox.pool.pool.SandboxPool") as MockPool,
                patch("lunar_sandbox.scheduler.scheduler.BatchScheduler"),
                patch("lunar_sandbox.trajectory.store.TrajectoryStore") as MockTrajStore,
                patch("lunar_sandbox.scheduler.store.BatchResultStore") as MockBatchStore,
            ):
                mock_pool_instance = AsyncMock()
                MockPool.return_value = mock_pool_instance
                MockTrajStore.return_value = MagicMock()
                MockBatchStore.return_value = MagicMock()

                engine = LunarEngine()
                await engine.start()
                await engine.start()  # second call is noop
                assert mock_pool_instance.start.await_count == 1

                await engine.stop()

        asyncio.run(_test())

    def test_double_stop_is_noop(self) -> None:
        async def _test() -> None:
            with (
                patch("lunar_sandbox.pool.pool.SandboxPool") as MockPool,
                patch("lunar_sandbox.scheduler.scheduler.BatchScheduler"),
                patch("lunar_sandbox.trajectory.store.TrajectoryStore") as MockTrajStore,
                patch("lunar_sandbox.scheduler.store.BatchResultStore") as MockBatchStore,
            ):
                mock_pool_instance = AsyncMock()
                MockPool.return_value = mock_pool_instance
                MockTrajStore.return_value = MagicMock()
                MockBatchStore.return_value = MagicMock()

                engine = LunarEngine()
                await engine.start()
                await engine.stop()
                await engine.stop()  # second call is noop
                assert mock_pool_instance.shutdown.await_count == 1

        asyncio.run(_test())

    def test_async_context_manager(self) -> None:
        async def _test() -> None:
            with (
                patch("lunar_sandbox.pool.pool.SandboxPool") as MockPool,
                patch("lunar_sandbox.scheduler.scheduler.BatchScheduler"),
                patch("lunar_sandbox.trajectory.store.TrajectoryStore") as MockTrajStore,
                patch("lunar_sandbox.scheduler.store.BatchResultStore") as MockBatchStore,
            ):
                mock_pool_instance = AsyncMock()
                MockPool.return_value = mock_pool_instance
                MockTrajStore.return_value = MagicMock()
                MockBatchStore.return_value = MagicMock()

                async with LunarEngine() as engine:
                    assert engine._started is True

                assert engine._started is False
                mock_pool_instance.shutdown.assert_awaited_once()

        asyncio.run(_test())


# ---------- LunarEngine.run() with mocked scheduler ----------


class TestLunarEngineRun:
    """LunarEngine.run() delegates to scheduler.run_single()."""

    def test_run_calls_scheduler(self) -> None:
        async def _test() -> None:
            mock_task_def = MagicMock()

            with (
                patch("lunar_sandbox.pool.pool.SandboxPool") as MockPool,
                patch(
                    "lunar_sandbox.scheduler.scheduler.BatchScheduler"
                ) as MockScheduler,
                patch("lunar_sandbox.trajectory.store.TrajectoryStore") as MockTrajStore,
                patch(
                    "lunar_sandbox.scheduler.store.BatchResultStore"
                ) as MockBatchStore,
                patch("lunar_sandbox.task.loader.load_task", return_value=mock_task_def),
            ):
                mock_pool_instance = AsyncMock()
                MockPool.return_value = mock_pool_instance
                MockTrajStore.return_value = MagicMock()
                MockBatchStore.return_value = MagicMock()

                mock_scheduler_instance = AsyncMock()
                mock_result = MagicMock()
                mock_scheduler_instance.run_single.return_value = mock_result
                MockScheduler.return_value = mock_scheduler_instance

                engine = LunarEngine()
                await engine.start()

                result = await engine.run("task.yaml", EchoAgent)

                assert result is mock_result
                mock_scheduler_instance.run_single.assert_awaited_once()
                # Verify the task definition was passed
                call_args = mock_scheduler_instance.run_single.call_args
                assert call_args[0][0] is mock_task_def

                await engine.stop()

        asyncio.run(_test())


# ---------- LunarEngine.eval() with mocked scheduler ----------


class TestLunarEngineEval:
    """LunarEngine.eval() delegates to scheduler.run_batch()."""

    def test_eval_calls_scheduler(self) -> None:
        async def _test() -> None:
            mock_tasks = [MagicMock(), MagicMock()]

            with (
                patch("lunar_sandbox.pool.pool.SandboxPool") as MockPool,
                patch(
                    "lunar_sandbox.scheduler.scheduler.BatchScheduler"
                ) as MockScheduler,
                patch("lunar_sandbox.trajectory.store.TrajectoryStore") as MockTrajStore,
                patch(
                    "lunar_sandbox.scheduler.store.BatchResultStore"
                ) as MockBatchStore,
                patch(
                    "lunar_sandbox.scheduler.benchmark.load_benchmark",
                    return_value=(MagicMock(name="test-bench"), mock_tasks),
                ),
            ):
                mock_pool_instance = AsyncMock()
                MockPool.return_value = mock_pool_instance
                MockTrajStore.return_value = MagicMock()
                MockBatchStore.return_value = MagicMock()

                mock_scheduler_instance = AsyncMock()
                mock_batch_result = MagicMock()
                mock_scheduler_instance.run_batch.return_value = mock_batch_result
                MockScheduler.return_value = mock_scheduler_instance

                engine = LunarEngine()
                await engine.start()

                result = await engine.eval("bench.yaml", EchoAgent)

                assert result is mock_batch_result
                mock_scheduler_instance.run_batch.assert_awaited_once()

                await engine.stop()

        asyncio.run(_test())


# ---------- Convenience functions ----------


class TestConvenienceFunctions:
    """run_task and run_batch convenience wrappers create engine and call methods."""

    def test_run_task(self) -> None:
        async def _test() -> None:
            from lunar_sandbox.sdk.convenience import run_task

            mock_result = MagicMock()

            with patch("lunar_sandbox.sdk.engine.LunarEngine") as MockEngine:
                mock_engine_instance = AsyncMock()
                mock_engine_instance.run.return_value = mock_result
                MockEngine.return_value = mock_engine_instance

                result = await run_task("task.yaml", EchoAgent)

                assert result is mock_result
                mock_engine_instance.start.assert_awaited_once()
                mock_engine_instance.run.assert_awaited_once()
                mock_engine_instance.stop.assert_awaited_once()

        asyncio.run(_test())

    def test_run_batch(self) -> None:
        async def _test() -> None:
            from lunar_sandbox.sdk.convenience import run_batch

            mock_result = MagicMock()

            with patch("lunar_sandbox.sdk.engine.LunarEngine") as MockEngine:
                mock_engine_instance = AsyncMock()
                mock_engine_instance.eval.return_value = mock_result
                MockEngine.return_value = mock_engine_instance

                result = await run_batch("bench.yaml", EchoAgent)

                assert result is mock_result
                mock_engine_instance.start.assert_awaited_once()
                mock_engine_instance.eval.assert_awaited_once()
                mock_engine_instance.stop.assert_awaited_once()

        asyncio.run(_test())

    def test_run_task_stops_on_error(self) -> None:
        """Engine.stop() is called even when run() raises."""
        async def _test() -> None:
            from lunar_sandbox.sdk.convenience import run_task

            with patch("lunar_sandbox.sdk.engine.LunarEngine") as MockEngine:
                mock_engine_instance = AsyncMock()
                mock_engine_instance.run.side_effect = RuntimeError("boom")
                MockEngine.return_value = mock_engine_instance

                try:
                    await run_task("task.yaml", EchoAgent)
                except RuntimeError:
                    pass

                mock_engine_instance.stop.assert_awaited_once()

        asyncio.run(_test())

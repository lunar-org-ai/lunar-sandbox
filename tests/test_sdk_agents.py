"""Tests for EchoAgent and RandomAgent behavior.

Verifies agent Protocol compliance, action types, step counting,
and max_steps submission behavior. All act() calls tested via asyncio.run().
"""

from __future__ import annotations

import asyncio

from lunar_sandbox.agents.echo import EchoAgent
from lunar_sandbox.agents.random_agent import RandomAgent


# ---------- EchoAgent ----------


class TestEchoAgent:
    """EchoAgent always submits immediately."""

    def test_act_returns_submit(self) -> None:
        agent = EchoAgent()
        result = asyncio.run(agent.act(None))
        assert result == ("submit", {})

    def test_act_with_observation(self) -> None:
        """act() returns submit even with a non-None observation."""
        agent = EchoAgent()
        result = asyncio.run(agent.act({"some": "observation"}))
        assert result == ("submit", {})

    def test_with_task_parameter(self) -> None:
        """Task parameter is accepted but ignored."""
        agent = EchoAgent(task="some_task")
        result = asyncio.run(agent.act(None))
        assert result == ("submit", {})

    def test_multiple_calls(self) -> None:
        """act() always returns submit regardless of call count."""
        agent = EchoAgent()
        for _ in range(5):
            result = asyncio.run(agent.act(None))
            assert result == ("submit", {})

    def test_has_act_method(self) -> None:
        """EchoAgent satisfies the AgentAdapter Protocol."""
        agent = EchoAgent()
        assert hasattr(agent, "act")
        assert callable(agent.act)


# ---------- RandomAgent ----------


class TestRandomAgent:
    """RandomAgent takes random actions then submits after max_steps."""

    def test_act_returns_valid_tuple(self) -> None:
        agent = RandomAgent(max_steps=5)
        result = asyncio.run(agent.act(None))
        assert isinstance(result, tuple)
        assert len(result) == 2
        action_type, params = result
        assert isinstance(action_type, str)
        assert isinstance(params, dict)

    def test_valid_action_types(self) -> None:
        """RandomAgent only produces known action types."""
        valid_types = {"execute_command", "read_file", "submit"}
        agent = RandomAgent(max_steps=20)
        for _ in range(25):
            action_type, _ = asyncio.run(agent.act(None))
            assert action_type in valid_types

    def test_submits_after_max_steps(self) -> None:
        """After max_steps actions, always returns submit."""
        agent = RandomAgent(max_steps=3)
        # First 3 calls are random actions
        for _ in range(3):
            action_type, _ = asyncio.run(agent.act(None))
            assert action_type in {"execute_command", "read_file"}

        # After max_steps, should always submit
        for _ in range(5):
            action_type, _ = asyncio.run(agent.act(None))
            assert action_type == "submit"

    def test_max_steps_zero(self) -> None:
        """With max_steps=0, submits immediately."""
        agent = RandomAgent(max_steps=0)
        result = asyncio.run(agent.act(None))
        assert result == ("submit", {})

    def test_execute_command_has_command_param(self) -> None:
        """execute_command actions include a 'command' parameter."""
        agent = RandomAgent(max_steps=100)
        found_command = False
        for _ in range(50):
            action_type, params = asyncio.run(agent.act(None))
            if action_type == "execute_command":
                assert "command" in params
                assert isinstance(params["command"], str)
                found_command = True
                break
        # We should find at least one execute_command in 50 tries
        assert found_command, "Expected at least one execute_command action"

    def test_read_file_has_path_param(self) -> None:
        """read_file actions include a 'path' parameter."""
        agent = RandomAgent(max_steps=100)
        found_read = False
        for _ in range(50):
            action_type, params = asyncio.run(agent.act(None))
            if action_type == "read_file":
                assert "path" in params
                assert isinstance(params["path"], str)
                found_read = True
                break
        assert found_read, "Expected at least one read_file action"

    def test_with_task_parameter(self) -> None:
        """Task parameter is accepted."""
        agent = RandomAgent(task="some_task", max_steps=1)
        result = asyncio.run(agent.act(None))
        assert isinstance(result, tuple)

    def test_has_act_method(self) -> None:
        """RandomAgent satisfies the AgentAdapter Protocol."""
        agent = RandomAgent()
        assert hasattr(agent, "act")
        assert callable(agent.act)

    def test_default_max_steps(self) -> None:
        """Default max_steps is 5."""
        agent = RandomAgent()
        assert agent._max_steps == 5

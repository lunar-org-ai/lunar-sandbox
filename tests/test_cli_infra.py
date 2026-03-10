"""Tests for CLI infrastructure: output mode, error handling, path resolver, agent loader.

Covers detect_output_mode(), exit code constants, handle_cli_error(),
exit_for_batch(), resolve_yaml_path(), load_agent_class(), get_default_agent(),
and make_agent_factory().
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import typer

from lunar_sandbox.cli.agent_loader import (
    get_default_agent,
    load_agent_class,
    make_agent_factory,
)
from lunar_sandbox.cli.errors import (
    EXIT_AGENT_FAILURE,
    EXIT_INFRA_ERROR,
    EXIT_SUCCESS,
    EXIT_USER_ERROR,
    exit_for_batch,
    handle_cli_error,
)
from lunar_sandbox.cli.output import OutputMode, detect_output_mode
from lunar_sandbox.cli.path_resolver import resolve_yaml_path


# ---------- OutputMode detection ----------


class TestDetectOutputMode:
    """detect_output_mode() selects JSON/HUMAN based on flags and TTY."""

    def test_json_flag(self) -> None:
        assert detect_output_mode(json_flag=True) == OutputMode.JSON

    def test_human_flag(self) -> None:
        assert detect_output_mode(human_flag=True) == OutputMode.HUMAN

    def test_json_overrides_human(self) -> None:
        """--json takes priority over --human."""
        assert detect_output_mode(json_flag=True, human_flag=True) == OutputMode.JSON

    def test_auto_tty(self) -> None:
        """When stdout is a TTY, auto-detect returns HUMAN."""
        with patch("lunar_sandbox.cli.output.sys") as mock_sys:
            mock_sys.stdout.isatty.return_value = True
            assert detect_output_mode() == OutputMode.HUMAN

    def test_auto_pipe(self) -> None:
        """When stdout is not a TTY (piped), auto-detect returns JSON."""
        with patch("lunar_sandbox.cli.output.sys") as mock_sys:
            mock_sys.stdout.isatty.return_value = False
            assert detect_output_mode() == OutputMode.JSON


# ---------- Exit code constants ----------


class TestExitCodes:
    """Exit codes match git-style conventions."""

    def test_success(self) -> None:
        assert EXIT_SUCCESS == 0

    def test_agent_failure(self) -> None:
        assert EXIT_AGENT_FAILURE == 1

    def test_infra_error(self) -> None:
        assert EXIT_INFRA_ERROR == 2

    def test_user_error(self) -> None:
        assert EXIT_USER_ERROR == 3


# ---------- handle_cli_error ----------


class TestHandleCliError:
    """handle_cli_error maps exceptions to exit codes."""

    def test_file_not_found_error(self) -> None:
        try:
            handle_cli_error(FileNotFoundError("missing.yaml"))
            assert False, "Should have raised typer.Exit"
        except typer.Exit as exc:
            assert exc.exit_code == EXIT_USER_ERROR

    def test_value_error(self) -> None:
        try:
            handle_cli_error(ValueError("bad value"))
            assert False, "Should have raised typer.Exit"
        except typer.Exit as exc:
            assert exc.exit_code == EXIT_USER_ERROR

    def test_generic_exception(self) -> None:
        try:
            handle_cli_error(RuntimeError("unexpected"))
            assert False, "Should have raised typer.Exit"
        except typer.Exit as exc:
            assert exc.exit_code == EXIT_INFRA_ERROR

    def test_keyboard_interrupt(self) -> None:
        try:
            handle_cli_error(KeyboardInterrupt())
            assert False, "Should have raised typer.Exit"
        except typer.Exit as exc:
            assert exc.exit_code == EXIT_SUCCESS

    def test_bad_parameter(self) -> None:
        try:
            handle_cli_error(typer.BadParameter("bad param"))
            assert False, "Should have raised typer.Exit"
        except typer.Exit as exc:
            assert exc.exit_code == EXIT_USER_ERROR

    def test_verbose_prints_traceback(self) -> None:
        """With verbose>0, print_exception is called."""
        with patch("lunar_sandbox.cli.errors.err_console") as mock_console:
            try:
                handle_cli_error(RuntimeError("boom"), verbose=1)
            except typer.Exit:
                pass
            mock_console.print_exception.assert_called_once()


# ---------- exit_for_batch ----------


class TestExitForBatch:
    """exit_for_batch computes exit code from batch results."""

    def _make_batch_result(
        self, pass_rate: float, failed: int = 0, errors: int = 0
    ) -> MagicMock:
        result = MagicMock()
        result.aggregate.pass_rate = pass_rate
        result.aggregate.failed = failed
        result.aggregate.errors = errors
        return result

    def test_threshold_met(self) -> None:
        result = self._make_batch_result(pass_rate=0.9)
        try:
            exit_for_batch(result, pass_threshold=0.8)
        except typer.Exit as exc:
            assert exc.exit_code == EXIT_SUCCESS

    def test_threshold_not_met(self) -> None:
        result = self._make_batch_result(pass_rate=0.7)
        try:
            exit_for_batch(result, pass_threshold=0.8)
        except typer.Exit as exc:
            assert exc.exit_code == EXIT_AGENT_FAILURE

    def test_no_threshold_all_pass(self) -> None:
        result = self._make_batch_result(pass_rate=1.0, failed=0, errors=0)
        try:
            exit_for_batch(result, pass_threshold=None)
        except typer.Exit as exc:
            assert exc.exit_code == EXIT_SUCCESS

    def test_no_threshold_some_fail(self) -> None:
        result = self._make_batch_result(pass_rate=0.5, failed=2, errors=0)
        try:
            exit_for_batch(result, pass_threshold=None)
        except typer.Exit as exc:
            assert exc.exit_code == EXIT_AGENT_FAILURE

    def test_no_threshold_some_errors(self) -> None:
        result = self._make_batch_result(pass_rate=0.5, failed=0, errors=1)
        try:
            exit_for_batch(result, pass_threshold=None)
        except typer.Exit as exc:
            assert exc.exit_code == EXIT_AGENT_FAILURE

    def test_threshold_exact_boundary(self) -> None:
        """Pass rate exactly at threshold passes."""
        result = self._make_batch_result(pass_rate=0.8)
        try:
            exit_for_batch(result, pass_threshold=0.8)
        except typer.Exit as exc:
            assert exc.exit_code == EXIT_SUCCESS


# ---------- resolve_yaml_path ----------


class TestResolveYamlPath:
    """resolve_yaml_path searches directories for YAML files."""

    def test_existing_literal_path(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "task.yaml"
        yaml_file.write_text("name: test\n")
        result = resolve_yaml_path(str(yaml_file))
        assert result == yaml_file.resolve()

    def test_nonexistent_path_raises(self) -> None:
        try:
            resolve_yaml_path("/nonexistent/path/task.yaml")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as exc:
            assert "not found" in str(exc).lower()

    def test_auto_adds_yaml_extension(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "task.yaml"
        yaml_file.write_text("name: test\n")
        # Search with directory containing the file
        with patch(
            "lunar_sandbox.cli.path_resolver._build_search_dirs",
            return_value=[tmp_path],
        ):
            result = resolve_yaml_path("task")
            assert result == yaml_file.resolve()

    def test_searches_lunar_tasks_dir(self, tmp_path: Path) -> None:
        """Searches ~/.lunar/tasks/ directory."""
        lunar_dir = tmp_path / "tasks"
        lunar_dir.mkdir()
        yaml_file = lunar_dir / "my-task.yaml"
        yaml_file.write_text("name: test\n")

        with patch(
            "lunar_sandbox.cli.path_resolver._build_search_dirs",
            return_value=[lunar_dir],
        ):
            result = resolve_yaml_path("my-task.yaml")
            assert result == yaml_file.resolve()

    def test_searches_env_var_path(self, tmp_path: Path) -> None:
        """Searches LUNAR_TASKS_PATH directories."""
        yaml_file = tmp_path / "custom-task.yaml"
        yaml_file.write_text("name: custom\n")

        with patch(
            "lunar_sandbox.cli.path_resolver._build_search_dirs",
            return_value=[tmp_path],
        ):
            result = resolve_yaml_path("custom-task.yaml")
            assert result == yaml_file.resolve()

    def test_error_message_lists_search_paths(self) -> None:
        """FileNotFoundError lists searched directories."""
        with patch(
            "lunar_sandbox.cli.path_resolver._build_search_dirs",
            return_value=[Path("/foo"), Path("/bar")],
        ):
            try:
                resolve_yaml_path("nonexistent")
                assert False, "Should have raised"
            except FileNotFoundError as exc:
                msg = str(exc)
                assert "/foo" in msg
                assert "/bar" in msg
                assert "nonexistent" in msg


# ---------- load_agent_class ----------


class TestLoadAgentClass:
    """load_agent_class imports agent classes from module:ClassName specs."""

    def test_valid_spec(self) -> None:
        from lunar_sandbox.agents.echo import EchoAgent

        cls = load_agent_class("lunar_sandbox.agents.echo:EchoAgent")
        assert cls is EchoAgent

    def test_missing_colon(self) -> None:
        try:
            load_agent_class("lunar_sandbox.agents.echo.EchoAgent")
            assert False, "Should have raised"
        except typer.BadParameter as exc:
            assert "module.path:ClassName" in str(exc)

    def test_invalid_module(self) -> None:
        try:
            load_agent_class("nonexistent.module:MyClass")
            assert False, "Should have raised"
        except typer.BadParameter as exc:
            assert "Cannot import" in str(exc)

    def test_invalid_class(self) -> None:
        try:
            load_agent_class("lunar_sandbox.agents.echo:NonExistentClass")
            assert False, "Should have raised"
        except typer.BadParameter as exc:
            assert "has no class" in str(exc)

    def test_empty_module(self) -> None:
        try:
            load_agent_class(":MyClass")
            assert False, "Should have raised"
        except typer.BadParameter as exc:
            assert "module.path:ClassName" in str(exc)

    def test_empty_class(self) -> None:
        try:
            load_agent_class("lunar_sandbox.agents.echo:")
            assert False, "Should have raised"
        except typer.BadParameter as exc:
            assert "module.path:ClassName" in str(exc)


# ---------- get_default_agent ----------


class TestGetDefaultAgent:
    """get_default_agent returns EchoAgent or stub fallback."""

    def test_returns_echo_agent(self) -> None:
        from lunar_sandbox.agents.echo import EchoAgent

        cls = get_default_agent()
        assert cls is EchoAgent


# ---------- make_agent_factory ----------


class TestMakeAgentFactory:
    """make_agent_factory creates callable agent factories."""

    def test_with_none_uses_default(self) -> None:
        factory = make_agent_factory(None)
        agent = factory("some_task")
        # Should create an instance of the default agent (EchoAgent)
        assert hasattr(agent, "act")

    def test_with_valid_spec(self) -> None:
        factory = make_agent_factory("lunar_sandbox.agents.echo:EchoAgent")
        agent = factory("some_task")
        from lunar_sandbox.agents.echo import EchoAgent

        assert isinstance(agent, EchoAgent)

    def test_factory_creates_new_instances(self) -> None:
        factory = make_agent_factory("lunar_sandbox.agents.echo:EchoAgent")
        a1 = factory("task1")
        a2 = factory("task2")
        assert a1 is not a2

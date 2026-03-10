"""``lunar run`` command: execute a single task evaluation.

Runs a single task through :class:`~lunar_sandbox.sdk.engine.LunarEngine`,
displaying results via Rich (TTY) or JSON (pipe).  Supports verbosity
levels, dry-run mode, and custom agent loading.

Usage::

    lunar run task.yaml
    lunar run task.yaml --agent my_module:MyAgent -v
    lunar run task.yaml --dry-run
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Optional

import structlog
import typer

from lunar_sandbox.cli.agent_loader import make_agent_factory
from lunar_sandbox.cli.errors import (
    EXIT_AGENT_FAILURE,
    EXIT_INFRA_ERROR,
    EXIT_SUCCESS,
    handle_cli_error,
)
from lunar_sandbox.cli.output import (
    OutputMode,
    console,
    detect_output_mode,
    print_json,
    render_result_table,
)
from lunar_sandbox.cli.path_resolver import resolve_yaml_path

__all__ = ["run"]


def _configure_verbosity(verbose: int) -> None:
    """Set structlog / logging level based on verbosity count.

    0 = WARNING (quiet), 1 = INFO (actions), 2 = DEBUG (full details).
    """
    level_map = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    level = level_map.get(verbose, logging.DEBUG)
    logging.basicConfig(level=level, force=True)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )


async def _run_async(
    task_path: str,
    agent_factory: object,
    workers: int,
) -> object:
    """Async helper that creates engine, runs task, and shuts down."""
    from lunar_sandbox.sdk.config import EngineConfig
    from lunar_sandbox.sdk.engine import LunarEngine

    config = EngineConfig(max_workers=workers)
    engine = LunarEngine(config)
    await engine.start()
    try:
        result = await engine.run(task_path, agent_factory)
    finally:
        await engine.stop()
    return result


def run(
    task_path: Annotated[
        str,
        typer.Argument(help="Task YAML file or name"),
    ],
    agent: Annotated[
        Optional[str],
        typer.Option("--agent", help="Agent class: module.path:ClassName"),
    ] = None,
    verbose: Annotated[
        int,
        typer.Option("-v", "--verbose", count=True, help="Verbosity (-v, -vv)"),
    ] = 0,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Force JSON output"),
    ] = False,
    human_output: Annotated[
        bool,
        typer.Option("--human", help="Force human-readable output"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate without running"),
    ] = False,
    workers: Annotated[
        Optional[int],
        typer.Option("--workers", "-w", help="Number of workers"),
    ] = None,
) -> None:
    """Run a single task evaluation."""
    try:
        _configure_verbosity(verbose)
        mode = detect_output_mode(json_output, human_output)

        # Resolve YAML path
        yaml_path = resolve_yaml_path(task_path)

        # Build agent factory
        agent_factory = make_agent_factory(agent)

        if dry_run:
            # Validate YAML and agent loading without sandbox internals
            from lunar_sandbox.task.loader import load_task

            task_def = load_task(yaml_path)
            agent_name = agent if agent else "(default)"
            if mode == OutputMode.JSON:
                print_json({
                    "dry_run": True,
                    "task_name": task_def.name or yaml_path.stem,
                    "task_path": str(yaml_path),
                    "agent": agent_name,
                    "valid": True,
                })
            else:
                console.print(
                    f"[bold green]Dry-run OK[/]\n"
                    f"  Task:  {task_def.name or yaml_path.stem}\n"
                    f"  Path:  {yaml_path}\n"
                    f"  Agent: {agent_name}"
                )
            raise typer.Exit(EXIT_SUCCESS)

        # Live run
        effective_workers = workers if workers is not None else 0

        if mode == OutputMode.HUMAN:
            with console.status("Running task..."):
                result = asyncio.run(
                    _run_async(str(yaml_path), agent_factory, effective_workers)
                )
            render_result_table(result)
        else:
            result = asyncio.run(
                _run_async(str(yaml_path), agent_factory, effective_workers)
            )
            print_json(result.to_dict())

        # Exit code based on outcome
        if result.outcome == "pass":
            raise typer.Exit(EXIT_SUCCESS)
        elif result.outcome == "error":
            raise typer.Exit(EXIT_INFRA_ERROR)
        else:
            raise typer.Exit(EXIT_AGENT_FAILURE)

    except typer.Exit:
        raise
    except Exception as exc:
        handle_cli_error(exc, verbose)

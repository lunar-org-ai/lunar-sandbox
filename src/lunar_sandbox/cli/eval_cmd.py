"""``lunar eval`` command: batch evaluation with live dashboard.

Runs a benchmark through :class:`~lunar_sandbox.sdk.engine.LunarEngine`,
displaying a Rich live dashboard (TTY) or streaming JSON (pipe).
Supports pass-threshold for CI exit codes, dry-run mode, and fail-fast.

Usage::

    lunar eval benchmark.yaml
    lunar eval benchmark.yaml --agent my_module:MyAgent --workers 4
    lunar eval benchmark.yaml --pass-threshold 0.8 --json
    lunar eval benchmark.yaml --dry-run
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Optional

import structlog
import typer

from lunar_sandbox.cli.agent_loader import make_agent_factory
from lunar_sandbox.cli.errors import (
    exit_for_batch,
    handle_cli_error,
)
from lunar_sandbox.cli.output import (
    OutputMode,
    console,
    detect_output_mode,
    print_json,
    render_batch_summary,
)
from lunar_sandbox.cli.path_resolver import resolve_yaml_path

__all__ = ["eval_batch"]


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


async def _eval_async(
    benchmark_path: str,
    agent_factory: object,
    workers: int,
    fail_fast: bool,
    mode: OutputMode,
) -> object:
    """Async helper that creates engine, runs eval, and shuts down."""
    from lunar_sandbox.sdk.config import EngineConfig
    from lunar_sandbox.sdk.engine import LunarEngine

    config = EngineConfig(max_workers=workers, fail_fast=fail_fast)
    engine = LunarEngine(config)
    await engine.start()
    try:
        if mode == OutputMode.HUMAN:
            # Count tasks for dashboard progress bar
            from lunar_sandbox.scheduler.benchmark import load_benchmark
            from pathlib import Path

            _, tasks = load_benchmark(Path(benchmark_path))
            total = len(tasks)

            from lunar_sandbox.cli.dashboard import EvalDashboard

            dashboard = EvalDashboard(total_tasks=total)
            with dashboard.live:
                result = await engine.eval(
                    benchmark_path,
                    agent_factory,
                    on_task_complete=dashboard.on_task_complete,
                )
        else:
            result = await engine.eval(benchmark_path, agent_factory)
    finally:
        await engine.stop()
    return result


def eval_batch(
    benchmark: Annotated[
        str,
        typer.Argument(help="Benchmark YAML file or name"),
    ],
    agent: Annotated[
        Optional[str],
        typer.Option("--agent", help="Agent class: module.path:ClassName"),
    ] = None,
    workers: Annotated[
        Optional[int],
        typer.Option("--workers", "-w", help="Number of workers (auto-detect if omitted)"),
    ] = None,
    pass_threshold: Annotated[
        Optional[float],
        typer.Option("--pass-threshold", help="Pass rate threshold for exit code (CI mode)"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Force JSON output"),
    ] = False,
    human_output: Annotated[
        bool,
        typer.Option("--human", help="Force human-readable output"),
    ] = False,
    verbose: Annotated[
        int,
        typer.Option("-v", "--verbose", count=True, help="Verbosity"),
    ] = 0,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate without running"),
    ] = False,
    fail_fast: Annotated[
        bool,
        typer.Option("--fail-fast", help="Stop on first failure"),
    ] = False,
) -> None:
    """Run batch evaluation from a benchmark YAML file."""
    try:
        _configure_verbosity(verbose)
        mode = detect_output_mode(json_output, human_output)

        # Resolve benchmark path
        yaml_path = resolve_yaml_path(benchmark)

        # Build agent factory
        agent_factory = make_agent_factory(agent)

        if dry_run:
            # Validate benchmark YAML and agent without sandbox internals
            from lunar_sandbox.scheduler.benchmark import load_benchmark

            bench_def, tasks = load_benchmark(yaml_path)
            agent_name = agent if agent else "(default)"
            effective_workers = workers if workers is not None else "auto"

            if mode == OutputMode.JSON:
                print_json({
                    "dry_run": True,
                    "benchmark_name": bench_def.name,
                    "benchmark_path": str(yaml_path),
                    "task_count": len(tasks),
                    "tasks": [t.name or f"task-{i}" for i, t in enumerate(tasks, 1)],
                    "agent": agent_name,
                    "workers": effective_workers,
                    "valid": True,
                })
            else:
                task_list = "\n".join(
                    f"    - {t.name or f'task-{i}'}"
                    for i, t in enumerate(tasks, 1)
                )
                console.print(
                    f"[bold green]Dry-run OK[/]\n"
                    f"  Benchmark: {bench_def.name}\n"
                    f"  Path:      {yaml_path}\n"
                    f"  Tasks:     {len(tasks)}\n"
                    f"  Agent:     {agent_name}\n"
                    f"  Workers:   {effective_workers}\n"
                    f"  Task list:\n{task_list}"
                )
            raise typer.Exit(0)

        # Live eval
        effective_workers_int = workers if workers is not None else 0

        result = asyncio.run(
            _eval_async(
                str(yaml_path),
                agent_factory,
                effective_workers_int,
                fail_fast,
                mode,
            )
        )

        # Format final output
        if mode == OutputMode.JSON:
            print_json(result.to_dict())
        else:
            render_batch_summary(result)

        # Exit code
        exit_for_batch(result, pass_threshold)

    except typer.Exit:
        raise
    except Exception as exc:
        handle_cli_error(exc, verbose)

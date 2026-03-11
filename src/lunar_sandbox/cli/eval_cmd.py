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
    EXIT_INFRA_ERROR,
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


def _render_telemetry_summary(snapshot_data: dict, thresholds: object | None = None) -> None:
    """Render compact telemetry summary table after eval run completes.

    Displays per-metric P50/P95/count rows, throughput and cache hit rate
    footer rows, and a Warnings section listing threshold breaches.
    Threshold violations are highlighted in red/yellow.
    """
    from rich.table import Table

    metrics = snapshot_data.get("metrics", {})
    if not metrics:
        return

    table = Table(title="Performance Telemetry", show_lines=False)
    table.add_column("Metric", style="bold")
    table.add_column("P50", justify="right")
    table.add_column("P95", justify="right")
    table.add_column("Count", justify="right")

    # Map metric names to display names
    display_names = {
        "allocate_latency": "Allocate Latency",
        "reset_latency": "Reset Latency",
        "time_to_first_action": "Time to First Action",
        "episode_duration": "Episode Duration",
    }

    breaches = {b["metric"]: b for b in snapshot_data.get("breaches", [])}

    for metric_key, stats in metrics.items():
        if metric_key == "cache_hit":
            continue  # Shown separately as footer row
        display = display_names.get(metric_key, metric_key)
        p50_str = f"{stats['p50']:.1f}ms" if stats["p50"] is not None else "-"
        p95_str = f"{stats['p95']:.1f}ms" if stats["p95"] is not None else "-"

        # Highlight breaches in red/yellow
        if metric_key in breaches:
            breach = breaches[metric_key]
            style = "bold red" if breach["severity"] == "critical" else "bold yellow"
            p95_str = f"[{style}]{p95_str}[/]"

        table.add_row(display, p50_str, p95_str, str(stats["count"]))

    # Add throughput and cache hit rate as footer rows
    throughput = snapshot_data.get("throughput_eps_per_min", 0.0)
    cache_hit = snapshot_data.get("cache_hit_rate", 0.0)

    table.add_row("Throughput", "-", f"{throughput:.1f} eps/min", "-", style="dim")

    cache_str = f"{cache_hit:.1%}"
    cache_breach = breaches.get("cache_hit_rate")
    if cache_breach:
        style = "bold red" if cache_breach["severity"] == "critical" else "bold yellow"
        cache_str = f"[{style}]{cache_str}[/]"
    table.add_row("Cache Hit Rate", "-", cache_str, "-", style="dim")

    console.print(table)

    # Warnings section listing all breaches
    breach_list = snapshot_data.get("breaches", [])
    if breach_list:
        console.print()
        console.print("[bold yellow]Warnings:[/]")
        for b in breach_list:
            icon = "[red]![/]" if b["severity"] == "critical" else "[yellow]![/]"
            console.print(
                f"  {icon} {b['metric']}: {b['actual']:.1f} exceeds threshold {b['threshold']:.1f}"
            )


async def _eval_async(
    benchmark_path: str,
    agent_factory: object,
    workers: int,
    fail_fast: bool,
    mode: OutputMode,
    thresholds: object | None = None,
) -> tuple[object, dict]:
    """Async helper that creates engine, runs eval, and shuts down.

    Returns:
        Tuple of ``(BatchResult, snapshot_data_dict)``.
    """
    from lunar_sandbox.sdk.config import EngineConfig
    from lunar_sandbox.sdk.engine import LunarEngine

    config = EngineConfig(
        max_workers=workers,
        fail_fast=fail_fast,
        thresholds=thresholds,
    )
    engine = LunarEngine(config)
    await engine.start()
    try:
        if mode == OutputMode.HUMAN:
            # Count tasks for dashboard progress bar
            from pathlib import Path

            from lunar_sandbox.scheduler.benchmark import load_benchmark

            _, tasks = load_benchmark(Path(benchmark_path))
            total = len(tasks)

            from lunar_sandbox.cli.dashboard import EvalDashboard

            dashboard = EvalDashboard(
                total_tasks=total,
                telemetry_collector=engine.telemetry_collector,
                pool=engine.pool,
                threshold_config=thresholds,
            )
            with dashboard.live:
                result = await engine.eval(
                    benchmark_path,
                    agent_factory,
                    on_task_complete=dashboard.on_task_complete,
                )
        else:
            result = await engine.eval(benchmark_path, agent_factory)

        # CRITICAL: flush_telemetry drains the collector AND returns the snapshot.
        # Do NOT call telemetry_snapshot() after this -- the collector is empty.
        snapshot_data = await engine.flush_telemetry(
            result.batch_id,
            result.started_at,
            result.ended_at,
            result.aggregate.total_tasks,
        )
    finally:
        await engine.stop()
    return result, snapshot_data


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
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit non-zero on threshold breach (CI mode)"),
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

        result, snapshot_data = asyncio.run(
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
            output = result.to_dict()
            output["telemetry"] = snapshot_data
            print_json(output)
        else:
            render_batch_summary(result)
            _render_telemetry_summary(snapshot_data)

        # Exit code: pass/fail results first, then --strict check
        # exit_for_batch raises typer.Exit, so catch it if strict might override
        if strict and snapshot_data.get("breaches"):
            # Still call exit_for_batch but intercept to potentially worsen the code
            try:
                exit_for_batch(result, pass_threshold)
            except typer.Exit:
                # Threshold breach always exits non-zero in strict mode
                raise typer.Exit(code=EXIT_INFRA_ERROR)
        else:
            exit_for_batch(result, pass_threshold)

    except typer.Exit:
        raise
    except Exception as exc:
        handle_cli_error(exc, verbose)

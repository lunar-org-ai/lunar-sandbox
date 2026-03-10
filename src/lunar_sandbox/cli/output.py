"""TTY-aware output mode detection and shared Rich consoles.

Provides :func:`detect_output_mode` to auto-select human (Rich) or
JSON output based on TTY detection and explicit flags.  Rich output
goes to stderr so stdout stays clean for JSON piping.

Rendering helpers format :class:`~lunar_sandbox.scheduler.result.TaskResult`
and :class:`~lunar_sandbox.scheduler.result.BatchResult` as Rich tables.
"""

from __future__ import annotations

import json
import sys
from enum import Enum
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from lunar_sandbox.scheduler.result import BatchResult, TaskResult

__all__ = [
    "OutputMode",
    "detect_output_mode",
    "console",
    "data_console",
    "print_json",
    "render_result_table",
    "render_batch_summary",
]


class OutputMode(str, Enum):
    """Output format for CLI commands."""

    HUMAN = "human"
    JSON = "json"


def detect_output_mode(
    json_flag: bool = False,
    human_flag: bool = False,
) -> OutputMode:
    """Determine output mode from flags and TTY detection.

    Priority: ``--json`` flag > ``--human`` flag > auto-detect from
    ``sys.stdout.isatty()``.

    Args:
        json_flag: True when ``--json`` was passed.
        human_flag: True when ``--human`` was passed.

    Returns:
        :attr:`OutputMode.JSON` or :attr:`OutputMode.HUMAN`.
    """
    if json_flag:
        return OutputMode.JSON
    if human_flag:
        return OutputMode.HUMAN
    return OutputMode.HUMAN if sys.stdout.isatty() else OutputMode.JSON


# Shared console instances.
# Rich output -> stderr (keeps stdout clean for JSON / piping).
console = Console(stderr=True)

# Data console -> stdout (JSON data, machine-readable output).
data_console = Console()


def print_json(data: dict | list) -> None:
    """Write JSON data to stdout with pretty formatting.

    Uses ``default=str`` so non-serializable values (Path, datetime)
    are coerced to strings rather than raising.

    Args:
        data: Dictionary or list to serialize.
    """
    sys.stdout.write(json.dumps(data, indent=2, default=str) + "\n")


def render_result_table(task_result: TaskResult, out: Console | None = None) -> None:
    """Render a single task result as a Rich Panel.

    Displays task name, outcome badge, score, steps, and timing.

    Args:
        task_result: The task result to render.
        out: Console to write to (defaults to stderr console).
    """
    out = out or console

    outcome_text = _outcome_badge(task_result.outcome)

    score_str = (
        f"{task_result.score:.2f}" if task_result.score is not None else "-"
    )
    time_str = f"{task_result.wall_clock_ms / 1000:.1f}s"

    content = Text()
    content.append("Outcome: ")
    content.append_text(outcome_text)
    content.append(f"\nScore:   {score_str}")
    content.append(f"\nSteps:   {task_result.step_count}")
    content.append(f"\nTime:    {time_str}")

    if task_result.error_message:
        content.append(f"\nError:   {task_result.error_message}")

    panel = Panel(
        content,
        title=task_result.task_name,
        border_style="dim",
    )
    out.print(panel)


def render_batch_summary(batch_result: BatchResult, out: Console | None = None) -> None:
    """Render a pytest-style scorecard table for batch results.

    Columns: Task, Result (colored badge), Score, Steps, Time.
    Footer row with pass rate, mean score, and P50 timing.

    Args:
        batch_result: The complete batch result to render.
        out: Console to write to (defaults to stderr console).
    """
    out = out or console

    table = Table(title="Evaluation Results", show_lines=True)
    table.add_column("Task", style="bold")
    table.add_column("Result", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Steps", justify="right")
    table.add_column("Time", justify="right")

    for result in batch_result.task_results:
        outcome_text = _outcome_badge(result.outcome)
        score_str = (
            f"{result.score:.2f}" if result.score is not None else "-"
        )
        time_str = f"{result.wall_clock_ms / 1000:.1f}s"

        table.add_row(
            result.task_name,
            outcome_text,
            score_str,
            str(result.step_count),
            time_str,
        )

    # Aggregate footer
    agg = batch_result.aggregate
    pass_rate_str = f"{agg.pass_rate:.0%}"
    mean_score_str = (
        f"{agg.mean_score:.2f}" if agg.mean_score is not None else "-"
    )
    p50_str = (
        f"{agg.p50_wall_clock_ms / 1000:.1f}s"
        if agg.p50_wall_clock_ms is not None
        else "-"
    )

    table.add_row(
        Text("TOTAL", style="bold"),
        Text(pass_rate_str, style="bold"),
        mean_score_str,
        str(agg.total_tasks),
        p50_str,
        style="dim",
    )

    out.print(table)


def _outcome_badge(outcome: str) -> Text:
    """Return a colored Rich Text badge for an outcome string."""
    if outcome == "pass":
        return Text("PASS", style="bold green")
    elif outcome == "fail":
        return Text("FAIL", style="bold red")
    else:
        return Text("ERROR", style="bold yellow")

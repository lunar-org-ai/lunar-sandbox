"""Rich Live dashboard for ``lunar eval`` batch evaluation.

Provides :class:`EvalDashboard` -- a real-time terminal display showing
progress bar, pass/fail/error counters, and a scrolling table of recent
task results.  The dashboard renders to stderr via the shared Rich console.

The :meth:`on_task_complete` callback is designed to be lightweight so it
can run inside the asyncio event loop without blocking.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from lunar_sandbox.cli.output import console

if TYPE_CHECKING:
    from lunar_sandbox.scheduler.result import TaskResult

__all__ = ["EvalDashboard"]


class EvalDashboard:
    """Real-time Rich Live dashboard for batch evaluation.

    Displays a status panel with pass/fail/error counts, a progress bar,
    and a scrolling table of recent results.  Designed to be used as a
    context manager via ``with dashboard.live:``.

    Args:
        total_tasks: Total number of tasks in the evaluation batch.
    """

    def __init__(self, total_tasks: int) -> None:
        self.total_tasks = total_tasks

        # Counters
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.completed = 0

        # Recent results for scrolling table (bounded)
        self.results: deque[dict[str, str]] = deque(maxlen=30)

        # Progress bar
        self.progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        )
        self.task_id = self.progress.add_task(
            "Evaluating", total=total_tasks
        )

        # Live display
        self.live = Live(
            self._render(),
            refresh_per_second=4,
            console=console,
        )

    def _render(self) -> Group:
        """Build the composite dashboard renderable.

        Returns a :class:`Group` containing the status panel, progress
        bar, and recent results table.
        """
        # Status panel
        remaining = self.total_tasks - self.completed
        status_text = Text()
        status_text.append("Pass: ", style="bold")
        status_text.append(f"{self.passed}", style="bold green")
        status_text.append("  Fail: ", style="bold")
        status_text.append(f"{self.failed}", style="bold red")
        status_text.append("  Error: ", style="bold")
        status_text.append(f"{self.errors}", style="bold yellow")
        status_text.append(f"  Remaining: {remaining}")

        panel = Panel(status_text, title="Evaluation Status", border_style="blue")

        # Recent results table
        table = Table(title="Recent Results", show_lines=False, expand=True)
        table.add_column("Task", style="cyan", ratio=3)
        table.add_column("Result", justify="center", ratio=1)
        table.add_column("Score", justify="right", ratio=1)
        table.add_column("Time", justify="right", ratio=1)

        for entry in self.results:
            table.add_row(
                entry["name"],
                entry["badge"],
                entry["score"],
                entry["time"],
            )

        return Group(panel, self.progress, table)

    def on_task_complete(self, result: TaskResult) -> None:
        """Callback invoked after each task finishes.

        This runs inside the asyncio event loop, so it must be
        lightweight: update counters, append to deque, refresh display.

        Args:
            result: The completed task result.
        """
        self.completed += 1

        if result.outcome == "pass":
            self.passed += 1
        elif result.outcome == "fail":
            self.failed += 1
        else:
            self.errors += 1

        # Update progress bar
        self.progress.update(self.task_id, completed=self.completed)

        # Build result entry for table
        badge = _outcome_badge(result.outcome)
        score_str = (
            f"{result.score:.2f}" if result.score is not None else "-"
        )
        time_str = f"{result.wall_clock_ms / 1000:.1f}s"

        self.results.append({
            "name": result.task_name,
            "badge": badge,
            "score": score_str,
            "time": time_str,
        })

        # Refresh the live display
        self.live.update(self._render())


def _outcome_badge(outcome: str) -> str:
    """Return a Rich markup string for an outcome badge."""
    if outcome == "pass":
        return "[bold green]PASS[/]"
    elif outcome == "fail":
        return "[bold red]FAIL[/]"
    else:
        return "[bold yellow]ERROR[/]"

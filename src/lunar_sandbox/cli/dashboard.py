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
    and a scrolling table of recent results.  Optionally displays live
    telemetry headline metrics (avg latency, throughput, cache hit %,
    active sandboxes) when a :class:`TelemetryCollector` is provided.

    Args:
        total_tasks: Total number of tasks in the evaluation batch.
        telemetry_collector: Optional collector for live metrics display.
        pool: Optional pool reference for active sandbox count.
        threshold_config: Optional thresholds for live breach highlighting.
    """

    def __init__(
        self,
        total_tasks: int,
        telemetry_collector: object | None = None,
        pool: object | None = None,
        threshold_config: object | None = None,
    ) -> None:
        self.total_tasks = total_tasks
        self.telemetry_collector = telemetry_collector
        self.pool = pool
        self.threshold_config = threshold_config

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

        # Telemetry metrics row (3-4 headline numbers)
        metrics_text = self._build_metrics_text()
        if metrics_text is not None:
            return Group(panel, metrics_text, self.progress, table)
        return Group(panel, self.progress, table)

    def _build_metrics_text(self) -> Text | None:
        """Build a single-line metrics bar with live telemetry numbers.

        Shows avg latency, throughput eps/min, cache hit %, active sandboxes.
        Threshold violations are highlighted in red/yellow.
        """
        if self.telemetry_collector is None:
            return None

        samples = self.telemetry_collector.snapshot()
        if not samples:
            return None

        # Compute running averages (not percentiles -- too expensive for live refresh)
        alloc_values = [s.value for s in samples if s.metric == "allocate_latency"]
        cache_values = [s.value for s in samples if s.metric == "cache_hit"]
        episode_values = [s.value for s in samples if s.metric == "episode_duration"]

        avg_alloc = sum(alloc_values) / len(alloc_values) if alloc_values else 0.0
        cache_hit_pct = (sum(cache_values) / len(cache_values) * 100) if cache_values else 0.0

        # Throughput: episodes / elapsed minutes
        if episode_values and len(episode_values) >= 2:
            timestamps = [s.timestamp for s in samples if s.metric == "episode_duration"]
            elapsed_min = (max(timestamps) - min(timestamps)) / 60 if len(timestamps) >= 2 else 0.0
            throughput = len(episode_values) / elapsed_min if elapsed_min > 0 else 0.0
        else:
            throughput = 0.0

        # Active sandboxes from pool reference
        active_sandboxes = 0
        if self.pool is not None:
            try:
                active_sandboxes = self.pool.metrics.active_count
            except (AttributeError, Exception):
                active_sandboxes = 0

        # Determine threshold breaches for live highlighting
        latency_breach_style = None
        cache_breach_style = None
        if self.threshold_config is not None:
            # Check allocate latency P95 approximation
            if getattr(self.threshold_config, "allocate_p95_ms", None) is not None and alloc_values:
                sorted_alloc = sorted(alloc_values)
                approx_p95 = sorted_alloc[int(len(sorted_alloc) * 0.95)] if len(sorted_alloc) >= 20 else max(sorted_alloc)
                if approx_p95 > self.threshold_config.allocate_p95_ms * 1.5:
                    latency_breach_style = "bold red"
                elif approx_p95 > self.threshold_config.allocate_p95_ms:
                    latency_breach_style = "bold yellow"

            # Check cache hit rate minimum
            if getattr(self.threshold_config, "cache_hit_rate_min", None) is not None and cache_values:
                cache_rate = sum(cache_values) / len(cache_values)
                if cache_rate < self.threshold_config.cache_hit_rate_min * 0.67:
                    cache_breach_style = "bold red"
                elif cache_rate < self.threshold_config.cache_hit_rate_min:
                    cache_breach_style = "bold yellow"

        text = Text()
        text.append("  Avg Latency: ", style="dim")
        text.append(f"{avg_alloc:.0f}ms", style=latency_breach_style or "bold")
        text.append("  |  Throughput: ", style="dim")
        text.append(f"{throughput:.1f} eps/min", style="bold")
        text.append("  |  Cache Hit: ", style="dim")
        text.append(f"{cache_hit_pct:.0f}%", style=cache_breach_style or "bold")
        text.append("  |  Sandboxes: ", style="dim")
        text.append(f"{active_sandboxes}", style="bold")

        return text

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

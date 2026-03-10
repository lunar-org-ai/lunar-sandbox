"""``lunar replay`` command for trajectory playback.

Provides formatted summary and interactive step-through modes for
inspecting past evaluation runs.  Reads trajectory data directly from
the SQLite store, supporting both human-readable (Rich) and JSON output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

from typing_extensions import Annotated

import typer

from lunar_sandbox.cli.errors import EXIT_USER_ERROR, handle_cli_error
from lunar_sandbox.cli.output import (
    OutputMode,
    console,
    detect_output_mode,
    print_json,
)

__all__ = ["replay"]

# Default trajectory database location
_DEFAULT_DB = "trajectories/trajectories.db"


def replay(
    episode_id: Annotated[
        str,
        typer.Argument(help="Episode ID to replay (e.g., run_001)"),
    ],
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive", "-i", help="Step-through playback with navigation"
        ),
    ] = False,
    step: Annotated[
        bool,
        typer.Option(
            "--step", "-s", help="Step-through playback (alias for --interactive)"
        ),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Force JSON output")
    ] = False,
    human_output: Annotated[
        bool, typer.Option("--human", help="Force human-readable output")
    ] = False,
    db_path: Annotated[
        Optional[str],
        typer.Option("--db", help="Path to trajectory database"),
    ] = None,
) -> None:
    """Replay a past evaluation episode.

    Shows trajectory summary (default) or interactive step-through
    playback (--interactive / --step).
    """
    try:
        _replay_impl(
            episode_id=episode_id,
            interactive=interactive or step,
            json_output=json_output,
            human_output=human_output,
            db_path=db_path,
        )
    except Exception as exc:
        handle_cli_error(exc)


def _replay_impl(
    *,
    episode_id: str,
    interactive: bool,
    json_output: bool,
    human_output: bool,
    db_path: str | None,
) -> None:
    """Core replay logic, separated for testability."""
    from lunar_sandbox.trajectory.store import TrajectoryStore

    # Resolve database path
    resolved_db = Path(db_path) if db_path else Path(_DEFAULT_DB)
    if not resolved_db.exists():
        raise FileNotFoundError(
            f"Trajectory database not found: {resolved_db}\n"
            f"Default location: {_DEFAULT_DB}"
        )

    mode = detect_output_mode(json_flag=json_output, human_flag=human_output)

    with TrajectoryStore(resolved_db) as store:
        episodes = store.query_episodes(episode_id=episode_id)
        steps = store.query_steps([episode_id])

    if not episodes:
        if mode == OutputMode.JSON:
            print_json({"error": f"Episode not found: {episode_id}"})
        else:
            console.print(
                f"[bold red]Error:[/] Episode not found: [bold]{episode_id}[/]"
            )
            console.print(
                "[dim]Hint: check the episode ID or use a different --db path[/]"
            )
        raise typer.Exit(code=EXIT_USER_ERROR)

    episode = episodes[0]

    if mode == OutputMode.JSON:
        _render_json(episode, steps)
    elif interactive:
        _render_interactive(episode, steps)
    else:
        _render_summary(episode, steps)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


def _render_json(episode: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    """Emit episode and steps as JSON to stdout."""
    print_json({"episode": episode, "steps": steps})


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------


def _render_summary(
    episode: dict[str, Any], steps: list[dict[str, Any]]
) -> None:
    """Render a formatted Rich summary panel and steps table."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    # -- Header panel -------------------------------------------------------
    outcome_text = _outcome_badge(episode.get("outcome", "unknown"))
    score_str = (
        f"{episode['score']:.2f}"
        if episode.get("score") is not None
        else "-"
    )
    duration_ms = episode.get("duration_ms", 0.0)
    duration_str = f"{duration_ms / 1000:.1f}s" if duration_ms else "-"
    step_count = episode.get("step_count", len(steps))

    header = Text()
    header.append("Episode:   ")
    header.append(episode.get("episode_id", ""), style="bold")
    header.append("\nTask:      ")
    header.append(episode.get("task_name", ""), style="bold cyan")
    header.append("\nOutcome:   ")
    header.append_text(outcome_text)
    header.append(f"\nScore:     {score_str}")
    header.append(f"\nDuration:  {duration_str}")
    header.append(f"\nSteps:     {step_count}")

    console.print(Panel(header, title="Episode Summary", border_style="blue"))

    # -- Steps table --------------------------------------------------------
    if not steps:
        console.print("[dim]No trajectory data found for this episode.[/]")
        return

    table = Table(title="Trajectory Steps", show_lines=True)
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("Action", style="bold")
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Observation", max_width=80)

    for s in steps:
        step_num = str(s.get("step_idx", ""))
        action = s.get("action", "")
        dur_ms = s.get("duration_ms", 0.0)
        dur_str = f"{dur_ms:.0f}ms" if dur_ms else "-"
        obs = s.get("observation", {})
        obs_str = _truncate(
            json.dumps(obs, default=str) if isinstance(obs, dict) else str(obs),
            80,
        )

        table.add_row(step_num, action, dur_str, obs_str)

    console.print(table)


# ---------------------------------------------------------------------------
# Interactive step-through playback
# ---------------------------------------------------------------------------


def _render_interactive(
    episode: dict[str, Any], steps: list[dict[str, Any]]
) -> None:
    """Step-through terminal playback with navigation."""
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text

    if not steps:
        console.print("[dim]No trajectory data found for this episode.[/]")
        return

    total = len(steps)
    idx = 0

    while 0 <= idx < total:
        s = steps[idx]
        _render_step_panel(s, idx, total)

        # Navigation prompt
        if idx == total - 1:
            prompt = "[dim]Enter=summary, p=prev, q=quit[/]"
        elif idx == 0:
            prompt = "[dim]Enter=next, q=quit[/]"
        else:
            prompt = "[dim]Enter=next, p=prev, q=quit[/]"

        console.print(prompt)

        try:
            user_input = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return

        if user_input == "q":
            return
        elif user_input == "p":
            idx = max(0, idx - 1)
        else:
            idx += 1

    # Show episode summary at the end
    _render_summary(episode, steps)


def _render_step_panel(
    step: dict[str, Any], idx: int, total: int
) -> None:
    """Render a single step as a Rich panel."""
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text

    content = Text()

    # Step info
    content.append(f"Step {idx + 1}/{total}", style="bold")
    content.append(f"\nAction: ", style="dim")
    content.append(step.get("action", ""), style="bold cyan")

    # Duration
    dur_ms = step.get("duration_ms", 0.0)
    if dur_ms:
        content.append(f"\nDuration: {dur_ms:.0f}ms", style="dim")

    console.print(Panel(content, border_style="blue"))

    # Action params (syntax highlighted)
    params = step.get("action_params", {})
    if params:
        params_str = json.dumps(params, indent=2, default=str)
        try:
            syntax = Syntax(params_str, "json", theme="monokai", line_numbers=False)
            console.print(Panel(syntax, title="Action Params", border_style="dim"))
        except Exception:
            console.print(Panel(params_str, title="Action Params", border_style="dim"))

    # Observation (full)
    obs = step.get("observation", {})
    if obs:
        obs_str = (
            json.dumps(obs, indent=2, default=str)
            if isinstance(obs, dict)
            else str(obs)
        )
        console.print(Panel(obs_str, title="Observation", border_style="green"))

    # File diff if any
    file_diff = step.get("file_diff")
    if file_diff:
        diff_str = (
            json.dumps(file_diff, indent=2, default=str)
            if isinstance(file_diff, dict)
            else str(file_diff)
        )
        try:
            syntax = Syntax(diff_str, "diff", theme="monokai", line_numbers=False)
            console.print(Panel(syntax, title="File Diff", border_style="yellow"))
        except Exception:
            console.print(Panel(diff_str, title="File Diff", border_style="yellow"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outcome_badge(outcome: str) -> "Text":
    """Return a colored Rich Text badge for an outcome string."""
    from rich.text import Text

    if outcome == "pass":
        return Text("PASS", style="bold green")
    elif outcome == "fail":
        return Text("FAIL", style="bold red")
    else:
        return Text(outcome.upper(), style="bold yellow")


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."

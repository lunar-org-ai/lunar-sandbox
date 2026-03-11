"""``lunar telemetry`` subcommands for viewing performance telemetry.

Provides ``show``, ``compare``, ``export``, and ``clear`` subcommands
for querying, comparing, and exporting telemetry data from past evaluation
runs.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from typing_extensions import Annotated

import typer

from lunar_sandbox.cli.errors import (
    EXIT_USER_ERROR,
    handle_cli_error,
)
from lunar_sandbox.cli.output import (
    OutputMode,
    console,
    detect_output_mode,
    print_json,
)

__all__ = ["app"]

app = typer.Typer(help="View and manage performance telemetry")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_default_db_path() -> Path:
    """Derive the default trajectories.db path."""
    return Path("trajectories") / "trajectories.db"


def _samples_from_dicts(rows: list[dict]) -> list:
    """Convert store query results back to MetricSample objects."""
    from lunar_sandbox.telemetry.types import MetricSample

    return [
        MetricSample(
            metric=r["metric"],
            value=r["value"],
            fingerprint=r.get("fingerprint", ""),
            timestamp=r.get("timestamp", 0.0),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# lunar telemetry show
# ---------------------------------------------------------------------------


@app.command()
def show(
    run_id: Annotated[
        Optional[str],
        typer.Argument(help="Run ID (latest if omitted)"),
    ] = None,
    by_fingerprint: Annotated[
        bool,
        typer.Option("--by-fingerprint", help="Show per-fingerprint breakdown"),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Force JSON output")
    ] = False,
    human_output: Annotated[
        bool, typer.Option("--human", help="Force human-readable output")
    ] = False,
) -> None:
    """Show telemetry data for a run.

    Displays the most recent run if RUN_ID is omitted.
    Use --by-fingerprint for per-environment drill-down.
    """
    try:
        _show_impl(
            run_id=run_id,
            by_fingerprint=by_fingerprint,
            json_output=json_output,
            human_output=human_output,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        handle_cli_error(exc)


def _show_impl(
    *,
    run_id: str | None,
    by_fingerprint: bool,
    json_output: bool,
    human_output: bool,
) -> None:
    """Core show logic."""
    from lunar_sandbox.telemetry.compute import (
        compute_snapshot,
        compute_snapshot_by_fingerprint,
    )
    from lunar_sandbox.telemetry.store import TelemetryStore

    mode = detect_output_mode(json_flag=json_output, human_flag=human_output)
    db_path = _get_default_db_path()

    if not db_path.exists():
        _no_data(mode)
        return

    store = TelemetryStore(db_path)
    store.open()
    try:
        # Resolve run_id
        if run_id is None:
            runs = store.query_runs(limit=1)
            if not runs:
                _no_data(mode)
                return
            run_info = runs[0]
            run_id = run_info["run_id"]
        else:
            run_info = store.get_run(run_id)
            if run_info is None:
                if mode == OutputMode.JSON:
                    print_json({"error": f"Run '{run_id}' not found"})
                else:
                    console.print(f"[bold red]Error:[/] Run '{run_id}' not found")
                raise typer.Exit(code=EXIT_USER_ERROR)

        # Fetch samples
        sample_dicts = store.query_samples(run_id)
        if not sample_dicts:
            if mode == OutputMode.JSON:
                print_json({"run_id": run_id, "message": "No samples for this run"})
            else:
                console.print(f"[dim]No samples found for run {run_id}[/]")
            return

        samples = _samples_from_dicts(sample_dicts)
        duration = run_info.get("duration_seconds", 0.0) or 0.0

        if by_fingerprint:
            fp_snapshots = compute_snapshot_by_fingerprint(
                samples, run_id, duration
            )
            if mode == OutputMode.JSON:
                result = {}
                for fp, snap in fp_snapshots.items():
                    result[fp] = _snapshot_to_dict(snap)
                print_json({"run_id": run_id, "fingerprints": result})
            else:
                console.print(
                    f"\n[bold]Telemetry[/] run [cyan]{run_id}[/] (by fingerprint)\n"
                )
                for fp, snap in sorted(fp_snapshots.items()):
                    console.print(f"  [bold]Fingerprint:[/] {fp}")
                    _render_snapshot_table(snap)
                    console.print()
        else:
            snapshot = compute_snapshot(samples, run_id, duration)
            if mode == OutputMode.JSON:
                print_json(_snapshot_to_dict(snapshot))
            else:
                console.print(
                    f"\n[bold]Telemetry[/] run [cyan]{run_id}[/]"
                    f" ({run_info.get('total_episodes', 0)} episodes,"
                    f" {duration:.1f}s)\n"
                )
                _render_snapshot_table(snapshot)
    finally:
        store.close()


def _no_data(mode: OutputMode) -> None:
    """Print a 'no data' message in the appropriate mode."""
    msg = "No telemetry data. Run `lunar eval` to generate telemetry."
    if mode == OutputMode.JSON:
        print_json({"message": msg})
    else:
        console.print(f"[dim]{msg}[/]")


def _snapshot_to_dict(snapshot) -> dict:
    """Convert a TelemetrySnapshot to a JSON-friendly dict."""
    metrics_dict = {}
    for name, stats in snapshot.metrics.items():
        metrics_dict[name] = asdict(stats)
    return {
        "run_id": snapshot.run_id,
        "throughput_eps_per_min": snapshot.throughput_eps_per_min,
        "cache_hit_rate": snapshot.cache_hit_rate,
        "total_episodes": snapshot.total_episodes,
        "duration_seconds": snapshot.duration_seconds,
        "metrics": metrics_dict,
    }


def _render_snapshot_table(snapshot) -> None:
    """Render a TelemetrySnapshot as a Rich table to stderr."""
    from rich.table import Table

    table = Table(show_lines=False)
    table.add_column("Metric", style="bold")
    table.add_column("P50", justify="right")
    table.add_column("P95", justify="right")
    table.add_column("Mean", justify="right")
    table.add_column("Count", justify="right")

    for name, stats in sorted(snapshot.metrics.items()):
        p50_str = f"{stats.p50:.1f}" if stats.p50 is not None else "-"
        p95_str = f"{stats.p95:.1f}" if stats.p95 is not None else "-"
        table.add_row(
            name,
            p50_str,
            p95_str,
            f"{stats.mean:.1f}",
            str(stats.count),
        )

    # Special summary rows
    table.add_row(
        "throughput (eps/min)",
        f"{snapshot.throughput_eps_per_min:.2f}",
        "",
        "",
        "",
        style="dim",
    )
    table.add_row(
        "cache_hit_rate",
        f"{snapshot.cache_hit_rate:.1%}",
        "",
        "",
        "",
        style="dim",
    )
    console.print(table)


# ---------------------------------------------------------------------------
# lunar telemetry compare
# ---------------------------------------------------------------------------


@app.command()
def compare(
    run_a: Annotated[
        str,
        typer.Argument(help="First run ID (baseline)"),
    ],
    run_b: Annotated[
        str,
        typer.Argument(help="Second run ID (comparison)"),
    ],
    json_output: Annotated[
        bool, typer.Option("--json", help="Force JSON output")
    ] = False,
    human_output: Annotated[
        bool, typer.Option("--human", help="Force human-readable output")
    ] = False,
) -> None:
    """Compare telemetry between two runs.

    Shows side-by-side P50/P95 values with deltas and % change.
    Green = improvement, red = regression.
    """
    try:
        _compare_impl(
            run_a=run_a,
            run_b=run_b,
            json_output=json_output,
            human_output=human_output,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        handle_cli_error(exc)


def _compare_impl(
    *,
    run_a: str,
    run_b: str,
    json_output: bool,
    human_output: bool,
) -> None:
    """Core compare logic."""
    from lunar_sandbox.telemetry.compute import compare_runs, compute_snapshot
    from lunar_sandbox.telemetry.store import TelemetryStore

    mode = detect_output_mode(json_flag=json_output, human_flag=human_output)
    db_path = _get_default_db_path()

    if not db_path.exists():
        _no_data(mode)
        return

    store = TelemetryStore(db_path)
    store.open()
    try:
        # Validate both runs exist
        info_a = store.get_run(run_a)
        info_b = store.get_run(run_b)
        if info_a is None:
            msg = f"Run '{run_a}' not found"
            if mode == OutputMode.JSON:
                print_json({"error": msg})
            else:
                console.print(f"[bold red]Error:[/] {msg}")
            raise typer.Exit(code=EXIT_USER_ERROR)
        if info_b is None:
            msg = f"Run '{run_b}' not found"
            if mode == OutputMode.JSON:
                print_json({"error": msg})
            else:
                console.print(f"[bold red]Error:[/] {msg}")
            raise typer.Exit(code=EXIT_USER_ERROR)

        # Build snapshots
        samples_a = _samples_from_dicts(store.query_samples(run_a))
        samples_b = _samples_from_dicts(store.query_samples(run_b))

        dur_a = info_a.get("duration_seconds", 0.0) or 0.0
        dur_b = info_b.get("duration_seconds", 0.0) or 0.0

        snap_a = compute_snapshot(samples_a, run_a, dur_a)
        snap_b = compute_snapshot(samples_b, run_b, dur_b)

        comparisons = compare_runs(snap_a, snap_b)

        if mode == OutputMode.JSON:
            print_json({"run_a": run_a, "run_b": run_b, "comparisons": comparisons})
        else:
            _render_comparison_table(run_a, run_b, comparisons)
    finally:
        store.close()


# Metrics where higher is better (deltas inverted for color)
_HIGHER_IS_BETTER = {"cache_hit_rate", "throughput_eps_per_min"}


def _render_comparison_table(
    run_a: str, run_b: str, comparisons: list[dict]
) -> None:
    """Render a comparison table with colored deltas."""
    from rich.table import Table
    from rich.text import Text

    console.print(
        f"\n[bold]Compare[/] [cyan]{run_a}[/] vs [cyan]{run_b}[/]\n"
    )

    table = Table(show_lines=True)
    table.add_column("Metric", style="bold")
    table.add_column("A P50", justify="right")
    table.add_column("A P95", justify="right")
    table.add_column("B P50", justify="right")
    table.add_column("B P95", justify="right")
    table.add_column("Delta P95", justify="right")
    table.add_column("% Change", justify="right")

    for row in comparisons:
        metric = row["metric"]
        a_p50 = _fmt_val(row.get("a_p50"))
        a_p95 = _fmt_val(row.get("a_p95"))
        b_p50 = _fmt_val(row.get("b_p50"))
        b_p95 = _fmt_val(row.get("b_p95"))

        delta = row.get("delta_p95")
        pct = row.get("pct_change_p95")

        # For special rows without P95, use P50 delta
        if delta is None:
            delta = row.get("delta_p50")
            pct = row.get("pct_change_p50")

        delta_text = _colored_delta(delta, metric)
        pct_text = _colored_pct(pct, metric)

        table.add_row(metric, a_p50, a_p95, b_p50, b_p95, delta_text, pct_text)

    console.print(table)


def _fmt_val(v: float | None) -> str:
    """Format a numeric value for table display."""
    if v is None:
        return "-"
    return f"{v:.2f}"


def _colored_delta(delta: float | None, metric: str) -> Text:
    """Return a Rich Text with green/red coloring for the delta."""
    from rich.text import Text

    if delta is None:
        return Text("-")
    higher_is_better = metric in _HIGHER_IS_BETTER
    if delta > 0:
        style = "green" if higher_is_better else "red"
    elif delta < 0:
        style = "red" if higher_is_better else "green"
    else:
        style = "dim"
    return Text(f"{delta:+.2f}", style=style)


def _colored_pct(pct: float | None, metric: str) -> Text:
    """Return a Rich Text with green/red coloring for % change."""
    from rich.text import Text

    if pct is None:
        return Text("-")
    higher_is_better = metric in _HIGHER_IS_BETTER
    if pct > 0:
        style = "green" if higher_is_better else "red"
    elif pct < 0:
        style = "red" if higher_is_better else "green"
    else:
        style = "dim"
    return Text(f"{pct:+.1f}%", style=style)


# ---------------------------------------------------------------------------
# lunar telemetry export
# ---------------------------------------------------------------------------


@app.command(name="export")
def export_cmd(
    run_id: Annotated[
        str,
        typer.Argument(help="Run ID to export"),
    ],
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: json or csv"),
    ] = "json",
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output file path (default: stdout)"),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Force JSON output mode")
    ] = False,
) -> None:
    """Export raw telemetry samples for a run.

    Outputs JSON or CSV to stdout or a file.
    """
    try:
        _export_impl(run_id=run_id, fmt=fmt, output=output)
    except typer.Exit:
        raise
    except Exception as exc:
        handle_cli_error(exc)


def _export_impl(*, run_id: str, fmt: str, output: str | None) -> None:
    """Core export logic."""
    from lunar_sandbox.telemetry.store import TelemetryStore

    db_path = _get_default_db_path()

    if not db_path.exists():
        console.print("[dim]No telemetry data.[/]")
        return

    store = TelemetryStore(db_path)
    store.open()
    try:
        samples = store.export_samples(run_id)
        if not samples:
            console.print(f"[dim]No samples found for run '{run_id}'[/]")
            return

        if fmt == "json":
            text = json.dumps(samples, indent=2, default=str)
        elif fmt == "csv":
            fieldnames = ["run_id", "metric", "value", "fingerprint", "timestamp"]
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(samples)
            text = buf.getvalue()
        else:
            console.print(f"[bold red]Error:[/] Unknown format '{fmt}'. Use 'json' or 'csv'.")
            raise typer.Exit(code=EXIT_USER_ERROR)

        if output:
            Path(output).write_text(text)
        else:
            sys.stdout.write(text + "\n")

        console.print(f"Exported {len(samples)} samples")
    finally:
        store.close()


# ---------------------------------------------------------------------------
# lunar telemetry clear
# ---------------------------------------------------------------------------


@app.command()
def clear(
    run_id: Annotated[
        Optional[str],
        typer.Option("--run-id", help="Clear a specific run"),
    ] = None,
    all_runs: Annotated[
        bool,
        typer.Option("--all", help="Clear all telemetry data"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-y", help="Skip confirmation"),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Force JSON output")
    ] = False,
) -> None:
    """Clear telemetry data.

    Use --run-id to clear a specific run, or --all for everything.
    """
    try:
        _clear_impl(
            run_id=run_id,
            all_runs=all_runs,
            force=force,
            json_output=json_output,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        handle_cli_error(exc)


def _clear_impl(
    *,
    run_id: str | None,
    all_runs: bool,
    force: bool,
    json_output: bool,
) -> None:
    """Core clear logic."""
    from lunar_sandbox.telemetry.store import TelemetryStore

    mode = detect_output_mode(json_flag=json_output, human_flag=False)

    if not run_id and not all_runs:
        msg = "Specify --run-id <ID> or --all to clear telemetry data."
        if mode == OutputMode.JSON:
            print_json({"error": msg})
        else:
            console.print(f"[bold red]Error:[/] {msg}")
        raise typer.Exit(code=EXIT_USER_ERROR)

    db_path = _get_default_db_path()
    if not db_path.exists():
        msg = "No telemetry data to clear."
        if mode == OutputMode.JSON:
            print_json({"message": msg})
        else:
            console.print(f"[dim]{msg}[/]")
        return

    # Confirmation prompt
    if not force:
        target = f"run '{run_id}'" if run_id else "ALL telemetry data"
        confirm = typer.confirm(f"Clear {target}?")
        if not confirm:
            console.print("[dim]Cancelled.[/]")
            return

    store = TelemetryStore(db_path)
    store.open()
    try:
        if run_id:
            deleted = store.delete_run(run_id)
            if mode == OutputMode.JSON:
                print_json({"deleted": deleted, "run_id": run_id})
            else:
                if deleted:
                    console.print(f"[bold green]Deleted[/] run '{run_id}'")
                else:
                    console.print(f"[dim]Run '{run_id}' not found[/]")
        else:
            count = store.delete_all()
            if mode == OutputMode.JSON:
                print_json({"deleted_runs": count})
            else:
                console.print(f"[bold green]Deleted[/] {count} run(s)")
    finally:
        store.close()

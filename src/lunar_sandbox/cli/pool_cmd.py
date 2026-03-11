"""``lunar pool`` subcommands for sandbox pool daemon management.

Provides ``start``, ``status``, and ``stop`` subcommands for managing
a persistent sandbox pool daemon.  The daemon runs in the foreground
and communicates status via a Unix socket.  PID and socket paths live
under ``~/.lunar/``.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Any

from typing_extensions import Annotated

import typer

from lunar_sandbox.cli.errors import (
    EXIT_INFRA_ERROR,
    EXIT_SUCCESS,
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

app = typer.Typer(help="Manage sandbox pool daemon")

# Daemon file locations
_LUNAR_DIR = Path.home() / ".lunar"
_PID_FILE = _LUNAR_DIR / "pool.pid"
_SOCK_FILE = _LUNAR_DIR / "pool.sock"


# ---------------------------------------------------------------------------
# lunar pool status
# ---------------------------------------------------------------------------


@app.command()
def status(
    json_output: Annotated[
        bool, typer.Option("--json", help="Force JSON output")
    ] = False,
    human_output: Annotated[
        bool, typer.Option("--human", help="Force human-readable output")
    ] = False,
) -> None:
    """Show pool daemon status.

    Reports pool metrics if a daemon is running, or indicates
    on-demand mode when no daemon is active.
    """
    try:
        _status_impl(json_output=json_output, human_output=human_output)
    except Exception as exc:
        handle_cli_error(exc)


def _status_impl(*, json_output: bool, human_output: bool) -> None:
    """Core status logic."""
    mode = detect_output_mode(json_flag=json_output, human_flag=human_output)
    daemon_pid = _read_pid()

    if daemon_pid is None or not _pid_alive(daemon_pid):
        # No daemon running
        data = {
            "running": False,
            "mode": "on-demand",
            "message": "No persistent pool running. Pools are created on-demand per command.",
        }
        if mode == OutputMode.JSON:
            print_json(data)
        else:
            from rich.panel import Panel
            from rich.text import Text

            content = Text()
            content.append("Status: ", style="dim")
            content.append("Not running", style="bold yellow")
            content.append("\nMode:   ", style="dim")
            content.append("on-demand", style="bold")
            content.append(
                "\n\nPools are created on-demand per command.",
                style="dim",
            )
            content.append(
                "\nUse 'lunar pool start' to launch a persistent pool daemon.",
                style="dim",
            )
            console.print(
                Panel(content, title="Pool Status", border_style="yellow")
            )
        return

    # Daemon is running -- try to query status via socket
    pool_data = _query_daemon_status()
    if pool_data is None:
        # Socket query failed, but PID exists
        data = {
            "running": True,
            "pid": daemon_pid,
            "message": "Pool daemon running but status query failed.",
        }
        if mode == OutputMode.JSON:
            print_json(data)
        else:
            console.print(
                f"[bold green]Pool daemon running[/] (PID {daemon_pid})"
            )
            console.print("[dim]Status query via socket failed.[/]")
        return

    # Full status available
    if mode == OutputMode.JSON:
        pool_data["pid"] = daemon_pid
        _enrich_json_with_telemetry(pool_data)
        print_json(pool_data)
    else:
        _render_pool_status(pool_data, daemon_pid)


def _render_pool_status(data: dict[str, Any], pid: int) -> None:
    """Render pool status as a Rich panel."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    metrics = data.get("metrics", {})

    content = Text()
    content.append("Status:   ", style="dim")
    content.append("Running", style="bold green")
    content.append(f"\nPID:      {pid}")
    content.append(f"\nPool size: {metrics.get('pool_size', 0)}")
    content.append(f"\nIdle:     {metrics.get('idle_count', 0)}")
    content.append(f"\nActive:   {metrics.get('active_count', 0)}")
    content.append(f"\nHit rate: {metrics.get('hit_rate', 0.0):.1%}")

    pressure_str = "N/A"
    if "memory_pressure" in data:
        pressure_str = f"{data['memory_pressure']:.1%}"
    content.append(f"\nMemory:   {pressure_str}")

    console.print(Panel(content, title="Pool Status", border_style="green"))

    # Fingerprints table
    fingerprints = data.get("fingerprints", [])
    if fingerprints:
        table = Table(title="Known Fingerprints")
        table.add_column("Fingerprint", style="bold")
        table.add_column("Target", justify="right")
        targets = data.get("targets", {})
        for fp in fingerprints:
            table.add_row(fp, str(targets.get(fp, "-")))
        console.print(table)

    # Brief telemetry summary (if data exists)
    _render_brief_telemetry()


# ---------------------------------------------------------------------------
# lunar pool start
# ---------------------------------------------------------------------------


@app.command()
def start(
    size: Annotated[
        int,
        typer.Option("--size", help="Initial pool size"),
    ] = 4,
    foreground: Annotated[
        bool,
        typer.Option("--foreground", "-f", help="Run in foreground"),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Force JSON output")
    ] = False,
) -> None:
    """Start a persistent pool daemon.

    Runs in the foreground (like redis-server). Press Ctrl+C to stop.
    For background operation, run in another terminal or use '&'.
    """
    try:
        _start_impl(size=size, json_output=json_output)
    except Exception as exc:
        handle_cli_error(exc)


def _start_impl(*, size: int, json_output: bool) -> None:
    """Core start logic -- launches the pool event loop."""
    # Check if already running
    existing_pid = _read_pid()
    if existing_pid is not None and _pid_alive(existing_pid):
        msg = f"Pool daemon already running (PID {existing_pid}). Use 'lunar pool stop' first."
        if json_output:
            print_json({"error": msg, "pid": existing_pid})
        else:
            console.print(f"[bold red]Error:[/] {msg}")
        raise typer.Exit(code=EXIT_USER_ERROR)

    # Ensure ~/.lunar/ exists
    _LUNAR_DIR.mkdir(parents=True, exist_ok=True)

    # Write PID file
    _PID_FILE.write_text(str(os.getpid()))

    if not json_output:
        console.print(
            f"[bold green]Pool daemon started[/] (PID {os.getpid()}, size={size})"
        )
        console.print("[dim]Press Ctrl+C to stop.[/]")

    try:
        asyncio.run(_run_pool_daemon(size=size, json_output=json_output))
    except KeyboardInterrupt:
        if not json_output:
            console.print("\n[bold yellow]Pool daemon stopping...[/]")
    finally:
        _cleanup_daemon_files()
        if not json_output:
            console.print("[bold green]Pool daemon stopped.[/]")


async def _run_pool_daemon(*, size: int, json_output: bool) -> None:
    """Run the pool daemon event loop with a status socket server."""
    from lunar_sandbox.pool.config import PoolConfig
    from lunar_sandbox.pool.pool import SandboxPool

    config = PoolConfig(global_max_sandboxes=size)
    pool = SandboxPool(config)
    await pool.start()

    # Start Unix socket server for status queries
    sock_server: asyncio.AbstractServer | None = None
    try:
        # Clean up stale socket file
        if _SOCK_FILE.exists():
            _SOCK_FILE.unlink()

        sock_server = await asyncio.start_unix_server(
            lambda r, w: _handle_socket_client(r, w, pool),
            path=str(_SOCK_FILE),
        )

        # Block until interrupted -- use Event.wait()
        shutdown = asyncio.Event()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, shutdown.set)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        await shutdown.wait()
    finally:
        if sock_server is not None:
            sock_server.close()
            await sock_server.wait_closed()

        await pool.shutdown()

        if _SOCK_FILE.exists():
            _SOCK_FILE.unlink(missing_ok=True)


async def _handle_socket_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    pool: Any,
) -> None:
    """Handle a client connection on the status socket."""
    try:
        data = await asyncio.wait_for(reader.read(1024), timeout=5.0)
        request = data.decode().strip()

        if request == "status":
            status_data = await pool.status()
            response = json.dumps(status_data, default=str)
        elif request == "stop":
            response = json.dumps({"ok": True, "message": "Stopping"})
            # Signal the event loop to shut down
            loop = asyncio.get_running_loop()
            loop.call_soon(lambda: os.kill(os.getpid(), signal.SIGTERM))
        else:
            response = json.dumps({"error": f"Unknown command: {request}"})

        writer.write(response.encode())
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# lunar pool stop
# ---------------------------------------------------------------------------


@app.command()
def stop(
    json_output: Annotated[
        bool, typer.Option("--json", help="Force JSON output")
    ] = False,
) -> None:
    """Stop a running pool daemon.

    Sends SIGTERM to the daemon process and waits for it to exit.
    """
    try:
        _stop_impl(json_output=json_output)
    except Exception as exc:
        handle_cli_error(exc)


def _stop_impl(*, json_output: bool) -> None:
    """Core stop logic."""
    daemon_pid = _read_pid()

    if daemon_pid is None:
        msg = "No pool daemon running (no PID file found)."
        if json_output:
            print_json({"running": False, "message": msg})
        else:
            console.print(f"[dim]{msg}[/]")
        return

    if not _pid_alive(daemon_pid):
        # PID file exists but process is dead -- clean up
        _cleanup_daemon_files()
        msg = f"Pool daemon (PID {daemon_pid}) is not running. Cleaned up stale files."
        if json_output:
            print_json({"running": False, "message": msg, "pid": daemon_pid})
        else:
            console.print(f"[dim]{msg}[/]")
        return

    # Try socket-based stop first
    stop_sent = _send_stop_via_socket()
    if not stop_sent:
        # Fall back to SIGTERM
        try:
            os.kill(daemon_pid, signal.SIGTERM)
        except ProcessLookupError:
            _cleanup_daemon_files()
            if json_output:
                print_json({"stopped": True, "pid": daemon_pid})
            else:
                console.print(f"[bold green]Pool daemon stopped[/] (PID {daemon_pid})")
            return

    # Wait briefly for process to exit
    for _ in range(20):  # up to 2 seconds
        if not _pid_alive(daemon_pid):
            break
        time.sleep(0.1)

    if _pid_alive(daemon_pid):
        msg = f"Pool daemon (PID {daemon_pid}) did not stop within 2 seconds."
        if json_output:
            print_json({"stopped": False, "pid": daemon_pid, "message": msg})
        else:
            console.print(f"[bold yellow]Warning:[/] {msg}")
    else:
        if json_output:
            print_json({"stopped": True, "pid": daemon_pid})
        else:
            console.print(f"[bold green]Pool daemon stopped[/] (PID {daemon_pid})")

    # Clean up any leftover files
    _cleanup_daemon_files()


# ---------------------------------------------------------------------------
# Telemetry enrichment (optional -- never breaks pool status)
# ---------------------------------------------------------------------------


def _render_brief_telemetry() -> None:
    """Render a brief telemetry summary below pool status (if data exists)."""
    try:
        from rich.text import Text

        from lunar_sandbox.telemetry.store import TelemetryStore

        db_path = Path("trajectories") / "trajectories.db"
        if not db_path.exists():
            return

        store = TelemetryStore(db_path)
        store.open()
        try:
            runs = store.query_runs(limit=1)
            if not runs:
                return

            latest = runs[0]
            telem_text = Text()
            telem_text.append("\nTelemetry ", style="bold dim")
            telem_text.append(f"(run: {latest['run_id'][:16]})", style="dim")

            cache_rate = latest.get("cache_hit_rate")
            if cache_rate is not None:
                telem_text.append(f"\n  Cache hit rate: {cache_rate:.1%}")

            # Fetch allocate_latency samples for avg
            samples = store.query_samples(
                latest["run_id"], metric="allocate_latency"
            )
            if samples:
                avg_alloc = sum(s["value"] for s in samples) / len(samples)
                telem_text.append(f"\n  Avg allocate:   {avg_alloc:.1f}ms")

            telem_text.append(
                "\n  Use 'lunar telemetry' for full details", style="dim"
            )
            console.print(telem_text)
        finally:
            store.close()
    except Exception:
        pass  # Telemetry is optional -- never break pool status


def _enrich_json_with_telemetry(pool_data: dict[str, Any]) -> None:
    """Add a telemetry_summary field to JSON pool status output."""
    try:
        from lunar_sandbox.telemetry.store import TelemetryStore

        db_path = Path("trajectories") / "trajectories.db"
        if not db_path.exists():
            return

        store = TelemetryStore(db_path)
        store.open()
        try:
            runs = store.query_runs(limit=1)
            if runs:
                pool_data["telemetry_summary"] = {
                    "run_id": runs[0]["run_id"],
                    "cache_hit_rate": runs[0].get("cache_hit_rate"),
                    "throughput_eps_per_min": runs[0].get("throughput_eps_per_min"),
                }
        finally:
            store.close()
    except Exception:
        pass  # Telemetry is optional -- never break pool status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_pid() -> int | None:
    """Read the daemon PID from the PID file, or None if not found."""
    try:
        return int(_PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _cleanup_daemon_files() -> None:
    """Remove PID and socket files."""
    for f in (_PID_FILE, _SOCK_FILE):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass


def _query_daemon_status() -> dict[str, Any] | None:
    """Query the running daemon for status via Unix socket."""
    if not _SOCK_FILE.exists():
        return None

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(str(_SOCK_FILE))
        sock.sendall(b"status")
        data = sock.recv(65536)
        sock.close()
        return json.loads(data.decode())
    except Exception:
        return None


def _send_stop_via_socket() -> bool:
    """Send a stop command to the daemon via Unix socket."""
    if not _SOCK_FILE.exists():
        return False

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(str(_SOCK_FILE))
        sock.sendall(b"stop")
        data = sock.recv(1024)
        sock.close()
        response = json.loads(data.decode())
        return response.get("ok", False)
    except Exception:
        return False

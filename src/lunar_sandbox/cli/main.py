"""Root Typer application for the ``lunar`` CLI.

Defines the top-level app, ``--version`` flag, and lazy command
registration.  Command modules (``run_cmd``, ``eval_cmd``,
``replay_cmd``, ``pool_cmd``) are imported conditionally so the app
works even before those modules are created by Plans 03 and 04.
"""

from __future__ import annotations

from importlib.metadata import version as pkg_version

import typer

__all__ = ["app"]


def _version_callback(value: bool) -> None:
    """Print version and exit when ``--version`` is passed."""
    if value:
        v = pkg_version("lunar-sandbox")
        typer.echo(f"lunar-sandbox {v}")
        raise typer.Exit()


app = typer.Typer(
    name="lunar",
    help="Lunar Sandbox: fast evaluation engine for coding agents",
    pretty_exceptions_enable=False,
    no_args_is_help=True,
)


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Lunar Sandbox: fast evaluation engine for coding agents."""


# -------------------------------------------------------------------
# Command registration -- modules created by subsequent plans.
# Each try/except allows the app to function even when command
# modules have not yet been implemented.
# -------------------------------------------------------------------

try:
    from lunar_sandbox.cli import run_cmd  # noqa: F401

    app.command(name="run")(run_cmd.run)
except (ImportError, AttributeError):
    pass

try:
    from lunar_sandbox.cli import eval_cmd  # noqa: F401

    app.command(name="eval")(eval_cmd.eval_batch)
except (ImportError, AttributeError):
    pass

try:
    from lunar_sandbox.cli import replay_cmd  # noqa: F401

    app.command(name="replay")(replay_cmd.replay)
except (ImportError, AttributeError):
    pass

try:
    from lunar_sandbox.cli import pool_cmd  # noqa: F401

    app.add_typer(pool_cmd.app, name="pool", help="Manage sandbox pool daemon")
except (ImportError, AttributeError):
    pass

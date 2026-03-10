"""Semantic exit codes and CLI error formatting.

Maps exception types to exit codes following git-style conventions:
0 = success, 1 = agent failure, 2 = infrastructure error, 3 = user error.

Error messages are printed to stderr via a dedicated Rich console.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer
from rich.console import Console

if TYPE_CHECKING:
    from lunar_sandbox.scheduler.result import BatchResult

__all__ = [
    "EXIT_SUCCESS",
    "EXIT_AGENT_FAILURE",
    "EXIT_INFRA_ERROR",
    "EXIT_USER_ERROR",
    "handle_cli_error",
    "exit_for_batch",
]

# Semantic exit codes
EXIT_SUCCESS = 0
EXIT_AGENT_FAILURE = 1
EXIT_INFRA_ERROR = 2
EXIT_USER_ERROR = 3

# Dedicated error console (stderr)
err_console = Console(stderr=True)


def handle_cli_error(exc: Exception, verbose: int = 0) -> None:
    """Map an exception to a semantic exit code and display a friendly message.

    Error messages follow git's style: ``Error: {short message}`` with
    a suggestion on the next line when applicable.

    Args:
        exc: The exception to handle.
        verbose: Verbosity level. When > 0, print the full traceback.

    Raises:
        typer.Exit: Always raised to set the process exit code.
    """
    if isinstance(exc, KeyboardInterrupt):
        err_console.print()  # clean line after ^C
        raise typer.Exit(code=EXIT_SUCCESS)

    if isinstance(exc, (FileNotFoundError, ValueError, typer.BadParameter)):
        code = EXIT_USER_ERROR
        err_console.print(f"[bold red]Error:[/] {exc}")
        if isinstance(exc, FileNotFoundError):
            err_console.print(
                "[dim]Hint: check the file path or run with --help[/]"
            )
    else:
        # Attempt lazy import of infrastructure error types
        code = EXIT_INFRA_ERROR
        try:
            from lunar_sandbox.sandbox.errors import InfraError
            from lunar_sandbox.pool.errors import PoolError

            if isinstance(exc, (InfraError, PoolError)):
                code = EXIT_INFRA_ERROR
                err_console.print(f"[bold red]Infrastructure error:[/] {exc}")
            else:
                err_console.print(f"[bold red]Error:[/] {exc}")
        except ImportError:
            err_console.print(f"[bold red]Error:[/] {exc}")

    if verbose > 0:
        err_console.print_exception()

    raise typer.Exit(code=code)


def exit_for_batch(
    batch_result: BatchResult,
    pass_threshold: float | None = None,
) -> None:
    """Compute exit code for batch evaluation results.

    When ``pass_threshold`` is set, exits 0 if the pass rate meets or
    exceeds the threshold, 1 otherwise.  Without a threshold, exits 0
    if all tasks passed, 1 if any failed.

    Args:
        batch_result: The complete batch result.
        pass_threshold: Optional minimum pass rate (0.0 to 1.0).

    Raises:
        typer.Exit: Always raised with the computed exit code.
    """
    if pass_threshold is not None:
        code = (
            EXIT_SUCCESS
            if batch_result.aggregate.pass_rate >= pass_threshold
            else EXIT_AGENT_FAILURE
        )
    else:
        code = (
            EXIT_SUCCESS
            if batch_result.aggregate.failed == 0
            and batch_result.aggregate.errors == 0
            else EXIT_AGENT_FAILURE
        )
    raise typer.Exit(code=code)

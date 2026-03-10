"""Episode scoring subsystem.

Provides scoring functions for evaluating agent performance:

- :func:`score_by_test` -- binary pass/fail based on exit code
- :func:`score_by_script` -- custom scorer script (last line = float)
- :func:`score_by_parser` -- extract partial scores from test output
- :func:`run_scoring` -- high-level orchestrator delegating to the above
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

__all__ = [
    "run_scoring",
    "score_by_parser",
    "score_by_script",
    "score_by_test",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------


def score_by_test(exit_code: int) -> float:
    """Score by test pass/fail: exit code 0 = 1.0, anything else = 0.0.

    This is the default scoring method when no custom scorer or parser
    is configured.

    Args:
        exit_code: Process exit code from running the test command.

    Returns:
        1.0 if exit_code == 0, else 0.0.
    """
    return 1.0 if exit_code == 0 else 0.0


def score_by_script(stdout: str, exit_code: int) -> float:
    """Score using a custom scorer script's output.

    Reads the LAST non-empty line of stdout as a float score.
    Scorers may print debug info on earlier lines, so only the
    final non-empty line is parsed.

    The result is clamped to [0.0, 1.0].

    Args:
        stdout: Full standard output from the scorer script.
        exit_code: Exit code of the scorer script itself.

    Returns:
        Parsed and clamped score, or 0.0 on any parse failure
        or non-zero exit code.
    """
    if exit_code != 0:
        logger.warning(
            "Custom scorer script failed with exit code %d", exit_code
        )
        return 0.0

    # Find the last non-empty line
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        logger.warning("Custom scorer script produced no output")
        return 0.0

    last_line = lines[-1]
    try:
        value = float(last_line)
    except ValueError:
        logger.warning(
            "Custom scorer script output is not a valid float: %r", last_line
        )
        return 0.0

    # Clamp to [0.0, 1.0]
    clamped = max(0.0, min(1.0, value))
    if clamped != value:
        logger.warning(
            "Clamped scorer output from %f to %f", value, clamped
        )
    return clamped


def score_by_parser(stdout: str, parser_name: str) -> float:
    """Extract a partial score from test output using a named parser.

    Supported parsers:

    - ``"pytest"``: Looks for ``N passed`` and ``N failed`` patterns,
      computes ``passed / (passed + failed)``.
    - ``"fraction"``: Looks for ``N/M`` pattern,
      computes ``N / M``.

    Args:
        stdout: Test command standard output.
        parser_name: Name of the parser to use.

    Returns:
        Extracted score in [0.0, 1.0], or 0.0 if no match found
        or unknown parser.
    """
    if parser_name == "pytest":
        return _parse_pytest(stdout)
    elif parser_name == "fraction":
        return _parse_fraction(stdout)
    else:
        logger.warning("Unknown scoring parser: %r", parser_name)
        return 0.0


# ---------------------------------------------------------------------------
# Parser implementations
# ---------------------------------------------------------------------------

# Patterns match pytest summary lines like "8 passed, 2 failed"
_PYTEST_PASSED_RE = re.compile(r"(\d+)\s+passed")
_PYTEST_FAILED_RE = re.compile(r"(\d+)\s+failed")

# Matches fraction patterns like "7/10" or "3/4"
_FRACTION_RE = re.compile(r"(\d+)\s*/\s*(\d+)")


def _parse_pytest(stdout: str) -> float:
    """Parse pytest-style output for passed/failed counts."""
    passed_match = _PYTEST_PASSED_RE.search(stdout)
    failed_match = _PYTEST_FAILED_RE.search(stdout)

    passed = int(passed_match.group(1)) if passed_match else 0
    failed = int(failed_match.group(1)) if failed_match else 0

    total = passed + failed
    if total == 0:
        if passed_match is None and failed_match is None:
            logger.warning("No pytest pass/fail counts found in output")
        return 0.0

    return passed / total


def _parse_fraction(stdout: str) -> float:
    """Parse fraction-style output (e.g., '7/10')."""
    match = _FRACTION_RE.search(stdout)
    if match is None:
        logger.warning("No fraction pattern found in output")
        return 0.0

    numerator = int(match.group(1))
    denominator = int(match.group(2))

    if denominator == 0:
        logger.warning("Fraction denominator is zero")
        return 0.0

    return numerator / denominator


# ---------------------------------------------------------------------------
# High-level scoring orchestrator
# ---------------------------------------------------------------------------


class _SandboxExecuteFn(Protocol):
    """Protocol for the sandbox execution callable."""

    async def __call__(
        self, command: str, timeout: float = ...
    ) -> dict[str, Any]: ...


async def run_scoring(
    sandbox_execute_fn: Any,
    task: Any,
    action_response_stdout: str | None = None,
) -> tuple[float, str]:
    """Run scoring for an episode, delegating to the appropriate method.

    This is the high-level orchestrator called by EpisodeRunner during
    the SCORING phase.  It executes commands in the sandbox (which is
    still alive) and parses results.

    Args:
        sandbox_execute_fn: An async callable with signature
            ``(command: str, timeout: float) -> {"exit_code": int, "stdout": str, "stderr": str}``.
            Typically wired to ``client.execute_command()``.
        task: A task definition (or duck-typed object) with attributes:
            ``test_command``, ``scoring_script``, ``scoring_parser``.
        action_response_stdout: Optional stdout from the agent's action
            (not currently used, reserved for future scorer input).

    Returns:
        A tuple of ``(score, method)`` where method is one of
        ``"test_pass_fail"``, ``"custom_script"``, or ``"parser:{name}"``.
    """
    scoring_script = getattr(task, "scoring_script", None)
    scoring_parser = getattr(task, "scoring_parser", None)
    test_command = getattr(task, "test_command", None)

    # Path 1: Custom scoring script
    if scoring_script:
        try:
            result = await sandbox_execute_fn(scoring_script, timeout=60.0)
            score = score_by_script(result["stdout"], result["exit_code"])
            return score, "custom_script"
        except Exception:
            logger.warning(
                "Custom scoring script execution failed", exc_info=True
            )
            return 0.0, "custom_script"

    # Path 2: Run test command
    if test_command:
        try:
            result = await sandbox_execute_fn(test_command, timeout=60.0)
        except Exception:
            logger.warning(
                "Test command execution failed", exc_info=True
            )
            return 0.0, "test_pass_fail"

        # Path 2a: With parser
        if scoring_parser:
            score = score_by_parser(result["stdout"], scoring_parser)
            return score, f"parser:{scoring_parser}"

        # Path 2b: Simple pass/fail
        score = score_by_test(result["exit_code"])
        return score, "test_pass_fail"

    # No scoring method configured
    logger.warning("No test_command or scoring_script configured for task")
    return 0.0, "test_pass_fail"

"""Unit tests for episode scoring subsystem.

Tests score_by_test, score_by_script, score_by_parser functions
covering happy paths, edge cases, clamping, and all supported parsers.
"""

from __future__ import annotations

from lunar_sandbox.episode.scoring import (
    score_by_parser,
    score_by_script,
    score_by_test,
)


class TestScoreByTest:
    """Tests for score_by_test() -- binary pass/fail."""

    def test_score_by_test_pass(self) -> None:
        """exit_code=0 returns 1.0."""
        assert score_by_test(0) == 1.0

    def test_score_by_test_fail(self) -> None:
        """exit_code=1 returns 0.0."""
        assert score_by_test(1) == 0.0

    def test_score_by_test_signal(self) -> None:
        """exit_code=137 (SIGKILL) returns 0.0."""
        assert score_by_test(137) == 0.0


class TestScoreByScript:
    """Tests for score_by_script() -- custom scorer output parsing."""

    def test_score_by_script_valid(self) -> None:
        """'0.85' returns 0.85."""
        assert score_by_script("0.85", 0) == 0.85

    def test_score_by_script_with_debug_output(self) -> None:
        """'debug\\n0.75\\n' returns 0.75 (last non-empty line)."""
        assert score_by_script("debug info\n0.75\n", 0) == 0.75

    def test_score_by_script_failed_exit(self) -> None:
        """exit_code=1 returns 0.0 regardless of output."""
        assert score_by_script("0.85", 1) == 0.0

    def test_score_by_script_invalid_output(self) -> None:
        """'not_a_number' returns 0.0."""
        assert score_by_script("not_a_number", 0) == 0.0

    def test_score_by_script_clamp_high(self) -> None:
        """'1.5' returns 1.0 (clamped)."""
        assert score_by_script("1.5", 0) == 1.0

    def test_score_by_script_clamp_low(self) -> None:
        """'-0.5' returns 0.0 (clamped)."""
        assert score_by_script("-0.5", 0) == 0.0

    def test_score_by_script_empty_output(self) -> None:
        """Empty output returns 0.0."""
        assert score_by_script("", 0) == 0.0

    def test_score_by_script_whitespace_only(self) -> None:
        """Whitespace-only output returns 0.0."""
        assert score_by_script("   \n   \n", 0) == 0.0


class TestScoreByParser:
    """Tests for score_by_parser() -- pytest and fraction parsers."""

    def test_score_by_parser_pytest(self) -> None:
        """'8 passed, 2 failed' returns 0.8."""
        assert score_by_parser("8 passed, 2 failed", "pytest") == 0.8

    def test_score_by_parser_pytest_all_pass(self) -> None:
        """'10 passed' returns 1.0."""
        assert score_by_parser("10 passed", "pytest") == 1.0

    def test_score_by_parser_pytest_all_fail(self) -> None:
        """'0 passed, 5 failed' returns 0.0."""
        assert score_by_parser("0 passed, 5 failed", "pytest") == 0.0

    def test_score_by_parser_pytest_no_match(self) -> None:
        """No pytest pattern found returns 0.0."""
        assert score_by_parser("no test output here", "pytest") == 0.0

    def test_score_by_parser_fraction(self) -> None:
        """'7/10' returns 0.7."""
        assert score_by_parser("Tests: 7/10", "fraction") == 0.7

    def test_score_by_parser_fraction_perfect(self) -> None:
        """'10/10' returns 1.0."""
        assert score_by_parser("Score: 10/10", "fraction") == 1.0

    def test_score_by_parser_fraction_no_match(self) -> None:
        """No fraction pattern returns 0.0."""
        assert score_by_parser("no fraction here", "fraction") == 0.0

    def test_score_by_parser_unknown(self) -> None:
        """Unknown parser returns 0.0."""
        assert score_by_parser("some output", "unknown_parser") == 0.0

"""Episode lifecycle management.

Public API::

    from lunar_sandbox.episode import (
        # State machine
        EpisodeOutcome, EpisodePhase, EpisodeState, VALID_TRANSITIONS,
        # Result
        EpisodeResult,
        # Scoring
        score_by_test, score_by_script, score_by_parser, run_scoring,
        # Runner
        EpisodeRunner,
    )
"""

from lunar_sandbox.episode.result import EpisodeResult
from lunar_sandbox.episode.runner import EpisodeRunner
from lunar_sandbox.episode.scoring import (
    run_scoring,
    score_by_parser,
    score_by_script,
    score_by_test,
)
from lunar_sandbox.episode.state import (
    VALID_TRANSITIONS,
    EpisodeOutcome,
    EpisodePhase,
    EpisodeState,
)

__all__ = [
    # State machine
    "EpisodeOutcome",
    "EpisodePhase",
    "EpisodeState",
    "VALID_TRANSITIONS",
    # Result
    "EpisodeResult",
    # Scoring
    "run_scoring",
    "score_by_parser",
    "score_by_script",
    "score_by_test",
    # Runner
    "EpisodeRunner",
]

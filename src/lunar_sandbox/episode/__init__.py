"""Episode lifecycle management.

Public API::

    from lunar_sandbox.episode import (
        EpisodeOutcome,
        EpisodePhase,
        EpisodeState,
        EpisodeResult,
        VALID_TRANSITIONS,
        score_by_test,
        score_by_script,
        score_by_parser,
        run_scoring,
    )
"""

from lunar_sandbox.episode.result import EpisodeResult
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
    "EpisodeOutcome",
    "EpisodePhase",
    "EpisodeResult",
    "EpisodeState",
    "VALID_TRANSITIONS",
    "run_scoring",
    "score_by_parser",
    "score_by_script",
    "score_by_test",
]

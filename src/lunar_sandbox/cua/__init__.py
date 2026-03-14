"""CUA (Computer-Using Agent) task definitions, observation models, and episode runner."""

from lunar_sandbox.cua.observation import CUAObservation
from lunar_sandbox.cua.retention import RetentionPolicy, cleanup_episodes
from lunar_sandbox.cua.runner import CUAEpisodeResult, CUAEpisodeRunner
from lunar_sandbox.cua.task import (
    CUATask,
    ManualReward,
    RewardVariant,
    ScreenshotReward,
    ScriptReward,
)

__all__ = [
    "CUATask",
    "ScriptReward",
    "ScreenshotReward",
    "ManualReward",
    "RewardVariant",
    "CUAObservation",
    "RetentionPolicy",
    "cleanup_episodes",
    "CUAEpisodeRunner",
    "CUAEpisodeResult",
]

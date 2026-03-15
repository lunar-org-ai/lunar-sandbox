"""CUA (Computer-Using Agent) task definitions, observation models, episode runner, reward evaluation, and pool management."""

from lunar_sandbox.cua.observation import CUAObservation
from lunar_sandbox.cua.pool import CUAPool, CUAPoolConfig, cua_pool_fingerprint
from lunar_sandbox.cua.retention import RetentionPolicy, cleanup_episodes
from lunar_sandbox.cua.reward import CUARewardEvaluator
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
    "CUARewardEvaluator",
    "CUAPool",
    "CUAPoolConfig",
    "cua_pool_fingerprint",
]

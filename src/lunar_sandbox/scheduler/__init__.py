"""Scheduler and batch evaluation subsystem.

Provides batch evaluation of tasks with configurable parallelism,
result collection, aggregate metrics, and persistence.

Public API::

    from lunar_sandbox.scheduler import (
        # Scheduler
        BatchScheduler,
        # Configuration
        BatchConfig,
        # Results
        TaskResult, AggregateMetrics, BatchResult,
        # Benchmark
        BenchmarkDefinition, BenchmarkTask, load_benchmark,
        # Persistence
        BatchResultStore,
    )
"""

from lunar_sandbox.scheduler.benchmark import (
    BenchmarkDefinition,
    BenchmarkTask,
    load_benchmark,
)
from lunar_sandbox.scheduler.config import BatchConfig
from lunar_sandbox.scheduler.result import AggregateMetrics, BatchResult, TaskResult
from lunar_sandbox.scheduler.scheduler import BatchScheduler
from lunar_sandbox.scheduler.store import BatchResultStore

__all__ = [
    "AggregateMetrics",
    "BatchConfig",
    "BatchResult",
    "BatchResultStore",
    "BatchScheduler",
    "BenchmarkDefinition",
    "BenchmarkTask",
    "TaskResult",
    "load_benchmark",
]

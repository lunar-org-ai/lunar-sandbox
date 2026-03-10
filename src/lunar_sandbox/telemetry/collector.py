"""Thread-safe in-memory telemetry collector.

Provides :class:`TelemetryCollector` for recording metric samples
during evaluation.  Uses ``threading.Lock`` because sandbox pool
operations run in real OS threads via ``asyncio.to_thread``.

The collector is intentionally minimal -- record() is < 1 us
(lock + list.append, no string formatting or I/O).
"""

from __future__ import annotations

import threading
import time

from lunar_sandbox.telemetry.types import MetricSample

__all__ = ["TelemetryCollector"]


class TelemetryCollector:
    """Thread-safe in-memory metric sample collector.

    Accumulates :class:`MetricSample` objects in a list protected by
    a :class:`threading.Lock`.  Designed for hot-path instrumentation
    with < 1 us overhead per ``record()`` call.

    Usage::

        collector = TelemetryCollector()
        collector.record("allocate_latency", 42.5, fingerprint="abc123")
        samples = collector.drain()
    """

    def __init__(self) -> None:
        self._samples: list[MetricSample] = []
        self._lock = threading.Lock()

    def record(
        self,
        metric: str,
        value: float,
        fingerprint: str = "",
        batch_run_id: str = "",
    ) -> None:
        """Record a metric sample.

        Creates a :class:`MetricSample` and appends it to the internal
        list under the lock.  Uses ``time.monotonic()`` for the
        timestamp.

        Args:
            metric: Metric name (e.g. ``"allocate_latency"``).
            value: Measured value in milliseconds (or 1.0/0.0 for
                cache hits).
            fingerprint: Environment fingerprint.
            batch_run_id: Batch run identifier.
        """
        sample = MetricSample(
            metric=metric,
            value=value,
            fingerprint=fingerprint,
            batch_run_id=batch_run_id,
            timestamp=time.monotonic(),
        )
        with self._lock:
            self._samples.append(sample)

    def snapshot(self) -> list[MetricSample]:
        """Return a copy of all recorded samples.

        Returns:
            A new list containing all samples recorded so far.
        """
        with self._lock:
            return list(self._samples)

    def drain(self) -> list[MetricSample]:
        """Return all samples and clear the internal buffer.

        Performs an atomic swap under the lock so no samples are lost.

        Returns:
            All samples that were in the buffer.
        """
        with self._lock:
            samples = self._samples
            self._samples = []
            return samples

    def count(self) -> int:
        """Return the approximate number of buffered samples.

        This is a lock-free read; the value may be slightly stale
        under concurrent writes, which is acceptable for monitoring.

        Returns:
            Number of samples currently buffered.
        """
        return len(self._samples)

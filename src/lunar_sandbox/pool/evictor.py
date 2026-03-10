"""Pool eviction strategies: TTL expiry, idle timeout, LRU with diversity.

Pure functions that select PoolEntry candidates for eviction. These do NOT
destroy sandboxes -- they return lists of entries to evict and remove them
from the input data structures. The caller (pool manager) handles actual
sandbox destruction.

Three strategies:
  - select_expired: Always-run TTL check for stale sandboxes.
  - select_idle_timeout: Remove sandboxes idle beyond a threshold.
  - select_eviction_candidates: LRU with diversity -- prefers fingerprints
    with many idle sandboxes, keeping at least keep_minimum per fingerprint.
"""

from __future__ import annotations

from collections import OrderedDict

from lunar_sandbox.pool.entry import PoolEntry


def select_expired(
    idle_pools: dict[str, OrderedDict[str, PoolEntry]],
    ttl_seconds: float,
) -> list[PoolEntry]:
    """Select all entries that have exceeded their TTL.

    Always runs regardless of memory pressure. Expired sandboxes are
    removed from idle_pools (mutates input).

    Args:
        idle_pools: Mapping of fingerprint -> ordered dict of idle entries.
        ttl_seconds: Maximum allowed sandbox age in seconds.

    Returns:
        List of PoolEntry instances whose age exceeds the TTL.
    """
    expired: list[PoolEntry] = []
    for fp, entries in idle_pools.items():
        to_remove: list[str] = []
        for sid, entry in entries.items():
            if entry.is_expired(ttl_seconds):
                expired.append(entry)
                to_remove.append(sid)
        for sid in to_remove:
            del entries[sid]
    return expired


def select_idle_timeout(
    idle_pools: dict[str, OrderedDict[str, PoolEntry]],
    idle_timeout_seconds: float,
) -> list[PoolEntry]:
    """Select all entries that have been idle beyond the timeout.

    Removes matched entries from idle_pools (mutates input).

    Args:
        idle_pools: Mapping of fingerprint -> ordered dict of idle entries.
        idle_timeout_seconds: Maximum allowed idle time in seconds.

    Returns:
        List of PoolEntry instances idle longer than the timeout.
    """
    idle: list[PoolEntry] = []
    for fp, entries in idle_pools.items():
        to_remove: list[str] = []
        for sid, entry in entries.items():
            if entry.is_idle_too_long(idle_timeout_seconds):
                idle.append(entry)
                to_remove.append(sid)
        for sid in to_remove:
            del entries[sid]
    return idle


def select_eviction_candidates(
    idle_pools: dict[str, OrderedDict[str, PoolEntry]],
    count: int,
    keep_minimum: int = 1,
) -> list[PoolEntry]:
    """Select up to ``count`` idle entries for eviction using LRU-diversity.

    Algorithm:
      1. Sort fingerprints by idle count descending.
      2. Pick the LRU entry (oldest ``last_used_at``) from the fingerprint
         with the most idle sandboxes.
      3. Skip fingerprints with ``<= keep_minimum`` idle entries.
      4. Repeat until ``count`` reached or no more eligible fingerprints.

    This ensures eviction pressure spreads across fingerprints rather than
    draining a single one. The ``keep_minimum`` parameter guarantees at
    least that many idle sandboxes per fingerprint survive eviction.

    Removes selected entries from idle_pools (mutates input).

    Args:
        idle_pools: Mapping of fingerprint -> ordered dict of idle entries.
        count: Maximum number of entries to select for eviction.
        keep_minimum: Minimum idle entries to preserve per fingerprint.
            Fingerprints at or below this count are skipped.

    Returns:
        List of up to ``count`` PoolEntry instances selected for eviction.
    """
    result: list[PoolEntry] = []

    while len(result) < count:
        # Find eligible fingerprint with the most idle entries.
        best_fp: str | None = None
        best_count = 0

        for fp, entries in idle_pools.items():
            n = len(entries)
            if n > keep_minimum and n > best_count:
                best_fp = fp
                best_count = n

        if best_fp is None:
            # No fingerprint has more than keep_minimum idle entries.
            break

        # Pop the LRU entry (first item in OrderedDict = oldest insertion).
        entries = idle_pools[best_fp]
        sid, entry = entries.popitem(last=False)
        result.append(entry)

    return result

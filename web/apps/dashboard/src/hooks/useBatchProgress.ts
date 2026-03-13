import { useEffect, useRef, useState } from 'react'

import { useEventStream } from '@/hooks/useEventStream'
import { fetchBatch, type BatchDetail } from '@/lib/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseBatchProgressReturn {
  batch: BatchDetail | null
  loading: boolean
  error: string | null
  /** Latest total_cost from WS batch_progress event (preferred for live counter) */
  liveCost: number | null
  /** Latest total_tokens from WS batch_progress event */
  liveTokens: number | null
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5000

export function useBatchProgress(batchId: string | null): UseBatchProgressReturn {
  const [batch, setBatch] = useState<BatchDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [liveCost, setLiveCost] = useState<number | null>(null)
  const [liveTokens, setLiveTokens] = useState<number | null>(null)

  // Latest-ref for batchId to avoid useEffect re-triggers on identity changes
  const batchIdRef = useRef(batchId)
  batchIdRef.current = batchId

  // WS subscription to batch:{batchId} topic
  const topic = batchId ? `batch:${batchId}` : null
  const { events } = useEventStream({ topic })

  // Fetch batch data from REST
  async function doFetch() {
    const id = batchIdRef.current
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const data = await fetchBatch(id)
      setBatch(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load batch.')
    } finally {
      setLoading(false)
    }
  }

  // Mount: initial fetch + poll interval
  useEffect(() => {
    if (!batchId) {
      setBatch(null)
      setLoading(false)
      setError(null)
      return
    }

    doFetch()

    const intervalId = setInterval(() => {
      doFetch()
    }, POLL_INTERVAL_MS)

    return () => {
      clearInterval(intervalId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId])

  // WS events: trigger immediate re-fetch on new events AND extract live cost/tokens
  const prevEventsLengthRef = useRef(0)
  useEffect(() => {
    if (events.length === 0) return

    // Extract live cost/tokens from LATEST batch_progress event
    const lastEvent = events[events.length - 1]
    if (lastEvent && lastEvent.type === 'batch_progress') {
      const payload = lastEvent.payload as Record<string, unknown>
      if (typeof payload['total_cost'] === 'number') {
        setLiveCost(payload['total_cost'])
      }
      if (typeof payload['total_tokens'] === 'number') {
        setLiveTokens(payload['total_tokens'])
      }
    }

    // If new events arrived, trigger an immediate re-fetch to invalidate REST cache
    if (events.length !== prevEventsLengthRef.current) {
      prevEventsLengthRef.current = events.length
      doFetch()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events])

  return { batch, loading, error, liveCost, liveTokens }
}

import { useEffect, useRef, useState } from 'react'

import { useEventStream } from '@/hooks/useEventStream'
import { stepsToSpans, type TraceSpan } from '@/lib/trace-utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseTraceStreamOptions {
  episodeId: string | null
  sandboxId: string | null
  initialSteps?: Record<string, unknown>[]
  /** Unix seconds float for the episode start time */
  episodeStartTs?: number
}

export interface UseTraceStreamReturn {
  spans: TraceSpan[]
  /** true if WS events have been received within the last 5 seconds */
  isLive: boolean
  totalSpans: number
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LIVE_THRESHOLD_MS = 5000

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTraceStream(options: UseTraceStreamOptions): UseTraceStreamReturn {
  const { episodeId, sandboxId, initialSteps = [], episodeStartTs = 0 } = options

  // Build the WS topic only when both IDs are present
  const topic =
    sandboxId && episodeId ? `sandbox:${sandboxId}:episode:${episodeId}` : null

  const { events } = useEventStream({ topic })

  // Span buffer stored in a ref (EventBuffer pattern from Phase 09-02)
  // Initial spans keyed by stepIdx for fast dedup
  const initialSpansRef = useRef<TraceSpan[]>([])
  const liveSpansRef = useRef<Map<number, TraceSpan>>(new Map())
  const lastEventTimeRef = useRef<number>(0)

  // React state for rendering
  const [spans, setSpans] = useState<TraceSpan[]>([])
  const [isLive, setIsLive] = useState(false)

  // Re-compute initial spans when inputs change
  useEffect(() => {
    if (!episodeId) {
      initialSpansRef.current = []
      liveSpansRef.current = new Map()
      setSpans([])
      setIsLive(false)
      return
    }

    const converted = stepsToSpans(initialSteps, episodeStartTs, episodeId)
    initialSpansRef.current = converted
    // Reset live spans when episode changes
    liveSpansRef.current = new Map()
    setSpans(merged(converted, liveSpansRef.current))
  }, [episodeId, episodeStartTs, initialSteps])

  // Process incoming WS trace_events
  useEffect(() => {
    if (!episodeId || events.length === 0) return

    const lastEvent = events[events.length - 1]
    if (!lastEvent || lastEvent.type !== 'trace_event') return

    const payload = lastEvent.payload as Record<string, unknown>

    // Normalize action field (some events use "action_type" instead of "action")
    const action = ((payload['action'] ?? payload['action_type'] ?? 'unknown') as string)

    // Calculate startMs relative to episode start
    let startMs: number
    let accumulatedMs = 0
    if (typeof payload['ts'] === 'number' && episodeStartTs > 0) {
      startMs = (payload['ts'] - episodeStartTs) * 1000
    } else {
      // Fall back to accumulating from the last known span end
      const liveSpansArr = Array.from(liveSpansRef.current.values())
      const lastLiveSpan = liveSpansArr.length > 0
        ? liveSpansArr[liveSpansArr.length - 1]
        : null
      const lastInitial = initialSpansRef.current.length > 0
        ? initialSpansRef.current[initialSpansRef.current.length - 1]
        : null

      if (lastLiveSpan) {
        accumulatedMs = lastLiveSpan.startMs + lastLiveSpan.durationMs
      } else if (lastInitial) {
        accumulatedMs = lastInitial.startMs + lastInitial.durationMs
      }
      startMs = accumulatedMs
    }

    const durationMs =
      typeof payload['duration_ms'] === 'number' ? payload['duration_ms'] : 0

    // Normalize params: prefer "params" field, fall back to constructing from "command"
    let params: Record<string, unknown> = {}
    if (payload['params'] && typeof payload['params'] === 'object') {
      params = payload['params'] as Record<string, unknown>
    } else if (payload['command'] != null) {
      params = { command: payload['command'] }
    }

    const observation: Record<string, unknown> =
      payload['output'] && typeof payload['output'] === 'object'
        ? (payload['output'] as Record<string, unknown>)
        : {}

    const rawStatus = (payload['status'] ?? 'completed') as string
    const status = (['success', 'error', 'timeout', 'completed', 'running'].includes(rawStatus)
      ? rawStatus
      : 'completed') as TraceSpan['status']

    const stepIdx =
      typeof payload['step_idx'] === 'number' ? payload['step_idx'] : liveSpansRef.current.size

    const span: TraceSpan = {
      id: `${episodeId}_${stepIdx}`,
      stepIdx,
      action,
      status,
      startMs,
      durationMs,
      params,
      observation,
      source: (payload['source'] ?? '') as string,
      depth: 0,
    }

    liveSpansRef.current.set(stepIdx, span)
    lastEventTimeRef.current = Date.now()

    // Sync rendered state
    setSpans(merged(initialSpansRef.current, liveSpansRef.current))
    setIsLive(true)
  }, [episodeId, episodeStartTs, events])

  // Decay isLive after LIVE_THRESHOLD_MS of silence
  useEffect(() => {
    if (!isLive) return

    const timer = setTimeout(() => {
      const elapsed = Date.now() - lastEventTimeRef.current
      if (elapsed >= LIVE_THRESHOLD_MS) {
        setIsLive(false)
      }
    }, LIVE_THRESHOLD_MS)

    return () => clearTimeout(timer)
  }, [isLive, events])

  return {
    spans,
    isLive,
    totalSpans: spans.length,
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Merges initial (REST) spans with live (WS) spans.
 * Live spans override initial spans at the same stepIdx, and any additional
 * live spans are appended after the initial ones.
 */
function merged(
  initialSpans: TraceSpan[],
  liveSpans: Map<number, TraceSpan>,
): TraceSpan[] {
  if (liveSpans.size === 0) return [...initialSpans]

  // Start with initial spans, allowing live spans to override by stepIdx
  const resultMap = new Map<number, TraceSpan>()
  for (const span of initialSpans) {
    resultMap.set(span.stepIdx, span)
  }
  liveSpans.forEach((span, idx) => {
    resultMap.set(idx, span)
  })

  // Sort by stepIdx ascending
  return Array.from(resultMap.values()).sort((a, b) => a.stepIdx - b.stepIdx)
}

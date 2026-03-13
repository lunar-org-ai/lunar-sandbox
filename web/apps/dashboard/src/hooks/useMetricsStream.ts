import { useEffect, useRef, useState } from 'react'

import { useEventStream } from '@/hooks/useEventStream'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MetricKey =
  | 'allocate_latency'
  | 'reset_latency'
  | 'episode_duration'
  | 'cache_hit_rate'

export interface MetricState {
  values: number[]
  current: number
}

export type MetricsRecord = Record<MetricKey, MetricState>

export interface UseMetricsStreamReturn {
  metrics: MetricsRecord
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const METRIC_KEYS: MetricKey[] = [
  'allocate_latency',
  'reset_latency',
  'episode_duration',
  'cache_hit_rate',
]

const MAX_SPARKLINE_POINTS = 30
const THROTTLE_MS = 200

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function emptyMetrics(): MetricsRecord {
  const record = {} as MetricsRecord
  for (const key of METRIC_KEYS) {
    record[key] = { values: [], current: 0 }
  }
  return record
}

function isMetricKey(name: string): name is MetricKey {
  return METRIC_KEYS.includes(name as MetricKey)
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Subscribe to telemetry_metric WS events on the given topic and aggregate
 * data into per-metric sparkline arrays with 200ms throttled state updates.
 *
 * @param topic - Explicit WS topic string (e.g. "telemetry:mock-run-1"). Pass
 *   null to skip subscription.
 */
export function useMetricsStream(topic: string | null): UseMetricsStreamReturn {
  // Mutable accumulator stored in ref -- not state (mutated in place)
  const metricsRef = useRef<MetricsRecord>(emptyMetrics())

  // React state for rendering (throttled snapshot)
  const [metrics, setMetrics] = useState<MetricsRecord>(emptyMetrics)

  // Throttle timer ref
  const throttleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Subscribe to WS topic -- topic is passed in, NOT hardcoded
  const { events } = useEventStream({ topic })

  // Process incoming WS telemetry_metric events
  useEffect(() => {
    if (events.length === 0) return

    const lastEvent = events[events.length - 1]
    if (!lastEvent || lastEvent.type !== 'telemetry_metric') return

    const payload = lastEvent.payload as Record<string, unknown>
    const metricName = payload['metric'] as string | undefined
    const value = payload['value']

    if (!metricName || !isMetricKey(metricName) || typeof value !== 'number') return

    // Mutate the ref in place
    const metricState = metricsRef.current[metricName]
    const nextValues = [...metricState.values, value]
    if (nextValues.length > MAX_SPARKLINE_POINTS) {
      nextValues.shift()
    }
    metricsRef.current = {
      ...metricsRef.current,
      [metricName]: { values: nextValues, current: value },
    }

    // Throttle state update to at most every 200ms
    if (throttleTimerRef.current === null) {
      throttleTimerRef.current = setTimeout(() => {
        throttleTimerRef.current = null
        setMetrics({ ...metricsRef.current })
      }, THROTTLE_MS)
    }
  }, [events])

  // Cleanup throttle timer on unmount
  useEffect(() => {
    return () => {
      if (throttleTimerRef.current !== null) {
        clearTimeout(throttleTimerRef.current)
      }
    }
  }, [])

  return { metrics }
}

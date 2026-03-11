import { useCallback, useEffect, useRef, useState } from 'react'

import { EventBuffer } from '@/lib/event-buffer'
import { useWebSocket, type ReadyState, type WsMessage } from '@/lib/ws'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseEventStreamOptions {
  /** Topic to subscribe to. Pass `null` to skip subscription. */
  topic: string | null
  /** Maximum number of events kept in the sliding window (default: 2000). */
  bufferSize?: number
  /** WebSocket URL override (default: derived from window.location). */
  url?: string
}

export interface UseEventStreamReturn {
  /** Current buffer contents. */
  events: readonly WsMessage[]
  /** Total events received since subscription (including evicted). */
  totalReceived: number
  /** Number of events evicted from the buffer. */
  evicted: number
  /** WebSocket connection state. */
  readyState: ReadyState
  /** Whether event processing (rendering) is paused. */
  paused: boolean
  /** Pause event processing -- connection stays open, events buffer silently. */
  pause: () => void
  /** Resume event processing -- UI catches up with buffered events. */
  resume: () => void
  /** Clear the event buffer and reset counters. */
  clear: () => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getWsUrl(override?: string): string {
  if (override) return override
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/api/ws`
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useEventStream(
  options: UseEventStreamOptions,
): UseEventStreamReturn {
  const { topic, bufferSize = 2000 } = options
  const url = getWsUrl(options.url)

  // Mutable buffer stored in ref -- not state (buffer is mutated in place)
  const bufferRef = useRef(new EventBuffer<WsMessage>(bufferSize))

  // React state for rendering
  const [events, setEvents] = useState<readonly WsMessage[]>([])
  const [totalReceived, setTotalReceived] = useState(0)
  const [evicted, setEvicted] = useState(0)
  const [paused, setPaused] = useState(false)

  // Latest-ref for paused so onMessage callback stays stable
  const pausedRef = useRef(paused)
  pausedRef.current = paused

  // onMessage: always buffer, only update state if not paused
  const onMessage = useCallback((message: WsMessage) => {
    const buf = bufferRef.current
    buf.push(message)

    if (!pausedRef.current) {
      setEvents([...buf.items])
      setTotalReceived(buf.totalReceived)
      setEvicted(buf.evicted)
    }
  }, [])

  const { readyState, subscribe, unsubscribe } = useWebSocket({
    url,
    onMessage,
  })

  // Manage topic subscription lifecycle
  useEffect(() => {
    if (!topic) return

    subscribe(topic)

    return () => {
      unsubscribe(topic)
    }
  }, [topic, subscribe, unsubscribe])

  const pause = useCallback(() => {
    setPaused(true)
  }, [])

  const resume = useCallback(() => {
    setPaused(false)
    // Sync UI with whatever accumulated in the buffer while paused
    const buf = bufferRef.current
    setEvents([...buf.items])
    setTotalReceived(buf.totalReceived)
    setEvicted(buf.evicted)
  }, [])

  const clear = useCallback(() => {
    bufferRef.current.clear()
    setEvents([])
    setTotalReceived(0)
    setEvicted(0)
  }, [])

  return {
    events,
    totalReceived,
    evicted,
    readyState,
    paused,
    pause,
    resume,
    clear,
  }
}

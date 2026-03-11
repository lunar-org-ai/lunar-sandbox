import { useCallback, useEffect, useRef, useState } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ReadyState =
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected'

export interface WsMessage {
  type: string
  topic: string
  timestamp: number
  payload: Record<string, unknown>
}

export interface UseWebSocketOptions {
  url: string
  onMessage?: (message: WsMessage) => void
  onConnect?: () => void
  onReconnect?: () => void
  onDisconnect?: () => void
  reconnectAttempts?: number // default: 20
  reconnectBaseDelay?: number // default: 1000 (ms)
  reconnectMaxDelay?: number // default: 30000 (ms)
}

export interface UseWebSocketReturn {
  readyState: ReadyState
  send: (data: unknown) => void
  subscribe: (topic: string) => void
  unsubscribe: (topic: string) => void
}

// ---------------------------------------------------------------------------
// Backoff
// ---------------------------------------------------------------------------

function getDelay(
  attempt: number,
  baseDelay: number,
  maxDelay: number,
): number {
  const delay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay)
  return delay + Math.random() * 1000 // jitter
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useWebSocket(options: UseWebSocketOptions): UseWebSocketReturn {
  const { url } = options

  const [readyState, setReadyState] = useState<ReadyState>('connecting')

  // Refs -- mutable state that must NOT trigger re-renders
  const wsRef = useRef<WebSocket | null>(null)
  const attemptRef = useRef<number>(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const topicsRef = useRef<Set<string>>(new Set())

  // Latest-ref pattern: store callbacks in refs so the effect never re-runs
  // when callback identity changes.
  const onMessageRef = useRef(options.onMessage)
  const onConnectRef = useRef(options.onConnect)
  const onReconnectRef = useRef(options.onReconnect)
  const onDisconnectRef = useRef(options.onDisconnect)

  onMessageRef.current = options.onMessage
  onConnectRef.current = options.onConnect
  onReconnectRef.current = options.onReconnect
  onDisconnectRef.current = options.onDisconnect

  // Config refs
  const maxAttempts = options.reconnectAttempts ?? 20
  const baseDelay = options.reconnectBaseDelay ?? 1000
  const maxDelay = options.reconnectMaxDelay ?? 30000

  useEffect(() => {
    let disposed = false

    function connect() {
      if (disposed) return

      setReadyState((prev) =>
        prev === 'reconnecting' ? 'reconnecting' : 'connecting',
      )

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        if (disposed) return
        setReadyState('connected')
        attemptRef.current = 0

        // Re-subscribe all tracked topics (critical after reconnection)
        for (const topic of topicsRef.current) {
          ws.send(JSON.stringify({ subscribe: topic }))
        }

        onConnectRef.current?.()
      }

      ws.onmessage = (event: MessageEvent) => {
        if (disposed) return
        try {
          const message = JSON.parse(event.data as string) as WsMessage
          onMessageRef.current?.(message)
        } catch {
          // Ignore malformed messages
        }
      }

      ws.onerror = () => {
        // onclose fires after onerror; let onclose handle reconnection
      }

      ws.onclose = () => {
        if (disposed) return

        wsRef.current = null

        if (attemptRef.current < maxAttempts) {
          const isFirstReconnect = attemptRef.current === 0
          setReadyState('reconnecting')

          if (isFirstReconnect) {
            onReconnectRef.current?.()
          }

          const delay = getDelay(attemptRef.current, baseDelay, maxDelay)
          attemptRef.current += 1

          reconnectTimerRef.current = setTimeout(() => {
            reconnectTimerRef.current = null
            connect()
          }, delay)
        } else {
          setReadyState('disconnected')
          onDisconnectRef.current?.()
        }
      }
    }

    connect()

    return () => {
      disposed = true

      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }

      const ws = wsRef.current
      if (ws) {
        // Prevent onclose from triggering reconnection during cleanup
        ws.onclose = null
        ws.onerror = null
        ws.onmessage = null
        ws.onopen = null
        ws.close(1000)
        wsRef.current = null
      }

      setReadyState('disconnected')
    }
  }, [url, maxAttempts, baseDelay, maxDelay])

  const send = useCallback((data: unknown) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
    }
  }, [])

  const subscribe = useCallback((topic: string) => {
    topicsRef.current.add(topic)
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ subscribe: topic }))
    }
  }, [])

  const unsubscribe = useCallback((topic: string) => {
    topicsRef.current.delete(topic)
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ unsubscribe: topic }))
    }
  }, [])

  return { readyState, send, subscribe, unsubscribe }
}

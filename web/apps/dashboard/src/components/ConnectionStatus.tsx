import { useCallback, useEffect, useRef, useState } from 'react'

import { useEventStream } from '@/hooks/useEventStream'
import type { ReadyState } from '@/lib/ws'

// ---------------------------------------------------------------------------
// Toast system (simple, no external dependency)
// ---------------------------------------------------------------------------

interface Toast {
  id: number
  message: string
  variant: 'success' | 'warning' | 'error'
}

let toastId = 0

function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback(
    (message: string, variant: Toast['variant']) => {
      const id = ++toastId
      setToasts((prev) => [...prev, { id, message, variant }])
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, 3000)
    },
    [],
  )

  return { toasts, addToast }
}

const toastStyles: Record<Toast['variant'], string> = {
  success:
    'bg-green-900/90 text-green-100 border border-green-700',
  warning:
    'bg-yellow-900/90 text-yellow-100 border border-yellow-700',
  error:
    'bg-red-900/90 text-red-100 border border-red-700',
}

function ToastContainer({ toasts }: { toasts: Toast[] }) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`px-4 py-2 rounded-lg text-sm shadow-lg ${toastStyles[t.variant]}`}
        >
          {t.message}
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Status indicator config
// ---------------------------------------------------------------------------

const stateConfig: Record<
  ReadyState,
  { dot: string; label: string; tooltip: string }
> = {
  connected: {
    dot: 'bg-green-500',
    label: 'Live',
    tooltip: 'Connected',
  },
  connecting: {
    dot: 'bg-yellow-500',
    label: 'Connecting...',
    tooltip: 'Connecting...',
  },
  reconnecting: {
    dot: 'bg-yellow-500',
    label: 'Reconnecting...',
    tooltip: 'Reconnecting...',
  },
  disconnected: {
    dot: 'bg-red-500',
    label: 'Offline',
    tooltip: 'Disconnected',
  },
}

// ---------------------------------------------------------------------------
// ConnectionStatus component
// ---------------------------------------------------------------------------

export function ConnectionStatus() {
  const { readyState } = useEventStream({ topic: null })
  const { toasts, addToast } = useToasts()

  // Track previous readyState for toast transitions.
  // null on first render means "skip the initial mount toast".
  const prevStateRef = useRef<ReadyState | null>(null)

  useEffect(() => {
    // Skip the very first render (initial connecting state)
    if (prevStateRef.current === null) {
      prevStateRef.current = readyState
      return
    }

    // Only fire toast when state actually changes
    if (readyState === prevStateRef.current) return
    prevStateRef.current = readyState

    switch (readyState) {
      case 'connected':
        addToast('Connected to live updates', 'success')
        break
      case 'reconnecting':
        addToast('Connection lost, reconnecting...', 'warning')
        break
      case 'disconnected':
        addToast('Disconnected from live updates', 'error')
        break
      // 'connecting' -- no toast
    }
  }, [readyState, addToast])

  const { dot, label, tooltip } = stateConfig[readyState]
  const showBanner =
    readyState === 'disconnected' || readyState === 'reconnecting'

  return (
    <>
      {/* Status dot + label */}
      <div className="flex items-center gap-1.5" title={tooltip}>
        <span className={`${dot} rounded-full w-2 h-2`} />
        <span className="text-xs text-zinc-400">{label}</span>
      </div>

      {/* Warning banner */}
      {showBanner && (
        <div className="fixed top-12 left-0 right-0 z-40 bg-amber-600 text-neutral-950 text-sm text-center py-1.5 px-4 font-medium">
          Real-time updates paused &mdash; reconnecting...
        </div>
      )}

      {/* Toast container */}
      <ToastContainer toasts={toasts} />
    </>
  )
}

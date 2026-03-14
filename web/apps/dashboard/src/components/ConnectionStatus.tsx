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
    'bg-emerald-950/90 text-emerald-200 border border-emerald-800/50 backdrop-blur-sm',
  warning:
    'bg-amber-950/90 text-amber-200 border border-amber-800/50 backdrop-blur-sm',
  error:
    'bg-red-950/90 text-red-200 border border-red-800/50 backdrop-blur-sm',
}

function ToastContainer({ toasts }: { toasts: Toast[] }) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`px-4 py-2.5 rounded-lg text-sm shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-200 ${toastStyles[t.variant]}`}
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
    dot: 'bg-emerald-500',
    label: 'Live',
    tooltip: 'Connected',
  },
  connecting: {
    dot: 'bg-amber-500 animate-pulse',
    label: 'Connecting...',
    tooltip: 'Connecting...',
  },
  reconnecting: {
    dot: 'bg-amber-500 animate-pulse',
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
      <div className="flex items-center gap-2 rounded-full border border-border/50 px-2.5 py-1" title={tooltip}>
        <span className={`${dot} rounded-full size-1.5`} />
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>

      {/* Warning banner */}
      {showBanner && (
        <div className="fixed top-12 left-0 right-0 z-40 bg-amber-500/90 text-black text-sm text-center py-1.5 px-4 font-medium backdrop-blur-sm">
          Real-time updates paused &mdash; reconnecting...
        </div>
      )}

      {/* Toast container */}
      <ToastContainer toasts={toasts} />
    </>
  )
}

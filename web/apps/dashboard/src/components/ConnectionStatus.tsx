import { useEffect, useRef } from 'react'
import { toast } from 'sonner'

import { useEventStream } from '@/hooks/useEventStream'
import type { ReadyState } from '@/lib/ws'

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
        toast.success('Connected to live updates')
        break
      case 'reconnecting':
        toast.warning('Connection lost, reconnecting...')
        break
      case 'disconnected':
        toast.error('Disconnected from live updates')
        break
      // 'connecting' -- no toast
    }
  }, [readyState])

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
    </>
  )
}

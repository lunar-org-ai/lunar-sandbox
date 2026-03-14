import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable'
import { ACTION_TYPES, getActionColor, type TraceSpan } from '@/lib/trace-utils'
import { cn } from '@/lib/utils'
import { TraceTimelineHeader } from './TraceTimelineHeader'
import { TraceTimelineRowBar, TraceTimelineRowLabel } from './TraceTimelineRow'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TraceTimelineProps {
  spans: TraceSpan[]
  isLive: boolean
  totalSpans: number
  onSpanSelect?: (span: TraceSpan | null) => void
  selectedSpanId?: string | null
  /** Episode is still running (not yet complete) */
  isRunning?: boolean
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ZOOM_MIN = 0.25
const ZOOM_MAX = 10
const ZOOM_STEP = 0.15
const AT_BOTTOM_THRESHOLD_PX = 50

// ---------------------------------------------------------------------------
// TraceTimeline
// ---------------------------------------------------------------------------

export function TraceTimeline({
  spans,
  isLive,
  totalSpans,
  onSpanSelect,
  selectedSpanId,
  isRunning = false,
}: TraceTimelineProps) {
  // --- Legend filter state ---
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set())

  // --- Zoom state ---
  const [zoom, setZoom] = useState(1)

  // --- Refs for synchronized scrolling ---
  const labelScrollRef = useRef<HTMLDivElement>(null)
  const barScrollRef = useRef<HTMLDivElement>(null)
  const syncingRef = useRef(false)

  // Ref for attaching the wheel listener (non-passive)
  const barPanelRef = useRef<HTMLDivElement>(null)

  // --- Auto-scroll / new events tracking ---
  const isAtBottomRef = useRef(true)
  const prevSpanCountRef = useRef(spans.length)
  const [newCount, setNewCount] = useState(0)

  // --- Derived: totalMs ---
  const totalMs = useMemo(() => {
    if (spans.length === 0) return 1
    let max = 1
    for (const span of spans) {
      const end = span.startMs + span.durationMs
      if (end > max) max = end
    }
    return max
  }, [spans])

  // --- Derived: filteredSpans ---
  const filteredSpans = useMemo(
    () => spans.filter((s) => !hiddenTypes.has(s.action)),
    [spans, hiddenTypes],
  )

  // --- Toggle legend filter ---
  const toggleType = useCallback((type: string) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) {
        next.delete(type)
      } else {
        next.add(type)
      }
      return next
    })
  }, [])

  // --- Handle span selection ---
  const handleSpanClick = useCallback(
    (span: TraceSpan) => {
      if (!onSpanSelect) return
      if (selectedSpanId === span.id) {
        onSpanSelect(null)
      } else {
        onSpanSelect(span)
      }
    },
    [onSpanSelect, selectedSpanId],
  )

  // --- Auto-scroll to latest when live and at bottom ---
  useEffect(() => {
    if (!isLive) {
      // Reset counters for historical episodes
      prevSpanCountRef.current = spans.length
      setNewCount(0)
      return
    }

    const currentCount = spans.length
    const prevCount = prevSpanCountRef.current
    prevSpanCountRef.current = currentCount

    if (currentCount <= prevCount) return // no new spans

    const newlyArrived = currentCount - prevCount

    if (isAtBottomRef.current) {
      // Auto-scroll the bar panel
      const barEl = barScrollRef.current
      if (barEl) {
        barEl.scrollTo({ top: barEl.scrollHeight, behavior: 'smooth' })
      }
      // Reset new count since we're following the stream
      setNewCount(0)
    } else {
      // User has scrolled away — increment counter
      setNewCount((prev) => prev + newlyArrived)
    }
  }, [isLive, spans.length])

  // --- Check if at bottom helper ---
  const checkAtBottom = useCallback((el: HTMLDivElement) => {
    return el.scrollHeight - el.scrollTop - el.clientHeight < AT_BOTTOM_THRESHOLD_PX
  }, [])

  // --- Scroll to bottom and reset new count ---
  const scrollToBottom = useCallback(() => {
    const barEl = barScrollRef.current
    if (barEl) {
      barEl.scrollTo({ top: barEl.scrollHeight, behavior: 'smooth' })
    }
    isAtBottomRef.current = true
    setNewCount(0)
  }, [])

  // --- Synchronized vertical scrolling ---
  const onLabelScroll = useCallback(() => {
    if (syncingRef.current) return
    const labelEl = labelScrollRef.current
    const barEl = barScrollRef.current
    if (!labelEl || !barEl) return
    syncingRef.current = true
    barEl.scrollTop = labelEl.scrollTop
    syncingRef.current = false
  }, [])

  const onBarScroll = useCallback(() => {
    if (syncingRef.current) return
    const labelEl = labelScrollRef.current
    const barEl = barScrollRef.current
    if (!labelEl || !barEl) return
    syncingRef.current = true
    labelEl.scrollTop = barEl.scrollTop
    syncingRef.current = false

    // Update "at bottom" tracking
    if (barEl) {
      isAtBottomRef.current = checkAtBottom(barEl)
      if (isAtBottomRef.current) {
        setNewCount(0)
      }
    }
  }, [checkAtBottom])

  // --- Ctrl/Cmd + scroll zoom (non-passive) ---
  useEffect(() => {
    const el = barPanelRef.current
    if (!el) return

    function handleWheel(e: WheelEvent) {
      if (!e.ctrlKey && !e.metaKey) return
      e.preventDefault()

      const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP
      setZoom((prev) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, prev + delta)))
    }

    el.addEventListener('wheel', handleWheel, { passive: false })
    return () => {
      el.removeEventListener('wheel', handleWheel)
    }
  }, [])

  // Determine which span should pulse (last span during live mode)
  const lastSpanId = useMemo(() => {
    if (!isLive || filteredSpans.length === 0) return null
    const lastSpan = filteredSpans[filteredSpans.length - 1]
    if (!lastSpan) return null
    return lastSpan.status === 'running' || lastSpan.status === 'completed'
      ? lastSpan.id
      : null
  }, [isLive, filteredSpans])

  // --- Empty state ---
  if (spans.length === 0) {
    return (
      <div className="flex h-full flex-col">
        <StatusBar isLive={isLive || isRunning} totalSpans={totalSpans} />
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm text-zinc-500">
          {isLive || isRunning ? (
            <>
              <span className="relative flex size-4">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                <span className="relative inline-flex size-4 rounded-full bg-blue-500" />
              </span>
              <span>Waiting for trace events…</span>
            </>
          ) : (
            <span>No trace events</span>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      {/* 1. Status bar */}
      <StatusBar isLive={isLive || isRunning} totalSpans={totalSpans} />

      {/* 2. Legend bar */}
      <div className="flex flex-wrap gap-1.5 border-b border-zinc-800 px-3 py-2">
        {ACTION_TYPES.map((type) => {
          const color = getActionColor(type)
          const isHidden = hiddenTypes.has(type)
          return (
            <button
              key={type}
              type="button"
              onClick={() => toggleType(type)}
              className={cn(
                'flex items-center gap-1 rounded px-1.5 py-0.5 text-xs transition-opacity',
                isHidden ? 'opacity-40' : 'opacity-100',
              )}
            >
              {/* Colored square chip */}
              <span
                className={cn('inline-block shrink-0 rounded-sm', color.bg)}
                style={{ width: 12, height: 12 }}
              />
              <span
                className={cn(
                  'text-zinc-300 transition-colors',
                  isHidden && 'text-zinc-500 line-through',
                )}
              >
                {type}
              </span>
            </button>
          )
        })}
      </div>

      {/* 3. Timeline body — resizable label / bar split */}
      <div className="flex min-h-0 flex-1">
        <ResizablePanelGroup orientation="horizontal" className="h-full">
          {/* Left panel — labels */}
          <ResizablePanel defaultSize={25} minSize={15}>
            <div className="flex h-full flex-col overflow-hidden">
              {/* Header placeholder to align with time axis header height */}
              <div
                className="shrink-0 border-b border-zinc-800 bg-zinc-900/95"
                style={{ height: 28 }}
              >
                <span className="flex h-full items-center px-2 text-xs text-zinc-500">
                  Step
                </span>
              </div>
              {/* Scrollable label list */}
              <div
                ref={labelScrollRef}
                className="flex-1 overflow-y-auto overflow-x-hidden"
                onScroll={onLabelScroll}
              >
                {filteredSpans.map((span) => (
                  <TraceTimelineRowLabel
                    key={span.id}
                    span={span}
                    isSelected={selectedSpanId === span.id}
                    onClick={() => handleSpanClick(span)}
                  />
                ))}
              </div>
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Right panel — time axis + bars */}
          <ResizablePanel defaultSize={75} minSize={40}>
            <div
              ref={barPanelRef}
              className="flex h-full flex-col overflow-hidden"
            >
              {/* Sticky time axis header — must be inside the scrolling container
                  so it sticks at the top of the bar panel */}
              <div className="shrink-0 overflow-x-auto overflow-y-hidden">
                <TraceTimelineHeader totalMs={totalMs} zoom={zoom} />
              </div>

              {/* Scrollable bar list */}
              <div
                ref={barScrollRef}
                className="flex-1 overflow-auto"
                onScroll={onBarScroll}
              >
                {filteredSpans.map((span) => (
                  <TraceTimelineRowBar
                    key={span.id}
                    span={span}
                    totalMs={totalMs}
                    zoom={zoom}
                    isSelected={selectedSpanId === span.id}
                    isPulsing={span.id === lastSpanId}
                    onClick={() => handleSpanClick(span)}
                  />
                ))}
              </div>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      {/* 4. "New events" floating pill badge */}
      {isLive && !isAtBottomRef.current && newCount > 0 && (
        <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
          <button
            type="button"
            onClick={scrollToBottom}
            className="pointer-events-auto bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium px-3 py-1.5 rounded-full shadow-lg cursor-pointer transition-colors"
          >
            {newCount} new event{newCount !== 1 ? 's' : ''} &darr;
          </button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// StatusBar
// ---------------------------------------------------------------------------

interface StatusBarProps {
  isLive: boolean
  totalSpans: number
}

function StatusBar({ isLive, totalSpans }: StatusBarProps) {
  return (
    <div className="flex items-center gap-2 border-b border-zinc-800 px-3 py-1.5 text-xs">
      {isLive ? (
        <>
          {/* Pulsing live indicator */}
          <span className="relative flex size-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
            <span className="relative inline-flex size-2 rounded-full bg-green-500" />
          </span>
          <span className="font-semibold text-green-400">LIVE</span>
          <span className="text-zinc-400">Running</span>
        </>
      ) : (
        <>
          <span className="size-2 rounded-full bg-zinc-500" />
          <span className="text-zinc-300">Complete</span>
        </>
      )}
      <span className="ml-auto text-zinc-500">{totalSpans} steps</span>
    </div>
  )
}

import { formatDurationMs, getActionColor, type TraceSpan } from '@/lib/trace-utils'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// TraceTimelineRow – label + bar for a single span
// ---------------------------------------------------------------------------

interface TraceTimelineRowBaseProps {
  span: TraceSpan
  isSelected: boolean
  onClick: () => void
}

interface TraceTimelineRowBarProps extends TraceTimelineRowBaseProps {
  totalMs: number
  zoom: number
  isPulsing?: boolean
}

// ---------------------------------------------------------------------------
// TraceTimelineRowLabel — left panel: index, action type, duration
// ---------------------------------------------------------------------------

export function TraceTimelineRowLabel({
  span,
  isSelected,
  onClick,
}: TraceTimelineRowBaseProps) {
  const color = getActionColor(span.action)

  return (
    <div
      className={cn(
        'flex h-8 cursor-pointer items-center gap-1.5 border-b border-zinc-800/50 px-2 text-xs',
        'hover:bg-zinc-800/60 transition-colors',
        isSelected && 'bg-zinc-800',
      )}
      style={{ paddingLeft: `${8 + span.depth * 16}px` }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onClick()
      }}
    >
      {/* Colored action type dot */}
      <span
        className={cn('inline-block size-2 shrink-0 rounded-full', color.bg)}
      />
      {/* Step index */}
      <span className="shrink-0 font-mono text-zinc-500">
        {span.stepIdx + 1}
      </span>
      {/* Action type name */}
      <span className="truncate text-zinc-300">{span.action}</span>
      {/* Duration */}
      <span className="ml-auto shrink-0 font-mono text-zinc-500">
        {formatDurationMs(span.durationMs)}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TraceTimelineRowBar — right panel: horizontal duration bar
// ---------------------------------------------------------------------------

const ERROR_STATUSES = new Set<string>(['error', 'timeout'])

export function TraceTimelineRowBar({
  span,
  totalMs,
  zoom,
  isSelected,
  isPulsing = false,
  onClick,
}: TraceTimelineRowBarProps) {
  const color = getActionColor(span.action)
  const isError = ERROR_STATUSES.has(span.status)

  // Compute bar position as percentages relative to total duration,
  // then apply zoom factor so the bar container scales with the header.
  const leftPct = totalMs > 0 ? (span.startMs / totalMs) * 100 : 0
  const widthPct = totalMs > 0 ? (span.durationMs / totalMs) * 100 : 0

  // Minimum 2px visual width: we use a min-width style for zero-duration spans.
  // We keep percentage-based left/width and add minWidth on the bar element itself.

  return (
    <div
      className={cn(
        'relative flex h-8 cursor-pointer items-center border-b border-zinc-800/50',
        'hover:bg-zinc-800/30 transition-colors',
        isSelected && 'bg-zinc-800/50',
      )}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onClick()
      }}
      style={{
        // Width tracks zoom so bars align with the header
        width: `${zoom * 100}%`,
        minWidth: '100%',
      }}
    >
      {/* Duration bar */}
      <div
        className={cn(
          'absolute h-5 rounded-sm',
          color.bg,
          isError && 'border-2 border-red-500',
          isSelected ? 'opacity-100 ring-1 ring-white/30' : 'opacity-80 hover:opacity-100',
          isPulsing && 'animate-pulse',
        )}
        style={{
          left: `${leftPct}%`,
          width: `${widthPct}%`,
          minWidth: 2,
          ...(isError
            ? {
                backgroundImage:
                  'repeating-linear-gradient(45deg, transparent, transparent 3px, rgba(239,68,68,0.3) 3px, rgba(239,68,68,0.3) 6px)',
              }
            : {}),
        }}
      />
    </div>
  )
}

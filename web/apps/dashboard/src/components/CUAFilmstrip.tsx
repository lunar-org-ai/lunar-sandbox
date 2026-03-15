import { useEffect, useRef } from 'react'

import { cuaScreenshotUrl } from '@/lib/api'
import type { TraceSpan } from '@/lib/trace-utils'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// CUAFilmstrip Props
// ---------------------------------------------------------------------------

interface CUAFilmstripProps {
  episodeId: string
  steps: TraceSpan[]
  currentStep: number
  onSelectStep: (idx: number) => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Extract screenshot filename from a span's observation dict.
 * CUA observations store `screenshot_path` as a relative filename (e.g., "step_0001.jpg").
 */
function extractScreenshotPath(span: TraceSpan): string | null {
  const path = span.observation['screenshot_path']
  if (typeof path === 'string' && path.length > 0) {
    // Extract just the filename (path is relative like "screenshots/step_000.jpg")
    const parts = path.split('/')
    return parts[parts.length - 1]
  }
  return null
}

// ---------------------------------------------------------------------------
// CUAFilmstrip
// ---------------------------------------------------------------------------

export function CUAFilmstrip({
  episodeId,
  steps,
  currentStep,
  onSelectStep,
}: CUAFilmstripProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const selectedRef = useRef<HTMLButtonElement | null>(null)

  // Auto-scroll the selected thumbnail into the center of the filmstrip
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ inline: 'center', behavior: 'smooth' })
  }, [currentStep])

  if (steps.length === 0) {
    return (
      <div className="flex items-center justify-center h-24 bg-muted/50 text-xs text-muted-foreground">
        No screenshots
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="flex flex-row gap-1.5 overflow-x-auto bg-muted/50 px-3 py-2 h-24 items-center shrink-0"
    >
      {steps.map((span, idx) => {
        const screenshotPath = extractScreenshotPath(span)
        const isSelected = idx === currentStep
        const src = screenshotPath ? cuaScreenshotUrl(episodeId, screenshotPath) : null

        return (
          <button
            key={span.id}
            ref={isSelected ? selectedRef : null}
            type="button"
            onClick={() => onSelectStep(idx)}
            className={cn(
              'relative shrink-0 w-32 aspect-video rounded-md cursor-pointer overflow-hidden transition-all',
              isSelected
                ? 'border-2 border-blue-500 ring-1 ring-blue-500/30'
                : 'border border-border/30 hover:border-border/60',
            )}
            title={`Step ${idx + 1}: ${span.action}`}
          >
            {src ? (
              <img
                src={src}
                alt={`Step ${idx + 1}`}
                loading="lazy"
                className="w-full h-full object-cover"
              />
            ) : (
              /* Placeholder for steps without screenshots */
              <div className="w-full h-full bg-muted flex items-center justify-center">
                <span className="text-[10px] text-muted-foreground font-mono truncate px-1">
                  {span.action}
                </span>
              </div>
            )}

            {/* Step number label */}
            <span className="absolute bottom-0.5 left-1 text-[9px] font-mono font-semibold text-white drop-shadow-[0_1px_1px_rgba(0,0,0,0.9)] leading-none">
              {idx + 1}
            </span>
          </button>
        )
      })}
    </div>
  )
}

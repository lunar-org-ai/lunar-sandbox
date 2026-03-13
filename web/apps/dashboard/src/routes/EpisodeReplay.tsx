import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Pause,
  Play,
  SkipBack,
  SkipForward,
} from 'lucide-react'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DiffViewer, type FileDiffEntry } from '@/components/DiffViewer'
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchEpisode, type EpisodeDetail } from '@/lib/api'
import {
  formatDurationMs,
  getActionColor,
  stepsToSpans,
  type TraceSpan,
} from '@/lib/trace-utils'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Speed = 0.5 | 1 | 2

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusIcon(status: TraceSpan['status']): string {
  switch (status) {
    case 'success':
    case 'completed':
      return '✓'
    case 'error':
      return '✗'
    case 'timeout':
      return '⏱'
    case 'running':
      return '…'
    default:
      return '·'
  }
}

function statusColor(status: TraceSpan['status']): string {
  switch (status) {
    case 'success':
    case 'completed':
      return 'text-green-400'
    case 'error':
      return 'text-red-400'
    case 'timeout':
      return 'text-orange-400'
    case 'running':
      return 'text-blue-400'
    default:
      return 'text-zinc-400'
  }
}

function extractFileDiffs(span: TraceSpan): FileDiffEntry[] {
  const raw = (span.observation['file_diff'] ?? span.params['file_diff']) as
    | { created?: string[]; modified?: string[]; deleted?: string[] }
    | undefined

  if (!raw) return []

  const files: FileDiffEntry[] = []
  if (raw.created) {
    for (const path of raw.created) {
      files.push({ path, type: 'A' })
    }
  }
  if (raw.modified) {
    for (const path of raw.modified) {
      files.push({ path, type: 'M' })
    }
  }
  if (raw.deleted) {
    for (const path of raw.deleted) {
      files.push({ path, type: 'D' })
    }
  }
  return files
}

// ---------------------------------------------------------------------------
// StepList
// ---------------------------------------------------------------------------

interface StepListProps {
  spans: TraceSpan[]
  currentStep: number
  onSelect: (idx: number) => void
}

function StepList({ spans, currentStep, onSelect }: StepListProps) {
  const selectedRef = useRef<HTMLButtonElement | null>(null)

  // Scroll selected item into view
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [currentStep])

  if (spans.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-xs text-zinc-500">
        No steps
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto bg-zinc-900">
      <div className="px-2 py-2 text-[10px] uppercase tracking-wider text-zinc-500 font-semibold border-b border-zinc-800">
        Steps ({spans.length})
      </div>
      {spans.map((span, idx) => {
        const color = getActionColor(span.action)
        const isSelected = idx === currentStep
        return (
          <button
            key={span.id}
            ref={isSelected ? selectedRef : null}
            type="button"
            onClick={() => onSelect(idx)}
            className={cn(
              'w-full text-left px-3 py-2 flex items-start gap-2 hover:bg-zinc-800/60 transition-colors border-b border-zinc-800/50',
              isSelected && 'bg-zinc-800',
            )}
          >
            {/* Step number */}
            <span className="shrink-0 text-[10px] font-mono text-zinc-500 w-5 pt-0.5 text-right">
              {idx + 1}
            </span>

            {/* Color dot */}
            <span
              className={cn(
                'shrink-0 mt-1 size-2 rounded-full',
                color.bg,
              )}
            />

            {/* Action + duration */}
            <div className="flex-1 min-w-0">
              <span className="block text-xs font-mono text-zinc-200 truncate">
                {span.action}
              </span>
              <span className="block text-[10px] text-zinc-500 mt-0.5">
                {formatDurationMs(span.durationMs)}
              </span>
            </div>

            {/* Status icon */}
            <span className={cn('shrink-0 text-xs font-bold mt-0.5', statusColor(span.status))}>
              {statusIcon(span.status)}
            </span>
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// StatePanel — right side showing I/O, Diffs, Screenshot
// ---------------------------------------------------------------------------

interface StatePanelProps {
  span: TraceSpan
  episodeId: string
}

function StatePanel({ span }: StatePanelProps) {
  const fileDiffs = extractFileDiffs(span)
  const diffCount = fileDiffs.length

  const screenshot =
    typeof span.observation['screenshot'] === 'string'
      ? (span.observation['screenshot'] as string)
      : null

  return (
    <Tabs defaultValue="io" className="flex flex-col h-full">
      <TabsList className="shrink-0 w-full rounded-none border-b border-zinc-800 bg-zinc-900 justify-start gap-0 px-3 py-0 h-9">
        <TabsTrigger
          value="io"
          className="rounded-none h-full px-3 text-xs data-[state=active]:border-b-2 data-[state=active]:border-blue-400 data-[state=active]:bg-transparent"
        >
          I/O
        </TabsTrigger>
        <TabsTrigger
          value="diffs"
          className="rounded-none h-full px-3 text-xs data-[state=active]:border-b-2 data-[state=active]:border-blue-400 data-[state=active]:bg-transparent"
        >
          {diffCount > 0 ? `Diffs (${diffCount})` : 'Diffs'}
        </TabsTrigger>
        {screenshot && (
          <TabsTrigger
            value="screenshot"
            className="rounded-none h-full px-3 text-xs data-[state=active]:border-b-2 data-[state=active]:border-blue-400 data-[state=active]:bg-transparent"
          >
            Screenshot
          </TabsTrigger>
        )}
      </TabsList>

      {/* I/O tab */}
      <TabsContent value="io" className="flex-1 overflow-auto m-0 p-4">
        <div className="space-y-4">
          {/* Timing */}
          <div>
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1.5">
              Timing
            </p>
            <div className="flex gap-3 text-xs">
              <span className="text-zinc-400">
                Start:{' '}
                <span className="font-mono text-zinc-200">
                  {formatDurationMs(span.startMs)}
                </span>
              </span>
              <span className="text-zinc-400">
                Duration:{' '}
                <span className="font-mono text-zinc-200">
                  {formatDurationMs(span.durationMs)}
                </span>
              </span>
            </div>
          </div>

          {/* Input */}
          <div>
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1.5">
              Input
            </p>
            <pre className="text-xs font-mono bg-zinc-950 text-zinc-300 p-3 rounded border border-zinc-800 overflow-auto max-h-60 whitespace-pre-wrap break-words">
              {JSON.stringify(span.params, null, 2)}
            </pre>
          </div>

          {/* Output */}
          <div>
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1.5">
              Output
            </p>
            <pre className="text-xs font-mono bg-zinc-950 text-zinc-300 p-3 rounded border border-zinc-800 overflow-auto max-h-60 whitespace-pre-wrap break-words">
              {JSON.stringify(span.observation, null, 2)}
            </pre>
          </div>
        </div>
      </TabsContent>

      {/* Diffs tab */}
      <TabsContent value="diffs" className="flex-1 overflow-hidden m-0">
        <div className="h-full">
          <DiffViewer files={fileDiffs} />
        </div>
      </TabsContent>

      {/* Screenshot tab (conditional) */}
      {screenshot && (
        <TabsContent value="screenshot" className="flex-1 overflow-auto m-0 p-4">
          <img
            src={screenshot.startsWith('data:') ? screenshot : `data:image/png;base64,${screenshot}`}
            alt={`Step ${span.stepIdx + 1} screenshot`}
            className="max-w-full rounded border border-zinc-800"
          />
        </TabsContent>
      )}
    </Tabs>
  )
}

// ---------------------------------------------------------------------------
// PlaybackControls
// ---------------------------------------------------------------------------

interface PlaybackControlsProps {
  playing: boolean
  speed: Speed
  currentStep: number
  totalSteps: number
  onPlay: () => void
  onPause: () => void
  onPrev: () => void
  onNext: () => void
  onFirst: () => void
  onLast: () => void
  onSpeedChange: (s: Speed) => void
  onScrub: (idx: number) => void
}

const SPEEDS: Speed[] = [0.5, 1, 2]

function PlaybackControls({
  playing,
  speed,
  currentStep,
  totalSteps,
  onPlay,
  onPause,
  onPrev,
  onNext,
  onFirst,
  onLast,
  onSpeedChange,
  onScrub,
}: PlaybackControlsProps) {
  return (
    <div className="shrink-0 flex flex-col gap-2 bg-zinc-900 border-b border-zinc-800 px-4 py-2">
      {/* Controls row */}
      <div className="flex items-center gap-3">
        {/* Playback buttons */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            title="First step"
            onClick={onFirst}
            disabled={currentStep === 0}
            className="p-1.5 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <SkipBack className="size-3.5" />
          </button>
          <button
            type="button"
            title="Previous step"
            onClick={onPrev}
            disabled={currentStep === 0}
            className="p-1.5 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="size-3.5" />
          </button>
          <button
            type="button"
            title={playing ? 'Pause' : 'Play'}
            onClick={playing ? onPause : onPlay}
            disabled={totalSteps === 0}
            className="p-1.5 rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
          </button>
          <button
            type="button"
            title="Next step"
            onClick={onNext}
            disabled={currentStep >= totalSteps - 1}
            className="p-1.5 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronRight className="size-3.5" />
          </button>
          <button
            type="button"
            title="Last step"
            onClick={onLast}
            disabled={currentStep >= totalSteps - 1}
            className="p-1.5 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <SkipForward className="size-3.5" />
          </button>
        </div>

        {/* Step counter */}
        <span className="text-xs text-zinc-400 font-mono whitespace-nowrap">
          {totalSteps > 0 ? `${currentStep + 1} / ${totalSteps}` : '0 / 0'}
        </span>

        {/* Speed selector */}
        <div className="ml-auto flex items-center gap-1 bg-zinc-800 rounded-md p-0.5">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onSpeedChange(s)}
              className={cn(
                'px-2 py-0.5 rounded text-xs transition-colors',
                speed === s
                  ? 'bg-zinc-700 text-zinc-200'
                  : 'text-zinc-500 hover:text-zinc-300',
              )}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      {/* Timeline scrubber */}
      <input
        type="range"
        min={0}
        max={Math.max(0, totalSteps - 1)}
        value={currentStep}
        onChange={(e) => onScrub(Number(e.target.value))}
        className="w-full h-1.5 accent-blue-500 cursor-pointer"
        disabled={totalSteps === 0}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// EpisodeReplay — main page
// ---------------------------------------------------------------------------

export default function EpisodeReplay() {
  const { id } = useParams<{ id: string }>()
  const episodeId = id ?? ''
  const [searchParams] = useSearchParams()

  // Episode data
  const [episode, setEpisode] = useState<EpisodeDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)

  // Derived spans
  const [spans, setSpans] = useState<TraceSpan[]>([])

  // Playback state
  const initialStep = parseInt(searchParams.get('step') ?? '0', 10)
  const [currentStep, setCurrentStep] = useState(isNaN(initialStep) ? 0 : initialStep)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<Speed>(1)

  // Interval ref for auto-play
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ---------------------------------------------------------------------------
  // Load episode
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!episodeId) return
    setLoading(true)
    fetchEpisode(episodeId)
      .then((data) => {
        setEpisode(data)
        const steps = stepsToSpans(
          data.steps as Record<string, unknown>[],
          data.started_at,
          episodeId,
        )
        setSpans(steps)
        setLoading(false)
      })
      .catch((e: Error) => {
        setFetchError(e.message.includes('404') ? 'Episode not found.' : e.message)
        setLoading(false)
      })
  }, [episodeId])

  // Clamp currentStep when spans load
  useEffect(() => {
    if (spans.length > 0) {
      setCurrentStep((prev) => Math.min(prev, spans.length - 1))
    }
  }, [spans.length])

  // ---------------------------------------------------------------------------
  // Auto-play
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    if (!playing || spans.length === 0) return

    intervalRef.current = setInterval(() => {
      setCurrentStep((prev) => {
        if (prev >= spans.length - 1) {
          setPlaying(false)
          return prev
        }
        return prev + 1
      })
    }, Math.round(1000 / speed))

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [playing, speed, spans.length])

  // ---------------------------------------------------------------------------
  // Keyboard shortcuts
  // ---------------------------------------------------------------------------

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Ignore if focus is in an input/textarea
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return

      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault()
          setPlaying(false)
          setCurrentStep((prev) => Math.max(0, prev - 1))
          break
        case 'ArrowRight':
          e.preventDefault()
          setPlaying(false)
          setCurrentStep((prev) => Math.min(spans.length - 1, prev + 1))
          break
        case ' ':
          e.preventDefault()
          setPlaying((prev) => !prev)
          break
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [spans.length])

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handleSelectStep(idx: number) {
    setPlaying(false)
    setCurrentStep(idx)
  }

  function handleScrub(idx: number) {
    setPlaying(false)
    setCurrentStep(idx)
  }

  // ---------------------------------------------------------------------------
  // Render: loading / error states
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="flex flex-col h-screen bg-neutral-950">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800 bg-zinc-900">
          <Skeleton className="h-5 w-20" />
          <Skeleton className="h-5 w-48" />
        </div>
        <div className="flex flex-1 overflow-hidden">
          <div className="w-64 border-r border-zinc-800 p-3 space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
          <div className="flex-1 p-6 space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-64 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        </div>
      </div>
    )
  }

  if (fetchError) {
    return (
      <div className="flex flex-col h-screen bg-neutral-950">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800 bg-zinc-900">
          <Link
            to={`/runs/${episodeId}`}
            className="inline-flex items-center gap-1 text-sm text-neutral-400 hover:text-neutral-200"
          >
            <ArrowLeft className="size-4" />
            Back
          </Link>
        </div>
        <div className="flex items-center justify-center flex-1">
          <p className="text-red-400 text-sm">{fetchError}</p>
        </div>
      </div>
    )
  }

  if (!episode) return null

  const currentSpan = spans[currentStep] ?? null

  return (
    <div className="flex flex-col h-screen bg-neutral-950 overflow-hidden">
      {/* ------------------------------------------------------------------ */}
      {/* Header bar                                                          */}
      {/* ------------------------------------------------------------------ */}
      <div className="shrink-0 flex items-center gap-3 px-4 py-2 border-b border-zinc-800 bg-zinc-900 min-w-0">
        <Link
          to={`/runs/${episodeId}`}
          className="shrink-0 inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          <ArrowLeft className="size-4" />
          Back
        </Link>

        <span className="text-zinc-700">|</span>

        <span className="text-xs font-mono text-zinc-300 truncate min-w-0">
          {episodeId}
        </span>

        {episode.task_name && (
          <span className="hidden sm:block text-xs text-zinc-500 truncate">
            {episode.task_name}
          </span>
        )}

        <span className="ml-auto text-[10px] text-zinc-600 font-mono hidden md:block">
          Space: play/pause &nbsp;|&nbsp; &larr;&rarr;: step
        </span>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Body: ResizablePanelGroup                                           */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex-1 min-h-0">
        <ResizablePanelGroup orientation="horizontal" className="h-full">
          {/* Left panel: step list */}
          <ResizablePanel defaultSize={25} minSize={15}>
            <StepList
              spans={spans}
              currentStep={currentStep}
              onSelect={handleSelectStep}
            />
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Right panel: playback controls + state panel */}
          <ResizablePanel defaultSize={75} minSize={40}>
            <div className="flex flex-col h-full overflow-hidden">
              {/* Playback controls */}
              <PlaybackControls
                playing={playing}
                speed={speed}
                currentStep={currentStep}
                totalSteps={spans.length}
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                onPrev={() => {
                  setPlaying(false)
                  setCurrentStep((prev) => Math.max(0, prev - 1))
                }}
                onNext={() => {
                  setPlaying(false)
                  setCurrentStep((prev) => Math.min(spans.length - 1, prev + 1))
                }}
                onFirst={() => {
                  setPlaying(false)
                  setCurrentStep(0)
                }}
                onLast={() => {
                  setPlaying(false)
                  setCurrentStep(spans.length - 1)
                }}
                onSpeedChange={(s) => setSpeed(s)}
                onScrub={handleScrub}
              />

              {/* State content */}
              <div className="flex-1 min-h-0 overflow-hidden">
                {currentSpan ? (
                  <StatePanel
                    span={currentSpan}
                    episodeId={episodeId}
                  />
                ) : (
                  <div className="flex items-center justify-center h-full text-xs text-zinc-500">
                    {spans.length === 0 ? 'No steps in this episode.' : 'Select a step'}
                  </div>
                )}
              </div>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  )
}

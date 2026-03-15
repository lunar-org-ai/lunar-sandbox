import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Pause,
  Play,
  SkipBack,
  SkipForward,
} from 'lucide-react'
import { useHotkeys } from 'react-hotkeys-hook'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { DiffViewer, type FileDiffEntry } from '@/components/DiffViewer'
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable'
import { Skeleton } from '@/components/ui/skeleton'
import { CUAFilmstrip } from '@/components/CUAFilmstrip'
import { ManualReviewSidebar } from '@/components/ManualReviewSidebar'
import {
  fetchEpisode,
  fetchCUAEpisodeDetail,
  cuaScreenshotUrl,
  type EpisodeDetail,
  type CUAEpisodeInfo,
} from '@/lib/api'
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
      return '\u2713'
    case 'error':
      return '\u2717'
    case 'timeout':
      return '\u23F1'
    case 'running':
      return '\u2026'
    default:
      return '\u00B7'
  }
}

function statusColor(status: TraceSpan['status']): string {
  switch (status) {
    case 'success':
    case 'completed':
      return 'text-emerald-400'
    case 'error':
      return 'text-red-400'
    case 'timeout':
      return 'text-amber-400'
    case 'running':
      return 'text-blue-400'
    default:
      return 'text-muted-foreground'
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
      <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
        No steps
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto bg-background">
      <div className="px-3 py-2.5 text-[11px] uppercase tracking-wider text-muted-foreground font-medium border-b border-border/50">
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
              'w-full text-left px-3 py-2 flex items-start gap-2 hover:bg-accent/50 transition-colors border-b border-border/30',
              isSelected && 'bg-accent',
            )}
          >
            {/* Step number */}
            <span className="shrink-0 text-[10px] font-mono text-muted-foreground w-5 pt-0.5 text-right tabular-nums">
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
              <span className="block text-xs font-mono text-foreground truncate">
                {span.action}
              </span>
              <span className="block text-[10px] text-muted-foreground mt-0.5">
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
      <TabsList className="shrink-0 w-full rounded-none border-b border-border/50 bg-background justify-start gap-0 px-3 py-0 h-9">
        <TabsTrigger
          value="io"
          className="rounded-none h-full px-3 text-xs data-[state=active]:border-b-2 data-[state=active]:border-foreground data-[state=active]:bg-transparent"
        >
          I/O
        </TabsTrigger>
        <TabsTrigger
          value="diffs"
          className="rounded-none h-full px-3 text-xs data-[state=active]:border-b-2 data-[state=active]:border-foreground data-[state=active]:bg-transparent"
        >
          {diffCount > 0 ? `Diffs (${diffCount})` : 'Diffs'}
        </TabsTrigger>
        {screenshot && (
          <TabsTrigger
            value="screenshot"
            className="rounded-none h-full px-3 text-xs data-[state=active]:border-b-2 data-[state=active]:border-foreground data-[state=active]:bg-transparent"
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
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5">
              Timing
            </p>
            <div className="flex gap-3 text-xs">
              <span className="text-muted-foreground">
                Start:{' '}
                <span className="font-mono text-foreground tabular-nums">
                  {formatDurationMs(span.startMs)}
                </span>
              </span>
              <span className="text-muted-foreground">
                Duration:{' '}
                <span className="font-mono text-foreground tabular-nums">
                  {formatDurationMs(span.durationMs)}
                </span>
              </span>
            </div>
          </div>

          {/* Input */}
          <div>
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5">
              Input
            </p>
            <pre className="text-xs font-mono bg-muted/50 text-foreground/80 p-3 rounded-md border border-border/50 overflow-auto max-h-60 whitespace-pre-wrap break-words">
              {JSON.stringify(span.params, null, 2)}
            </pre>
          </div>

          {/* Output */}
          <div>
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5">
              Output
            </p>
            <pre className="text-xs font-mono bg-muted/50 text-foreground/80 p-3 rounded-md border border-border/50 overflow-auto max-h-60 whitespace-pre-wrap break-words">
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
            className="max-w-full rounded-md border border-border/50"
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
    <div className="shrink-0 flex flex-col gap-2 bg-background border-b border-border/50 px-4 py-2.5">
      {/* Controls row */}
      <div className="flex items-center gap-3">
        {/* Playback buttons */}
        <div className="flex items-center gap-0.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                onClick={onFirst}
                disabled={currentStep === 0}
              >
                <SkipBack className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>First step (Home)</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                onClick={onPrev}
                disabled={currentStep === 0}
              >
                <ChevronLeft className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Previous (k / Left)</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="default"
                size="icon"
                className="size-7"
                onClick={playing ? onPause : onPlay}
                disabled={totalSteps === 0}
              >
                {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{playing ? 'Pause' : 'Play'} (Space)</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                onClick={onNext}
                disabled={currentStep >= totalSteps - 1}
              >
                <ChevronRight className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Next (j / Right)</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                onClick={onLast}
                disabled={currentStep >= totalSteps - 1}
              >
                <SkipForward className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Last step (End)</TooltipContent>
          </Tooltip>
        </div>

        {/* Step counter */}
        <span className="text-xs text-muted-foreground font-mono whitespace-nowrap tabular-nums">
          {totalSteps > 0 ? `${currentStep + 1} / ${totalSteps}` : '0 / 0'}
        </span>

        {/* Speed selector */}
        <ToggleGroup
          type="single"
          value={String(speed)}
          onValueChange={(v) => { if (v) onSpeedChange(Number(v) as Speed) }}
          size="sm"
          variant="outline"
          className="ml-auto"
        >
          {SPEEDS.map((s) => (
            <ToggleGroupItem key={s} value={String(s)} className="px-2 py-0.5 text-xs">
              {s}x
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      {/* Timeline scrubber */}
      <Slider
        min={0}
        max={Math.max(0, totalSteps - 1)}
        value={[currentStep]}
        onValueChange={([v]) => onScrub(v)}
        disabled={totalSteps === 0}
        className="w-full"
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

  // CUA-specific state
  const [isCUA, setIsCUA] = useState(false)
  const [cuaDetail, setCuaDetail] = useState<CUAEpisodeInfo | null>(null)

  // Navigation (for post-review redirect)
  const navigate = useNavigate()

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

        // Detect CUA episode: episode_type field or screenshot_path in any step observation
        const hasCUAType = (data as unknown as Record<string, unknown>)['episode_type'] === 'cua'
        const hasScreenshots = steps.some(
          (s) => typeof s.observation['screenshot_path'] === 'string',
        )
        setIsCUA(hasCUAType || hasScreenshots)

        setLoading(false)
      })
      .catch((e: Error) => {
        setFetchError(e.message.includes('404') ? 'Episode not found.' : e.message)
        setLoading(false)
      })
  }, [episodeId])

  // Fetch CUA-specific detail (score, review_notes) when episode is identified as CUA
  useEffect(() => {
    if (!isCUA || !episodeId) return
    fetchCUAEpisodeDetail(episodeId)
      .then(setCuaDetail)
      .catch(() => {
        // Non-fatal: sidebar will just show defaults
      })
  }, [isCUA, episodeId])

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
  // Keyboard shortcuts (react-hotkeys-hook — not fired in form inputs/terminal)
  // ---------------------------------------------------------------------------

  const hotkeyOpts = {
    enableOnFormTags: false,
    ignoreEventWhen: (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      return (
        target.classList.contains('xterm-helper-textarea') ||
        !!target.closest('.xterm')
      )
    },
  } as const

  useHotkeys(
    'arrowleft',
    (e) => {
      e.preventDefault()
      setPlaying(false)
      setCurrentStep((prev) => Math.max(0, prev - 1))
    },
    hotkeyOpts,
    [spans.length],
  )

  useHotkeys(
    'arrowright',
    (e) => {
      e.preventDefault()
      setPlaying(false)
      setCurrentStep((prev) => Math.min(spans.length - 1, prev + 1))
    },
    hotkeyOpts,
    [spans.length],
  )

  useHotkeys(
    'j',
    (e) => {
      e.preventDefault()
      setPlaying(false)
      setCurrentStep((prev) => Math.min(spans.length - 1, prev + 1))
    },
    hotkeyOpts,
    [spans.length],
  )

  useHotkeys(
    'k',
    (e) => {
      e.preventDefault()
      setPlaying(false)
      setCurrentStep((prev) => Math.max(0, prev - 1))
    },
    hotkeyOpts,
    [spans.length],
  )

  useHotkeys(
    'space',
    (e) => {
      e.preventDefault()
      setPlaying((prev) => !prev)
    },
    hotkeyOpts,
  )

  useHotkeys(
    'home',
    (e) => {
      e.preventDefault()
      setPlaying(false)
      setCurrentStep(0)
    },
    hotkeyOpts,
  )

  useHotkeys(
    'end',
    (e) => {
      e.preventDefault()
      setPlaying(false)
      setCurrentStep(spans.length - 1)
    },
    hotkeyOpts,
    [spans.length],
  )

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
      <div className="flex flex-col h-screen bg-background">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border/50">
          <Skeleton className="h-5 w-20" />
          <Skeleton className="h-5 w-48" />
        </div>
        <div className="flex flex-1 overflow-hidden">
          <div className="w-64 border-r border-border/50 p-3 space-y-2">
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
      <div className="flex flex-col h-screen bg-background">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border/50">
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link to={`/runs/${episodeId}`}>Run</Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Replay</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </div>
        <div className="flex items-center justify-center flex-1 p-6">
          <Alert variant="destructive" className="max-w-md">
            <AlertCircle className="size-4" />
            <AlertDescription>{fetchError}</AlertDescription>
          </Alert>
        </div>
      </div>
    )
  }

  if (!episode) return null

  const currentSpan = spans[currentStep] ?? null

  // Determine if this CUA episode has a manual reward (needs review sidebar)
  const isManualReview = isCUA && (cuaDetail?.score === null || cuaDetail?.score !== undefined)
  // More precise: show sidebar only when we have cuaDetail and its task uses manual reward.
  // We infer manual reward if score is null (not yet scored) or already has a score
  // (could be re-scored). If cuaDetail hasn't loaded yet, we don't show it.
  const showReviewSidebar = isCUA && cuaDetail !== null

  // Shared playback controls props
  const playbackControlsProps = {
    playing,
    speed,
    currentStep,
    totalSteps: spans.length,
    onPlay: () => setPlaying(true),
    onPause: () => setPlaying(false),
    onPrev: () => {
      setPlaying(false)
      setCurrentStep((prev) => Math.max(0, prev - 1))
    },
    onNext: () => {
      setPlaying(false)
      setCurrentStep((prev) => Math.min(spans.length - 1, prev + 1))
    },
    onFirst: () => {
      setPlaying(false)
      setCurrentStep(0)
    },
    onLast: () => {
      setPlaying(false)
      setCurrentStep(spans.length - 1)
    },
    onSpeedChange: (s: Speed) => setSpeed(s),
    onScrub: handleScrub,
  }

  return (
    <div className="flex flex-col h-screen bg-background overflow-hidden">
      {/* ------------------------------------------------------------------ */}
      {/* Header bar                                                          */}
      {/* ------------------------------------------------------------------ */}
      <div className="shrink-0 flex items-center gap-3 px-4 py-2 border-b border-border/50 min-w-0">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to={`/runs/${episodeId}`}>Run</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage className="font-mono text-xs truncate max-w-[200px]">{episodeId}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>

        {episode.task_name && (
          <span className="hidden sm:block text-xs text-muted-foreground truncate">
            {episode.task_name}
          </span>
        )}

        {isCUA && (
          <Badge variant="outline" className="text-[10px] font-mono bg-blue-500/15 text-blue-400 border-blue-500/30">
            CUA
          </Badge>
        )}

        <span className="ml-auto text-[10px] text-muted-foreground/50 font-mono hidden md:block">
          Space: play/pause &nbsp;|&nbsp; &larr;&rarr; / j k: step &nbsp;|&nbsp; Home/End: first/last
        </span>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Body: CUA layout or coding layout                                  */}
      {/* ------------------------------------------------------------------ */}
      {isCUA ? (
        /* ----------------------------------------------------------------
           CUA Layout:
           +-------------------------------------+------------------+
           |  Full screenshot + action card       | ManualReview    |
           |                                     | Sidebar         |
           +-------------------------------------+------------------+
           | [filmstrip thumbnails -- horizontal scroll]            |
           +-------------------------------------------------------+
           | PlaybackControls                                       |
           +-------------------------------------------------------+
        ---------------------------------------------------------------- */
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          {/* Main area: screenshot viewer + optional review sidebar */}
          <div className="flex-1 min-h-0 flex overflow-hidden">
            {/* Screenshot viewer */}
            <div className="flex-1 min-w-0 overflow-auto p-4 space-y-4">
              {currentSpan ? (
                <>
                  {/* Full-size screenshot */}
                  {(() => {
                    const rawPath = currentSpan.observation['screenshot_path']
                    const filename = typeof rawPath === 'string' ? rawPath.split('/').pop() : null
                    const src = filename ? cuaScreenshotUrl(episodeId, filename) : null
                    return src ? (
                      <img
                        src={src}
                        alt={`Step ${currentStep + 1} screenshot`}
                        className="max-w-full rounded-md border border-border/50 shadow-sm"
                      />
                    ) : (
                      <div className="flex items-center justify-center h-64 rounded-md border border-border/50 bg-muted/30 text-xs text-muted-foreground">
                        No screenshot for this step
                      </div>
                    )
                  })()}

                  {/* Action detail card */}
                  <div className="rounded-md border border-border/50 bg-card/50 p-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-semibold text-foreground">
                        Step {currentStep + 1}
                      </span>
                      <span className="text-[10px] font-mono text-muted-foreground">
                        {currentSpan.action}
                      </span>
                      <span className="ml-auto text-[10px] text-muted-foreground">
                        {formatDurationMs(currentSpan.durationMs)}
                      </span>
                    </div>
                    <div className="space-y-2">
                      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
                        Input
                      </p>
                      <pre className="text-xs font-mono bg-muted/50 text-foreground/80 p-3 rounded-md border border-border/50 overflow-auto max-h-40 whitespace-pre-wrap break-words">
                        {JSON.stringify(currentSpan.params, null, 2)}
                      </pre>
                    </div>
                    {Object.keys(currentSpan.observation).length > 1 && (
                      <div className="space-y-2">
                        <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
                          Observation
                        </p>
                        <pre className="text-xs font-mono bg-muted/50 text-foreground/80 p-3 rounded-md border border-border/50 overflow-auto max-h-40 whitespace-pre-wrap break-words">
                          {JSON.stringify(
                            Object.fromEntries(
                              Object.entries(currentSpan.observation).filter(
                                ([k]) => k !== 'screenshot_path',
                              ),
                            ),
                            null,
                            2,
                          )}
                        </pre>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
                  {spans.length === 0 ? 'No steps in this episode.' : 'Select a step'}
                </div>
              )}
            </div>

            {/* Manual review sidebar */}
            {showReviewSidebar && cuaDetail && (
              <ManualReviewSidebar
                episodeId={episodeId}
                existingScore={cuaDetail.score}
                existingNotes={cuaDetail.review_notes}
                onScoreSubmitted={(nextId) => {
                  if (nextId) {
                    navigate(`/replay/${nextId}`)
                  }
                }}
              />
            )}
          </div>

          {/* Filmstrip */}
          <CUAFilmstrip
            episodeId={episodeId}
            steps={spans}
            currentStep={currentStep}
            onSelectStep={handleSelectStep}
          />

          {/* Playback controls */}
          <PlaybackControls {...playbackControlsProps} />
        </div>
      ) : (
        /* ----------------------------------------------------------------
           Coding episode layout (unchanged)
        ---------------------------------------------------------------- */
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
                <PlaybackControls {...playbackControlsProps} />

                {/* State content */}
                <div className="flex-1 min-h-0 overflow-hidden">
                  {currentSpan ? (
                    <StatePanel
                      span={currentSpan}
                      episodeId={episodeId}
                    />
                  ) : (
                    <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
                      {spans.length === 0 ? 'No steps in this episode.' : 'Select a step'}
                    </div>
                  )}
                </div>
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      )}
    </div>
  )
}

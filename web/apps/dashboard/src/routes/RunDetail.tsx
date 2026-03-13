import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { format } from 'date-fns'
import { ArrowLeft, GitBranch, LayoutGrid, List, RotateCcw } from 'lucide-react'
import type { PanelImperativeHandle } from 'react-resizable-panels'
import { useHotkeys } from 'react-hotkeys-hook'

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable'
import { Skeleton } from '@/components/ui/skeleton'
import { ExportButton } from '@/components/ExportButton'
import { StatusBadge } from '@/components/StatusBadge'
import { TraceDetailPanel } from '@/components/TraceDetailPanel'
import { TraceGraph } from '@/components/TraceGraph'
import { TraceTimeline } from '@/components/TraceTimeline'
import { useTraceStream } from '@/hooks/useTraceStream'
import { fetchEpisode, type EpisodeDetail } from '@/lib/api'
import { flattenEpisodeForCsv } from '@/lib/export-utils'
import { type TraceSpan } from '@/lib/trace-utils'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(ms: number): string {
  if (ms <= 0) return '--'
  const totalSeconds = Math.floor(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds}s`
  return `${minutes}m ${seconds}s`
}

function formatCost(usd: number | null | undefined): string {
  if (usd == null) return '--'
  return `$${usd.toFixed(4)}`
}

function formatDatetime(ts: number | null | undefined): string {
  if (!ts) return '--'
  return format(new Date(ts * 1000), 'MMM d, yyyy HH:mm:ss')
}

// ---------------------------------------------------------------------------
// Metric tile
// ---------------------------------------------------------------------------

interface MetricProps {
  label: string
  value: React.ReactNode
}

function Metric({ label, value }: MetricProps) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-neutral-400 uppercase tracking-wider">{label}</span>
      <span className="text-lg font-semibold">{value}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RunDetail page
// ---------------------------------------------------------------------------

export default function RunDetail() {
  const { id } = useParams<{ id: string }>()
  const episodeId = id ?? ''

  const [episode, setEpisode] = useState<EpisodeDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)

  // Selected span state
  const [selectedSpan, setSelectedSpan] = useState<TraceSpan | null>(null)

  // Ref for the detail panel (for programmatic collapse/expand)
  const detailPanelRef = useRef<PanelImperativeHandle | null>(null)

  useEffect(() => {
    if (!episodeId) return
    setLoading(true)
    fetchEpisode(episodeId)
      .then((data) => {
        setEpisode(data)
        setLoading(false)
      })
      .catch((e: Error) => {
        setFetchError(e.message.includes('404') ? 'Run not found.' : e.message)
        setLoading(false)
      })
  }, [episodeId])

  // Escape key closes the detail panel
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setSelectedSpan(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Collapse/expand detail panel based on selectedSpan
  useEffect(() => {
    const panel = detailPanelRef.current
    if (!panel) return
    if (selectedSpan) {
      panel.expand()
    } else {
      panel.collapse()
    }
  }, [selectedSpan])

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto p-8 space-y-4">
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  if (fetchError) {
    return (
      <div className="max-w-6xl mx-auto p-8 space-y-4">
        <Link
          to="/runs"
          className="inline-flex items-center gap-1 text-sm text-neutral-400 hover:text-neutral-200"
        >
          <ArrowLeft className="size-4" />
          Runs
        </Link>
        <p className="text-red-400 text-sm">{fetchError}</p>
      </div>
    )
  }

  if (!episode) return null

  return (
    <RunDetailContent
      episode={episode}
      episodeId={episodeId}
      selectedSpan={selectedSpan}
      setSelectedSpan={setSelectedSpan}
      detailPanelRef={detailPanelRef}
    />
  )
}

// ---------------------------------------------------------------------------
// RunDetailContent — separated so hooks always run in the same component
// ---------------------------------------------------------------------------

interface RunDetailContentProps {
  episode: EpisodeDetail
  episodeId: string
  selectedSpan: TraceSpan | null
  setSelectedSpan: (span: TraceSpan | null) => void
  detailPanelRef: React.RefObject<PanelImperativeHandle | null>
}

// ---------------------------------------------------------------------------
// View mode types
// ---------------------------------------------------------------------------

type ViewMode = 'timeline' | 'graph' | 'split'

function RunDetailContent({
  episode,
  episodeId,
  selectedSpan,
  setSelectedSpan,
  detailPanelRef,
}: RunDetailContentProps) {
  // --- useTraceStream integration ---
  const { spans, isLive, totalSpans } = useTraceStream({
    episodeId,
    sandboxId: episode.sandbox_id || null,
    initialSteps: episode.steps as Record<string, unknown>[],
    episodeStartTs: episode.started_at,
  })

  // --- View mode state (synced with ?view= search param) ---
  const [searchParams, setSearchParams] = useSearchParams()
  const viewParam = searchParams.get('view')
  const initialViewMode: ViewMode =
    viewParam === 'graph' || viewParam === 'split' ? viewParam : 'timeline'
  const [viewMode, setViewMode] = useState<ViewMode>(initialViewMode)

  const setViewModeAndParam = (mode: ViewMode) => {
    setViewMode(mode)
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('view', mode)
        return next
      },
      { replace: true },
    )
  }

  // 1/2/3 hotkeys for view switching
  useHotkeys('1', () => setViewModeAndParam('timeline'), { enableOnFormTags: false })
  useHotkeys('2', () => setViewModeAndParam('graph'), { enableOnFormTags: false })
  useHotkeys('3', () => setViewModeAndParam('split'), { enableOnFormTags: false })

  // --- Derive card title from view mode ---
  const cardTitle =
    viewMode === 'timeline'
      ? 'Trace Timeline'
      : viewMode === 'graph'
        ? 'Trace Graph'
        : 'Trace Timeline & Graph'

  return (
    <div className="max-w-6xl mx-auto p-8 space-y-6">
      {/* Breadcrumb / back navigation */}
      <div className="flex items-center gap-2 text-sm text-neutral-400">
        <Link
          to="/runs"
          className="inline-flex items-center gap-1 hover:text-neutral-200 transition-colors"
        >
          <ArrowLeft className="size-4" />
          Runs
        </Link>
        <span>/</span>
        <span className="font-mono text-neutral-300 text-xs truncate max-w-xs">{episodeId}</span>
      </div>

      {/* Outcome Summary Card */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-3 flex-wrap">
              <StatusBadge status={episode.outcome} type="outcome" />
              <span className="font-mono text-sm text-neutral-300 break-all">{episode.episode_id}</span>
              <span className="text-sm text-neutral-400">{episode.task_name}</span>
            </div>
            <div className="flex items-center gap-2">
              {episode.ended_at != null && (
                <Link
                  to={`/replay/${episodeId}`}
                  className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 border border-zinc-700 transition-colors"
                >
                  <RotateCcw className="size-3.5" />
                  Replay
                </Link>
              )}
              <ExportButton
                data={episode}
                filename={`episode-${episodeId}`}
                csvRows={[flattenEpisodeForCsv(episode as Record<string, unknown>)]}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-8 gap-y-6">
            <Metric
              label="Score"
              value={episode.score != null ? episode.score.toFixed(2) : '--'}
            />
            <Metric
              label="Steps"
              value={episode.step_count}
            />
            <Metric
              label="Duration"
              value={formatDuration(episode.duration_ms)}
            />
            <Metric
              label="Cost"
              value={formatCost(episode.cost_usd)}
            />
            <Metric
              label="Started"
              value={
                <span className="text-sm font-normal">{formatDatetime(episode.started_at)}</span>
              }
            />
            <Metric
              label="Ended"
              value={
                <span className="text-sm font-normal">
                  {episode.ended_at ? formatDatetime(episode.ended_at) : 'In progress'}
                </span>
              }
            />
          </div>
        </CardContent>
      </Card>

      {/* Trace Timeline + Detail Panel */}
      <Card className="overflow-hidden rounded-lg border border-zinc-800 p-0">
        <CardHeader className="border-b border-zinc-800 px-4 py-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium text-zinc-300">{cardTitle}</CardTitle>
            {/* View mode toggle */}
            <div className="flex gap-1 bg-zinc-800 rounded-md p-0.5">
              <button
                type="button"
                title="Timeline (1)"
                onClick={() => setViewModeAndParam('timeline')}
                className={`px-2 py-1 rounded text-xs transition-colors ${
                  viewMode === 'timeline'
                    ? 'bg-zinc-700 text-zinc-200'
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                <List className="size-3.5" />
              </button>
              <button
                type="button"
                title="Graph (2)"
                onClick={() => setViewModeAndParam('graph')}
                className={`px-2 py-1 rounded text-xs transition-colors ${
                  viewMode === 'graph'
                    ? 'bg-zinc-700 text-zinc-200'
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                <GitBranch className="size-3.5" />
              </button>
              <button
                type="button"
                title="Split view (3)"
                onClick={() => setViewModeAndParam('split')}
                className={`px-2 py-1 rounded text-xs transition-colors ${
                  viewMode === 'split'
                    ? 'bg-zinc-700 text-zinc-200'
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                <LayoutGrid className="size-3.5" />
              </button>
            </div>
          </div>
        </CardHeader>
        <div
          className="overflow-hidden"
          style={{ height: 'calc(100vh - 420px)', minHeight: 360 }}
        >
          <ResizablePanelGroup orientation="horizontal" className="h-full">
            {/* Left panel: Timeline / Graph / Split */}
            <ResizablePanel defaultSize={selectedSpan ? 65 : 100} minSize={40}>
              {viewMode === 'timeline' && (
                <TraceTimeline
                  spans={spans}
                  isLive={isLive}
                  totalSpans={totalSpans}
                  onSpanSelect={setSelectedSpan}
                  selectedSpanId={selectedSpan?.id ?? null}
                />
              )}
              {viewMode === 'graph' && (
                <TraceGraph
                  spans={spans}
                  isLive={isLive}
                  onSpanSelect={setSelectedSpan}
                  selectedSpanId={selectedSpan?.id ?? null}
                />
              )}
              {viewMode === 'split' && (
                <ResizablePanelGroup orientation="vertical" className="h-full">
                  <ResizablePanel defaultSize={50} minSize={25}>
                    <TraceTimeline
                      spans={spans}
                      isLive={isLive}
                      totalSpans={totalSpans}
                      onSpanSelect={setSelectedSpan}
                      selectedSpanId={selectedSpan?.id ?? null}
                    />
                  </ResizablePanel>
                  <ResizableHandle withHandle />
                  <ResizablePanel defaultSize={50} minSize={25}>
                    <TraceGraph
                      spans={spans}
                      isLive={isLive}
                      onSpanSelect={setSelectedSpan}
                      selectedSpanId={selectedSpan?.id ?? null}
                    />
                  </ResizablePanel>
                </ResizablePanelGroup>
              )}
            </ResizablePanel>

            {/* Handle only visible when detail panel open */}
            {selectedSpan && <ResizableHandle withHandle />}

            {/* Right panel: Detail panel — shared between all view modes */}
            <ResizablePanel
              defaultSize={35}
              minSize={20}
              collapsible
              collapsedSize={0}
              panelRef={detailPanelRef}
            >
              {selectedSpan && (
                <div className="flex flex-col h-full overflow-hidden">
                  <div className="shrink-0 flex items-center justify-end px-3 py-1 bg-zinc-900 border-b border-zinc-800">
                    <Link
                      to={`/replay/${episodeId}?step=${selectedSpan.stepIdx}`}
                      className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                    >
                      Open in Replay
                    </Link>
                  </div>
                  <div className="flex-1 min-h-0 overflow-hidden">
                    <TraceDetailPanel
                      span={selectedSpan}
                      episodeStartTs={episode.started_at}
                      parentDurationMs={episode.duration_ms > 0 ? episode.duration_ms : undefined}
                      onClose={() => setSelectedSpan(null)}
                    />
                  </div>
                </div>
              )}
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      </Card>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router'
import { format } from 'date-fns'
import { ArrowLeft } from 'lucide-react'

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { fetchEpisode, type EpisodeDetail } from '@/lib/api'

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

// Mini timeline color palette keyed by action_type or index
const SEGMENT_COLORS = [
  'bg-blue-500',
  'bg-violet-500',
  'bg-emerald-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-cyan-500',
  'bg-pink-500',
  'bg-indigo-500',
]

function getSegmentColor(actionType: string | undefined, index: number): string {
  if (!actionType) return SEGMENT_COLORS[index % SEGMENT_COLORS.length]
  // Simple deterministic hash from action_type string
  let hash = 0
  for (let i = 0; i < actionType.length; i++) {
    hash = (hash + actionType.charCodeAt(i)) % SEGMENT_COLORS.length
  }
  return SEGMENT_COLORS[hash]
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
// Mini Timeline Preview
// ---------------------------------------------------------------------------

interface Step {
  duration_ms?: number
  action_type?: string
  [key: string]: unknown
}

interface MiniTimelineProps {
  steps: Step[]
}

function MiniTimeline({ steps }: MiniTimelineProps) {
  if (steps.length === 0) {
    return (
      <p className="text-sm text-neutral-400">No steps recorded.</p>
    )
  }

  const totalDuration = steps.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0)

  return (
    <div className="space-y-3">
      <div className="flex h-8 rounded overflow-hidden border border-neutral-800">
        {steps.map((step, i) => {
          const dur = step.duration_ms ?? 0
          const widthPct = totalDuration > 0 ? (dur / totalDuration) * 100 : 100 / steps.length
          const color = getSegmentColor(step.action_type, i)
          return (
            <div
              key={i}
              className={`${color} opacity-80 hover:opacity-100 transition-opacity`}
              style={{ width: `${widthPct}%` }}
              title={`Step ${i + 1}${step.action_type ? ` (${step.action_type})` : ''}: ${formatDuration(dur)}`}
            />
          )
        })}
      </div>
      <p className="text-xs text-neutral-500">{steps.length} step{steps.length !== 1 ? 's' : ''}</p>
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

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto p-8 space-y-4">
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (fetchError) {
    return (
      <div className="max-w-4xl mx-auto p-8 space-y-4">
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

  const steps = episode.steps as Step[]

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="max-w-4xl mx-auto p-8 space-y-6">
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
          <div className="flex items-center gap-3 flex-wrap">
            <StatusBadge status={episode.outcome} type="outcome" />
            <span className="font-mono text-sm text-neutral-300 break-all">{episode.episode_id}</span>
            <span className="text-sm text-neutral-400">{episode.task_name}</span>
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

      {/* Mini Timeline Preview */}
      <Card>
        <CardHeader>
          <CardTitle>Timeline Preview</CardTitle>
        </CardHeader>
        <CardContent>
          <MiniTimeline steps={steps} />
        </CardContent>
      </Card>
    </div>
  )
}

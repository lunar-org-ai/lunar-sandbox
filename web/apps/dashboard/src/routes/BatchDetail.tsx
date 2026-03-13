import { useNavigate, useParams, Link } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { BatchProgressBar } from '@/components/BatchProgressBar'
import { BatchEtaStats } from '@/components/BatchEtaStats'
import { BatchTaskList } from '@/components/BatchTaskList'
import { useBatchProgress } from '@/hooks/useBatchProgress'

// ---------------------------------------------------------------------------
// BatchDetail page
// ---------------------------------------------------------------------------

export default function BatchDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { batch, loading, error, liveCost } = useBatchProgress(id ?? null)

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (loading && !batch) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Error state
  // ---------------------------------------------------------------------------

  if (error && !batch) {
    return (
      <div className="p-6">
        <p className="text-sm text-red-400">Error: {error}</p>
      </div>
    )
  }

  if (!batch) {
    return null
  }

  // ---------------------------------------------------------------------------
  // Derived values
  // ---------------------------------------------------------------------------

  const inProgress = Math.max(
    0,
    batch.total_tasks - batch.passed - batch.failed - batch.errors,
  )
  const completed = batch.passed + batch.failed + batch.errors
  const recentDurationsMs = batch.task_results.map((t) => t.wall_clock_ms)

  // Prefer WS live cost, fall back to REST total_cost
  const displayCost = liveCost !== null ? liveCost : batch.total_cost
  const costLabel =
    displayCost > 0 ? `$${displayCost.toFixed(4)}` : '--'

  const isComplete = completed >= batch.total_tasks && batch.total_tasks > 0

  // Worst-performing tasks by error count
  const taskErrorCounts = batch.task_results.reduce<Map<string, number>>((acc, t) => {
    if (t.outcome === 'error' || t.outcome === 'fail') {
      acc.set(t.task_name, (acc.get(t.task_name) ?? 0) + 1)
    }
    return acc
  }, new Map())
  const worstTasks = Array.from(taskErrorCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="p-6 space-y-6">
      {/* Breadcrumb */}
      <nav className="text-sm text-zinc-500">
        <Link to="/runs" className="hover:text-zinc-300 transition-colors">
          Batches
        </Link>
        <span className="mx-1">/</span>
        <span className="text-zinc-200 font-mono">{batch.batch_id}</span>
      </nav>

      {/* Header section: progress bar + ETA + live cost */}
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          {/* Progress bar -- takes up most width */}
          <div className="flex-1 min-w-64">
            <BatchProgressBar
              passed={batch.passed}
              failed={batch.failed}
              errors={batch.errors}
              inProgress={inProgress}
              total={batch.total_tasks}
            />
          </div>

          {/* Live cost counter */}
          <div className="rounded bg-zinc-800 px-3 py-2 shrink-0">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500">Cost</div>
            <div
              className="text-lg font-mono font-bold text-zinc-100"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {costLabel}
            </div>
          </div>
        </div>

        {/* ETA stats */}
        <BatchEtaStats
          completed={completed}
          total={batch.total_tasks}
          startedAt={batch.started_at}
          recentDurationsMs={recentDurationsMs}
        />
      </div>

      {/* Completion summary (only shown when batch is complete) */}
      {isComplete && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-2">
          <h3 className="text-sm font-semibold text-zinc-200">Completion Summary</h3>
          <div className="flex flex-wrap gap-4 text-sm">
            <span className="text-zinc-400">
              Pass rate:{' '}
              <span className="text-zinc-100 font-mono">
                {(batch.pass_rate * 100).toFixed(1)}%
              </span>
            </span>
            <span className="text-zinc-400">
              Cost:{' '}
              <span className="text-zinc-100 font-mono">{costLabel}</span>
            </span>
          </div>
          {worstTasks.length > 0 && (
            <div className="text-sm text-zinc-400">
              <span className="text-zinc-500">Highest error tasks: </span>
              {worstTasks.map(([name, count]) => (
                <span key={name} className="font-mono text-zinc-300 mr-2">
                  {name} ({count})
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tabbed content */}
      <Tabs defaultValue="tasks">
        <TabsList>
          <TabsTrigger value="tasks">Tasks</TabsTrigger>
          <TabsTrigger value="metrics">Metrics</TabsTrigger>
          <TabsTrigger value="cost">Cost</TabsTrigger>
        </TabsList>

        <TabsContent value="tasks" className="mt-4">
          {batch.task_results.length === 0 ? (
            <p className="text-sm text-zinc-500 py-4">No task results yet.</p>
          ) : (
            <BatchTaskList
              taskResults={batch.task_results}
              onEpisodeClick={(episodeId) => navigate(`/runs/${episodeId}`)}
            />
          )}
        </TabsContent>

        <TabsContent value="metrics" className="mt-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6 text-center">
            <p className="text-sm text-zinc-500">Metrics coming soon</p>
          </div>
        </TabsContent>

        <TabsContent value="cost" className="mt-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6 text-center">
            <p className="text-sm text-zinc-500">Cost tracking coming soon</p>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}

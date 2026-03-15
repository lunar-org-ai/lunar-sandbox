import { useNavigate, useParams, Link } from 'react-router'
import { AlertCircle } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { BatchProgressBar } from '@/components/BatchProgressBar'
import { BatchEtaStats } from '@/components/BatchEtaStats'
import { BatchTaskList } from '@/components/BatchTaskList'
import { CostChart, type CostDataPoint } from '@/components/CostChart'
import { ExportButton } from '@/components/ExportButton'
import { MetricsGrid } from '@/components/MetricsGrid'
import { useBatchProgress } from '@/hooks/useBatchProgress'
import { useMetricsStream } from '@/hooks/useMetricsStream'

// ---------------------------------------------------------------------------
// BatchDetail page
// ---------------------------------------------------------------------------

export default function BatchDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { batch, loading, error, liveCost } = useBatchProgress(id ?? null)

  // Metrics tab: WS telemetry stream (hardcoded topic for Phase 13)
  const { metrics } = useMetricsStream('telemetry:mock-run-1')

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (loading && !batch) {
    return (
      <div className="p-6 space-y-4 max-w-6xl mx-auto">
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
      <div className="p-6 max-w-6xl mx-auto space-y-4">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/runs">Batches</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Error</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
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

  // Cost tab: derive cumulative cost chart data from task_results
  let runningCost = 0
  const costData: CostDataPoint[] = batch.task_results
    .filter((t) => t.wall_clock_ms > 0)
    .sort((a, b) => a.wall_clock_ms - b.wall_clock_ms)
    .map((t) => {
      runningCost += t.estimated_cost
      return {
        elapsed_s: t.wall_clock_ms / 1000,
        cumulative_usd: runningCost,
      }
    })

  // Token breakdown: token_count is total; split 60/40 input/output as estimate
  const totalTokens = batch.task_results.reduce((sum, t) => sum + t.token_count, 0)
  const totalInputTokens = Math.round(totalTokens * 0.6)
  const totalOutputTokens = totalTokens - totalInputTokens

  // Use WS live cost for totalCost prop if available
  const chartTotalCost = liveCost !== null ? liveCost : batch.total_cost

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
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {/* Breadcrumb + export */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/runs">Batches</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage className="font-mono">{batch.batch_id}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <ExportButton
          data={batch}
          filename={`batch-${id ?? batch.batch_id}`}
          csvRows={batch.task_results.map((tr) => tr as Record<string, unknown>)}
        />
      </div>

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
          <div className="rounded-lg border border-border/50 bg-card/50 px-3 py-2 shrink-0">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Cost</div>
            <div
              className="text-lg font-mono font-bold tabular-nums"
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
        <div className="rounded-lg border border-border/50 bg-card/50 p-4 space-y-2">
          <h3 className="text-sm font-medium">Completion Summary</h3>
          <div className="flex flex-wrap gap-4 text-sm">
            <span className="text-muted-foreground">
              Pass rate:{' '}
              <span className="text-foreground font-mono tabular-nums">
                {(batch.pass_rate * 100).toFixed(1)}%
              </span>
            </span>
            <span className="text-muted-foreground">
              Cost:{' '}
              <span className="text-foreground font-mono tabular-nums">{costLabel}</span>
            </span>
          </div>
          {worstTasks.length > 0 && (
            <div className="text-sm text-muted-foreground">
              <span>Highest error tasks: </span>
              {worstTasks.map(([name, count]) => (
                <span key={name} className="font-mono text-foreground mr-2">
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
            <p className="text-sm text-muted-foreground py-4">No task results yet.</p>
          ) : (
            <BatchTaskList
              taskResults={batch.task_results}
              onEpisodeClick={(episodeId) => navigate(`/runs/${episodeId}`)}
            />
          )}
        </TabsContent>

        <TabsContent value="metrics" className="mt-4">
          <MetricsGrid metrics={metrics} />
        </TabsContent>

        <TabsContent value="cost" className="mt-4">
          <CostChart
            data={costData}
            inputTokens={totalInputTokens}
            outputTokens={totalOutputTokens}
            totalCost={chartTotalCost}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}

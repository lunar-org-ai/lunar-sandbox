import { useNavigate, useParams, Link } from "react-router";
import { AlertCircle } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BatchProgressBar } from "@/components/BatchProgressBar";
import { BatchEtaStats } from "@/components/BatchEtaStats";
import { BatchTaskList } from "@/components/BatchTaskList";
import { CostChart, type CostDataPoint } from "@/components/CostChart";
import { ExportButton } from "@/components/ExportButton";
import { MetricsGrid } from "@/components/MetricsGrid";
import { useBatchProgress } from "@/hooks/useBatchProgress";
import { useMetricsStream } from "@/hooks/useMetricsStream";

export default function BatchDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { batch, loading, error, liveCost } = useBatchProgress(id ?? null);

  // Metrics tab: WS telemetry stream scoped to this batch
  const { metrics } = useMetricsStream(id ? `telemetry:${id}` : null);

  if (loading && !batch) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 p-6">
        <Skeleton className="h-48 w-full rounded-3xl" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    );
  }

  if (error && !batch) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 p-6">
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
        <Alert variant="destructive" className="border-0">
          <AlertCircle className="size-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!batch) {
    return null;
  }

  const inProgress = Math.max(
    0,
    batch.total_tasks - batch.passed - batch.failed - batch.errors,
  );
  const completed = batch.passed + batch.failed + batch.errors;
  const recentDurationsMs = batch.task_results.map((t) => t.wall_clock_ms);

  // Prefer WS live cost, fall back to REST total_cost
  const displayCost = liveCost !== null ? liveCost : batch.total_cost;
  const costLabel = displayCost > 0 ? `$${displayCost.toFixed(4)}` : "--";

  const isComplete = completed >= batch.total_tasks && batch.total_tasks > 0;

  // Cost tab: derive cumulative cost chart data from task_results
  let runningCost = 0;
  const costData: CostDataPoint[] = batch.task_results
    .filter((t) => t.wall_clock_ms > 0)
    .sort((a, b) => a.wall_clock_ms - b.wall_clock_ms)
    .map((t) => {
      runningCost += t.estimated_cost;
      return {
        elapsed_s: t.wall_clock_ms / 1000,
        cumulative_usd: runningCost,
      };
    });

  // Token breakdown: token_count is total; split 60/40 input/output as estimate
  const totalTokens = batch.task_results.reduce(
    (sum, t) => sum + t.token_count,
    0,
  );
  const totalInputTokens = Math.round(totalTokens * 0.6);
  const totalOutputTokens = totalTokens - totalInputTokens;

  // Use WS live cost for totalCost prop if available
  const chartTotalCost = liveCost !== null ? liveCost : batch.total_cost;

  // Worst-performing tasks by error count
  const taskErrorCounts = batch.task_results.reduce<Map<string, number>>(
    (acc, t) => {
      if (t.outcome === "error" || t.outcome === "fail") {
        acc.set(t.task_name, (acc.get(t.task_name) ?? 0) + 1);
      }
      return acc;
    },
    new Map(),
  );
  const worstTasks = Array.from(taskErrorCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      {/* Hero card */}
      <Card className="gap-0 rounded-3xl bg-secondary text-secondary-foreground">
        <CardHeader className="gap-4">
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link to="/runs" className="text-secondary-foreground">
                    Batches
                  </Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage className="font-mono">
                  {batch.batch_id}
                </BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="default">Batch</Badge>
                {isComplete && <Badge variant="secondary">Complete</Badge>}
              </div>
              <CardTitle className="text-2xl tracking-tight">
                {batch.benchmark_name || batch.batch_id}
              </CardTitle>
              <CardDescription className="text-secondary-foreground">
                {completed} / {batch.total_tasks} tasks complete
              </CardDescription>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <div className="rounded-xl bg-muted px-4 py-2 text-center">
                <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
                  Pass Rate
                </p>
                <p className="text-lg font-mono font-bold tabular-nums">
                  {(batch.pass_rate * 100).toFixed(1)}%
                </p>
              </div>
              <div className="rounded-xl bg-muted px-4 py-2 text-center">
                <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
                  Cost
                </p>
                <p className="text-lg font-mono font-bold tabular-nums">
                  {costLabel}
                </p>
              </div>
              <ExportButton
                data={batch}
                filename={`batch-${id ?? batch.batch_id}`}
                csvRows={batch.task_results.map(
                  (tr) => tr as Record<string, unknown>,
                )}
              />
            </div>
          </div>
          <BatchProgressBar
            passed={batch.passed}
            failed={batch.failed}
            errors={batch.errors}
            inProgress={inProgress}
            total={batch.total_tasks}
          />
        </CardHeader>
      </Card>

      <BatchEtaStats
        completed={completed}
        total={batch.total_tasks}
        startedAt={batch.started_at}
        recentDurationsMs={recentDurationsMs}
      />

      {isComplete && (
        <Card className="gap-0 rounded-2xl">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Completion Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex flex-wrap gap-6 text-sm">
              <div>
                <span className="text-muted-foreground">Pass rate</span>
                <span className="ml-2 font-mono tabular-nums">
                  {(batch.pass_rate * 100).toFixed(1)}%
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Total cost</span>
                <span className="ml-2 font-mono tabular-nums">{costLabel}</span>
              </div>
            </div>
            {worstTasks.length > 0 && (
              <p className="text-sm text-muted-foreground">
                Highest error tasks:{" "}
                {worstTasks.map(([name, count]) => (
                  <span key={name} className="font-mono text-foreground mr-2">
                    {name} ({count})
                  </span>
                ))}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="tasks">
        <TabsList>
          <TabsTrigger value="tasks">Tasks</TabsTrigger>
          <TabsTrigger value="metrics">Metrics</TabsTrigger>
          <TabsTrigger value="cost">Cost</TabsTrigger>
        </TabsList>

        <TabsContent value="tasks" className="mt-4">
          {batch.task_results.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">
              No task results yet.
            </p>
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
  );
}

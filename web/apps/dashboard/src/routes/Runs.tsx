import { useState, useEffect, useCallback } from "react";
import { Link, useNavigate } from "react-router";
import { type ColumnDef, type SortingState } from "@tanstack/react-table";
import { formatDistanceToNow } from "date-fns";
import {
  AlertCircle,
  ArrowRight,
  ArrowUpDown,
  Filter,
  Rocket,
} from "lucide-react";

import { StatusBadge } from "@/components/StatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  fetchBatches,
  fetchEpisodes,
  type BatchSummary,
  type EpisodeSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import CUALauncher from "@/routes/CUALauncher";

function formatDuration(ms: number): string {
  if (ms <= 0) return "--";
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds}s`;
  return `${minutes}m ${seconds}s`;
}

function formatCost(usd: number | null | undefined): string {
  if (usd == null) return "--";
  return `$${usd.toFixed(2)}`;
}

function buildColumns(): ColumnDef<EpisodeSummary>[] {
  return [
    {
      accessorKey: "task_name",
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8 font-medium text-muted-foreground"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Task
          <ArrowUpDown className="ml-1 size-3" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="font-mono text-sm">{row.getValue("task_name")}</span>
      ),
    },
    {
      accessorKey: "outcome",
      header: "Outcome",
      cell: ({ row }) => (
        <StatusBadge status={row.getValue("outcome")} type="outcome" />
      ),
    },
    {
      accessorKey: "score",
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8 font-medium text-muted-foreground"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Score
          <ArrowUpDown className="ml-1 size-3" />
        </Button>
      ),
      cell: ({ row }) => {
        const score: number | null = row.getValue("score");
        return (
          <span className="block text-right tabular-nums">
            {score != null ? score.toFixed(2) : "--"}
          </span>
        );
      },
    },
    {
      accessorKey: "duration_ms",
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8 font-medium text-muted-foreground"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Duration
          <ArrowUpDown className="ml-1 size-3" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="block text-right tabular-nums text-muted-foreground">
          {formatDuration(row.getValue("duration_ms"))}
        </span>
      ),
    },
    {
      accessorKey: "cost_usd",
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8 font-medium text-muted-foreground"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Cost
          <ArrowUpDown className="ml-1 size-3" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="block text-right tabular-nums text-muted-foreground">
          {formatCost(row.getValue("cost_usd"))}
        </span>
      ),
    },
    {
      accessorKey: "started_at",
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8 font-medium text-muted-foreground"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Date
          <ArrowUpDown className="ml-1 size-3" />
        </Button>
      ),
      cell: ({ row }) => {
        const ts: number = row.getValue("started_at");
        if (!ts)
          return (
            <span className="block text-right text-muted-foreground">--</span>
          );
        return (
          <span className="block text-right text-xs text-muted-foreground">
            {formatDistanceToNow(new Date(ts * 1000), { addSuffix: true })}
          </span>
        );
      },
    },
  ];
}

function BatchesTab() {
  const navigate = useNavigate();
  const [batches, setBatches] = useState<BatchSummary[]>([]);
  const [loadingBatches, setLoadingBatches] = useState(true);
  const [batchError, setBatchError] = useState<string | null>(null);

  useEffect(() => {
    setLoadingBatches(true);
    setBatchError(null);
    fetchBatches({ limit: 50 })
      .then((data) => setBatches(data.items))
      .catch((e) => {
        setBatchError(
          e instanceof Error ? e.message : "Failed to load batches.",
        );
      })
      .finally(() => setLoadingBatches(false));
  }, []);

  if (loadingBatches) {
    return (
      <div className="mt-4 space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (batchError) {
    return (
      <Alert variant="destructive" className="mt-4 border-0">
        <AlertCircle className="size-4" />
        <AlertTitle>Unable to load batches</AlertTitle>
        <AlertDescription>{batchError}</AlertDescription>
      </Alert>
    );
  }

  if (batches.length === 0) {
    return (
      <div className="mt-4 rounded-2xl bg-muted px-6 py-16 text-center">
        <Badge variant="secondary">No batches</Badge>
        <p className="mt-4 text-sm text-muted-foreground">No batches found.</p>
      </div>
    );
  }

  return (
    <div className="mt-4 space-y-2">
      {batches.map((batch) => {
        const completed = batch.passed + batch.failed + batch.errors;
        const passRatePct =
          completed > 0 ? ((batch.passed / completed) * 100).toFixed(1) : "--";

        return (
          <div
            key={batch.batch_id}
            onClick={() => navigate(`/batches/${batch.batch_id}`)}
            className="flex cursor-pointer items-center gap-4 rounded-2xl bg-muted px-4 py-3 hover:bg-accent"
          >
            <span className="w-40 shrink-0 truncate font-mono text-sm">
              {batch.batch_id.slice(0, 20)}
            </span>
            <span className="flex-1 truncate font-mono text-xs text-muted-foreground">
              {batch.benchmark_name || "--"}
            </span>
            <span className="shrink-0 text-xs text-muted-foreground">
              {completed}/{batch.total_tasks} complete
            </span>
            <Badge variant="secondary" className="w-16 justify-center text-xs">
              {passRatePct !== "--" ? `${passRatePct}%` : "--"}
            </Badge>
            {batch.started_at > 0 && (
              <span className="shrink-0 text-xs text-muted-foreground">
                {formatDistanceToNow(new Date(batch.started_at * 1000), {
                  addSuffix: true,
                })}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

const PAGE_SIZE = 50;

export default function Runs() {
  const navigate = useNavigate();
  const [outcomeFilters, setOutcomeFilters] = useState<Set<string>>(new Set());
  const [taskSearch, setTaskSearch] = useState("");
  const [debouncedTask, setDebouncedTask] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [scoreMin, setScoreMin] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedTask(taskSearch), 300);
    return () => clearTimeout(timer);
  }, [taskSearch]);

  const [episodes, setEpisodes] = useState<EpisodeSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [sorting, setSorting] = useState<SortingState>([
    { id: "started_at", desc: true },
  ]);

  const loadEpisodes = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const params: Parameters<typeof fetchEpisodes>[0] = {
        offset,
        limit: PAGE_SIZE,
      };

      if (debouncedTask) params.task_name = debouncedTask;
      if (outcomeFilters.size > 0) {
        params.outcome = Array.from(outcomeFilters).join(",");
      }
      if (dateFrom)
        params.date_from = Math.floor(new Date(dateFrom).getTime() / 1000);
      if (dateTo)
        params.date_to = Math.floor(new Date(dateTo).getTime() / 1000);
      if (scoreMin !== "") params.score_min = parseFloat(scoreMin);

      if (sorting.length > 0) {
        params.sort_by = sorting[0].id;
        params.sort_order = sorting[0].desc ? "desc" : "asc";
      }

      const data = await fetchEpisodes(params);
      setEpisodes(data.items);
      setTotal(data.total);
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : "Failed to load runs.");
    } finally {
      setLoading(false);
    }
  }, [
    debouncedTask,
    outcomeFilters,
    dateFrom,
    dateTo,
    scoreMin,
    offset,
    sorting,
  ]);

  useEffect(() => {
    loadEpisodes();
  }, [loadEpisodes]);

  useEffect(() => {
    setOffset(0);
  }, [debouncedTask, outcomeFilters, dateFrom, dateTo, scoreMin]);

  function toggleOutcome(outcome: string) {
    setOutcomeFilters((prev) => {
      const next = new Set(prev);
      if (next.has(outcome)) next.delete(outcome);
      else next.add(outcome);
      return next;
    });
  }

  const columns = buildColumns();
  const activeFilters =
    outcomeFilters.size +
    Number(Boolean(taskSearch)) +
    Number(Boolean(dateFrom)) +
    Number(Boolean(dateTo)) +
    Number(Boolean(scoreMin));

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <Card className="gap-0 rounded-3xl bg-secondary text-secondary-foreground">
        <CardHeader className="gap-5 lg:grid-cols-[1fr_auto] lg:items-end">
          <div className="space-y-4">
            <Badge variant="default" className="w-fit">
              Run archive
            </Badge>
            <div className="space-y-2">
              <CardTitle className="text-3xl tracking-tight">
                Run History
              </CardTitle>
              <CardDescription className="max-w-2xl text-base text-secondary-foreground">
                Browse recent episodes, inspect batches, and launch new CUA runs
                from the same workspace.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="default">{total} total runs</Badge>
              <Badge variant="default">{activeFilters} active filters</Badge>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 sm:justify-end">
            <Button asChild variant="default" size="sm">
              <Link to="/launcher">
                <Rocket className="size-4" />
                New Run
              </Link>
            </Button>
          </div>
        </CardHeader>
      </Card>

      <Tabs defaultValue="episodes">
        <TabsList>
          <TabsTrigger value="episodes">Episodes</TabsTrigger>
          <TabsTrigger value="batches">Batches</TabsTrigger>
          <TabsTrigger value="new-cua">New CUA Episode</TabsTrigger>
        </TabsList>

        <TabsContent value="episodes">
          <div className="mt-4 space-y-4">
            <Card className="gap-0 rounded-2xl">
              <CardHeader className="pb-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <CardTitle className="text-base">Episode Filters</CardTitle>
                    <CardDescription>
                      Narrow results by outcome, task, date, and minimum score.
                    </CardDescription>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">
                      <Filter className="size-3" />
                      {activeFilters} active
                    </Badge>
                    {activeFilters > 0 && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          setOutcomeFilters(new Set());
                          setTaskSearch("");
                          setDateFrom("");
                          setDateTo("");
                          setScoreMin("");
                        }}
                      >
                        Clear filters
                      </Button>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto]">
                  <div className="flex flex-wrap items-center gap-2">
                    {(["pass", "fail", "error"] as const).map((outcome) => (
                      <Label
                        key={outcome}
                        className={cn(
                          "gap-2 rounded-xl bg-muted px-3 py-2 text-xs font-medium capitalize",
                          outcomeFilters.has(outcome) &&
                            "bg-secondary text-secondary-foreground",
                        )}
                      >
                        <Checkbox
                          checked={outcomeFilters.has(outcome)}
                          onCheckedChange={() => toggleOutcome(outcome)}
                        />
                        {outcome}
                      </Label>
                    ))}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      type="text"
                      placeholder="Filter by task..."
                      value={taskSearch}
                      onChange={(e) => setTaskSearch(e.target.value)}
                      className="h-9 w-56 text-sm"
                    />
                    <Input
                      type="date"
                      value={dateFrom}
                      onChange={(e) => setDateFrom(e.target.value)}
                      className="h-9 w-40 text-sm"
                      title="From date"
                    />
                    <Input
                      type="date"
                      value={dateTo}
                      onChange={(e) => setDateTo(e.target.value)}
                      className="h-9 w-40 text-sm"
                      title="To date"
                    />
                    <Input
                      type="number"
                      placeholder="Min score"
                      value={scoreMin}
                      onChange={(e) => setScoreMin(e.target.value)}
                      step="0.1"
                      min="0"
                      max="1"
                      className="h-9 w-32 text-sm"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            {fetchError && (
              <Alert variant="destructive" className="border-0">
                <AlertCircle className="size-4" />
                <AlertTitle>Unable to load runs</AlertTitle>
                <AlertDescription>{fetchError}</AlertDescription>
              </Alert>
            )}

            {loading ? (
              <div className="space-y-2 rounded-2xl bg-muted p-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : episodes.length === 0 ? (
              <div className="rounded-2xl bg-muted px-6 py-16 text-center">
                <Badge variant="secondary">No results</Badge>
                <p className="text-sm text-muted-foreground">
                  No runs found. Adjust filters or launch a new experiment.
                </p>
                <div className="mt-4 flex justify-center">
                  <Button asChild variant="secondary" size="sm">
                    <Link to="/launcher">
                      Go to Launcher
                      <ArrowRight className="size-4" />
                    </Link>
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <div className="rounded-2xl bg-muted p-2">
                  <DataTable
                    columns={columns}
                    data={episodes}
                    sorting={sorting}
                    onSortingChange={setSorting}
                    manualSorting
                    onRowClick={(row) =>
                      navigate(`/runs/${row.original.episode_id}`)
                    }
                  />
                </div>

                <div className="flex items-center justify-between pt-2 text-sm text-muted-foreground">
                  <span>
                    Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)}{" "}
                    of {total}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8"
                      disabled={offset === 0}
                      onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="h-8"
                      disabled={offset + PAGE_SIZE >= total}
                      onClick={() => setOffset(offset + PAGE_SIZE)}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </>
            )}
          </div>
        </TabsContent>

        <TabsContent value="batches">
          <BatchesTab />
        </TabsContent>

        <TabsContent value="new-cua">
          <CUALauncher />
        </TabsContent>
      </Tabs>
    </div>
  );
}

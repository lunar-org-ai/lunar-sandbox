import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  CircleHelp,
  CircleStop,
  LayoutGrid,
  ListFilter,
  Monitor,
  Play,
  Rocket,
  Rows3,
  Server,
} from "lucide-react";

import { StatusBadge } from "@/components/StatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useSandboxUpdates } from "@/hooks/useSandboxUpdates";
import {
  fetchEpisodes,
  fetchHealth,
  stopSandbox,
  type EpisodeSummary,
  type HealthResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function EngineStatusCard() {
  const [data, setData] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <Card className="gap-0 rounded-2xl">
      <CardHeader className="pb-4">
        <div className="flex items-start gap-3">
          <Badge variant="secondary" className="size-10 rounded-xl p-0">
            <Server className="size-4" />
          </Badge>
          <div className="space-y-1">
            <CardTitle className="text-base">Engine Status</CardTitle>
            <CardDescription>
              Backend availability and storage readiness.
            </CardDescription>
          </div>
        </div>
        <CardAction>
          <Badge variant="secondary">Health</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        {error ? (
          <Alert variant="destructive" className="border-0">
            <AlertCircle className="size-4" />
            <AlertTitle>Unable to load engine status</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : !data ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-muted p-4">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="mt-3 h-8 w-20" />
            </div>
            <div className="rounded-xl bg-muted p-4">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="mt-3 h-8 w-20" />
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <StatusBadge status={data.status} type="sandbox" />
              <p className="text-sm text-muted-foreground">
                Current engine heartbeat.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-muted p-4">
                <p className="text-sm text-muted-foreground">Engine started</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight">
                  {data.engine_started ? "Yes" : "No"}
                </p>
              </div>
              <div className="rounded-xl bg-muted p-4">
                <p className="text-sm text-muted-foreground">
                  Stores available
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight">
                  {data.stores_available ? "Yes" : "No"}
                </p>
              </div>
            </div>
          </>
        )}
      </CardContent>
      <CardFooter>
        <Badge variant="secondary">Snapshot on page load</Badge>
      </CardFooter>
    </Card>
  );
}

function SandboxPoolCard() {
  const { sandboxes, loading, error } = useSandboxUpdates();

  const stateCounts = sandboxes.reduce<Record<string, number>>(
    (acc, sandbox) => {
      acc[sandbox.state] = (acc[sandbox.state] ?? 0) + 1;
      return acc;
    },
    {},
  );

  const stateEntries = Object.entries(stateCounts);
  const runningCount = stateCounts.Running ?? 0;
  const totalMemory = sandboxes.reduce(
    (sum, sandbox) => sum + (sandbox.memory_mb ?? 0),
    0,
  );
  const cpuSamples = sandboxes.filter((sandbox) => sandbox.cpu_percent != null);
  const averageCpu =
    cpuSamples.length > 0
      ? cpuSamples.reduce(
          (sum, sandbox) => sum + (sandbox.cpu_percent ?? 0),
          0,
        ) / cpuSamples.length
      : 0;

  return (
    <Card className="gap-0 rounded-2xl">
      <CardHeader className="pb-4">
        <div className="flex items-start gap-3">
          <Badge variant="secondary" className="size-10 rounded-xl p-0">
            <Monitor className="size-4" />
          </Badge>
          <div className="space-y-1">
            <CardTitle className="text-base">Sandbox Pool</CardTitle>
            <CardDescription>
              Current resource pool and active sessions.
            </CardDescription>
          </div>
        </div>
        <CardAction>
          <Badge variant="secondary">Live</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        {error ? (
          <Alert variant="destructive" className="border-0">
            <AlertCircle className="size-4" />
            <AlertTitle>Unable to load sandboxes</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : loading ? (
          <div className="space-y-3">
            <Skeleton className="h-10 w-20" />
            <div className="grid gap-3 sm:grid-cols-2">
              <Skeleton className="h-24 w-full rounded-xl" />
              <Skeleton className="h-24 w-full rounded-xl" />
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="text-3xl font-semibold tracking-tight">
                  {sandboxes.length}
                </p>
                <p className="text-sm text-muted-foreground">
                  sandboxes available in the pool
                </p>
              </div>
              <Badge variant="secondary">{runningCount} running</Badge>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-muted p-4">
                <p className="text-sm text-muted-foreground">Average CPU</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight">
                  {averageCpu.toFixed(1)}%
                </p>
              </div>
              <div className="rounded-xl bg-muted p-4">
                <p className="text-sm text-muted-foreground">Tracked memory</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight">
                  {totalMemory.toFixed(0)} MB
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {stateEntries.length > 0 ? (
                stateEntries.map(([state, count]) => (
                  <Badge key={state} variant="secondary">
                    {count} {state}
                  </Badge>
                ))
              ) : (
                <Badge variant="secondary">No sandboxes</Badge>
              )}
            </div>
          </>
        )}
      </CardContent>
      <CardFooter>
        <Badge variant="secondary">Live telemetry stream</Badge>
      </CardFooter>
    </Card>
  );
}

function RecentEpisodesCard() {
  const [total, setTotal] = useState<number | null>(null);
  const [latest, setLatest] = useState<EpisodeSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEpisodes({ limit: 5 })
      .then((data) => {
        setTotal(data.total);
        setLatest(data.items[0] ?? null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <Card className="gap-0 rounded-2xl">
      <CardHeader className="pb-4">
        <div className="flex items-start gap-3">
          <Badge variant="secondary" className="size-10 rounded-xl p-0">
            <Rocket className="size-4" />
          </Badge>
          <div className="space-y-1">
            <CardTitle className="text-base">Recent Episodes</CardTitle>
            <CardDescription>
              Latest execution outcomes and quick access to runs.
            </CardDescription>
          </div>
        </div>
        <CardAction>
          <Badge variant="secondary">Runs</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        {error ? (
          <Alert variant="destructive" className="border-0">
            <AlertCircle className="size-4" />
            <AlertTitle>Unable to load recent runs</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : total === null ? (
          <div className="space-y-3">
            <Skeleton className="h-10 w-16" />
            <div className="grid gap-3 sm:grid-cols-2">
              <Skeleton className="h-24 w-full rounded-xl" />
              <Skeleton className="h-24 w-full rounded-xl" />
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="text-3xl font-semibold tracking-tight">{total}</p>
                <p className="text-sm text-muted-foreground">
                  total runs indexed
                </p>
              </div>
              <Badge variant="secondary">Last 5 fetched</Badge>
            </div>
            <div className="rounded-xl bg-muted p-4">
              <p className="text-sm text-muted-foreground">Latest outcome</p>
              <div className="mt-3 flex items-center gap-2">
                {latest ? (
                  <>
                    <StatusBadge status={latest.outcome} type="outcome" />
                    <p className="text-sm text-muted-foreground">
                      Most recent execution result.
                    </p>
                  </>
                ) : (
                  <Badge variant="secondary">No episodes yet</Badge>
                )}
              </div>
            </div>
          </>
        )}
      </CardContent>
      <CardFooter>
        <Button asChild variant="secondary" size="sm">
          <Link to="/runs">
            View all runs
            <ArrowRight className="size-4" />
          </Link>
        </Button>
      </CardFooter>
    </Card>
  );
}

interface SandboxRowProps {
  sandbox: {
    sandbox_id: string;
    state: string;
    cpu_percent?: number | null;
    memory_mb?: number | null;
  };
  onStop: (id: string) => void;
  stopping: boolean;
  compactRows: boolean;
}

function SandboxRow({
  sandbox,
  onStop,
  stopping,
  compactRows,
}: SandboxRowProps) {
  const prevStateRef = useRef(sandbox.state);
  const [highlighted, setHighlighted] = useState(false);

  useEffect(() => {
    if (prevStateRef.current !== sandbox.state) {
      prevStateRef.current = sandbox.state;
      setHighlighted(true);
      const timer = setTimeout(() => setHighlighted(false), 800);
      return () => clearTimeout(timer);
    }
  }, [sandbox.state]);

  return (
    <TableRow
      className={cn(
        "border-0 hover:bg-accent",
        compactRows ? "h-10" : "h-14",
        highlighted && "bg-muted",
      )}
    >
      <TableCell className="max-w-64">
        <p className="truncate font-mono text-xs text-muted-foreground">
          {sandbox.sandbox_id}
        </p>
      </TableCell>
      <TableCell>
        <StatusBadge status={sandbox.state} type="sandbox" />
      </TableCell>
      <TableCell className="text-right">
        <span className="font-medium tabular-nums">
          {sandbox.cpu_percent != null
            ? `${sandbox.cpu_percent.toFixed(1)}%`
            : "--"}
        </span>
      </TableCell>
      <TableCell className="text-right">
        <span className="font-medium tabular-nums">
          {sandbox.memory_mb != null
            ? `${sandbox.memory_mb.toFixed(0)} MB`
            : "--"}
        </span>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" asChild>
            <Link to={`/sandboxes/${sandbox.sandbox_id}`}>View</Link>
          </Button>
          {sandbox.state === "Running" && (
            <Button
              variant="secondary"
              size="sm"
              disabled={stopping}
              onClick={() => onStop(sandbox.sandbox_id)}
            >
              <CircleStop className="size-4" />
              {stopping ? "Stopping" : "Stop"}
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}

function SandboxTable() {
  const { sandboxes, loading, error } = useSandboxUpdates();
  const [onlyRunning, setOnlyRunning] = useState(false);
  const [compactRows, setCompactRows] = useState(false);
  const [stoppingIds, setStoppingIds] = useState<Set<string>>(new Set());

  const visibleSandboxes = useMemo(
    () =>
      sandboxes.filter((sandbox) =>
        onlyRunning ? sandbox.state === "Running" : true,
      ),
    [sandboxes, onlyRunning],
  );

  async function handleStop(sandboxId: string) {
    setStoppingIds((prev) => new Set(prev).add(sandboxId));
    try {
      await stopSandbox(sandboxId);
    } finally {
      setStoppingIds((prev) => {
        const next = new Set(prev);
        next.delete(sandboxId);
        return next;
      });
    }
  }

  return (
    <Card className="gap-0 rounded-2xl">
      <CardHeader className="pb-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Badge variant="secondary" className="size-10 rounded-xl p-0">
                <Activity className="size-4" />
              </Badge>
              <div>
                <CardTitle className="text-lg">Sandbox Monitor</CardTitle>
                <CardDescription>
                  Live CPU and memory usage across active sandboxes.
                </CardDescription>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary">
                {visibleSandboxes.length} visible
              </Badge>
              <Badge variant="secondary">
                {onlyRunning ? "Running only" : "All states"}
              </Badge>
              <Badge variant="secondary">
                {compactRows ? "Compact density" : "Comfort density"}
              </Badge>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant={onlyRunning ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setOnlyRunning((current) => !current)}
            >
              <ListFilter className="size-4" />
              Running only
            </Button>
            <Button
              variant={compactRows ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setCompactRows((current) => !current)}
            >
              {compactRows ? (
                <Rows3 className="size-4" />
              ) : (
                <LayoutGrid className="size-4" />
              )}
              Compact rows
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {error ? (
          <Alert variant="destructive" className="border-0">
            <AlertCircle className="size-4" />
            <AlertTitle>Unable to load sandbox monitor</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : !loading && visibleSandboxes.length === 0 ? (
          <div className="rounded-2xl bg-muted px-6 py-12 text-center">
            <Badge variant="secondary">Empty view</Badge>
            <p className="mt-4 text-base font-medium">
              No sandboxes match the current view.
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              Start a new run or remove the running-only filter to see more.
            </p>
            <div className="mt-6 flex justify-center">
              <Button asChild variant="secondary" size="sm">
                <Link to="/launcher">
                  <Rocket className="size-4" />
                  Go to Launcher
                </Link>
              </Button>
            </div>
          </div>
        ) : (
          <div className="rounded-2xl bg-muted p-2">
            <ScrollArea className="h-96 rounded-xl bg-card">
              <Table>
                <TableCaption>
                  Sandbox metrics update automatically.
                </TableCaption>
                <TableHeader className="[&_tr]:border-0">
                  <TableRow className="border-0 hover:bg-transparent">
                    <TableHead className="text-muted-foreground">
                      Sandbox ID
                    </TableHead>
                    <TableHead className="text-muted-foreground">
                      State
                    </TableHead>
                    <TableHead className="text-right text-muted-foreground">
                      CPU
                    </TableHead>
                    <TableHead className="text-right text-muted-foreground">
                      Memory
                    </TableHead>
                    <TableHead className="text-muted-foreground">
                      Actions
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="[&_tr]:border-0">
                  {loading
                    ? Array.from({ length: 4 }).map((_, i) => (
                        <TableRow
                          key={i}
                          className="border-0 hover:bg-transparent"
                        >
                          <TableCell>
                            <Skeleton className="h-4 w-40" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-5 w-24" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="ml-auto h-4 w-16" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="ml-auto h-4 w-20" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-8 w-28" />
                          </TableCell>
                        </TableRow>
                      ))
                    : visibleSandboxes.map((sandbox) => (
                        <SandboxRow
                          key={sandbox.sandbox_id}
                          sandbox={sandbox}
                          onStop={handleStop}
                          stopping={stoppingIds.has(sandbox.sandbox_id)}
                          compactRows={compactRows}
                        />
                      ))}
                </TableBody>
              </Table>
            </ScrollArea>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function Home() {
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 md:p-6">
      <Card className="gap-0 rounded-3xl bg-secondary text-secondary-foreground">
        <CardHeader className="gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
          <div className="space-y-4">
            <Badge variant="default" className="w-fit">
              Live operations
            </Badge>
            <div className="space-y-2">
              <CardTitle className="text-3xl tracking-tight">
                Operations Dashboard
              </CardTitle>
              <CardDescription className="max-w-2xl text-base text-secondary-foreground">
                Monitor engine health, active sandboxes, and the latest run
                outcomes from one clean command center.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="default">Engine health</Badge>
              <Badge variant="default">Sandbox telemetry</Badge>
              <Badge variant="default">Recent run outcomes</Badge>
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-end">
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="default" size="sm">
                  <CircleHelp className="size-4" />
                  Quick Tips
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-80 border-0">
                <PopoverHeader>
                  <PopoverTitle>Using this dashboard</PopoverTitle>
                  <PopoverDescription>
                    Keep the page focused on operations, then jump into runs or
                    sandboxes only when you need more detail.
                  </PopoverDescription>
                </PopoverHeader>
                <div className="mt-4 grid gap-3">
                  <div className="rounded-xl bg-muted p-3">
                    <p className="text-sm font-medium">
                      Start from the top cards
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Health, pool size, and run history give you the fastest
                      status snapshot.
                    </p>
                  </div>
                  <div className="rounded-xl bg-muted p-3">
                    <p className="text-sm font-medium">Filter the table</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Toggle running-only mode or compact density when the pool
                      gets busy.
                    </p>
                  </div>
                  <div className="rounded-xl bg-muted p-3">
                    <p className="text-sm font-medium">Take action quickly</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Open details or stop active sandboxes directly from the
                      monitor.
                    </p>
                  </div>
                </div>
              </PopoverContent>
            </Popover>
            <Button asChild variant="default" size="sm">
              <Link to="/runs">
                <Play className="size-4" />
                View Runs
              </Link>
            </Button>
            <Button asChild size="sm">
              <Link to="/launcher">
                <Rocket className="size-4" />
                Start New Run
              </Link>
            </Button>
          </div>
        </CardHeader>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <EngineStatusCard />
        <SandboxPoolCard />
        <RecentEpisodesCard />
      </div>

      <SandboxTable />
    </div>
  );
}

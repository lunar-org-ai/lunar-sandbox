import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { format } from "date-fns";
import {
  AlertCircle,
  GitBranch,
  LayoutGrid,
  List,
  RotateCcw,
} from "lucide-react";
import type { PanelImperativeHandle } from "react-resizable-panels";
import { useHotkeys } from "react-hotkeys-hook";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ExportButton } from "@/components/ExportButton";
import { StatusBadge } from "@/components/StatusBadge";
import { TraceDetailPanel } from "@/components/TraceDetailPanel";
import { TraceGraph } from "@/components/TraceGraph";
import { TraceTimeline } from "@/components/TraceTimeline";
import { useTraceStream } from "@/hooks/useTraceStream";
import { fetchEpisode, type EpisodeDetail } from "@/lib/api";
import { flattenEpisodeForCsv } from "@/lib/export-utils";
import { type TraceSpan } from "@/lib/trace-utils";

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
  return `$${usd.toFixed(4)}`;
}

function formatDatetime(ts: number | null | undefined): string {
  if (!ts) return "--";
  return format(new Date(ts * 1000), "MMM d, yyyy HH:mm:ss");
}

export default function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const episodeId = id ?? "";

  const [episode, setEpisode] = useState<EpisodeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Selected span state
  const [selectedSpan, setSelectedSpan] = useState<TraceSpan | null>(null);

  // Ref for the detail panel (for programmatic collapse/expand)
  const detailPanelRef = useRef<PanelImperativeHandle | null>(null);

  useEffect(() => {
    if (!episodeId) return;
    let cancelled = false;

    function load() {
      fetchEpisode(episodeId!)
        .then((data) => {
          if (cancelled) return;
          setEpisode(data);
          setLoading(false);
        })
        .catch((e: Error) => {
          if (cancelled) return;
          setFetchError(
            e.message.includes("404") ? "Run not found." : e.message,
          );
          setLoading(false);
        });
    }

    setLoading(true);
    load();

    // Poll every 2s while episode is not terminal
    let pollFailures = 0;
    const interval = setInterval(() => {
      if (cancelled) return;
      fetchEpisode(episodeId)
        .then((data) => {
          if (cancelled) return;
          pollFailures = 0;
          setEpisode(data);
          if (data.is_complete === 1) {
            clearInterval(interval);
          }
        })
        .catch((err: Error) => {
          if (cancelled) return;
          pollFailures++;
          // Surface persistent failures (3+ consecutive) so user knows
          if (pollFailures >= 3) {
            setFetchError(`Polling failed: ${err.message}`);
            clearInterval(interval);
          }
        });
    }, 2000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [episodeId]);

  // Escape key closes the detail panel
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setSelectedSpan(null);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Collapse/expand detail panel based on selectedSpan
  useEffect(() => {
    const panel = detailPanelRef.current;
    if (!panel) return;
    if (selectedSpan) {
      panel.expand();
    } else {
      panel.collapse();
    }
  }, [selectedSpan]);

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 p-6">
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-48 w-full rounded-3xl" />
        <Skeleton className="h-96 w-full rounded-3xl" />
      </div>
    );
  }

  if (fetchError) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 p-6">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/runs">Runs</Link>
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
          <AlertTitle>Unable to load run</AlertTitle>
          <AlertDescription>{fetchError}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!episode) return null;

  return (
    <RunDetailContent
      episode={episode}
      episodeId={episodeId}
      selectedSpan={selectedSpan}
      setSelectedSpan={setSelectedSpan}
      detailPanelRef={detailPanelRef}
    />
  );
}

interface RunDetailContentProps {
  episode: EpisodeDetail;
  episodeId: string;
  selectedSpan: TraceSpan | null;
  setSelectedSpan: (span: TraceSpan | null) => void;
  detailPanelRef: React.RefObject<PanelImperativeHandle | null>;
}

type ViewMode = "timeline" | "graph" | "split";

function RunDetailContent({
  episode,
  episodeId,
  selectedSpan,
  setSelectedSpan,
  detailPanelRef,
}: RunDetailContentProps) {
  const { spans, isLive, totalSpans } = useTraceStream({
    episodeId,
    sandboxId: episode.sandbox_id || null,
    initialSteps: episode.steps as Record<string, unknown>[],
    episodeStartTs: episode.started_at,
  });

  const isRunning = episode.is_complete !== 1;

  const [searchParams, setSearchParams] = useSearchParams();
  const viewParam = searchParams.get("view");
  const initialViewMode: ViewMode =
    viewParam === "graph" || viewParam === "split" ? viewParam : "timeline";
  const [viewMode, setViewMode] = useState<ViewMode>(initialViewMode);

  const setViewModeAndParam = (mode: ViewMode) => {
    setViewMode(mode);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("view", mode);
        return next;
      },
      { replace: true },
    );
  };

  // 1/2/3 hotkeys for view switching
  useHotkeys("1", () => setViewModeAndParam("timeline"), {
    enableOnFormTags: false,
  });
  useHotkeys("2", () => setViewModeAndParam("graph"), {
    enableOnFormTags: false,
  });
  useHotkeys("3", () => setViewModeAndParam("split"), {
    enableOnFormTags: false,
  });

  const cardTitle =
    viewMode === "timeline"
      ? "Trace Timeline"
      : viewMode === "graph"
        ? "Trace Graph"
        : "Trace Timeline & Graph";

  return (
    <div className="flex flex-col" style={{ height: "calc(100vh - 48px)" }}>
      {/* Compact header */}
      <div className="shrink-0 mx-auto w-full max-w-6xl space-y-3 px-6 pt-4 pb-3">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/runs">Runs</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage className="font-mono text-xs truncate max-w-xs">
                {episodeId}
              </BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>

        <Card className="gap-0 rounded-2xl bg-secondary text-secondary-foreground">
          <CardHeader className="py-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="space-y-1.5 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="default">Run detail</Badge>
                  <StatusBadge
                    status={episode.outcome}
                    type="outcome"
                    className="bg-background text-foreground"
                  />
                  {isLive && <Badge variant="secondary">Live</Badge>}
                </div>
                <CardTitle className="font-mono text-sm truncate text-secondary-foreground">
                  {episodeId}
                </CardTitle>
                <CardDescription className="text-secondary-foreground">
                  {episode.task_name}
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2 shrink-0">
                {episode.ended_at != null && (
                  <>
                    <Button variant="default" size="sm" className="h-8" asChild>
                      <Link to={`/replay/${episodeId}`}>
                        <RotateCcw className="size-3.5" />
                        Open Replay
                      </Link>
                    </Button>
                    <ExportButton
                      data={episode}
                      filename={`episode-${episodeId}`}
                      csvRows={[
                        flattenEpisodeForCsv(
                          episode as Record<string, unknown>,
                        ),
                      ]}
                    />
                  </>
                )}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-secondary-foreground mt-2">
              <span>
                Score:{" "}
                <span className="font-mono font-semibold">
                  {episode.score != null ? episode.score.toFixed(2) : "--"}
                </span>
              </span>
              <span>
                Steps:{" "}
                <span className="font-mono font-semibold">
                  {episode.step_count}
                </span>
              </span>
              <span>
                Duration:{" "}
                <span className="font-mono font-semibold">
                  {formatDuration(episode.duration_ms)}
                </span>
              </span>
              <span>
                Cost:{" "}
                <span className="font-mono font-semibold">
                  {formatCost(episode.cost_usd)}
                </span>
              </span>
              <span>
                Started:{" "}
                <span className="font-semibold">
                  {formatDatetime(episode.started_at)}
                </span>
              </span>
              {episode.ended_at && (
                <span>
                  Ended:{" "}
                  <span className="font-semibold">
                    {formatDatetime(episode.ended_at)}
                  </span>
                </span>
              )}
            </div>
          </CardHeader>
        </Card>
      </div>

      {/* Trace card — fills remaining viewport height */}
      <div className="flex-1 min-h-0 px-6 pb-6">
        <Card className="overflow-hidden p-0 rounded-3xl h-full flex flex-col">
          <CardHeader className="shrink-0 px-4 py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CardTitle className="text-sm font-medium">
                  {cardTitle}
                </CardTitle>
                {isLive && (
                  <Badge variant="secondary" className="text-xs">
                    Live
                  </Badge>
                )}
                {totalSpans > 0 && (
                  <Badge variant="secondary" className="text-xs tabular-nums">
                    {totalSpans} spans
                  </Badge>
                )}
              </div>
              <ToggleGroup
                type="single"
                value={viewMode}
                onValueChange={(v) => {
                  if (v) setViewModeAndParam(v as ViewMode);
                }}
                size="sm"
                variant="default"
              >
                <Tooltip>
                  <TooltipTrigger asChild>
                    <ToggleGroupItem value="timeline" className="px-2 py-1">
                      <List className="size-3.5" />
                    </ToggleGroupItem>
                  </TooltipTrigger>
                  <TooltipContent>Timeline (1)</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <ToggleGroupItem value="graph" className="px-2 py-1">
                      <GitBranch className="size-3.5" />
                    </ToggleGroupItem>
                  </TooltipTrigger>
                  <TooltipContent>Graph (2)</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <ToggleGroupItem value="split" className="px-2 py-1">
                      <LayoutGrid className="size-3.5" />
                    </ToggleGroupItem>
                  </TooltipTrigger>
                  <TooltipContent>Split view (3)</TooltipContent>
                </Tooltip>
              </ToggleGroup>
            </div>
          </CardHeader>
          <div className="flex-1 min-h-0 overflow-hidden rounded-[inherit] bg-muted p-2">
            <ResizablePanelGroup
              orientation="horizontal"
              className="h-full rounded-[inherit] bg-card"
            >
              <ResizablePanel
                defaultSize={selectedSpan ? 60 : 100}
                minSize={35}
              >
                {viewMode === "timeline" && (
                  <TraceTimeline
                    spans={spans}
                    isLive={isLive}
                    isRunning={isRunning}
                    totalSpans={totalSpans}
                    onSpanSelect={setSelectedSpan}
                    selectedSpanId={selectedSpan?.id ?? null}
                  />
                )}
                {viewMode === "graph" && (
                  <TraceGraph
                    spans={spans}
                    isLive={isLive}
                    onSpanSelect={setSelectedSpan}
                    selectedSpanId={selectedSpan?.id ?? null}
                  />
                )}
                {viewMode === "split" && (
                  <ResizablePanelGroup
                    orientation="vertical"
                    className="h-full"
                  >
                    <ResizablePanel defaultSize={50} minSize={25}>
                      <TraceTimeline
                        spans={spans}
                        isLive={isLive}
                        isRunning={isRunning}
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

              {selectedSpan && <ResizableHandle withHandle />}

              <ResizablePanel
                defaultSize={40}
                minSize={25}
                collapsible
                collapsedSize={0}
                panelRef={detailPanelRef}
              >
                {selectedSpan && (
                  <TraceDetailPanel
                    span={selectedSpan}
                    episodeStartTs={episode.started_at}
                    parentDurationMs={
                      episode.duration_ms > 0 ? episode.duration_ms : undefined
                    }
                    onClose={() => setSelectedSpan(null)}
                  />
                )}
              </ResizablePanel>
            </ResizablePanelGroup>
          </div>
        </Card>
      </div>
    </div>
  );
}

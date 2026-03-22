import { useState, useEffect, useCallback } from "react";
import { Link, useNavigate } from "react-router";
import { formatDistanceToNow } from "date-fns";
import { AlertCircle, ArrowRight, Monitor, Rocket } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  fetchCUAEpisodes,
  type EpisodeSummary,
} from "@/lib/api";
import CUALauncher from "@/routes/CUALauncher";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(ms: number): string {
  if (ms <= 0) return "--";
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds}s`;
  return `${minutes}m ${seconds}s`;
}

// ---------------------------------------------------------------------------
// CUA Episode History
// ---------------------------------------------------------------------------

const PAGE_SIZE = 30;

function CUAHistory() {
  const navigate = useNavigate();
  const [episodes, setEpisodes] = useState<EpisodeSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const loadEpisodes = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const data = await fetchCUAEpisodes({ offset, limit: PAGE_SIZE });
      setEpisodes(data.items);
      setTotal(data.total);
    } catch (e) {
      setFetchError(
        e instanceof Error ? e.message : "Failed to load CUA episodes.",
      );
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    loadEpisodes();
  }, [loadEpisodes]);

  if (fetchError) {
    return (
      <Alert variant="destructive" className="mt-4 border-0">
        <AlertCircle className="size-4" />
        <AlertTitle>Unable to load CUA episodes</AlertTitle>
        <AlertDescription>{fetchError}</AlertDescription>
      </Alert>
    );
  }

  if (loading) {
    return (
      <div className="mt-4 space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full rounded-2xl" />
        ))}
      </div>
    );
  }

  if (episodes.length === 0) {
    return (
      <div className="mt-4 rounded-2xl bg-muted px-6 py-16 text-center">
        <Badge variant="secondary">No CUA episodes</Badge>
        <p className="mt-4 text-sm text-muted-foreground">
          No desktop agent episodes yet. Launch one from the New Episode tab.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-4 space-y-4">
      <div className="space-y-2">
        {episodes.map((ep) => (
          <div
            key={ep.episode_id}
            onClick={() => navigate(`/replay/${ep.episode_id}`)}
            className="flex cursor-pointer items-center gap-4 rounded-2xl bg-muted px-4 py-3 hover:bg-accent transition-colors"
          >
            <Monitor className="size-4 text-muted-foreground shrink-0" />
            <div className="flex-1 min-w-0">
              <span className="block font-mono text-sm truncate">
                {ep.task_name || ep.episode_id}
              </span>
              <span className="block text-xs text-muted-foreground truncate">
                {ep.episode_id}
              </span>
            </div>
            <StatusBadge status={ep.outcome} type="outcome" />
            <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
              {ep.score != null ? ep.score.toFixed(2) : "--"}
            </span>
            <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
              {formatDuration(ep.duration_ms)}
            </span>
            {ep.started_at > 0 && (
              <span className="shrink-0 text-xs text-muted-foreground">
                {formatDistanceToNow(new Date(ep.started_at * 1000), {
                  addSuffix: true,
                })}
              </span>
            )}
            <ArrowRight className="size-3.5 text-muted-foreground shrink-0" />
          </div>
        ))}
      </div>

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of{" "}
            {total}
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
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CUA Page
// ---------------------------------------------------------------------------

export default function CUA() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <Card className="gap-0 rounded-3xl bg-secondary text-secondary-foreground">
        <CardHeader className="gap-5 lg:grid-cols-[1fr_auto] lg:items-end">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Badge variant="default" className="w-fit">
                <Monitor className="size-3" />
                Computer-Using Agent
              </Badge>
              <Badge variant="secondary" className="text-[10px]">
                Beta
              </Badge>
            </div>
            <div className="space-y-2">
              <CardTitle className="text-3xl tracking-tight">
                CUA Desktop Agent
              </CardTitle>
              <CardDescription className="max-w-2xl text-base text-secondary-foreground">
                Launch and review desktop agent episodes. Each episode runs in
                an isolated sandbox with a full X11 desktop, Chromium browser,
                and VNC streaming.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
      </Card>

      <Tabs defaultValue="launch">
        <TabsList>
          <TabsTrigger value="launch">
            <Rocket className="size-3.5" />
            New Episode
          </TabsTrigger>
          <TabsTrigger value="history">
            <Monitor className="size-3.5" />
            History
          </TabsTrigger>
        </TabsList>

        <TabsContent value="launch">
          <CUALauncher />
        </TabsContent>

        <TabsContent value="history">
          <CUAHistory />
        </TabsContent>
      </Tabs>
    </div>
  );
}

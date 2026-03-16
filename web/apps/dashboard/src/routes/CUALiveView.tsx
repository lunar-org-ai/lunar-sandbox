import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, Link, useNavigate, useLocation } from "react-router";
import {
  Eye,
  MousePointer,
  Maximize2,
  Camera,
  Square,
  ArrowLeft,
  Monitor,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { NoVNCViewer } from "@/components/NoVNCViewer";
import { fetchCUAEpisodeDetail, type CUAEpisodeInfo } from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// CUALiveView
// ---------------------------------------------------------------------------

export default function CUALiveView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const episodeId = id ?? "";

  // VNC URL passed from launcher via navigation state
  const vncUrl = (location.state as { vncUrl?: string } | null)?.vncUrl ?? "";

  // Connection state
  const [connected, setConnected] = useState(false);

  // Episode info state
  const [episodeInfo, setEpisodeInfo] = useState<CUAEpisodeInfo | null>(null);
  const [complete, setComplete] = useState(false);

  // Toolbar state
  const [viewOnly, setViewOnly] = useState(true);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Refs for timers
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ---------------------------------------------------------------------------
  // Episode polling (every 3 seconds)
  // ---------------------------------------------------------------------------
  const pollEpisode = useCallback(async () => {
    if (!episodeId) return;
    try {
      const info = await fetchCUAEpisodeDetail(episodeId);
      setEpisodeInfo(info);
      if (info.outcome && info.outcome !== "running") {
        setComplete(true);
      }
    } catch {
      // Silently ignore poll errors
    }
  }, [episodeId]);

  useEffect(() => {
    pollEpisode();
    pollTimerRef.current = setInterval(pollEpisode, 3000);
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [pollEpisode]);

  // ---------------------------------------------------------------------------
  // Elapsed timer (starts when connected)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (connected && !complete) {
      elapsedTimerRef.current = setInterval(() => {
        setElapsedSeconds((s) => s + 1);
      }, 1000);
    } else {
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
    }
    return () => {
      if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    };
  }, [connected, complete]);

  // ---------------------------------------------------------------------------
  // Fullscreen
  // ---------------------------------------------------------------------------
  const viewerContainerRef = useRef<HTMLDivElement | null>(null);

  function handleFullscreen() {
    if (!viewerContainerRef.current) return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      viewerContainerRef.current.requestFullscreen().catch(() => {});
    }
  }

  // ---------------------------------------------------------------------------
  // Stop episode (navigate away)
  // ---------------------------------------------------------------------------
  function handleStop() {
    navigate("/runs");
  }

  // ---------------------------------------------------------------------------
  // Screenshot capture (opens screenshot in new tab)
  // ---------------------------------------------------------------------------
  function handleScreenshot() {
    // Screenshot API not yet wired -- placeholder
    window.open(
      `/api/cua/episodes/${encodeURIComponent(episodeId)}/screenshot`,
      "_blank",
    );
  }

  // ---------------------------------------------------------------------------
  // Derived values
  // ---------------------------------------------------------------------------
  const wsUrl = vncUrl;
  const isRunning = !complete;
  const statusLabel = complete ? "Complete" : "Running";

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="h-screen flex flex-col bg-background text-foreground overflow-hidden">
      {/* Toolbar */}
      <div className="shrink-0 flex items-center gap-3 px-4 h-12 bg-background">
        {/* Back */}
        <Link
          to="/runs"
          className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors text-sm"
        >
          <ArrowLeft className="size-4" />
          Runs
        </Link>

        {/* Episode ID */}
        <div className="flex items-center gap-1.5">
          <Monitor className="size-4 text-muted-foreground" />
          <span className="font-mono text-xs text-muted-foreground truncate max-w-35">
            {episodeId || "--"}
          </span>
        </div>

        {/* Status badge */}
        <Badge variant={isRunning ? "secondary" : "default"}>
          {statusLabel}
        </Badge>

        {/* Elapsed time */}
        <span className="font-mono text-xs text-muted-foreground tabular-nums">
          {formatElapsed(elapsedSeconds)}
        </span>

        <div className="flex-1" />

        {/* Stop button */}
        <Button
          variant="ghost"
          size="sm"
          className="h-8 gap-1.5 text-xs text-muted-foreground hover:text-destructive hover:bg-destructive/10"
          onClick={handleStop}
          title="Stop and return to runs"
        >
          <Square className="size-3.5" />
          Stop
        </Button>

        {/* Interaction toggle */}
        <Button
          variant="ghost"
          size="sm"
          className={`h-8 gap-1.5 text-xs ${!viewOnly ? "text-foreground bg-muted" : "text-muted-foreground"}`}
          onClick={() => setViewOnly((v) => !v)}
          title={viewOnly ? "Enable interaction" : "Switch to view-only"}
        >
          {viewOnly ? (
            <>
              <Eye className="size-3.5" />
              View only
            </>
          ) : (
            <>
              <MousePointer className="size-3.5" />
              Interactive
            </>
          )}
        </Button>

        {/* Screenshot */}
        <Button
          variant="ghost"
          size="sm"
          className="h-8 px-2 text-muted-foreground hover:text-foreground"
          onClick={handleScreenshot}
          title="Capture screenshot"
        >
          <Camera className="size-4" />
        </Button>

        {/* Fullscreen */}
        <Button
          variant="ghost"
          size="sm"
          className="h-8 px-2 text-muted-foreground hover:text-foreground"
          onClick={handleFullscreen}
          title="Toggle fullscreen"
        >
          <Maximize2 className="size-4" />
        </Button>
      </div>

      {/* Desktop viewer */}
      <div ref={viewerContainerRef} className="flex-1 relative overflow-hidden">
        {episodeId && wsUrl && (
          <NoVNCViewer
            wsUrl={wsUrl}
            viewOnly={viewOnly}
            onConnect={() => setConnected(true)}
            onDisconnect={() => setConnected(false)}
            className="w-full h-full"
          />
        )}

        {/* No VNC URL available */}
        {episodeId && !wsUrl && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center space-y-2">
              <p className="text-sm font-medium">No VNC session available</p>
              <p className="text-xs text-muted-foreground">
                The desktop session URL was not provided. Try launching a new
                episode.
              </p>
            </div>
          </div>
        )}

        {/* Episode complete overlay */}
        {complete && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/80 z-10">
            <div className="rounded-2xl bg-card px-8 py-6 flex flex-col items-center gap-4 shadow-2xl">
              <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
                <Square className="size-5 text-secondary-foreground" />
              </div>
              <div className="text-center">
                <p className="font-semibold text-foreground">
                  Episode complete
                </p>
                {episodeInfo?.outcome && (
                  <p className="text-sm text-muted-foreground mt-1">
                    Outcome:{" "}
                    <span className="font-mono">{episodeInfo.outcome}</span>
                    {episodeInfo.score != null && (
                      <>
                        {" "}
                        &middot; Score:{" "}
                        <span className="font-mono">
                          {episodeInfo.score.toFixed(2)}
                        </span>
                      </>
                    )}
                  </p>
                )}
              </div>
              <Button size="sm" onClick={() => navigate("/runs")}>
                Back to Runs
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

import { useState, useEffect, useRef } from "react";
import { useParams, Link } from "react-router";
import { formatDistanceToNow } from "date-fns";
import { ArrowLeft, Terminal as TerminalIcon } from "lucide-react";
import type { PanelImperativeHandle } from "react-resizable-panels";

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
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { SandboxTerminal } from "@/components/SandboxTerminal";
import { useEventStream } from "@/hooks/useEventStream";
import { fetchSandbox, stopSandbox, type SandboxInfo } from "@/lib/api";

export default function SandboxDetail() {
  const { id } = useParams<{ id: string }>();
  const sandboxId = id ?? "";

  const [sandbox, setSandbox] = useState<SandboxInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);

  // Terminal drawer state
  const [terminalOpen, setTerminalOpen] = useState(false);
  // Once opened, keep mounted so the session persists when collapsed
  const terminalMountedRef = useRef(false);
  const terminalPanelRef = useRef<PanelImperativeHandle | null>(null);

  // Initial REST fetch
  useEffect(() => {
    if (!sandboxId) return;
    setLoading(true);
    fetchSandbox(sandboxId)
      .then((data) => {
        setSandbox(data);
        setLoading(false);
      })
      .catch((e: Error) => {
        setFetchError(e.message);
        setLoading(false);
      });
  }, [sandboxId]);

  // Live WS updates -- subscribe to sandbox topic
  const { events } = useEventStream({ topic: "sandbox" });

  useEffect(() => {
    const latest = events[events.length - 1];
    if (!latest || latest.type !== "sandbox_status") return;

    const payload = latest.payload as {
      sandbox_id?: string;
      state?: string;
      cpu_percent?: number;
      memory_mb?: number;
    };
    if (payload.sandbox_id !== sandboxId) return;

    setSandbox((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        state: (payload.state as string) ?? prev.state,
        cpu_percent: payload.cpu_percent ?? prev.cpu_percent,
        memory_mb: payload.memory_mb ?? prev.memory_mb,
      };
    });
  }, [events, sandboxId]);

  async function handleStop() {
    setStopError(null);
    setStopping(true);
    try {
      await stopSandbox(sandboxId);
      setSandbox((prev) => (prev ? { ...prev, state: "Finished" } : prev));
    } catch (e) {
      setStopError(e instanceof Error ? e.message : "Failed to stop sandbox.");
    } finally {
      setStopping(false);
    }
  }

  function handleToggleTerminal() {
    const opening = !terminalOpen;
    setTerminalOpen(opening);
    if (opening) {
      terminalMountedRef.current = true;
      // Expand the panel when opening
      setTimeout(() => {
        terminalPanelRef.current?.expand();
      }, 0);
    } else {
      // Collapse but keep mounted so session persists
      terminalPanelRef.current?.collapse();
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-6">
        <Skeleton className="h-48 w-full rounded-3xl" />
        <Skeleton className="h-48 w-full rounded-2xl" />
      </div>
    );
  }

  if (fetchError) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-6">
        <Button variant="ghost" size="sm" asChild className="-ml-2">
          <Link to="/">
            <ArrowLeft className="size-4" />
            Home
          </Link>
        </Button>
        <Alert variant="destructive" className="border-0">
          <AlertTitle>Unable to load sandbox</AlertTitle>
          <AlertDescription>{fetchError}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!sandbox) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-6">
        <Alert className="border-0">
          <AlertTitle>Sandbox not found</AlertTitle>
          <AlertDescription>
            <Button variant="ghost" size="sm" asChild className="-ml-2 mt-2">
              <Link to="/">
                <ArrowLeft className="size-4" />
                Back to Home
              </Link>
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const startedAtFormatted = sandbox.started_at
    ? formatDistanceToNow(new Date(sandbox.started_at * 1000), {
        addSuffix: true,
      })
    : "--";

  const mainContent = (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      {/* Hero card */}
      <Card className="gap-0 rounded-3xl bg-secondary text-secondary-foreground">
        <CardHeader className="gap-4">
          <div className="flex items-center justify-between">
            <Button
              variant="ghost"
              size="sm"
              asChild
              className="-ml-2 text-secondary-foreground"
            >
              <Link to="/">
                <ArrowLeft className="size-4" />
                Home
              </Link>
            </Button>
            <div className="flex items-center gap-2">
              <Badge variant="default">Sandbox</Badge>
              <StatusBadge status={sandbox.state} type="sandbox" />
            </div>
          </div>
          <div className="space-y-1">
            <CardTitle className="text-2xl tracking-tight">Sandbox</CardTitle>
            <CardDescription className="font-mono text-sm text-secondary-foreground">
              {sandboxId}
            </CardDescription>
          </div>
          {/* Actions */}
          <div className="flex flex-wrap items-center gap-2">
            {sandbox.state === "Running" && (
              <Button
                variant="destructive"
                size="sm"
                onClick={handleStop}
                disabled={stopping}
              >
                {stopping ? "Stopping..." : "Stop Sandbox"}
              </Button>
            )}
            <Button variant="default" size="sm" onClick={handleToggleTerminal}>
              <TerminalIcon className="size-4" />
              {terminalOpen ? "Hide Terminal" : "Terminal"}
            </Button>
          </div>
          {stopError && <p className="text-sm text-destructive">{stopError}</p>}
        </CardHeader>
      </Card>

      {/* Detail card */}
      <Card className="gap-0 rounded-2xl">
        <CardHeader>
          <CardTitle className="text-base font-medium">Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-muted p-4">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Sandbox ID
              </span>
              <span className="mt-2 block font-mono text-xs break-all">
                {sandbox.sandbox_id}
              </span>
            </div>
            <div className="rounded-xl bg-muted p-4">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Fingerprint
              </span>
              <span
                className="mt-2 block font-mono text-xs truncate"
                title={sandbox.fingerprint}
              >
                {sandbox.fingerprint || "--"}
              </span>
            </div>
            <div className="rounded-xl bg-muted p-4">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                State
              </span>
              <span className="mt-2 block">
                <StatusBadge status={sandbox.state} type="sandbox" />
              </span>
            </div>
            <div className="rounded-xl bg-muted p-4">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Started At
              </span>
              <span className="mt-2 block text-sm font-semibold">
                {startedAtFormatted}
              </span>
            </div>
            <div className="rounded-xl bg-muted p-4">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                CPU
              </span>
              <span className="mt-2 block text-lg font-semibold tabular-nums">
                {sandbox.cpu_percent != null
                  ? `${sandbox.cpu_percent.toFixed(1)}%`
                  : "--"}
              </span>
            </div>
            <div className="rounded-xl bg-muted p-4">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Memory
              </span>
              <span className="mt-2 block text-lg font-semibold tabular-nums">
                {sandbox.memory_mb != null
                  ? `${sandbox.memory_mb.toFixed(0)} MB`
                  : "--"}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );

  // Terminal drawer panel (always mounted once opened, hidden when collapsed)
  const terminalPanel = terminalMountedRef.current ? (
    <div className={terminalOpen ? "flex flex-col h-full" : "hidden"}>
      {/* Drawer header bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-muted shrink-0">
        <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
          <TerminalIcon className="size-3.5" />
          <span>Terminal — {sandboxId}</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
          onClick={handleToggleTerminal}
          aria-label="Close terminal"
        >
          x
        </Button>
      </div>
      {/* xterm.js terminal */}
      <div className="flex-1 min-h-0 bg-[#09090b]">
        <SandboxTerminal sandboxId={sandboxId} sandboxStatus={sandbox.state} />
      </div>
    </div>
  ) : null;

  return (
    <ResizablePanelGroup orientation="vertical" className="h-screen">
      {/* Top panel: sandbox detail content */}
      <ResizablePanel
        defaultSize={terminalOpen ? 55 : 100}
        minSize={30}
        className="overflow-y-auto"
      >
        {mainContent}
      </ResizablePanel>

      {/* Handle only visible when terminal is open */}
      {terminalOpen && <ResizableHandle withHandle />}

      {/* Bottom panel: terminal drawer */}
      {terminalMountedRef.current && (
        <ResizablePanel
          panelRef={terminalPanelRef}
          defaultSize={terminalOpen ? 45 : 0}
          minSize={0}
          collapsible
          collapsedSize={0}
          className="min-h-0"
        >
          {terminalPanel}
        </ResizablePanel>
      )}
    </ResizablePanelGroup>
  );
}

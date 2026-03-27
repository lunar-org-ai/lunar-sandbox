import { useEffect, useRef, useState } from "react";
import {
  Bot,
  User,
  MousePointer,
  Keyboard,
  ScrollText,
  CircleStop,
  Play,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Sparkles,
  Eye,
  ChevronDown,
  Image as ImageIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { CUAEvent } from "@/hooks/useCUAStream";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CUAActivityPanelProps {
  events: CUAEvent[];
  isLive: boolean;
}

// ---------------------------------------------------------------------------
// Action icon mapping
// ---------------------------------------------------------------------------

const ACTION_ICONS: Record<string, typeof MousePointer> = {
  click: MousePointer,
  left_click: MousePointer,
  right_click: MousePointer,
  double_click: MousePointer,
  mouse_move: MousePointer,
  type: Keyboard,
  key: Keyboard,
  scroll: ScrollText,
  screenshot: Sparkles,
  stop: CircleStop,
  done: CheckCircle2,
};

function getActionIcon(action: string) {
  return ACTION_ICONS[action] ?? MousePointer;
}

function formatActionLabel(action: string, params: Record<string, unknown>): string {
  switch (action) {
    case "click":
    case "left_click":
      return params.coordinate
        ? `Click (${(params.coordinate as number[]).join(", ")})`
        : "Click";
    case "right_click":
      return params.coordinate
        ? `Right-click (${(params.coordinate as number[]).join(", ")})`
        : "Right-click";
    case "double_click":
      return params.coordinate
        ? `Double-click (${(params.coordinate as number[]).join(", ")})`
        : "Double-click";
    case "mouse_move":
      return params.coordinate
        ? `Move to (${(params.coordinate as number[]).join(", ")})`
        : "Move";
    case "type":
      return params.text
        ? `Type "${truncate(params.text as string, 30)}"`
        : "Type";
    case "key":
      return params.text ? `Key: ${params.text}` : "Keystroke";
    case "scroll":
      return params.coordinate
        ? `Scroll (${(params.coordinate as number[]).join(", ")})`
        : "Scroll";
    case "screenshot":
      return "Take screenshot";
    case "stop":
    case "done":
      return "Task complete";
    default:
      return action.replace(/_/g, " ");
  }
}

function truncate(str: string, max: number): string {
  return str.length > max ? str.slice(0, max) + "\u2026" : str;
}

// ---------------------------------------------------------------------------
// Event renderers
// ---------------------------------------------------------------------------

function StartEvent({ event }: { event: CUAEvent }) {
  return (
    <div className="flex gap-3 px-3 py-3">
      <div className="shrink-0 mt-0.5">
        <div className="size-7 rounded-full bg-primary/10 flex items-center justify-center">
          <User className="size-3.5 text-primary" />
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
          Task
        </p>
        {event.instruction && (
          <div className="rounded-lg bg-primary/5 border border-primary/10 px-3 py-2">
            <p className="text-xs text-foreground leading-relaxed">
              {event.instruction}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function StepScreenshot({ url }: { url: string }) {
  const [expanded, setExpanded] = useState(false);
  const [hasError, setHasError] = useState(false);

  if (hasError) return null;

  return (
    <div
      className="cursor-pointer group"
      onClick={() => setExpanded((v) => !v)}
    >
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground mb-1">
        <ImageIcon className="size-3" />
        <span>Screenshot</span>
        <ChevronDown
          className={cn(
            "size-3 transition-transform",
            expanded && "rotate-180",
          )}
        />
      </div>
      {expanded && (
        <img
          src={url}
          alt="Step screenshot"
          className="rounded-md border border-border w-full max-h-48 object-contain bg-black/5"
          onError={() => setHasError(true)}
        />
      )}
    </div>
  );
}

function StepEvent({ event }: { event: CUAEvent }) {
  const ActionIcon = getActionIcon(event.action ?? "");
  const label = formatActionLabel(event.action ?? "", event.actionParams);
  const hasReasoning = event.reasoning && event.reasoning.trim().length > 0;

  return (
    <div className="flex gap-3 px-3 py-3">
      <div className="shrink-0 mt-0.5">
        <div className="size-7 rounded-full bg-muted flex items-center justify-center">
          <Bot className="size-3.5 text-muted-foreground" />
        </div>
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        {/* Step header */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
            Step {(event.step ?? 0) + 1}
          </span>
        </div>

        {/* Reasoning / thinking */}
        {hasReasoning && (
          <div className="rounded-lg bg-muted/50 border border-border/50 px-3 py-2">
            <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
              Reasoning
            </p>
            <p className="text-xs text-foreground leading-relaxed whitespace-pre-wrap">
              {event.reasoning}
            </p>
          </div>
        )}

        {/* Action */}
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className="gap-1.5 text-[10px] font-mono h-5"
          >
            <ActionIcon className="size-2.5" />
            {label}
          </Badge>
        </div>

        {/* Screenshot thumbnail */}
        {event.screenshotUrl && (
          <StepScreenshot url={event.screenshotUrl} />
        )}
      </div>
    </div>
  );
}

function EndEvent({ event }: { event: CUAEvent }) {
  const isSuccess = event.outcome === "completed";
  const isError = event.outcome === "agent_error" || event.outcome === "infra_error";

  return (
    <div className="flex gap-3 px-3 py-3">
      <div className="shrink-0 mt-0.5">
        <div
          className={cn(
            "size-7 rounded-full flex items-center justify-center",
            isSuccess && "bg-green-500/10",
            isError && "bg-destructive/10",
            !isSuccess && !isError && "bg-amber-500/10",
          )}
        >
          {isSuccess ? (
            <CheckCircle2 className="size-3.5 text-green-500" />
          ) : isError ? (
            <AlertTriangle className="size-3.5 text-destructive" />
          ) : (
            <Clock className="size-3.5 text-amber-500" />
          )}
        </div>
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-xs font-medium text-foreground">
          Episode {event.outcome?.replace(/_/g, " ") ?? "ended"}
        </p>
        <div className="flex items-center gap-3 flex-wrap">
          {event.stepCount != null && (
            <span className="text-[10px] text-muted-foreground">
              {event.stepCount} steps
            </span>
          )}
          {event.durationMs != null && (
            <span className="text-[10px] text-muted-foreground">
              {(event.durationMs / 1000).toFixed(1)}s
            </span>
          )}
        </div>
        {event.error && (
          <div className="rounded-lg bg-destructive/5 border border-destructive/10 px-3 py-2 mt-2">
            <p className="text-xs text-destructive">{event.error}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function CUAActivityPanel({ events, isLive }: CUAActivityPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new events
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="shrink-0 flex items-center gap-2 px-3 h-10 border-b border-border">
        <Bot className="size-4 text-muted-foreground" />
        <span className="text-xs font-medium text-foreground">
          Agent Activity
        </span>
        <div className="flex-1" />
        {isLive && (
          <span className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <span className="size-1.5 rounded-full bg-green-500 animate-pulse" />
            Live
          </span>
        )}
        {events.length > 0 && (
          <span className="text-[10px] text-muted-foreground tabular-nums">
            {events.filter((e) => e.type === "step").length} steps
          </span>
        )}
      </div>

      {/* Events list */}
      <div className="flex-1 min-h-0">
      <ScrollArea className="h-full">
        <div className="divide-y divide-border/50">
          {events.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
              <div className="size-10 rounded-full bg-muted flex items-center justify-center mb-3">
                <Bot className="size-5 text-muted-foreground" />
              </div>
              <p className="text-xs text-muted-foreground">
                Waiting for agent activity...
              </p>
              <p className="text-[10px] text-muted-foreground/70 mt-1">
                Events will appear here as the model runs
              </p>
            </div>
          )}

          {events.map((event) => {
            switch (event.type) {
              case "start":
                return <StartEvent key={event.id} event={event} />;
              case "step":
                return <StepEvent key={event.id} event={event} />;
              case "end":
                return <EndEvent key={event.id} event={event} />;
              default:
                return null;
            }
          })}
        </div>
        <div ref={bottomRef} />
      </ScrollArea>
      </div>
    </div>
  );
}

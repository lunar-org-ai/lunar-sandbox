import { ChevronDown, ChevronRight } from "lucide-react";

import {
  formatDurationMs,
  getActionColor,
  type TraceSpan,
} from "@/lib/trace-utils";
import { cn } from "@/lib/utils";

interface TraceTimelineRowBaseProps {
  span: TraceSpan;
  isSelected: boolean;
  onClick: () => void;
}

interface TraceTimelineRowBarProps extends TraceTimelineRowBaseProps {
  totalMs: number;
  zoom: number;
  isPulsing?: boolean;
}

export function TraceTimelineRowLabel({
  span,
  isSelected,
  onClick,
}: TraceTimelineRowBaseProps) {
  const color = getActionColor(span.action);

  return (
    <div
      className={cn(
        "flex h-9 cursor-pointer items-center gap-2 px-2 text-xs transition-colors",
        "hover:bg-accent",
        isSelected && "bg-accent",
      )}
      style={{ paddingLeft: `${8 + span.depth * 16}px` }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onClick();
      }}
    >
      {/* Colored action type pill */}
      <span
        className={cn("inline-block shrink-0 rounded-sm", color.bg)}
        style={{ width: 10, height: 10 }}
      />
      {/* Step index */}
      <span className="shrink-0 font-mono text-muted-foreground w-6 text-right">
        {span.stepIdx + 1}
      </span>
      {/* Action type name */}
      <span
        className={cn(
          "truncate flex-1",
          isSelected ? "text-foreground font-medium" : "text-foreground",
        )}
      >
        {span.action}
      </span>
      {/* Duration */}
      <span className="ml-auto shrink-0 font-mono text-muted-foreground">
        {formatDurationMs(span.durationMs)}
      </span>
    </div>
  );
}

const ERROR_STATUSES = new Set<string>(["error", "timeout"]);

export function TraceTimelineRowBar({
  span,
  totalMs,
  zoom,
  isSelected,
  isPulsing = false,
  onClick,
}: TraceTimelineRowBarProps) {
  const color = getActionColor(span.action);
  const isError = ERROR_STATUSES.has(span.status);

  const leftPct = totalMs > 0 ? (span.startMs / totalMs) * 100 : 0;
  const widthPct = totalMs > 0 ? (span.durationMs / totalMs) * 100 : 0;

  return (
    <div
      className={cn(
        "relative flex h-9 cursor-pointer items-center transition-colors",
        "hover:bg-accent",
        isSelected && "bg-accent",
      )}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onClick();
      }}
      style={{
        width: `${zoom * 100}%`,
        minWidth: "100%",
      }}
    >
      {/* Duration bar */}
      <div
        className={cn(
          "absolute h-5 rounded",
          color.bg,
          isError && "ring-1 ring-destructive",
          isSelected && "ring-1 ring-primary",
          isPulsing && "animate-pulse",
        )}
        style={{
          left: `${leftPct}%`,
          width: `${widthPct}%`,
          minWidth: 3,
        }}
      />
    </div>
  );
}

export interface SpanGroup {
  id: string;
  action: string;
  spans: TraceSpan[];
  totalMs: number;
}

interface GroupLabelProps {
  group: SpanGroup;
  isExpanded: boolean;
  onToggle: () => void;
}

export function TraceTimelineGroupLabel({
  group,
  isExpanded,
  onToggle,
}: GroupLabelProps) {
  const color = getActionColor(group.action);
  const totalDuration = group.spans.reduce((s, sp) => s + sp.durationMs, 0);

  return (
    <div
      className="flex h-9 cursor-pointer items-center gap-2 px-2 text-xs transition-colors hover:bg-accent bg-muted"
      onClick={onToggle}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onToggle();
      }}
    >
      {/* Expand/collapse icon */}
      {isExpanded ? (
        <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
      ) : (
        <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
      )}
      {/* Colored action type pill */}
      <span
        className={cn("inline-block shrink-0 rounded-sm", color.bg)}
        style={{ width: 10, height: 10 }}
      />
      {/* Action type name */}
      <span className="truncate flex-1 text-foreground font-medium">
        {group.action}
      </span>
      {/* Count badge */}
      <span className="shrink-0 rounded-full bg-secondary px-1.5 py-0.5 text-[10px] tabular-nums text-secondary-foreground font-semibold">
        ×{group.spans.length}
      </span>
      {/* Total duration */}
      <span className="shrink-0 font-mono text-muted-foreground">
        {formatDurationMs(totalDuration)}
      </span>
    </div>
  );
}

interface GroupBarProps {
  group: SpanGroup;
  totalMs: number;
  zoom: number;
  isExpanded: boolean;
  onToggle: () => void;
}

export function TraceTimelineGroupBar({
  group,
  totalMs,
  zoom,
  isExpanded,
  onToggle,
}: GroupBarProps) {
  const color = getActionColor(group.action);
  const firstSpan = group.spans[0]!;
  const lastSpan = group.spans[group.spans.length - 1]!;
  const groupStartMs = firstSpan.startMs;
  const groupEndMs = lastSpan.startMs + lastSpan.durationMs;
  const groupDurationMs = groupEndMs - groupStartMs;

  const leftPct = totalMs > 0 ? (groupStartMs / totalMs) * 100 : 0;
  const widthPct = totalMs > 0 ? (groupDurationMs / totalMs) * 100 : 0;

  return (
    <div
      className="relative flex h-9 cursor-pointer items-center transition-colors hover:bg-accent bg-muted"
      onClick={onToggle}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onToggle();
      }}
      style={{ width: `${zoom * 100}%`, minWidth: "100%" }}
    >
      {/* Group bar */}
      <div
        className={cn(
          "absolute h-5 rounded",
          color.bg,
          isExpanded && "ring-1 ring-primary",
        )}
        style={{
          left: `${leftPct}%`,
          width: `${Math.max(widthPct, 0.5)}%`,
          minWidth: 6,
        }}
      />
      {/* Count label inside bar */}
      <span
        className="absolute text-[9px] font-bold text-white pointer-events-none select-none px-1"
        style={{ left: `calc(${leftPct}% + 2px)` }}
      >
        ×{group.spans.length}
      </span>
    </div>
  );
}

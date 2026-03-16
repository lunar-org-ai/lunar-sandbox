import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import {
  ACTION_TYPES,
  getActionColor,
  type TraceSpan,
} from "@/lib/trace-utils";
import { cn } from "@/lib/utils";
import { TraceTimelineHeader } from "./TraceTimelineHeader";
import {
  TraceTimelineGroupBar,
  TraceTimelineGroupLabel,
  TraceTimelineRowBar,
  TraceTimelineRowLabel,
  type SpanGroup,
} from "./TraceTimelineRow";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TraceTimelineProps {
  spans: TraceSpan[];
  isLive: boolean;
  totalSpans: number;
  onSpanSelect?: (span: TraceSpan | null) => void;
  selectedSpanId?: string | null;
  /** Episode is still running (not yet complete) */
  isRunning?: boolean;
}

type SpanRow =
  | { kind: "single"; span: TraceSpan }
  | { kind: "group"; group: SpanGroup };

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 10;
const ZOOM_STEP = 0.15;
const AT_BOTTOM_THRESHOLD_PX = 50;

// ---------------------------------------------------------------------------
// TraceTimeline
// ---------------------------------------------------------------------------

export function TraceTimeline({
  spans,
  isLive,
  totalSpans,
  onSpanSelect,
  selectedSpanId,
  isRunning = false,
}: TraceTimelineProps) {
  // --- Legend filter state ---
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());

  // --- Expanded groups state ---
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  // --- Zoom state ---
  const [zoom, setZoom] = useState(1);

  // --- Refs for synchronized scrolling ---
  const labelScrollRef = useRef<HTMLDivElement>(null);
  const barScrollRef = useRef<HTMLDivElement>(null);
  const syncingRef = useRef(false);

  // Ref for attaching the wheel listener (non-passive)
  const barPanelRef = useRef<HTMLDivElement>(null);

  // --- Auto-scroll / new events tracking ---
  const isAtBottomRef = useRef(true);
  const prevSpanCountRef = useRef(spans.length);
  const [newCount, setNewCount] = useState(0);

  // --- Derived: totalMs ---
  const totalMs = useMemo(() => {
    if (spans.length === 0) return 1;
    let max = 1;
    for (const span of spans) {
      const end = span.startMs + span.durationMs;
      if (end > max) max = end;
    }
    return max;
  }, [spans]);

  // --- Derived: filteredSpans ---
  const filteredSpans = useMemo(
    () => spans.filter((s) => !hiddenTypes.has(s.action)),
    [spans, hiddenTypes],
  );

  // --- Group consecutive same-action spans (≥3) into collapsible rows ---
  const groupedRows = useMemo<SpanRow[]>(() => {
    const rows: SpanRow[] = [];
    let i = 0;
    while (i < filteredSpans.length) {
      const span = filteredSpans[i]!;
      let j = i + 1;
      while (
        j < filteredSpans.length &&
        filteredSpans[j]!.action === span.action
      )
        j++;
      if (j - i >= 3) {
        const groupSpans = filteredSpans.slice(i, j);
        const groupId = `${span.action}@${span.id}`;
        const totalDuration = groupSpans.reduce(
          (s, sp) => s + sp.durationMs,
          0,
        );
        rows.push({
          kind: "group",
          group: {
            id: groupId,
            action: span.action,
            spans: groupSpans,
            totalMs: totalDuration,
          },
        });
      } else {
        for (let k = i; k < j; k++)
          rows.push({ kind: "single", span: filteredSpans[k]! });
      }
      i = j;
    }
    return rows;
  }, [filteredSpans]);

  const toggleGroup = useCallback((groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }, []);

  // --- Toggle legend filter ---
  const toggleType = useCallback((type: string) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  // --- Handle span selection ---
  const handleSpanClick = useCallback(
    (span: TraceSpan) => {
      if (!onSpanSelect) return;
      if (selectedSpanId === span.id) {
        onSpanSelect(null);
      } else {
        onSpanSelect(span);
      }
    },
    [onSpanSelect, selectedSpanId],
  );

  // --- Auto-scroll to latest when live and at bottom ---
  useEffect(() => {
    if (!isLive) {
      // Reset counters for historical episodes
      prevSpanCountRef.current = spans.length;
      setNewCount(0);
      return;
    }

    const currentCount = spans.length;
    const prevCount = prevSpanCountRef.current;
    prevSpanCountRef.current = currentCount;

    if (currentCount <= prevCount) return; // no new spans

    const newlyArrived = currentCount - prevCount;

    if (isAtBottomRef.current) {
      // Auto-scroll the bar panel
      const barEl = barScrollRef.current;
      if (barEl) {
        barEl.scrollTo({ top: barEl.scrollHeight, behavior: "smooth" });
      }
      // Reset new count since we're following the stream
      setNewCount(0);
    } else {
      // User has scrolled away — increment counter
      setNewCount((prev) => prev + newlyArrived);
    }
  }, [isLive, spans.length]);

  // --- Check if at bottom helper ---
  const checkAtBottom = useCallback((el: HTMLDivElement) => {
    return (
      el.scrollHeight - el.scrollTop - el.clientHeight < AT_BOTTOM_THRESHOLD_PX
    );
  }, []);

  // --- Scroll to bottom and reset new count ---
  const scrollToBottom = useCallback(() => {
    const barEl = barScrollRef.current;
    if (barEl) {
      barEl.scrollTo({ top: barEl.scrollHeight, behavior: "smooth" });
    }
    isAtBottomRef.current = true;
    setNewCount(0);
  }, []);

  // --- Synchronized vertical scrolling ---
  const onLabelScroll = useCallback(() => {
    if (syncingRef.current) return;
    const labelEl = labelScrollRef.current;
    const barEl = barScrollRef.current;
    if (!labelEl || !barEl) return;
    syncingRef.current = true;
    barEl.scrollTop = labelEl.scrollTop;
    syncingRef.current = false;
  }, []);

  const onBarScroll = useCallback(() => {
    if (syncingRef.current) return;
    const labelEl = labelScrollRef.current;
    const barEl = barScrollRef.current;
    if (!labelEl || !barEl) return;
    syncingRef.current = true;
    labelEl.scrollTop = barEl.scrollTop;
    syncingRef.current = false;

    // Update "at bottom" tracking
    if (barEl) {
      isAtBottomRef.current = checkAtBottom(barEl);
      if (isAtBottomRef.current) {
        setNewCount(0);
      }
    }
  }, [checkAtBottom]);

  // --- Ctrl/Cmd + scroll zoom (non-passive) ---
  useEffect(() => {
    const el = barPanelRef.current;
    if (!el) return;

    function handleWheel(e: WheelEvent) {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();

      const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
      setZoom((prev) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, prev + delta)));
    }

    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", handleWheel);
    };
  }, []);

  // Determine which span should pulse (last span during live mode)
  const lastSpanId = useMemo(() => {
    if (!isLive || filteredSpans.length === 0) return null;
    const lastSpan = filteredSpans[filteredSpans.length - 1];
    if (!lastSpan) return null;
    return lastSpan.status === "running" || lastSpan.status === "completed"
      ? lastSpan.id
      : null;
  }, [isLive, filteredSpans]);

  // --- Empty state ---
  if (spans.length === 0) {
    return (
      <div className="flex h-full flex-col">
        <StatusBar isLive={isLive || isRunning} totalSpans={totalSpans} />
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
          {isLive || isRunning ? (
            <>
              <span className="relative flex size-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                <span className="relative inline-flex size-3 rounded-full bg-primary" />
              </span>
              <span>Waiting for trace events…</span>
            </>
          ) : (
            <span>No trace events</span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      {/* 1. Status bar */}
      <StatusBar isLive={isLive || isRunning} totalSpans={totalSpans} />

      {/* 2. Legend bar */}
      <div className="flex flex-wrap gap-1 bg-card px-3 py-1.5">
        {ACTION_TYPES.map((type) => {
          const color = getActionColor(type);
          const isHidden = hiddenTypes.has(type);
          return (
            <button
              key={type}
              type="button"
              onClick={() => toggleType(type)}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs transition-all",
                isHidden ? "text-muted-foreground" : "bg-muted text-foreground",
              )}
            >
              <span
                className={cn(
                  "inline-block shrink-0 rounded-full",
                  isHidden ? "bg-muted-foreground" : color.bg,
                )}
                style={{ width: 8, height: 8 }}
              />
              <span className={cn(isHidden && "line-through")}>{type}</span>
            </button>
          );
        })}
      </div>

      {/* 3. Timeline body — resizable label / bar split */}
      <div className="flex min-h-0 flex-1">
        <ResizablePanelGroup orientation="horizontal" className="h-full">
          {/* Left panel — labels */}
          <ResizablePanel defaultSize={30} minSize={18}>
            <div className="flex h-full flex-col overflow-hidden">
              {/* Header placeholder to align with time axis header height */}
              <div className="shrink-0 bg-card" style={{ height: 32 }}>
                <span className="flex h-full items-center px-3 text-xs text-muted-foreground font-medium">
                  Step · Action · Duration
                </span>
              </div>
              {/* Scrollable label list */}
              <div
                ref={labelScrollRef}
                className="flex-1 overflow-y-auto overflow-x-hidden"
                onScroll={onLabelScroll}
              >
                {groupedRows.flatMap((row) =>
                  row.kind === "group"
                    ? [
                        <TraceTimelineGroupLabel
                          key={row.group.id}
                          group={row.group}
                          isExpanded={expandedGroups.has(row.group.id)}
                          onToggle={() => toggleGroup(row.group.id)}
                        />,
                        ...(expandedGroups.has(row.group.id)
                          ? row.group.spans.map((span) => (
                              <TraceTimelineRowLabel
                                key={`${row.group.id}:${span.id}`}
                                span={span}
                                isSelected={selectedSpanId === span.id}
                                onClick={() => handleSpanClick(span)}
                              />
                            ))
                          : []),
                      ]
                    : [
                        <TraceTimelineRowLabel
                          key={row.span.id}
                          span={row.span}
                          isSelected={selectedSpanId === row.span.id}
                          onClick={() => handleSpanClick(row.span)}
                        />,
                      ],
                )}
              </div>
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Right panel — time axis + bars */}
          <ResizablePanel defaultSize={70} minSize={40}>
            <div
              ref={barPanelRef}
              className="flex h-full flex-col overflow-hidden"
            >
              {/* Sticky time axis header — must be inside the scrolling container
                  so it sticks at the top of the bar panel */}
              <div className="shrink-0 overflow-x-auto overflow-y-hidden">
                <TraceTimelineHeader totalMs={totalMs} zoom={zoom} />
              </div>

              {/* Scrollable bar list */}
              <div
                ref={barScrollRef}
                className="flex-1 overflow-auto"
                onScroll={onBarScroll}
              >
                {groupedRows.flatMap((row) =>
                  row.kind === "group"
                    ? [
                        <TraceTimelineGroupBar
                          key={row.group.id}
                          group={row.group}
                          totalMs={totalMs}
                          zoom={zoom}
                          isExpanded={expandedGroups.has(row.group.id)}
                          onToggle={() => toggleGroup(row.group.id)}
                        />,
                        ...(expandedGroups.has(row.group.id)
                          ? row.group.spans.map((span) => (
                              <TraceTimelineRowBar
                                key={`${row.group.id}:${span.id}`}
                                span={span}
                                totalMs={totalMs}
                                zoom={zoom}
                                isSelected={selectedSpanId === span.id}
                                isPulsing={span.id === lastSpanId}
                                onClick={() => handleSpanClick(span)}
                              />
                            ))
                          : []),
                      ]
                    : [
                        <TraceTimelineRowBar
                          key={row.span.id}
                          span={row.span}
                          totalMs={totalMs}
                          zoom={zoom}
                          isSelected={selectedSpanId === row.span.id}
                          isPulsing={row.span.id === lastSpanId}
                          onClick={() => handleSpanClick(row.span)}
                        />,
                      ],
                )}
              </div>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      {/* 4. "New events" floating pill badge */}
      {isLive && !isAtBottomRef.current && newCount > 0 && (
        <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
          <button
            type="button"
            onClick={scrollToBottom}
            className="pointer-events-auto bg-primary text-primary-foreground text-xs font-medium px-3 py-1.5 rounded-full shadow-lg cursor-pointer transition-colors"
          >
            {newCount} new event{newCount !== 1 ? "s" : ""} ↓
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// StatusBar
// ---------------------------------------------------------------------------

interface StatusBarProps {
  isLive: boolean;
  totalSpans: number;
}

function StatusBar({ isLive, totalSpans }: StatusBarProps) {
  return (
    <div className="flex items-center gap-2 bg-card px-3 py-2 text-xs">
      {isLive ? (
        <>
          <span className="relative flex size-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex size-2 rounded-full bg-primary" />
          </span>
          <span className="font-semibold text-primary">LIVE</span>
          <span className="text-muted-foreground">Running</span>
        </>
      ) : (
        <>
          <span className="size-2 rounded-full bg-muted-foreground" />
          <span className="text-foreground font-medium">Complete</span>
        </>
      )}
      <span className="ml-auto text-muted-foreground tabular-nums">
        {totalSpans} steps
      </span>
    </div>
  );
}

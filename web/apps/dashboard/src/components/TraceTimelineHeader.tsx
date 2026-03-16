import { formatTimestamp } from "@/lib/trace-utils";

// ---------------------------------------------------------------------------
// TraceTimelineHeader – sticky time axis with evenly spaced tick marks
// ---------------------------------------------------------------------------

interface TraceTimelineHeaderProps {
  /** Total duration of the episode in milliseconds */
  totalMs: number;
  /** Current zoom factor (1 = 100%) */
  zoom: number;
  /** Horizontal scroll offset in pixels (for tick alignment awareness) */
  offsetPx?: number;
}

/**
 * Renders a sticky header row showing elapsed time tick marks along a time axis.
 * Sits at the top of the bars (right) panel of the resizable timeline split.
 */
export function TraceTimelineHeader({
  totalMs,
  zoom,
}: TraceTimelineHeaderProps) {
  // Target 8-12 ticks across the visible span
  const tickCount = 10;

  // Ticks are evenly spaced across the full time range
  const ticks: number[] = [];
  for (let i = 0; i <= tickCount; i++) {
    ticks.push((totalMs / tickCount) * i);
  }

  return (
    <div
      className="sticky top-0 z-10 bg-card"
      style={{
        height: 32,
        width: `${zoom * 100}%`,
        minWidth: "100%",
        position: "relative",
      }}
    >
      <div className="relative h-full w-full">
        {ticks.map((ms, i) => {
          const leftPct = (ms / totalMs) * 100;
          return (
            <div
              key={i}
              className="absolute top-0 flex flex-col items-center"
              style={{ left: `${leftPct}%`, transform: "translateX(-50%)" }}
            >
              {/* Tick mark */}
              <div
                className="w-px bg-muted-foreground"
                style={{ height: 5, marginTop: 2 }}
              />
              {/* Label */}
              <span className="text-[10px] leading-none text-muted-foreground whitespace-nowrap px-0.5 mt-0.5">
                {formatTimestamp(ms)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

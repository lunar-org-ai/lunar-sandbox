import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cuaScreenshotUrl } from "@/lib/api";
import type { TraceSpan } from "@/lib/trace-utils";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// CUAFilmstrip Props
// ---------------------------------------------------------------------------

interface CUAFilmstripProps {
  episodeId: string;
  steps: TraceSpan[];
  currentStep: number;
  onSelectStep: (idx: number) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Extract screenshot filename from a span's observation dict. */
function extractScreenshotPath(span: TraceSpan): string | null {
  const path = span.observation["screenshot_path"];
  if (typeof path === "string" && path.length > 0) {
    const parts = path.split("/");
    return parts[parts.length - 1] ?? null;
  }
  return null;
}

// ---------------------------------------------------------------------------
// CUAFilmstrip — windowed filmstrip (no horizontal scroll)
// ---------------------------------------------------------------------------

const WINDOW_SIZE = 9;

export function CUAFilmstrip({
  episodeId,
  steps,
  currentStep,
  onSelectStep,
}: CUAFilmstripProps) {
  if (steps.length === 0) {
    return (
      <div className="flex items-center justify-center h-20 bg-muted text-xs text-muted-foreground shrink-0">
        No screenshots
      </div>
    );
  }

  // Compute visible window centred on currentStep
  const halfW = Math.floor(WINDOW_SIZE / 2);
  const rawStart = currentStep - halfW;
  const start = Math.max(0, Math.min(rawStart, steps.length - WINDOW_SIZE));
  const end = Math.min(steps.length, start + WINDOW_SIZE);
  const windowSteps = steps.slice(start, end);

  const canGoBack = start > 0;
  const canGoForward = end < steps.length;

  function jumpBack() {
    onSelectStep(Math.max(0, currentStep - WINDOW_SIZE));
  }
  function jumpForward() {
    onSelectStep(Math.min(steps.length - 1, currentStep + WINDOW_SIZE));
  }

  return (
    <div className="shrink-0 flex items-center gap-1.5 bg-muted px-2 py-2 h-20">
      {/* Prev page button */}
      <Button
        variant="ghost"
        size="icon"
        className="size-6 shrink-0"
        onClick={jumpBack}
        disabled={!canGoBack}
        title="Jump back"
      >
        <ChevronLeft className="size-3.5" />
      </Button>

      {/* Thumbnail window */}
      <div className="flex-1 flex items-center justify-center gap-1">
        {windowSteps.map((span, i) => {
          const idx = start + i;
          const screenshotPath = extractScreenshotPath(span);
          const isSelected = idx === currentStep;
          const src = screenshotPath
            ? cuaScreenshotUrl(episodeId, screenshotPath)
            : null;

          return (
            <button
              key={span.id}
              type="button"
              onClick={() => onSelectStep(idx)}
              className={cn(
                "relative shrink-0 aspect-video rounded-md cursor-pointer overflow-hidden transition-all",
                "hover:scale-105",
                isSelected
                  ? "ring-2 ring-primary scale-105"
                  : "ring-1 ring-transparent hover:ring-muted-foreground",
              )}
              style={{ height: "3.5rem" }}
              title={`Step ${idx + 1}: ${span.action}`}
            >
              {src ? (
                <img
                  src={src}
                  alt={`Step ${idx + 1}`}
                  loading="lazy"
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full bg-card flex items-center justify-center">
                  <span className="text-[9px] text-muted-foreground font-mono truncate px-0.5">
                    {span.action}
                  </span>
                </div>
              )}

              {/* Step number overlay */}
              <span className="absolute bottom-0.5 left-0.5 text-[8px] font-mono font-bold text-white drop-shadow-[0_1px_1px_rgba(0,0,0,0.9)] leading-none">
                {idx + 1}
              </span>
            </button>
          );
        })}
      </div>

      {/* Next page button */}
      <Button
        variant="ghost"
        size="icon"
        className="size-6 shrink-0"
        onClick={jumpForward}
        disabled={!canGoForward}
        title="Jump forward"
      >
        <ChevronRight className="size-3.5" />
      </Button>

      {/* Step counter */}
      <span className="shrink-0 text-[10px] font-mono text-muted-foreground tabular-nums whitespace-nowrap pr-1">
        {currentStep + 1}/{steps.length}
      </span>
    </div>
  );
}

interface BatchProgressBarProps {
  passed: number;
  failed: number;
  errors: number;
  inProgress: number;
  total: number;
}

interface SegmentDotProps {
  color: string;
  count: number;
  label: string;
}

function SegmentDot({ color, count, label }: SegmentDotProps) {
  if (count === 0) return null;
  return (
    <span className="flex items-center gap-1.5">
      <span className={`size-2 rounded-full ${color}`} />
      <span className="text-xs font-mono text-muted-foreground tabular-nums">
        {count} {label}
      </span>
    </span>
  );
}

export function BatchProgressBar({
  passed,
  failed,
  errors,
  inProgress,
  total,
}: BatchProgressBarProps) {
  const remaining = Math.max(0, total - passed - failed - errors - inProgress);
  const safeTotal = Math.max(total, 1);
  const completed = passed + failed + errors;

  const pct = (n: number) => `${((n / safeTotal) * 100).toFixed(2)}%`;

  return (
    <div className="w-full space-y-2">
      {/* X / N complete label */}
      <div className="text-sm font-medium">
        {completed} / {total} complete
      </div>

      {/* Segmented bar */}
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="bg-emerald-500 transition-all"
          style={{ width: pct(passed) }}
        />
        <div
          className="bg-red-500 transition-all"
          style={{ width: pct(failed) }}
        />
        <div
          className="bg-amber-500 transition-all"
          style={{ width: pct(errors) }}
        />
        <div
          className="bg-blue-500 transition-all"
          style={{ width: pct(inProgress) }}
        />
        <div
          className="bg-muted-foreground/20 transition-all"
          style={{ width: pct(remaining) }}
        />
      </div>

      {/* Segment counts */}
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        <SegmentDot color="bg-emerald-500" count={passed} label="passed" />
        <SegmentDot color="bg-red-500" count={failed} label="failed" />
        <SegmentDot color="bg-amber-500" count={errors} label="errors" />
        <SegmentDot color="bg-blue-500" count={inProgress} label="in progress" />
        <SegmentDot color="bg-muted-foreground/20" count={remaining} label="remaining" />
      </div>
    </div>
  );
}

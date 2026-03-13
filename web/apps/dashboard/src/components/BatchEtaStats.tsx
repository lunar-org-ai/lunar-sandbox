interface BatchEtaStatsProps {
  completed: number;
  total: number;
  startedAt: number; // unix seconds
  recentDurationsMs: number[];
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.round(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m ${seconds}s`;
}

interface StatTileProps {
  label: string;
  value: string;
}

function StatTile({ label, value }: StatTileProps) {
  return (
    <div className="rounded bg-zinc-800 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div
        className="text-sm font-mono text-zinc-200"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {value}
      </div>
    </div>
  );
}

export function BatchEtaStats({
  completed,
  total,
  startedAt,
  recentDurationsMs,
}: BatchEtaStatsProps) {
  const elapsedSeconds = Date.now() / 1000 - startedAt;
  const remaining = total - completed;

  const recent = recentDurationsMs.slice(-10);
  const avgMs =
    recent.length > 0
      ? recent.reduce((sum, d) => sum + d, 0) / recent.length
      : null;

  const etaMs = avgMs !== null ? avgMs * remaining : null;
  const epsPerMin = elapsedSeconds > 0 ? completed / (elapsedSeconds / 60) : null;

  const etaLabel =
    etaMs !== null && remaining > 0 ? formatDuration(etaMs) : "--";
  const elapsedLabel =
    elapsedSeconds > 0 ? formatDuration(elapsedSeconds * 1000) : "--";
  const avgLabel =
    avgMs !== null ? `${(avgMs / 1000).toFixed(1)}s` : "--";
  const rateLabel =
    epsPerMin !== null
      ? epsPerMin < 1
        ? `${(epsPerMin * 60).toFixed(1)}/hr`
        : `${epsPerMin.toFixed(1)}/min`
      : "--";

  return (
    <div className="flex flex-wrap gap-2">
      <StatTile label="ETA" value={etaLabel} />
      <StatTile label="Elapsed" value={elapsedLabel} />
      <StatTile label="Avg / Episode" value={avgLabel} />
      <StatTile label="Rate" value={rateLabel} />
    </div>
  );
}

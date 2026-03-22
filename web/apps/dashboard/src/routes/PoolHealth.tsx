import { useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useEventStream } from "@/hooks/useEventStream";
import {
  fetchPoolHealth,
  type FingerprintHealth,
  type PoolHealthDetail,
} from "@/lib/api";

function formatPercent(rate: number | null | undefined): string {
  if (rate == null) return "--";
  return `${(rate * 100).toFixed(1)}%`;
}

function hitRateColor(rate: number | null | undefined): string {
  if (rate == null) return "text-muted-foreground";
  if (rate >= 0.7) return "text-foreground";
  if (rate >= 0.5) return "text-muted-foreground";
  return "text-destructive";
}

function truncateHash(fingerprint: string): string {
  // Strip sha256: prefix if present, then truncate
  const hash = fingerprint.replace(/^sha256:/, "");
  if (hash.length <= 12) return hash;
  return `${hash.slice(0, 12)}...`;
}

interface StatsBarProps {
  data: PoolHealthDetail;
}

function StatsBar({ data }: StatsBarProps) {
  return (
    <Card className="gap-0 rounded-2xl">
      <CardContent className="flex flex-wrap gap-8 px-5 py-4">
        <div className="flex flex-col gap-0.5">
          <span className="text-xs uppercase tracking-wider text-muted-foreground font-medium">
            Total Sandboxes
          </span>
          <span className="text-xl font-mono font-bold tabular-nums">
            {data.total_sandboxes}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-xs uppercase tracking-wider text-muted-foreground font-medium">
            Overall Cache Hit
          </span>
          <span
            className={`text-xl font-mono font-bold tabular-nums ${hitRateColor(data.overall_cache_hit_rate)}`}
          >
            {formatPercent(data.overall_cache_hit_rate)}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-xs uppercase tracking-wider text-muted-foreground font-medium">
            Total Evictions
          </span>
          <span className="text-xl font-mono font-bold tabular-nums">
            {data.total_evictions}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-xs uppercase tracking-wider text-muted-foreground font-medium">
            Pool Running
          </span>
          <span className="text-sm font-semibold">
            {data.running ? "Yes" : "No"}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

interface FingerprintCardProps {
  fp: FingerprintHealth;
}

function FingerprintCard({ fp }: FingerprintCardProps) {
  return (
    <Card className="gap-0 rounded-2xl">
      <CardHeader className="pb-2">
        <CardTitle
          className="font-mono text-sm truncate"
          title={fp.fingerprint}
        >
          {truncateHash(fp.fingerprint)}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="secondary">{fp.idle_count} idle</Badge>
          <Badge variant="secondary">{fp.active_count} active</Badge>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-muted-foreground">Total</dt>
          <dd className="font-mono tabular-nums">{fp.total_count}</dd>
          <dt className="text-muted-foreground">Evictions</dt>
          <dd className="font-mono tabular-nums">{fp.eviction_count}</dd>
          <dt className="text-muted-foreground">Cache hit</dt>
          <dd
            className={`font-mono font-semibold tabular-nums ${hitRateColor(fp.cache_hit_rate)}`}
          >
            {formatPercent(fp.cache_hit_rate)}
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}

function PoolHealthSkeleton() {
  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap gap-6 px-5 py-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex flex-col gap-1.5">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-6 w-14" />
            </div>
          ))}
        </CardContent>
      </Card>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-32" />
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Skeleton className="h-5 w-14" />
                <Skeleton className="h-5 w-16" />
              </div>
              <div className="space-y-1.5">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default function PoolHealth() {
  const [data, setData] = useState<PoolHealthDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initial fetch on mount
  useEffect(() => {
    fetchPoolHealth()
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  // Subscribe to live WS pool:health updates
  const { events } = useEventStream({ topic: "pool:health" });

  useEffect(() => {
    if (events.length === 0) return;
    const last = events[events.length - 1];
    if (!last || last.type !== "pool_health") return;
    // WS payload matches PoolHealthDetail shape
    setData(last.payload as unknown as PoolHealthDetail);
  }, [events]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <Card className="gap-0 rounded-3xl bg-secondary text-secondary-foreground">
        <CardHeader className="gap-4">
          <Badge variant="default" className="w-fit">
            Pool
          </Badge>
          <div className="space-y-1">
            <CardTitle className="text-3xl tracking-tight">
              Pool Health
            </CardTitle>
            <CardDescription className="text-base text-secondary-foreground">
              Monitor sandbox pool performance and cache metrics.
            </CardDescription>
          </div>
        </CardHeader>
      </Card>

      {error ? (
        <Alert variant="destructive" className="border-0">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : loading ? (
        <PoolHealthSkeleton />
      ) : data ? (
        <>
          <StatsBar data={data} />

          {data.fingerprints.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
              <p className="text-muted-foreground text-sm">
                No fingerprint groups found.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {data.fingerprints.map((fp) => (
                <FingerprintCard key={fp.fingerprint} fp={fp} />
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

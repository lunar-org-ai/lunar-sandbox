import { useEffect, useState } from 'react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useEventStream } from '@/hooks/useEventStream'
import { fetchPoolHealth, type FingerprintHealth, type PoolHealthDetail } from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatPercent(rate: number | null | undefined): string {
  if (rate == null) return '--'
  return `${(rate * 100).toFixed(1)}%`
}

function hitRateColor(rate: number | null | undefined): string {
  if (rate == null) return 'text-zinc-400'
  if (rate >= 0.7) return 'text-green-400'
  if (rate >= 0.5) return 'text-yellow-400'
  return 'text-red-400'
}

function truncateHash(fingerprint: string): string {
  // Strip sha256: prefix if present, then truncate
  const hash = fingerprint.replace(/^sha256:/, '')
  if (hash.length <= 12) return hash
  return `${hash.slice(0, 12)}...`
}

// ---------------------------------------------------------------------------
// Overall stats bar
// ---------------------------------------------------------------------------

interface StatsBarProps {
  data: PoolHealthDetail
}

function StatsBar({ data }: StatsBarProps) {
  return (
    <div className="flex flex-wrap gap-6 rounded-lg border border-zinc-800 bg-zinc-900/50 px-5 py-3">
      <div className="flex flex-col gap-0.5">
        <span className="text-[10px] uppercase tracking-wider text-zinc-500">Total Sandboxes</span>
        <span className="text-lg font-mono font-bold text-zinc-100">{data.total_sandboxes}</span>
      </div>
      <div className="flex flex-col gap-0.5">
        <span className="text-[10px] uppercase tracking-wider text-zinc-500">Overall Cache Hit</span>
        <span className={`text-lg font-mono font-bold ${hitRateColor(data.overall_cache_hit_rate)}`}>
          {formatPercent(data.overall_cache_hit_rate)}
        </span>
      </div>
      <div className="flex flex-col gap-0.5">
        <span className="text-[10px] uppercase tracking-wider text-zinc-500">Total Evictions</span>
        <span className="text-lg font-mono font-bold text-zinc-100">{data.total_evictions}</span>
      </div>
      <div className="flex flex-col gap-0.5">
        <span className="text-[10px] uppercase tracking-wider text-zinc-500">Pool Running</span>
        <span className={`text-sm font-semibold ${data.running ? 'text-green-400' : 'text-zinc-500'}`}>
          {data.running ? 'Yes' : 'No (mock)'}
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Fingerprint card
// ---------------------------------------------------------------------------

interface FingerprintCardProps {
  fp: FingerprintHealth
}

function FingerprintCard({ fp }: FingerprintCardProps) {
  return (
    <Card className="bg-zinc-900/60 border-zinc-800">
      <CardHeader className="pb-2">
        <CardTitle className="font-mono text-sm text-zinc-300 truncate" title={fp.fingerprint}>
          {truncateHash(fp.fingerprint)}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Idle / Active badges */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="inline-flex items-center rounded-md border border-blue-500/20 bg-blue-500/10 px-2 py-0.5 text-xs font-medium text-blue-400">
            {fp.idle_count} idle
          </span>
          <span className="inline-flex items-center rounded-md border border-green-500/20 bg-green-500/10 px-2 py-0.5 text-xs font-medium text-green-400">
            {fp.active_count} active
          </span>
        </div>

        {/* Stats grid */}
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-zinc-500">Total</dt>
          <dd className="font-mono text-zinc-200">{fp.total_count}</dd>

          <dt className="text-zinc-500">Evictions</dt>
          <dd className="font-mono text-zinc-200">{fp.eviction_count}</dd>

          <dt className="text-zinc-500">Cache hit</dt>
          <dd className={`font-mono font-semibold ${hitRateColor(fp.cache_hit_rate)}`}>
            {formatPercent(fp.cache_hit_rate)}
          </dd>
        </dl>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function PoolHealthSkeleton() {
  return (
    <div className="space-y-6">
      {/* Stats bar skeleton */}
      <div className="flex flex-wrap gap-6 rounded-lg border border-zinc-800 bg-zinc-900/50 px-5 py-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex flex-col gap-1.5">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-6 w-14" />
          </div>
        ))}
      </div>
      {/* Card grid skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i} className="bg-zinc-900/60 border-zinc-800">
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
  )
}

// ---------------------------------------------------------------------------
// PoolHealth page
// ---------------------------------------------------------------------------

export default function PoolHealth() {
  const [data, setData] = useState<PoolHealthDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Initial fetch on mount
  useEffect(() => {
    fetchPoolHealth()
      .then((d) => {
        setData(d)
        setLoading(false)
      })
      .catch((e: Error) => {
        setError(e.message)
        setLoading(false)
      })
  }, [])

  // Subscribe to live WS pool:health updates
  const { events } = useEventStream({ topic: 'pool:health' })

  useEffect(() => {
    if (events.length === 0) return
    const last = events[events.length - 1]
    if (!last || last.type !== 'pool_health') return
    // WS payload matches PoolHealthDetail shape
    setData(last.payload as unknown as PoolHealthDetail)
  }, [events])

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Pool Health</h1>

      {error ? (
        <p className="text-destructive text-sm">{error}</p>
      ) : loading ? (
        <PoolHealthSkeleton />
      ) : data ? (
        <>
          <StatsBar data={data} />

          {data.fingerprints.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
              <p className="text-muted-foreground text-sm">No fingerprint groups found.</p>
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
  )
}

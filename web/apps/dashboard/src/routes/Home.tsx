import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'

import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useSandboxUpdates } from '@/hooks/useSandboxUpdates'
import {
  fetchEpisodes,
  fetchHealth,
  stopSandbox,
  type EpisodeSummary,
  type HealthResponse,
} from '@/lib/api'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Status summary cards
// ---------------------------------------------------------------------------

function EngineStatusCard() {
  const [data, setData] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchHealth()
      .then(setData)
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Engine Status</CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-destructive text-sm">{error}</p>
        ) : !data ? (
          <div className="space-y-2">
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-32" />
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Health:</span>
              <StatusBadge status={data.status} type="sandbox" />
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Engine started</dt>
              <dd>{data.engine_started ? 'Yes' : 'No'}</dd>
              <dt className="text-muted-foreground">Stores available</dt>
              <dd>{data.stores_available ? 'Yes' : 'No'}</dd>
            </dl>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function SandboxPoolCard() {
  const { sandboxes, loading, error } = useSandboxUpdates()

  const stateCounts = sandboxes.reduce<Record<string, number>>((acc, s) => {
    acc[s.state] = (acc[s.state] ?? 0) + 1
    return acc
  }, {})

  const stateEntries = Object.entries(stateCounts)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sandbox Pool</CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-destructive text-sm">{error}</p>
        ) : loading ? (
          <div className="space-y-2">
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-4 w-40" />
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-2xl font-bold">{sandboxes.length}</p>
            <p className="text-sm text-muted-foreground">
              {stateEntries.length > 0
                ? stateEntries.map(([state, count]) => `${count} ${state}`).join(', ')
                : 'No sandboxes'}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function RecentEpisodesCard() {
  const [total, setTotal] = useState<number | null>(null)
  const [latest, setLatest] = useState<EpisodeSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchEpisodes({ limit: 5 })
      .then(data => {
        setTotal(data.total)
        setLatest(data.items[0] ?? null)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Episodes</CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-destructive text-sm">{error}</p>
        ) : total === null ? (
          <div className="space-y-2">
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-4 w-32" />
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-2xl font-bold">{total}</p>
            {latest ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Latest:</span>
                <StatusBadge status={latest.outcome} type="outcome" />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No episodes yet</p>
            )}
            <Link to="/runs" className="text-xs text-primary underline-offset-4 hover:underline">
              View all runs
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Sandbox monitoring table
// ---------------------------------------------------------------------------

interface SandboxRowProps {
  sandbox: {
    sandbox_id: string
    state: string
    cpu_percent?: number | null
    memory_mb?: number | null
  }
  onStop: (id: string) => void
  stopping: boolean
}

function SandboxRow({ sandbox, onStop, stopping }: SandboxRowProps) {
  const prevStateRef = useRef(sandbox.state)
  const [highlighted, setHighlighted] = useState(false)

  useEffect(() => {
    if (prevStateRef.current !== sandbox.state) {
      prevStateRef.current = sandbox.state
      setHighlighted(true)
      const timer = setTimeout(() => setHighlighted(false), 800)
      return () => clearTimeout(timer)
    }
  }, [sandbox.state])

  return (
    <TableRow
      className={cn(
        'transition-colors duration-700',
        highlighted && 'bg-yellow-500/10',
      )}
    >
      <TableCell className="font-mono text-xs max-w-[180px] truncate">
        {sandbox.sandbox_id}
      </TableCell>
      <TableCell>
        <StatusBadge status={sandbox.state} type="sandbox" />
      </TableCell>
      <TableCell className="text-right">
        {sandbox.cpu_percent != null ? `${sandbox.cpu_percent.toFixed(1)}%` : '--'}
      </TableCell>
      <TableCell className="text-right">
        {sandbox.memory_mb != null ? `${sandbox.memory_mb.toFixed(0)} MB` : '--'}
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" asChild>
            <Link to={`/sandboxes/${sandbox.sandbox_id}`}>View</Link>
          </Button>
          {sandbox.state === 'Running' && (
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive hover:text-destructive"
              disabled={stopping}
              onClick={() => onStop(sandbox.sandbox_id)}
            >
              Stop
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  )
}

function SandboxTable() {
  const { sandboxes, loading, error } = useSandboxUpdates()
  const [stoppingIds, setStoppingIds] = useState<Set<string>>(new Set())

  async function handleStop(sandboxId: string) {
    setStoppingIds(prev => new Set(prev).add(sandboxId))
    try {
      await stopSandbox(sandboxId)
    } finally {
      setStoppingIds(prev => {
        const next = new Set(prev)
        next.delete(sandboxId)
        return next
      })
    }
  }

  if (error) {
    return (
      <p className="text-destructive text-sm p-4">{error}</p>
    )
  }

  if (!loading && sandboxes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-4">
        <p className="text-muted-foreground text-sm">
          No sandboxes running. Launch an experiment to get started.
        </p>
        <Button asChild variant="outline" size="sm">
          <Link to="/launcher">Go to Launcher</Link>
        </Button>
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Sandbox ID</TableHead>
          <TableHead>State</TableHead>
          <TableHead className="text-right">CPU %</TableHead>
          <TableHead className="text-right">Memory</TableHead>
          <TableHead>Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {loading
          ? Array.from({ length: 3 }).map((_, i) => (
              <TableRow key={i}>
                <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                <TableCell><Skeleton className="h-5 w-16" /></TableCell>
                <TableCell><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
                <TableCell><Skeleton className="h-4 w-16 ml-auto" /></TableCell>
                <TableCell><Skeleton className="h-6 w-20" /></TableCell>
              </TableRow>
            ))
          : sandboxes.map(sandbox => (
              <SandboxRow
                key={sandbox.sandbox_id}
                sandbox={sandbox}
                onStop={handleStop}
                stopping={stoppingIds.has(sandbox.sandbox_id)}
              />
            ))}
      </TableBody>
    </Table>
  )
}

// ---------------------------------------------------------------------------
// Home page
// ---------------------------------------------------------------------------

export default function Home() {
  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>

      {/* Status summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <EngineStatusCard />
        <SandboxPoolCard />
        <RecentEpisodesCard />
      </div>

      {/* Sandbox monitoring table */}
      <div className="space-y-2">
        <h2 className="text-lg font-semibold">Sandbox Monitor</h2>
        <SandboxTable />
      </div>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router'
import { formatDistanceToNow } from 'date-fns'
import { ArrowLeft } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { useEventStream } from '@/hooks/useEventStream'
import { fetchSandbox, stopSandbox, type SandboxInfo } from '@/lib/api'

// ---------------------------------------------------------------------------
// SandboxDetail page
// ---------------------------------------------------------------------------

export default function SandboxDetail() {
  const { id } = useParams<{ id: string }>()
  const sandboxId = id ?? ''

  const [sandbox, setSandbox] = useState<SandboxInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [stopping, setStopping] = useState(false)
  const [stopError, setStopError] = useState<string | null>(null)

  // Initial REST fetch
  useEffect(() => {
    if (!sandboxId) return
    setLoading(true)
    fetchSandbox(sandboxId)
      .then((data) => {
        setSandbox(data)
        setLoading(false)
      })
      .catch((e: Error) => {
        setFetchError(e.message)
        setLoading(false)
      })
  }, [sandboxId])

  // Live WS updates -- subscribe to sandbox topic
  const { events } = useEventStream({ topic: 'sandbox' })

  useEffect(() => {
    const latest = events[events.length - 1]
    if (!latest || latest.type !== 'sandbox_status') return

    const payload = latest.payload as {
      sandbox_id?: string
      state?: string
      cpu_percent?: number
      memory_mb?: number
    }
    if (payload.sandbox_id !== sandboxId) return

    setSandbox((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        state: (payload.state as string) ?? prev.state,
        cpu_percent: payload.cpu_percent ?? prev.cpu_percent,
        memory_mb: payload.memory_mb ?? prev.memory_mb,
      }
    })
  }, [events, sandboxId])

  async function handleStop() {
    setStopError(null)
    setStopping(true)
    try {
      await stopSandbox(sandboxId)
      setSandbox((prev) => (prev ? { ...prev, state: 'Finished' } : prev))
    } catch (e) {
      setStopError(e instanceof Error ? e.message : 'Failed to stop sandbox.')
    } finally {
      setStopping(false)
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-8 space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (fetchError) {
    return (
      <div className="max-w-3xl mx-auto p-8">
        <p className="text-red-400 text-sm">Error loading sandbox: {fetchError}</p>
        <Link to="/" className="mt-4 inline-flex items-center gap-1 text-sm text-neutral-400 hover:text-neutral-200">
          <ArrowLeft className="size-4" />
          Back to Home
        </Link>
      </div>
    )
  }

  if (!sandbox) {
    return (
      <div className="max-w-3xl mx-auto p-8">
        <p className="text-neutral-400 text-sm">Sandbox not found.</p>
        <Link to="/" className="mt-4 inline-flex items-center gap-1 text-sm text-neutral-400 hover:text-neutral-200">
          <ArrowLeft className="size-4" />
          Back to Home
        </Link>
      </div>
    )
  }

  const startedAtFormatted = sandbox.started_at
    ? formatDistanceToNow(new Date(sandbox.started_at * 1000), { addSuffix: true })
    : '--'

  return (
    <div className="max-w-3xl mx-auto p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">
            Sandbox{' '}
            <span className="font-mono text-lg text-neutral-300">{sandboxId}</span>
          </h1>
          <StatusBadge status={sandbox.state} type="sandbox" />
        </div>
        <Link
          to="/"
          className="inline-flex items-center gap-1 text-sm text-neutral-400 hover:text-neutral-200"
        >
          <ArrowLeft className="size-4" />
          Home
        </Link>
      </div>

      {/* Detail card */}
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-8 gap-y-4 text-sm">
            <div>
              <dt className="text-neutral-400 mb-1">Sandbox ID</dt>
              <dd className="font-mono text-xs break-all">{sandbox.sandbox_id}</dd>
            </div>
            <div>
              <dt className="text-neutral-400 mb-1">Fingerprint</dt>
              <dd className="font-mono text-xs truncate" title={sandbox.fingerprint}>
                {sandbox.fingerprint || '--'}
              </dd>
            </div>
            <div>
              <dt className="text-neutral-400 mb-1">State</dt>
              <dd>
                <StatusBadge status={sandbox.state} type="sandbox" />
              </dd>
            </div>
            <div>
              <dt className="text-neutral-400 mb-1">Started At</dt>
              <dd>{startedAtFormatted}</dd>
            </div>
            <div>
              <dt className="text-neutral-400 mb-1">CPU %</dt>
              <dd>
                {sandbox.cpu_percent != null
                  ? `${sandbox.cpu_percent.toFixed(1)}%`
                  : '--'}
              </dd>
            </div>
            <div>
              <dt className="text-neutral-400 mb-1">Memory MB</dt>
              <dd>
                {sandbox.memory_mb != null
                  ? `${sandbox.memory_mb.toFixed(0)} MB`
                  : '--'}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Actions */}
      {sandbox.state === 'Running' && (
        <div className="space-y-2">
          <Button
            variant="destructive"
            onClick={handleStop}
            disabled={stopping}
          >
            {stopping ? 'Stopping...' : 'Stop Sandbox'}
          </Button>
          {stopError && (
            <p className="text-sm text-red-400">{stopError}</p>
          )}
        </div>
      )}
    </div>
  )
}

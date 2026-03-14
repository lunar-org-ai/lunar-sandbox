import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router'
import { formatDistanceToNow } from 'date-fns'
import { ArrowLeft, Terminal as TerminalIcon } from 'lucide-react'
import type { PanelImperativeHandle } from 'react-resizable-panels'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable'
import { SandboxTerminal } from '@/components/SandboxTerminal'
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

  // Terminal drawer state
  const [terminalOpen, setTerminalOpen] = useState(false)
  // Once opened, keep mounted so the session persists when collapsed
  const terminalMountedRef = useRef(false)
  const terminalPanelRef = useRef<PanelImperativeHandle | null>(null)

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

  function handleToggleTerminal() {
    const opening = !terminalOpen
    setTerminalOpen(opening)
    if (opening) {
      terminalMountedRef.current = true
      // Expand the panel when opening
      setTimeout(() => {
        terminalPanelRef.current?.expand()
      }, 0)
    } else {
      // Collapse but keep mounted so session persists
      terminalPanelRef.current?.collapse()
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
        <p className="text-destructive text-sm">Error loading sandbox: {fetchError}</p>
        <Link to="/" className="mt-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="size-4" />
          Back to Home
        </Link>
      </div>
    )
  }

  if (!sandbox) {
    return (
      <div className="max-w-3xl mx-auto p-8">
        <p className="text-muted-foreground text-sm">Sandbox not found.</p>
        <Link to="/" className="mt-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="size-4" />
          Back to Home
        </Link>
      </div>
    )
  }

  const startedAtFormatted = sandbox.started_at
    ? formatDistanceToNow(new Date(sandbox.started_at * 1000), { addSuffix: true })
    : '--'

  const mainContent = (
    <div className="max-w-3xl mx-auto p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">
            Sandbox{' '}
            <span className="font-mono text-lg text-muted-foreground">{sandboxId}</span>
          </h1>
          <StatusBadge status={sandbox.state} type="sandbox" />
        </div>
        <Link
          to="/"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="size-4" />
          Home
        </Link>
      </div>

      {/* Detail card */}
      <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="text-base font-medium">Details</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-8 gap-y-4 text-sm">
            <div>
              <dt className="text-muted-foreground mb-1">Sandbox ID</dt>
              <dd className="font-mono text-xs break-all">{sandbox.sandbox_id}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground mb-1">Fingerprint</dt>
              <dd className="font-mono text-xs truncate" title={sandbox.fingerprint}>
                {sandbox.fingerprint || '--'}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground mb-1">State</dt>
              <dd>
                <StatusBadge status={sandbox.state} type="sandbox" />
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground mb-1">Started At</dt>
              <dd>{startedAtFormatted}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground mb-1">CPU %</dt>
              <dd className="tabular-nums">
                {sandbox.cpu_percent != null
                  ? `${sandbox.cpu_percent.toFixed(1)}%`
                  : '--'}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground mb-1">Memory MB</dt>
              <dd className="tabular-nums">
                {sandbox.memory_mb != null
                  ? `${sandbox.memory_mb.toFixed(0)} MB`
                  : '--'}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex items-center gap-3">
        {sandbox.state === 'Running' && (
          <Button
            variant="destructive"
            onClick={handleStop}
            disabled={stopping}
          >
            {stopping ? 'Stopping...' : 'Stop Sandbox'}
          </Button>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={handleToggleTerminal}
          className="flex items-center gap-1.5"
        >
          <TerminalIcon className="size-4" />
          {terminalOpen ? 'Hide Terminal' : 'Terminal'}
        </Button>
      </div>

      {stopError && (
        <p className="text-sm text-destructive">{stopError}</p>
      )}
    </div>
  )

  // Terminal drawer panel (always mounted once opened, hidden when collapsed)
  const terminalPanel = terminalMountedRef.current ? (
    <div className={terminalOpen ? 'flex flex-col h-full' : 'hidden'}>
      {/* Drawer header bar */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-border/50 bg-muted/50 shrink-0">
        <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
          <TerminalIcon className="size-3.5" />
          <span>Terminal — {sandboxId}</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
          onClick={handleToggleTerminal}
          aria-label="Close terminal"
        >
          x
        </Button>
      </div>
      {/* xterm.js terminal */}
      <div className="flex-1 min-h-0 bg-[#09090b]">
        <SandboxTerminal sandboxId={sandboxId} sandboxStatus={sandbox.state} />
      </div>
    </div>
  ) : null

  return (
    <ResizablePanelGroup orientation="vertical" className="h-screen">
      {/* Top panel: sandbox detail content */}
      <ResizablePanel defaultSize={terminalOpen ? 55 : 100} minSize={30} className="overflow-y-auto">
        {mainContent}
      </ResizablePanel>

      {/* Handle only visible when terminal is open */}
      {terminalOpen && <ResizableHandle withHandle />}

      {/* Bottom panel: terminal drawer */}
      {terminalMountedRef.current && (
        <ResizablePanel
          panelRef={terminalPanelRef}
          defaultSize={terminalOpen ? 45 : 0}
          minSize={0}
          collapsible
          collapsedSize={0}
          className="min-h-0"
        >
          {terminalPanel}
        </ResizablePanel>
      )}
    </ResizablePanelGroup>
  )
}

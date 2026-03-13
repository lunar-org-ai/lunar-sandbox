import {
  FileText,
  FilePen,
  FolderOpen,
  HelpCircle,
  ScrollText,
  Search,
  Send,
  Terminal,
  TestTubes,
  X,
} from 'lucide-react'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DiffViewer, type FileDiffEntry } from '@/components/DiffViewer'
import { formatDurationMs, type TraceSpan } from '@/lib/trace-utils'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TraceDetailPanelProps {
  span: TraceSpan
  /** Unix seconds, for computing absolute times */
  episodeStartTs: number
  /** Parent span's duration for percentage calc (episode total duration used) */
  parentDurationMs?: number
  onClose: () => void
}

// ---------------------------------------------------------------------------
// Constants / helpers
// ---------------------------------------------------------------------------

const ACTION_ICONS: Record<string, React.ElementType> = {
  execute_command: Terminal,
  read_file: FileText,
  write_file: FilePen,
  submit: Send,
  list_files: FolderOpen,
  search_code: Search,
  run_tests: TestTubes,
  get_logs: ScrollText,
}

function getActionIcon(action: string): React.ElementType {
  return ACTION_ICONS[action] ?? HelpCircle
}

/**
 * Maps a TraceSpan status to a StatusBadge-compatible string.
 * We render our own small badge here rather than re-using StatusBadge
 * to avoid coupling with the sandbox/outcome type system.
 */
function statusLabel(status: TraceSpan['status']): { label: string; className: string } {
  switch (status) {
    case 'success':
    case 'completed':
      return {
        label: 'success',
        className: 'bg-green-500/10 text-green-400 border border-green-500/20',
      }
    case 'error':
      return {
        label: 'error',
        className: 'bg-red-500/10 text-red-400 border border-red-500/20',
      }
    case 'timeout':
      return {
        label: 'timeout',
        className: 'bg-orange-500/10 text-orange-400 border border-orange-500/20',
      }
    case 'running':
      return {
        label: 'running',
        className: 'bg-blue-500/10 text-blue-400 border border-blue-500/20',
      }
    default:
      return {
        label: status,
        className: 'bg-zinc-500/10 text-zinc-400 border border-zinc-500/20',
      }
  }
}

function formatAbsoluteTime(episodeStartTs: number, relativeMs: number): string {
  const absoluteMs = episodeStartTs * 1000 + relativeMs
  const d = new Date(absoluteMs)
  // Format as HH:mm:ss.mmm
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  const ms = String(d.getMilliseconds()).padStart(3, '0')
  return `${hh}:${mm}:${ss}.${ms}`
}

/** Render a single value as readable text or JSON block */
function ValueView({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-zinc-500 italic">null</span>
  }
  if (typeof value === 'string') {
    return <span className="text-zinc-200 break-words">{value}</span>
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return <span className="text-blue-300">{String(value)}</span>
  }
  // Object or array — render as formatted JSON
  return (
    <pre className="text-xs font-mono bg-zinc-900 text-zinc-300 p-2 rounded overflow-auto max-h-40 border border-zinc-800">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

/** Render an object as a key-value list */
function KVList({ data }: { data: Record<string, unknown> }) {
  const keys = Object.keys(data)
  if (keys.length === 0) {
    return <span className="text-xs text-zinc-500 italic">empty</span>
  }
  return (
    <div className="space-y-2">
      {keys.map((key) => (
        <div key={key}>
          <span className="text-xs font-mono text-zinc-400 uppercase tracking-wide">{key}</span>
          <div className="mt-0.5 pl-2">
            <ValueView value={data[key]} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// extractFileDiffs — pull file_diff entries from span data
// ---------------------------------------------------------------------------

function extractFileDiffs(span: TraceSpan): FileDiffEntry[] {
  const raw = (span.observation['file_diff'] ?? span.params['file_diff']) as
    | { created?: string[]; modified?: string[]; deleted?: string[] }
    | undefined

  if (!raw) return []

  const files: FileDiffEntry[] = []
  if (raw.created) {
    for (const path of raw.created) {
      files.push({ path, type: 'A' })
    }
  }
  if (raw.modified) {
    for (const path of raw.modified) {
      files.push({ path, type: 'M' })
    }
  }
  if (raw.deleted) {
    for (const path of raw.deleted) {
      files.push({ path, type: 'D' })
    }
  }
  return files
}

// ---------------------------------------------------------------------------
// TraceDetailPanel
// ---------------------------------------------------------------------------

export function TraceDetailPanel({
  span,
  episodeStartTs,
  parentDurationMs,
  onClose,
}: TraceDetailPanelProps) {
  const isError = span.status === 'error' || span.status === 'timeout'

  const ActionIcon = getActionIcon(span.action)
  const badge = statusLabel(span.status)

  const startTime = formatAbsoluteTime(episodeStartTs, span.startMs)
  const endTime = formatAbsoluteTime(episodeStartTs, span.startMs + span.durationMs)

  const parentPct =
    parentDurationMs && parentDurationMs > 0
      ? `${((span.durationMs / parentDurationMs) * 100).toFixed(1)}%`
      : '--'

  const stdout =
    typeof span.observation['stdout'] === 'string' ? span.observation['stdout'] : null
  const stderr =
    typeof span.observation['stderr'] === 'string' ? span.observation['stderr'] : null
  const hasTerminalOutput = stdout !== null || stderr !== null

  const fileDiffs = extractFileDiffs(span)
  const diffCount = fileDiffs.length

  return (
    <div className="flex h-full flex-col overflow-hidden bg-zinc-900 border-l border-zinc-800">
      {/* ------------------------------------------------------------------ */}
      {/* Section 1: Summary header                                           */}
      {/* ------------------------------------------------------------------ */}
      <div
        className={cn(
          'shrink-0 border-b border-zinc-800 p-4',
          isError && 'bg-red-950/30 border-red-900/50',
        )}
      >
        {/* Top row: icon + action name + close button */}
        <div className="flex items-center gap-2">
          <ActionIcon
            className={cn('size-4 shrink-0', isError ? 'text-red-400' : 'text-zinc-400')}
          />
          <span className="font-semibold text-sm text-zinc-100 truncate flex-1">{span.action}</span>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto shrink-0 rounded p-0.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700 transition-colors"
            aria-label="Close detail panel"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Second row: duration badge + status badge + step index */}
        <div className="mt-2 flex items-center gap-2 flex-wrap">
          <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-mono bg-zinc-800 text-zinc-300 border border-zinc-700">
            {formatDurationMs(span.durationMs)}
          </span>
          <span
            className={cn(
              'inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium',
              badge.className,
            )}
          >
            {badge.label}
          </span>
          <span className="ml-auto text-xs text-zinc-500 font-mono">
            Step {span.stepIdx + 1}
          </span>
        </div>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* -------------------------------------------------------------- */}
        {/* Section 2: Timing breakdown                                     */}
        {/* -------------------------------------------------------------- */}
        <div>
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">
            Timing
          </h3>
          <div className="grid grid-cols-2 gap-2">
            <TimingTile label="Start" value={startTime} />
            <TimingTile label="End" value={endTime} />
            <TimingTile label="Duration" value={formatDurationMs(span.durationMs)} />
            <TimingTile label="% of Total" value={parentPct} />
          </div>
        </div>

        {/* -------------------------------------------------------------- */}
        {/* Section 3: Main content tabs — I/O | Diffs | Terminal           */}
        {/* -------------------------------------------------------------- */}
        <Tabs defaultValue={isError ? 'terminal' : 'io'}>
          <TabsList className="w-full">
            <TabsTrigger value="io" className="flex-1 text-xs">
              I/O
            </TabsTrigger>
            <TabsTrigger value="diffs" className="flex-1 text-xs">
              {diffCount > 0 ? `Diffs (${diffCount})` : 'Diffs'}
            </TabsTrigger>
            <TabsTrigger value="terminal" className="flex-1 text-xs">
              Terminal
            </TabsTrigger>
          </TabsList>

          {/* I/O tab — Formatted / Raw sub-tabs */}
          <TabsContent value="io">
            <Tabs defaultValue="formatted">
              <TabsList className="w-full mt-2">
                <TabsTrigger value="formatted" className="flex-1 text-xs">
                  Formatted
                </TabsTrigger>
                <TabsTrigger value="raw" className="flex-1 text-xs">
                  Raw
                </TabsTrigger>
              </TabsList>

              <TabsContent value="formatted">
                <div className="mt-2 space-y-3 max-h-64 overflow-auto rounded border border-zinc-800 p-3 bg-zinc-950">
                  <div>
                    <p className="text-xs font-semibold text-zinc-400 mb-1">Input</p>
                    <KVList data={span.params} />
                  </div>
                  <div className="border-t border-zinc-800 pt-3">
                    <p className="text-xs font-semibold text-zinc-400 mb-1">Output</p>
                    <KVList data={span.observation} />
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="raw">
                <pre className="mt-2 text-xs font-mono bg-zinc-950 text-zinc-300 p-3 rounded border border-zinc-800 max-h-64 overflow-auto">
                  {JSON.stringify({ params: span.params, observation: span.observation }, null, 2)}
                </pre>
              </TabsContent>
            </Tabs>
          </TabsContent>

          {/* Diffs tab */}
          <TabsContent value="diffs">
            <div
              className="mt-2 rounded border border-zinc-800 overflow-hidden"
              style={{ minHeight: 200 }}
            >
              <DiffViewer files={fileDiffs} />
            </div>
          </TabsContent>

          {/* Terminal tab */}
          <TabsContent value="terminal">
            <div className="mt-2">
              {isError ? (
                <div
                  className={cn(
                    'rounded border-l-4 border-red-600 bg-zinc-950 p-3',
                    'border border-red-900/50',
                  )}
                >
                  <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-2">
                    Terminal Output
                  </h3>
                  {hasTerminalOutput ? (
                    <TerminalOutputBlocks stdout={stdout} stderr={stderr} prominent />
                  ) : (
                    <p className="text-xs text-zinc-500 italic">No terminal output</p>
                  )}
                </div>
              ) : (
                <div className="rounded border border-zinc-800 bg-zinc-950 p-3">
                  {hasTerminalOutput ? (
                    <TerminalOutputBlocks stdout={stdout} stderr={stderr} prominent={false} />
                  ) : (
                    <p className="text-xs text-zinc-500 italic">No terminal output</p>
                  )}
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Supporting sub-components
// ---------------------------------------------------------------------------

interface TimingTileProps {
  label: string
  value: string
}

function TimingTile({ label, value }: TimingTileProps) {
  return (
    <div className="rounded bg-zinc-800 px-2 py-1.5">
      <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-0.5">{label}</p>
      <p className="text-xs font-mono text-zinc-200 truncate">{value}</p>
    </div>
  )
}

interface TerminalOutputBlocksProps {
  stdout: string | null
  stderr: string | null
  prominent: boolean
}

function TerminalOutputBlocks({ stdout, stderr, prominent }: TerminalOutputBlocksProps) {
  return (
    <div className="space-y-2">
      {stdout !== null && (
        <div>
          <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">stdout</p>
          <pre
            className={cn(
              'text-xs font-mono rounded p-2 overflow-auto whitespace-pre-wrap break-words',
              prominent ? 'bg-zinc-900 text-green-400 max-h-48' : 'bg-zinc-950 text-green-400 max-h-32',
            )}
          >
            {stdout}
          </pre>
        </div>
      )}
      {stderr !== null && (
        <div>
          <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">stderr</p>
          <pre
            className={cn(
              'text-xs font-mono rounded p-2 overflow-auto whitespace-pre-wrap break-words',
              prominent ? 'bg-zinc-900 text-red-400 max-h-48' : 'bg-zinc-950 text-red-400 max-h-32',
            )}
          >
            {stderr}
          </pre>
        </div>
      )}
    </div>
  )
}

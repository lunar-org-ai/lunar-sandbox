import { useEffect, useState } from 'react'
import { DiffView, DiffModeEnum } from '@git-diff-view/react'
import { FileText } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FileDiffEntry {
  path: string
  /** 'A' = added, 'M' = modified, 'D' = deleted */
  type: 'A' | 'M' | 'D'
  /** Optional: file content before the change (for unified diff) */
  before?: string
  /** Optional: file content after the change (for unified diff) */
  after?: string
}

export interface DiffViewerProps {
  /** Array of file changes for this action step */
  files: FileDiffEntry[]
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TYPE_BADGE_CLASSES: Record<FileDiffEntry['type'], string> = {
  A: 'bg-green-500/10 text-green-400 border border-green-500/20',
  M: 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20',
  D: 'bg-red-500/10 text-red-400 border border-red-500/20',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function basename(path: string): string {
  const parts = path.split('/')
  return parts[parts.length - 1] ?? path
}

function dirname(path: string): string {
  const parts = path.split('/')
  if (parts.length <= 1) return ''
  parts.pop()
  return parts.join('/')
}

// ---------------------------------------------------------------------------
// DiffViewer
// ---------------------------------------------------------------------------

export function DiffViewer({ files }: DiffViewerProps) {
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [mode, setMode] = useState<DiffModeEnum>(DiffModeEnum.Unified)

  // Auto-select first file when files change
  useEffect(() => {
    setSelectedIdx(0)
  }, [files])

  if (files.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-zinc-500">
        No file changes
      </div>
    )
  }

  const selected = files[selectedIdx]
  const hasContent = selected !== undefined && selected.before !== undefined && selected.after !== undefined

  return (
    <div className="flex h-full min-h-0">
      {/* ------------------------------------------------------------------ */}
      {/* Left: File tree sidebar                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="w-[200px] shrink-0 border-r border-zinc-800 overflow-y-auto bg-zinc-900">
        {files.map((file, idx) => {
          const name = basename(file.path)
          const dir = dirname(file.path)
          return (
            <button
              key={file.path}
              type="button"
              onClick={() => setSelectedIdx(idx)}
              className={cn(
                'w-full text-left px-2 py-1.5 flex items-start gap-1.5 hover:bg-zinc-800/50 transition-colors',
                idx === selectedIdx && 'bg-zinc-800',
              )}
            >
              <span
                className={cn(
                  'mt-0.5 shrink-0 inline-flex items-center justify-center rounded px-1 text-[10px] font-bold font-mono leading-4',
                  TYPE_BADGE_CLASSES[file.type],
                )}
              >
                {file.type}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-mono text-zinc-200 truncate">{name}</span>
                {dir && (
                  <span className="block text-[10px] font-mono text-zinc-500 truncate">{dir}</span>
                )}
              </span>
            </button>
          )
        })}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Right: Diff content area                                            */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex-1 flex flex-col min-w-0 overflow-auto bg-zinc-950">
        {/* Toggle bar */}
        <div className="shrink-0 flex items-center gap-1 border-b border-zinc-800 px-3 py-1.5">
          <span className="text-xs text-zinc-500 mr-2 font-mono truncate flex-1">
            {selected?.path ?? ''}
          </span>
          <button
            type="button"
            onClick={() => setMode(DiffModeEnum.Unified)}
            className={cn(
              'rounded px-2 py-0.5 text-xs transition-colors',
              mode === DiffModeEnum.Unified
                ? 'bg-zinc-700 text-zinc-100'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800',
            )}
          >
            Unified
          </button>
          <button
            type="button"
            onClick={() => setMode(DiffModeEnum.SplitGitHub)}
            className={cn(
              'rounded px-2 py-0.5 text-xs transition-colors',
              mode === DiffModeEnum.SplitGitHub
                ? 'bg-zinc-700 text-zinc-100'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800',
            )}
          >
            Side-by-side
          </button>
        </div>

        {/* Diff content */}
        <div className="flex-1 overflow-auto">
          {hasContent && selected !== undefined ? (
            <DiffView
              data={{
                oldFile: { fileName: selected.path, content: selected.before ?? '' },
                newFile: { fileName: selected.path, content: selected.after ?? '' },
                hunks: [],
              }}
              diffViewMode={mode}
              diffViewTheme="dark"
              diffViewHighlight
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full min-h-[160px] gap-3 text-zinc-500">
              <FileText className="size-8 opacity-40" />
              <div className="text-center">
                <p className="text-xs font-mono">{selected?.path ?? ''}</p>
                <p className="text-xs mt-1 text-zinc-600">Diff content not available</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TraceGraphNode — Custom React Flow action node card
// ---------------------------------------------------------------------------

import {
  AlertCircle,
  CheckCircle2,
  FileText,
  FilePen,
  FolderOpen,
  HelpCircle,
  Loader2,
  ScrollText,
  Search,
  Send,
  Terminal,
  TestTubes,
} from 'lucide-react'
import { Handle, Position } from '@xyflow/react'
import type { NodeProps, Node } from '@xyflow/react'

import type { ActionNodeData } from '@/lib/graph-layout'
import { formatDurationMs, getActionColor } from '@/lib/trace-utils'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Action icon map — matches TraceDetailPanel.tsx pattern
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

// ---------------------------------------------------------------------------
// ActionNode — the custom node card rendered by React Flow
// ---------------------------------------------------------------------------

type ActionNodeType = Node<ActionNodeData, 'action'>

export function ActionNode({ data }: NodeProps<ActionNodeType>) {
  const { action, status, durationMs, isActive } = data
  const ActionIcon = getActionIcon(action)
  const color = getActionColor(action)

  // --- Determine border style + status indicator ---
  let borderClass: string
  let StatusIcon: React.ElementType | null = null
  let statusIconClass = ''

  if (isActive) {
    borderClass = cn(color.border, 'border-2')
    StatusIcon = Loader2
    statusIconClass = 'animate-spin text-current'
  } else if (status === 'error') {
    borderClass = 'border-red-500 border-2'
    StatusIcon = AlertCircle
    statusIconClass = 'text-red-400'
  } else if (status === 'timeout') {
    borderClass = 'border-orange-500 border-2'
    StatusIcon = AlertCircle
    statusIconClass = 'text-orange-400'
  } else if (status === 'success' || status === 'completed') {
    borderClass = 'border-zinc-700'
    StatusIcon = CheckCircle2
    statusIconClass = 'text-green-400'
  } else {
    // running (not active, historical) or pending
    borderClass = 'border-zinc-700'
    StatusIcon = null
    statusIconClass = ''
  }

  // Pending nodes (future use): dim entire card
  const cardOpacity = status === 'running' && !isActive ? 'opacity-70' : ''

  return (
    <>
      {/* Target handle — left side for LR layout */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-2 !h-2 !bg-zinc-600 !border-zinc-700"
      />

      {/* Node card */}
      <div
        className={cn(
          'bg-zinc-900 border rounded-lg px-3 py-2 min-w-[200px] select-none',
          borderClass,
          cardOpacity,
        )}
        style={{ width: 220 }}
      >
        {/* Top row: action icon + action label */}
        <div className="flex items-center gap-2">
          <ActionIcon className={cn('size-3.5 shrink-0', color.text)} />
          <span className="text-sm font-medium text-zinc-200 truncate flex-1">{action}</span>
          {isActive && (
            <Loader2 className={cn('size-3 shrink-0 ml-auto', color.text, 'animate-spin')} />
          )}
        </div>

        {/* Bottom row: duration + status icon */}
        <div className="flex items-center justify-between mt-1">
          <span className="text-xs font-mono text-zinc-400">
            {formatDurationMs(durationMs)}
          </span>
          {StatusIcon && !isActive && (
            <StatusIcon className={cn('size-3 shrink-0', statusIconClass)} />
          )}
        </div>
      </div>

      {/* Source handle — right side for LR layout */}
      <Handle
        type="source"
        position={Position.Right}
        className="!w-2 !h-2 !bg-zinc-600 !border-zinc-700"
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// nodeTypes — MUST be at module scope (not inside a component)
// to prevent React Flow from remounting all nodes on every render.
// ---------------------------------------------------------------------------

export const nodeTypes = { action: ActionNode }

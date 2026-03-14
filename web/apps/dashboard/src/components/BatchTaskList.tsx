import { useState } from 'react'
import { ChevronRight } from 'lucide-react'

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { StatusBadge } from '@/components/StatusBadge'
import { BatchProgressBar } from '@/components/BatchProgressBar'
import { cn } from '@/lib/utils'
import { type TaskResultSummary } from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(ms: number): string {
  if (ms <= 0) return '--'
  const totalSeconds = Math.floor(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds}s`
  return `${minutes}m ${seconds}s`
}

function formatCost(cost: number): string {
  if (cost <= 0) return '--'
  return `$${cost.toFixed(4)}`
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface BatchTaskListProps {
  taskResults: TaskResultSummary[]
  onEpisodeClick: (episodeId: string) => void
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BatchTaskList({ taskResults, onEpisodeClick }: BatchTaskListProps) {
  // Group taskResults by task_name
  const grouped = taskResults.reduce<Map<string, TaskResultSummary[]>>((acc, item) => {
    const group = acc.get(item.task_name) ?? []
    group.push(item)
    acc.set(item.task_name, group)
    return acc
  }, new Map())

  return (
    <div className="space-y-1">
      {Array.from(grouped.entries()).map(([taskName, items]) => (
        <TaskGroup
          key={taskName}
          taskName={taskName}
          items={items}
          onEpisodeClick={onEpisodeClick}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// TaskGroup (single collapsible task row)
// ---------------------------------------------------------------------------

interface TaskGroupProps {
  taskName: string
  items: TaskResultSummary[]
  onEpisodeClick: (episodeId: string) => void
}

function TaskGroup({ taskName, items, onEpisodeClick }: TaskGroupProps) {
  const [open, setOpen] = useState(false)

  const passed = items.filter((i) => i.outcome === 'pass').length
  const failed = items.filter((i) => i.outcome === 'fail').length
  const errors = items.filter((i) => i.outcome === 'error').length
  const total = items.length

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="w-full">
        <div className="flex items-center gap-2 rounded-md px-3 py-2 hover:bg-accent/50 cursor-pointer text-left transition-colors">
          <ChevronRight
            className={cn(
              'size-4 text-muted-foreground transition-transform shrink-0',
              open && 'rotate-90',
            )}
          />
          <span className="font-mono text-sm flex-1 truncate">{taskName}</span>
          {/* Mini progress bar */}
          <div className="w-24 shrink-0">
            <div className="flex h-1.5 overflow-hidden rounded-full bg-muted">
              {total > 0 && (
                <>
                  <div
                    className="bg-emerald-500"
                    style={{ width: `${(passed / total) * 100}%` }}
                  />
                  <div
                    className="bg-red-500"
                    style={{ width: `${(failed / total) * 100}%` }}
                  />
                  <div
                    className="bg-amber-500"
                    style={{ width: `${(errors / total) * 100}%` }}
                  />
                </>
              )}
            </div>
          </div>
          {/* Pass/fail counts */}
          <div className="flex items-center gap-2 shrink-0 text-xs font-mono text-muted-foreground tabular-nums">
            {passed > 0 && <span className="text-emerald-400">{passed}P</span>}
            {failed > 0 && <span className="text-red-400">{failed}F</span>}
            {errors > 0 && <span className="text-amber-400">{errors}E</span>}
            <span className="text-muted-foreground/60">{total} ep</span>
          </div>
        </div>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="ml-9 space-y-0.5 pb-1">
          {items.map((episode) => (
            <div
              key={episode.episode_id}
              onClick={() => onEpisodeClick(episode.episode_id)}
              className="flex items-center gap-3 rounded-md px-3 py-1.5 cursor-pointer hover:bg-accent/50 transition-colors"
            >
              <StatusBadge status={episode.outcome} type="outcome" />
              <span className="text-xs font-mono text-muted-foreground w-16 shrink-0 tabular-nums">
                {formatDuration(episode.wall_clock_ms)}
              </span>
              <span className="text-xs font-mono text-muted-foreground/60 w-16 shrink-0 tabular-nums">
                {formatCost(episode.estimated_cost)}
              </span>
              <span className="text-xs font-mono text-muted-foreground/60 truncate">
                {episode.episode_id.slice(0, 16)}...
              </span>
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

// Re-export BatchProgressBar so BatchDetail can use it from this module path if needed
export { BatchProgressBar }

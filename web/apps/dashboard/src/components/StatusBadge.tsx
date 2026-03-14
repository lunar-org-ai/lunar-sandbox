import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// Color classes per sandbox state
const SANDBOX_COLORS: Record<string, string> = {
  Running: 'bg-blue-500/10 text-blue-400 border-blue-500/30 hover:bg-blue-500/15',
  Idle: 'bg-muted text-muted-foreground border-border hover:bg-muted/80',
  Starting: 'bg-amber-500/10 text-amber-400 border-amber-500/30 hover:bg-amber-500/15',
  Finished: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/15',
  Error: 'bg-red-500/10 text-red-400 border-red-500/30 hover:bg-red-500/15',
}

// Color classes per episode outcome
const OUTCOME_COLORS: Record<string, string> = {
  pass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/15',
  completed: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/15',
  fail: 'bg-red-500/10 text-red-400 border-red-500/30 hover:bg-red-500/15',
  failed: 'bg-red-500/10 text-red-400 border-red-500/30 hover:bg-red-500/15',
  error: 'bg-amber-500/10 text-amber-400 border-amber-500/30 hover:bg-amber-500/15',
  timeout: 'bg-amber-500/10 text-amber-400 border-amber-500/30 hover:bg-amber-500/15',
  running: 'bg-blue-500/10 text-blue-400 border-blue-500/30 hover:bg-blue-500/15',
  pending: 'bg-muted text-muted-foreground border-border hover:bg-muted/80',
}

interface StatusBadgeProps {
  status: string
  type: 'sandbox' | 'outcome'
}

export function StatusBadge({ status, type }: StatusBadgeProps) {
  const colorMap = type === 'sandbox' ? SANDBOX_COLORS : OUTCOME_COLORS
  const colorClasses = colorMap[status] ?? 'bg-muted text-muted-foreground border-border'

  return (
    <Badge
      variant="outline"
      className={cn('text-[11px] font-medium', colorClasses)}
    >
      {status}
    </Badge>
  )
}

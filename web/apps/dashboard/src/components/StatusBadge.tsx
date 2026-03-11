import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// Color classes per sandbox state
const SANDBOX_COLORS: Record<string, string> = {
  Running: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  Idle: 'bg-neutral-500/10 text-neutral-400 border-neutral-500/20',
  Starting: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  Finished: 'bg-green-500/10 text-green-400 border-green-500/20',
  Error: 'bg-red-500/10 text-red-400 border-red-500/20',
}

// Color classes per episode outcome
const OUTCOME_COLORS: Record<string, string> = {
  pass: 'bg-green-500/10 text-green-400 border-green-500/20',
  fail: 'bg-red-500/10 text-red-400 border-red-500/20',
  error: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
}

interface StatusBadgeProps {
  status: string
  type: 'sandbox' | 'outcome'
}

export function StatusBadge({ status, type }: StatusBadgeProps) {
  const colorMap = type === 'sandbox' ? SANDBOX_COLORS : OUTCOME_COLORS
  const colorClasses = colorMap[status] ?? 'bg-neutral-500/10 text-neutral-400 border-neutral-500/20'

  return (
    <Badge
      variant="outline"
      className={cn(colorClasses)}
    >
      {status}
    </Badge>
  )
}

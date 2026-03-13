import { AlertTriangle, XCircle } from 'lucide-react'

import { Sparkline } from '@/components/Sparkline'
import type { MetricKey } from '@/hooks/useMetricsStream'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type { MetricKey }

type HealthStatus = 'healthy' | 'warning' | 'critical'

interface ThresholdConfig {
  /** true = higher value is better (e.g. cache hit rate) */
  higherIsBetter: boolean
  warning: number
  critical: number
}

// ---------------------------------------------------------------------------
// Thresholds (hardcoded per spec)
// ---------------------------------------------------------------------------

const THRESHOLDS: Record<MetricKey, ThresholdConfig> = {
  allocate_latency: { higherIsBetter: false, warning: 2000, critical: 5000 },
  reset_latency: { higherIsBetter: false, warning: 1000, critical: 3000 },
  episode_duration: { higherIsBetter: false, warning: 60000, critical: 120000 },
  cache_hit_rate: { higherIsBetter: true, warning: 0.5, critical: 0.2 },
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function computeHealth(metricKey: MetricKey, current: number): HealthStatus {
  const { higherIsBetter, warning, critical } = THRESHOLDS[metricKey]

  if (higherIsBetter) {
    // Lower value = worse health
    if (current <= critical) return 'critical'
    if (current <= warning) return 'warning'
    return 'healthy'
  } else {
    // Higher value = worse health
    if (current >= critical) return 'critical'
    if (current >= warning) return 'warning'
    return 'healthy'
  }
}

function formatValue(metricKey: MetricKey, current: number): string {
  if (metricKey === 'cache_hit_rate') {
    return `${(current * 100).toFixed(1)}`
  }
  // ms metrics
  if (current >= 1000) {
    return `${(current / 1000).toFixed(1)}s`
  }
  return `${Math.round(current)}ms`
}

function getUnitLabel(metricKey: MetricKey, unit: string): string {
  // cache_hit_rate unit is "%" -- use that; ms metrics show unit inline in value
  if (metricKey === 'cache_hit_rate') return unit
  // For ms metrics, the unit is already embedded in formatValue ("ms" or "s")
  return ''
}

const HEALTH_COLORS: Record<HealthStatus, string> = {
  healthy: '#22c55e',  // green-500
  warning: '#f59e0b',  // amber-400/500
  critical: '#ef4444', // red-500
}

const HEALTH_BORDER: Record<HealthStatus, string> = {
  healthy: 'border-zinc-700',
  warning: 'border-amber-500/60',
  critical: 'border-red-500/60',
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface MetricCardProps {
  name: string
  metricKey: MetricKey
  current: number
  values: number[]
  unit: string
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MetricCard({ name, metricKey, current, values, unit }: MetricCardProps) {
  const hasData = values.length > 0

  const health = hasData ? computeHealth(metricKey, current) : 'healthy'
  const borderClass = HEALTH_BORDER[health]
  const sparklineColor = HEALTH_COLORS[health]

  const displayValue = hasData ? formatValue(metricKey, current) : '--'
  const displayUnit = hasData ? getUnitLabel(metricKey, unit) : ''

  return (
    <div className={`rounded-lg border ${borderClass} p-4 bg-zinc-900`}>
      {/* Top row: name + health indicator */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-zinc-400 uppercase tracking-wide">{name}</span>
        <span className="flex items-center">
          {health === 'healthy' && (
            <span className="size-2 rounded-full bg-green-500" />
          )}
          {health === 'warning' && (
            <AlertTriangle className="text-amber-400 size-4" />
          )}
          {health === 'critical' && (
            <XCircle className="text-red-500 size-4" />
          )}
        </span>
      </div>

      {/* Middle: current value */}
      <div className="flex items-baseline gap-1 mb-3">
        <span className="text-2xl font-mono font-bold text-zinc-100">
          {displayValue}
        </span>
        {displayUnit && (
          <span className="text-sm text-zinc-500">{displayUnit}</span>
        )}
      </div>

      {/* Bottom: sparkline */}
      <div className="w-full">
        <Sparkline
          data={values}
          width={200}
          height={28}
          color={sparklineColor}
        />
      </div>
    </div>
  )
}

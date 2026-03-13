import { MetricCard } from '@/components/MetricCard'
import type { MetricKey, MetricsRecord } from '@/hooks/useMetricsStream'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const METRIC_CONFIGS: Array<{
  key: MetricKey
  name: string
  unit: string
}> = [
  { key: 'allocate_latency', name: 'Allocate Latency', unit: 'ms' },
  { key: 'reset_latency', name: 'Reset Latency', unit: 'ms' },
  { key: 'episode_duration', name: 'Episode Duration', unit: 'ms' },
  { key: 'cache_hit_rate', name: 'Cache Hit Rate', unit: '%' },
]

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface MetricsGridProps {
  metrics: MetricsRecord
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MetricsGrid({ metrics }: MetricsGridProps) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {METRIC_CONFIGS.map(({ key, name, unit }) => {
        const metricState = metrics[key]
        return (
          <MetricCard
            key={key}
            metricKey={key}
            name={name}
            unit={unit}
            current={metricState.current}
            values={metricState.values}
          />
        )
      })}
    </div>
  )
}

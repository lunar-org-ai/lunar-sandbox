import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CostDataPoint {
  elapsed_s: number
  cumulative_usd: number
}

export interface CostChartProps {
  data: CostDataPoint[]
  inputTokens: number
  outputTokens: number
  totalCost: number
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

function formatMinutes(seconds: number): string {
  const m = Math.floor(seconds / 60)
  return `${m}m`
}

function formatUsdAxis(value: number): string {
  return `$${value.toFixed(3)}`
}

function formatUsdTooltip(value: number): string {
  return `$${value.toFixed(4)}`
}

const USD_FORMATTER = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
})

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CostChart({ data, inputTokens, outputTokens, totalCost }: CostChartProps) {
  return (
    <div className="space-y-4">
      {/* Summary stats */}
      <div className="flex flex-wrap items-baseline gap-6">
        {/* Running cost counter */}
        <div
          className="text-3xl font-mono font-bold tabular-nums"
        >
          {USD_FORMATTER.format(totalCost)}
        </div>

        {/* Token breakdown */}
        <div className="text-sm text-muted-foreground">
          Input:{' '}
          <span className="text-foreground font-mono tabular-nums">
            {inputTokens.toLocaleString()}
          </span>{' '}
          tokens | Output:{' '}
          <span className="text-foreground font-mono tabular-nums">
            {outputTokens.toLocaleString()}
          </span>{' '}
          tokens
        </div>
      </div>

      {/* Chart or placeholder */}
      {data.length === 0 ? (
        <div className="rounded-lg border border-border/50 bg-card/50 p-6 text-center h-[240px] flex items-center justify-center">
          <p className="text-sm text-muted-foreground">
            Cost data will appear as episodes complete
          </p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data}>
            <XAxis
              dataKey="elapsed_s"
              tickFormatter={formatMinutes}
              stroke="hsl(0 0% 20%)"
              tick={{ fill: 'hsl(0 0% 55%)', fontSize: 11 }}
            />
            <YAxis
              tickFormatter={formatUsdAxis}
              stroke="hsl(0 0% 20%)"
              tick={{ fill: 'hsl(0 0% 55%)', fontSize: 11 }}
              width={55}
            />
            <Tooltip
              formatter={(value) => [formatUsdTooltip(typeof value === 'number' ? value : 0), 'Cost']}
              contentStyle={{
                background: 'hsl(0 0% 7%)',
                border: '1px solid hsl(0 0% 15%)',
                borderRadius: '0.5rem',
              }}
              labelStyle={{ color: 'hsl(0 0% 55%)' }}
            />
            <Line
              type="monotone"
              dataKey="cumulative_usd"
              stroke="hsl(0 0% 93%)"
              strokeWidth={1.5}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

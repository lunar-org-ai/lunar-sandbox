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
          className="text-3xl font-mono font-bold text-zinc-100"
          style={{ fontVariantNumeric: 'tabular-nums' }}
        >
          {USD_FORMATTER.format(totalCost)}
        </div>

        {/* Token breakdown */}
        <div className="text-sm text-zinc-400">
          Input:{' '}
          <span className="text-zinc-200 font-mono">
            {inputTokens.toLocaleString()}
          </span>{' '}
          tokens | Output:{' '}
          <span className="text-zinc-200 font-mono">
            {outputTokens.toLocaleString()}
          </span>{' '}
          tokens
        </div>
      </div>

      {/* Chart or placeholder */}
      {data.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6 text-center h-[240px] flex items-center justify-center">
          <p className="text-sm text-zinc-500">
            Cost data will appear as episodes complete
          </p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data}>
            <XAxis
              dataKey="elapsed_s"
              tickFormatter={formatMinutes}
              stroke="#52525b"
              tick={{ fill: '#a1a1aa', fontSize: 11 }}
            />
            <YAxis
              tickFormatter={formatUsdAxis}
              stroke="#52525b"
              tick={{ fill: '#a1a1aa', fontSize: 11 }}
              width={55}
            />
            <Tooltip
              formatter={(value) => [formatUsdTooltip(typeof value === 'number' ? value : 0), 'Cost']}
              contentStyle={{
                background: '#18181b',
                border: '1px solid #3f3f46',
                borderRadius: '0.375rem',
              }}
              labelStyle={{ color: '#a1a1aa' }}
            />
            <Line
              type="monotone"
              dataKey="cumulative_usd"
              stroke="#22d3ee"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

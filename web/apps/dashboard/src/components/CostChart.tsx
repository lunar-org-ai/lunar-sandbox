import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";

export interface CostDataPoint {
  elapsed_s: number;
  cumulative_usd: number;
}

export interface CostChartProps {
  data: CostDataPoint[];
  inputTokens: number;
  outputTokens: number;
  totalCost: number;
}

const chartConfig = {
  cumulative_usd: {
    label: "Cost",
    color: "var(--color-chart-1)",
  },
} satisfies ChartConfig;

const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m${s > 0 ? `${s}s` : ""}` : `${seconds}s`;
}

function formatUsdAxis(value: number): string {
  return `$${value.toFixed(3)}`;
}

export function CostChart({
  data,
  inputTokens,
  outputTokens,
  totalCost,
}: CostChartProps) {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start gap-8">
        <div className="space-y-0.5">
          <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
            Total Cost
          </p>
          <p className="text-3xl font-mono font-bold tabular-nums">
            {USD_FORMATTER.format(totalCost)}
          </p>
        </div>
        <div className="space-y-0.5">
          <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
            Input Tokens
          </p>
          <p className="text-xl font-mono font-semibold tabular-nums">
            {inputTokens.toLocaleString()}
          </p>
        </div>
        <div className="space-y-0.5">
          <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
            Output Tokens
          </p>
          <p className="text-xl font-mono font-semibold tabular-nums">
            {outputTokens.toLocaleString()}
          </p>
        </div>
      </div>

      {data.length === 0 ? (
        <div className="flex h-48 items-center justify-center rounded-lg border bg-muted/20">
          <p className="text-sm text-muted-foreground">
            Cost data will appear as the episode progresses
          </p>
        </div>
      ) : (
        <ChartContainer config={chartConfig} className="h-52 w-full">
          <AreaChart
            data={data}
            margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor="var(--color-chart-1)"
                  stopOpacity={0.25}
                />
                <stop
                  offset="95%"
                  stopColor="var(--color-chart-1)"
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>
            <CartesianGrid
              vertical={false}
              stroke="var(--color-border)"
              strokeOpacity={0.5}
            />
            <XAxis
              dataKey="elapsed_s"
              tickFormatter={formatElapsed}
              tickLine={false}
              axisLine={false}
              tickMargin={8}
            />
            <YAxis
              tickFormatter={formatUsdAxis}
              tickLine={false}
              axisLine={false}
              width={52}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  formatter={(value) => [
                    `$${(typeof value === "number" ? value : 0).toFixed(4)}`,
                    "cumulative_usd",
                  ]}
                  labelFormatter={(label) =>
                    `${formatElapsed(Number(label))} elapsed`
                  }
                />
              }
            />
            <Area
              type="monotone"
              dataKey="cumulative_usd"
              stroke="var(--color-chart-1)"
              strokeWidth={2}
              fill="url(#costGradient)"
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
            />
          </AreaChart>
        </ChartContainer>
      )}
    </div>
  );
}

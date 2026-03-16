import { AlertTriangle, XCircle } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Sparkline } from "@/components/Sparkline";
import type { MetricKey } from "@/hooks/useMetricsStream";

export type { MetricKey };

type HealthStatus = "healthy" | "warning" | "critical";

interface ThresholdConfig {
  /** true = higher value is better (e.g. cache hit rate) */
  higherIsBetter: boolean;
  warning: number;
  critical: number;
}

const THRESHOLDS: Record<MetricKey, ThresholdConfig> = {
  allocate_latency: { higherIsBetter: false, warning: 2000, critical: 5000 },
  reset_latency: { higherIsBetter: false, warning: 1000, critical: 3000 },
  episode_duration: { higherIsBetter: false, warning: 60000, critical: 120000 },
  cache_hit_rate: { higherIsBetter: true, warning: 0.5, critical: 0.2 },
};

function computeHealth(metricKey: MetricKey, current: number): HealthStatus {
  const { higherIsBetter, warning, critical } = THRESHOLDS[metricKey];

  if (higherIsBetter) {
    // Lower value = worse health
    if (current <= critical) return "critical";
    if (current <= warning) return "warning";
    return "healthy";
  } else {
    // Higher value = worse health
    if (current >= critical) return "critical";
    if (current >= warning) return "warning";
    return "healthy";
  }
}

function formatValue(metricKey: MetricKey, current: number): string {
  if (metricKey === "cache_hit_rate") {
    return `${(current * 100).toFixed(1)}`;
  }
  // ms metrics
  if (current >= 1000) {
    return `${(current / 1000).toFixed(1)}s`;
  }
  return `${Math.round(current)}ms`;
}

function getUnitLabel(metricKey: MetricKey, unit: string): string {
  // cache_hit_rate unit is "%" -- use that; ms metrics show unit inline in value
  if (metricKey === "cache_hit_rate") return unit;
  // For ms metrics, the unit is already embedded in formatValue ("ms" or "s")
  return "";
}

const HEALTH_COLORS: Record<HealthStatus, string> = {
  healthy: "var(--color-foreground)",
  warning: "var(--color-muted-foreground)",
  critical: "var(--color-destructive)",
};

export interface MetricCardProps {
  name: string;
  metricKey: MetricKey;
  current: number;
  values: number[];
  unit: string;
}

export function MetricCard({
  name,
  metricKey,
  current,
  values,
  unit,
}: MetricCardProps) {
  const hasData = values.length > 0;
  const health = hasData ? computeHealth(metricKey, current) : "healthy";
  const sparklineColor = HEALTH_COLORS[health];
  const displayValue = hasData ? formatValue(metricKey, current) : "--";
  const displayUnit = hasData ? getUnitLabel(metricKey, unit) : "";

  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
            {name}
          </span>
          <span className="flex items-center">
            {health === "healthy" && (
              <span className="size-2 rounded-full bg-foreground" />
            )}
            {health === "warning" && (
              <AlertTriangle className="text-muted-foreground size-4" />
            )}
            {health === "critical" && (
              <XCircle className="text-destructive size-4" />
            )}
          </span>
        </div>
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-mono font-bold tabular-nums">
            {displayValue}
          </span>
          {displayUnit && (
            <span className="text-sm text-muted-foreground">{displayUnit}</span>
          )}
        </div>
        <div className="w-full">
          <Sparkline
            data={values}
            width={200}
            height={28}
            color={sparklineColor}
          />
        </div>
      </CardContent>
    </Card>
  );
}

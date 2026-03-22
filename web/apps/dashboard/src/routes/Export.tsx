import { useState } from "react";
import {
  AlertCircle,
  ChevronDown,
  Download,
  FileText,
  Layers,
  Activity,
  BarChart3,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { fetchEpisodes, fetchEpisode, fetchBatches, fetchTelemetryRuns } from "@/lib/api";
import {
  downloadJson,
  downloadCsv,
  flattenEpisodeForCsv,
} from "@/lib/export-utils";

type ExportFormat = "json" | "csv";

interface FormatPickerProps {
  value: ExportFormat;
  onChange: (v: ExportFormat) => void;
  id: string;
}

function FormatPicker({ value, onChange, id }: FormatPickerProps) {
  return (
    <RadioGroup
      value={value}
      onValueChange={(v) => onChange(v as ExportFormat)}
      className="flex items-center gap-4"
    >
      <div className="flex items-center gap-1.5">
        <RadioGroupItem value="json" id={`${id}-json`} />
        <Label htmlFor={`${id}-json`} className="cursor-pointer text-sm">
          JSON
        </Label>
      </div>
      <div className="flex items-center gap-1.5">
        <RadioGroupItem value="csv" id={`${id}-csv`} />
        <Label htmlFor={`${id}-csv`} className="cursor-pointer text-sm">
          CSV
        </Label>
      </div>
    </RadioGroup>
  );
}

function EpisodesExportInner() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [taskName, setTaskName] = useState("");
  const [outcome, setOutcome] = useState("all");
  const [format, setFormat] = useState<ExportFormat>("json");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setLoading(true);
    setError(null);
    try {
      const params: Parameters<typeof fetchEpisodes>[0] = {
        limit: 1000,
      };
      if (taskName.trim()) params.task_name = taskName.trim();
      if (outcome !== "all") params.outcome = outcome;
      if (dateFrom)
        params.date_from = Math.floor(new Date(dateFrom).getTime() / 1000);
      if (dateTo)
        params.date_to = Math.floor(new Date(dateTo).getTime() / 1000);

      const result = await fetchEpisodes(params);
      if (result.items.length === 0) {
        setError("No episodes found matching the current filters.");
        return;
      }
      const filename = `episodes-${new Date().toISOString().slice(0, 10)}`;

      if (format === "json") {
        downloadJson(result.items, filename);
      } else {
        const rows = result.items.map((ep) =>
          flattenEpisodeForCsv(ep as Record<string, unknown>),
        );
        downloadCsv(rows, filename);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <FieldGroup>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field>
            <FieldLabel>Date from</FieldLabel>
            <Input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Date to</FieldLabel>
            <Input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Task name</FieldLabel>
            <Input
              type="text"
              placeholder="Filter by task name"
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Outcome</FieldLabel>
            <Select value={outcome} onValueChange={setOutcome}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
                <SelectItem value="error">Error</SelectItem>
                <SelectItem value="running">Running</SelectItem>
                <SelectItem value="timeout">Timeout</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </div>
      </FieldGroup>

      <div className="flex items-center justify-between flex-wrap gap-3">
        <FormatPicker value={format} onChange={setFormat} id="episodes" />
        <Button onClick={handleExport} disabled={loading} size="sm">
          {loading ? "Exporting..." : "Export Episodes"}
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </>
  );
}

function BatchesExportInner() {
  const [format, setFormat] = useState<ExportFormat>("json");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchBatches({ limit: 1000 });
      if (result.items.length === 0) {
        setError("No batches found. Run a batch evaluation first.");
        return;
      }
      const filename = `batches-${new Date().toISOString().slice(0, 10)}`;

      if (format === "json") {
        downloadJson(result.items, filename);
      } else {
        const rows = result.items.map((b) => b as Record<string, unknown>);
        downloadCsv(rows, filename);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <FormatPicker value={format} onChange={setFormat} id="batches" />
        <Button onClick={handleExport} disabled={loading} size="sm">
          {loading ? "Exporting..." : "Export All Batches"}
        </Button>
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </>
  );
}

function TelemetryExportInner() {
  const [format, setFormat] = useState<ExportFormat>("json");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchTelemetryRuns({ limit: 1000 });
      if (result.items.length === 0) {
        setError("No telemetry data found. Run evaluations via CLI or batch API first.");
        return;
      }
      const filename = `telemetry-${new Date().toISOString().slice(0, 10)}`;

      if (format === "json") {
        downloadJson(result.items, filename);
      } else {
        const rows = result.items.map((r) => r as Record<string, unknown>);
        downloadCsv(rows, filename);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <FormatPicker value={format} onChange={setFormat} id="telemetry" />
        <Button onClick={handleExport} disabled={loading} size="sm">
          {loading ? "Exporting..." : "Export Telemetry"}
        </Button>
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </>
  );
}

function TracesExportInner() {
  const [taskName, setTaskName] = useState("");
  const [maxEpisodes, setMaxEpisodes] = useState("20");
  const [format, setFormat] = useState<ExportFormat>("json");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setLoading(true);
    setError(null);
    setProgress("");
    try {
      const limit = Math.min(parseInt(maxEpisodes, 10) || 20, 100);
      const params: Parameters<typeof fetchEpisodes>[0] = { limit };
      if (taskName.trim()) params.task_name = taskName.trim();

      const listing = await fetchEpisodes(params);
      if (listing.items.length === 0) {
        setError("No episodes found matching the current filters.");
        return;
      }

      // Fetch full detail (with steps) for each episode
      const traces = [];
      for (let i = 0; i < listing.items.length; i++) {
        const ep = listing.items[i];
        setProgress(`Fetching ${i + 1}/${listing.items.length}...`);
        try {
          const detail = await fetchEpisode(ep.episode_id);
          traces.push(detail);
        } catch {
          // Skip episodes that fail to load
          traces.push({ ...ep, steps: [], fetch_error: true });
        }
      }

      const filename = `traces-${new Date().toISOString().slice(0, 10)}`;

      if (format === "json") {
        downloadJson(traces, filename);
      } else {
        // Flatten: one row per step with episode metadata
        const rows: Record<string, unknown>[] = [];
        for (const ep of traces) {
          const { steps, ...meta } = ep as Record<string, unknown>;
          if (Array.isArray(steps)) {
            for (const step of steps) {
              const s = step as Record<string, unknown>;
              rows.push({
                ...meta,
                step_idx: s.step_idx,
                step_action: s.action,
                step_action_params: JSON.stringify(s.action_params),
                step_observation: JSON.stringify(s.observation),
                step_duration_ms: s.duration_ms,
                step_reward: s.reward,
                step_cost_usd: s.cost_usd,
                step_token_usage: s.token_usage ? JSON.stringify(s.token_usage) : null,
                step_source: s.source,
              });
            }
          } else {
            rows.push({ ...meta, step_idx: null, step_action: null });
          }
        }
        if (rows.length === 0) {
          setError("Episodes found but no steps to export.");
          return;
        }
        downloadCsv(rows, filename);
      }

      setProgress(`Exported ${traces.length} episodes.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <FieldGroup>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field>
            <FieldLabel>Task name</FieldLabel>
            <Input
              type="text"
              placeholder="Filter by task name"
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
            />
          </Field>
          <Field>
            <FieldLabel>Max episodes</FieldLabel>
            <Input
              type="number"
              placeholder="20"
              value={maxEpisodes}
              onChange={(e) => setMaxEpisodes(e.target.value)}
              min={1}
              max={100}
            />
          </Field>
        </div>
      </FieldGroup>

      <div className="flex items-center justify-between flex-wrap gap-3">
        <FormatPicker value={format} onChange={setFormat} id="traces" />
        <div className="flex items-center gap-3">
          {progress && (
            <span className="text-xs text-muted-foreground">{progress}</span>
          )}
          <Button onClick={handleExport} disabled={loading} size="sm">
            {loading ? "Exporting..." : "Export Traces"}
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </>
  );
}

interface ExportSectionProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function ExportSection({
  icon,
  title,
  description,
  defaultOpen = false,
  children,
}: ExportSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className="gap-0 rounded-2xl">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="w-full text-left px-6 py-4 flex items-center gap-4 hover:bg-accent/50 transition-colors rounded-2xl"
          >
            <div className="size-9 rounded-xl bg-muted flex items-center justify-center shrink-0">
              {icon}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold">{title}</p>
              <p className="text-xs text-muted-foreground">{description}</p>
            </div>
            <ChevronDown
              className={`size-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
            />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="pt-0 space-y-4">{children}</CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}

export default function Export() {
  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6">
      <Card className="gap-0 rounded-3xl bg-secondary text-secondary-foreground">
        <CardHeader className="gap-4">
          <Badge variant="default" className="w-fit">
            <Download className="size-3" />
            Export
          </Badge>
          <div className="space-y-1">
            <CardTitle className="text-3xl tracking-tight">
              Export Data
            </CardTitle>
            <CardDescription className="text-base text-secondary-foreground">
              Download traces, episodes, batches, and telemetry as JSON or CSV.
            </CardDescription>
          </div>
        </CardHeader>
      </Card>

      <ExportSection
        icon={<Layers className="size-4" />}
        title="Traces"
        description="Full step-by-step execution traces with actions, observations, and timing"
        defaultOpen
      >
        <TracesExportInner />
      </ExportSection>

      <ExportSection
        icon={<FileText className="size-4" />}
        title="Episodes"
        description="Episode summaries with outcome, score, duration, and cost"
      >
        <EpisodesExportInner />
      </ExportSection>

      <ExportSection
        icon={<BarChart3 className="size-4" />}
        title="Batches"
        description="Batch evaluation runs with pass rates and task breakdowns"
      >
        <BatchesExportInner />
      </ExportSection>

      <ExportSection
        icon={<Activity className="size-4" />}
        title="Telemetry"
        description="Performance metrics, latencies, and cache hit rates"
      >
        <TelemetryExportInner />
      </ExportSection>
    </div>
  );
}

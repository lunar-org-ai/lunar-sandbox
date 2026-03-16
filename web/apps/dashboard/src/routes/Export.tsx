import { useState } from "react";
import { AlertCircle, Download } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { fetchEpisodes, fetchBatches, fetchTelemetryRuns } from "@/lib/api";
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

function EpisodesExportCard() {
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
    <Card className="gap-0 rounded-2xl">
      <CardHeader>
        <CardTitle className="text-base">Episodes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
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
                  <SelectItem value="pass">Passed</SelectItem>
                  <SelectItem value="fail">Failed</SelectItem>
                  <SelectItem value="error">Error</SelectItem>
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
      </CardContent>
    </Card>
  );
}

function BatchesExportCard() {
  const [format, setFormat] = useState<ExportFormat>("json");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchBatches({ limit: 1000 });
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
    <Card className="gap-0 rounded-2xl">
      <CardHeader>
        <CardTitle className="text-base">Batches</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
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
      </CardContent>
    </Card>
  );
}

function TelemetryExportCard() {
  const [format, setFormat] = useState<ExportFormat>("json");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchTelemetryRuns({ limit: 1000 });
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
    <Card className="gap-0 rounded-2xl">
      <CardHeader>
        <CardTitle className="text-base">Telemetry</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
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
      </CardContent>
    </Card>
  );
}

export default function Export() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
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
              Download runs, batches, and telemetry data as JSON or CSV.
            </CardDescription>
          </div>
        </CardHeader>
      </Card>

      <EpisodesExportCard />
      <BatchesExportCard />
      <TelemetryExportCard />
    </div>
  );
}

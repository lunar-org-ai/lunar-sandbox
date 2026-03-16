import {
  Clock,
  FileText,
  FilePen,
  FolderOpen,
  HelpCircle,
  ScrollText,
  Search,
  Send,
  Terminal,
  TestTubes,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DiffViewer, type FileDiffEntry } from "@/components/DiffViewer";
import {
  formatDurationMs,
  getActionColor,
  type TraceSpan,
} from "@/lib/trace-utils";
import { cn } from "@/lib/utils";

export interface TraceDetailPanelProps {
  span: TraceSpan;
  episodeStartTs: number;
  parentDurationMs?: number;
  onClose: () => void;
}

const ACTION_ICONS: Record<string, React.ElementType> = {
  execute_command: Terminal,
  read_file: FileText,
  write_file: FilePen,
  submit: Send,
  list_files: FolderOpen,
  search_code: Search,
  run_tests: TestTubes,
  get_logs: ScrollText,
};

function getActionIcon(action: string): React.ElementType {
  return ACTION_ICONS[action] ?? HelpCircle;
}

type StatusVariant = "default" | "secondary" | "destructive" | "outline";

function statusVariant(status: TraceSpan["status"]): {
  label: string;
  variant: StatusVariant;
} {
  switch (status) {
    case "success":
    case "completed":
      return { label: "success", variant: "secondary" };
    case "error":
      return { label: "error", variant: "destructive" };
    case "timeout":
      return { label: "timeout", variant: "outline" };
    case "running":
      return { label: "running", variant: "outline" };
    default:
      return { label: status, variant: "secondary" };
  }
}

function formatAbsoluteTime(
  episodeStartTs: number,
  relativeMs: number,
): string {
  const absoluteMs = episodeStartTs * 1000 + relativeMs;
  const d = new Date(absoluteMs);
  // Format as HH:mm:ss.mmm
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

/** Render a single value as readable text or JSON block */
function ValueView({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground italic">null</span>;
  }
  if (typeof value === "string") {
    return <span className="text-foreground wrap-break-word">{value}</span>;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return <span className="text-foreground font-mono">{String(value)}</span>;
  }
  return (
    <pre className="text-xs font-mono bg-card text-muted-foreground p-2 rounded-lg overflow-auto max-h-40">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

/** Render an object as a key-value list */
function KVList({ data }: { data: Record<string, unknown> }) {
  const keys = Object.keys(data);
  if (keys.length === 0) {
    return <span className="text-xs text-muted-foreground italic">empty</span>;
  }
  return (
    <div className="space-y-2">
      {keys.map((key) => (
        <div key={key}>
          <span className="text-xs font-mono text-muted-foreground uppercase tracking-wide">
            {key}
          </span>
          <div className="mt-0.5 pl-2">
            <ValueView value={data[key]} />
          </div>
        </div>
      ))}
    </div>
  );
}

function extractFileDiffs(span: TraceSpan): FileDiffEntry[] {
  const raw = (span.observation["file_diff"] ?? span.params["file_diff"]) as
    | { created?: string[]; modified?: string[]; deleted?: string[] }
    | undefined;

  if (!raw) return [];

  const files: FileDiffEntry[] = [];
  if (raw.created) {
    for (const path of raw.created) {
      files.push({ path, type: "A" });
    }
  }
  if (raw.modified) {
    for (const path of raw.modified) {
      files.push({ path, type: "M" });
    }
  }
  if (raw.deleted) {
    for (const path of raw.deleted) {
      files.push({ path, type: "D" });
    }
  }
  return files;
}

// ---------------------------------------------------------------------------
// TraceDetailPanel
// ---------------------------------------------------------------------------

export function TraceDetailPanel({
  span,
  episodeStartTs,
  parentDurationMs,
  onClose,
}: TraceDetailPanelProps) {
  const isError = span.status === "error" || span.status === "timeout";

  const ActionIcon = getActionIcon(span.action);
  const badge = statusVariant(span.status);
  const color = getActionColor(span.action);

  const startTime = formatAbsoluteTime(episodeStartTs, span.startMs);
  const endTime = formatAbsoluteTime(
    episodeStartTs,
    span.startMs + span.durationMs,
  );

  const stdout =
    typeof span.observation["stdout"] === "string"
      ? span.observation["stdout"]
      : null;
  const stderr =
    typeof span.observation["stderr"] === "string"
      ? span.observation["stderr"]
      : null;
  const hasTerminalOutput = stdout !== null || stderr !== null;

  const fileDiffs = extractFileDiffs(span);
  const diffCount = fileDiffs.length;

  // Cost & token fields from observation or params
  const cost_usd =
    (span.observation["cost_usd"] as number | undefined) ??
    (span.params["cost_usd"] as number | undefined);
  const token_count_in =
    (span.observation["token_count_in"] as number | undefined) ??
    (span.params["token_count_in"] as number | undefined);
  const token_count_out =
    (span.observation["token_count_out"] as number | undefined) ??
    (span.params["token_count_out"] as number | undefined);
  const model =
    (span.observation["model"] as string | undefined) ??
    (span.params["model"] as string | undefined);

  const hasCostTokenData =
    cost_usd !== undefined ||
    token_count_in !== undefined ||
    token_count_out !== undefined ||
    model !== undefined;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-card">
      {/* ── Header ── */}
      <div
        className={cn(
          "shrink-0 px-4 pt-4 pb-3",
          isError ? "bg-destructive/10" : "bg-muted",
        )}
      >
        {/* Top row: icon + action name + close */}
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg",
              color.bg,
            )}
          >
            <ActionIcon className="size-4 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-sm leading-tight truncate text-foreground">
              {span.action}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5 font-mono">
              Step {span.stepIdx + 1}
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 shrink-0"
            onClick={onClose}
            aria-label="Close detail panel"
          >
            <X className="size-3.5" />
          </Button>
        </div>

        {/* Chips row */}
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <Badge variant={badge.variant} className="text-xs">
            {badge.label}
          </Badge>
          <Badge variant="secondary" className="font-mono text-xs">
            <Clock className="size-3 mr-1" />
            {formatDurationMs(span.durationMs)}
          </Badge>
          {parentDurationMs && parentDurationMs > 0 && (
            <Badge variant="secondary" className="font-mono text-xs">
              {((span.durationMs / parentDurationMs) * 100).toFixed(1)}% of run
            </Badge>
          )}
        </div>
      </div>

      {/* ── Timing row ── */}
      <div className="shrink-0 grid grid-cols-2 gap-px bg-background">
        <MetricCell label="Start" value={startTime} mono />
        <MetricCell label="End" value={endTime} mono />
      </div>

      {/* ── Cost & tokens (conditional) ── */}
      {hasCostTokenData && (
        <div className="shrink-0 grid grid-cols-2 gap-px bg-background">
          {model && <MetricCell label="Model" value={model} />}
          {cost_usd !== undefined && (
            <MetricCell label="Cost" value={`$${cost_usd.toFixed(4)}`} mono />
          )}
          {token_count_in !== undefined && (
            <MetricCell
              label="In tokens"
              value={token_count_in.toLocaleString()}
              mono
            />
          )}
          {token_count_out !== undefined && (
            <MetricCell
              label="Out tokens"
              value={token_count_out.toLocaleString()}
              mono
            />
          )}
        </div>
      )}

      {/* ── Tabs: I/O / Diffs / Terminal ── */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <Tabs
          defaultValue={isError ? "terminal" : "io"}
          className="flex flex-col h-full"
        >
          <TabsList className="shrink-0 w-full rounded-none bg-muted justify-start gap-0 px-3 py-0 h-9">
            <TabsTrigger
              value="io"
              className="rounded-none h-full px-3 text-xs data-[state=active]:bg-card data-[state=active]:shadow-none"
            >
              I/O
            </TabsTrigger>
            <TabsTrigger
              value="diffs"
              className="rounded-none h-full px-3 text-xs data-[state=active]:bg-card data-[state=active]:shadow-none"
            >
              {diffCount > 0 ? `Diffs (${diffCount})` : "Diffs"}
            </TabsTrigger>
            <TabsTrigger
              value="terminal"
              className="rounded-none h-full px-3 text-xs data-[state=active]:bg-card data-[state=active]:shadow-none"
            >
              Terminal
            </TabsTrigger>
          </TabsList>

          {/* I/O tab */}
          <TabsContent
            value="io"
            className="flex-1 overflow-y-auto m-0 p-4 space-y-4"
          >
            <Section label="Input">
              {Object.keys(span.params).length === 0 ? (
                <Empty />
              ) : (
                <KVList data={span.params} />
              )}
            </Section>
            <Section label="Output">
              {Object.keys(span.observation).length === 0 ? (
                <Empty />
              ) : (
                <KVList data={span.observation} />
              )}
            </Section>
          </TabsContent>

          {/* Diffs tab */}
          <TabsContent value="diffs" className="flex-1 overflow-hidden m-0">
            {diffCount === 0 ? (
              <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
                No file changes
              </div>
            ) : (
              <div className="h-full">
                <DiffViewer files={fileDiffs} />
              </div>
            )}
          </TabsContent>

          {/* Terminal tab */}
          <TabsContent
            value="terminal"
            className="flex-1 overflow-y-auto m-0 p-4 space-y-4"
          >
            {hasTerminalOutput ? (
              <TerminalOutputBlocks
                stdout={stdout}
                stderr={stderr}
                prominent={isError}
              />
            ) : (
              <Empty label="No terminal output" />
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

interface MetricCellProps {
  label: string;
  value: string;
  mono?: boolean;
}

function MetricCell({ label, value, mono }: MetricCellProps) {
  return (
    <div className="bg-muted px-4 py-2.5">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-0.5">
        {label}
      </p>
      <p
        className={cn("text-xs text-foreground truncate", mono && "font-mono")}
      >
        {value}
      </p>
    </div>
  );
}

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">
        {label}
      </p>
      <div className="rounded-xl bg-muted p-3">{children}</div>
    </div>
  );
}

function Empty({ label = "empty" }: { label?: string }) {
  return <span className="text-xs text-muted-foreground italic">{label}</span>;
}

interface TerminalOutputBlocksProps {
  stdout: string | null;
  stderr: string | null;
  prominent: boolean;
}

function TerminalOutputBlocks({
  stdout,
  stderr,
  prominent,
}: TerminalOutputBlocksProps) {
  return (
    <div className="space-y-3">
      {stdout !== null && (
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5 font-medium">
            stdout
          </p>
          <pre
            className={cn(
              "text-xs font-mono rounded-xl p-3 overflow-auto whitespace-pre-wrap wrap-break-word bg-muted",
              prominent ? "max-h-60" : "max-h-40",
            )}
          >
            {stdout}
          </pre>
        </div>
      )}
      {stderr !== null && (
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5 font-medium">
            stderr
          </p>
          <pre
            className={cn(
              "text-xs font-mono rounded-xl p-3 overflow-auto whitespace-pre-wrap wrap-break-word bg-muted text-destructive",
              prominent ? "max-h-60" : "max-h-40",
            )}
          >
            {stderr}
          </pre>
        </div>
      )}
    </div>
  );
}

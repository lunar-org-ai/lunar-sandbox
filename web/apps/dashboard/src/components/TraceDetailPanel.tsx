import {
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
import { formatDurationMs, type TraceSpan } from "@/lib/trace-utils";
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
    <pre className="text-xs font-mono bg-muted text-muted-foreground p-2 rounded overflow-auto max-h-40 border">
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

  const startTime = formatAbsoluteTime(episodeStartTs, span.startMs);
  const endTime = formatAbsoluteTime(
    episodeStartTs,
    span.startMs + span.durationMs,
  );

  const parentPct =
    parentDurationMs && parentDurationMs > 0
      ? `${((span.durationMs / parentDurationMs) * 100).toFixed(1)}%`
      : "--";

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

  // Per-token rates: only when model and both token counts and cost are available
  const rateIn =
    cost_usd !== undefined && token_count_in !== undefined && token_count_in > 0
      ? (cost_usd / token_count_in) * 1000
      : undefined;
  const rateOut =
    cost_usd !== undefined &&
    token_count_out !== undefined &&
    token_count_out > 0
      ? (cost_usd / token_count_out) * 1000
      : undefined;
  const showRates =
    model !== undefined && rateIn !== undefined && rateOut !== undefined;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background border-l">
      <div className={cn("shrink-0 border-b p-4", isError && "bg-secondary")}>
        <div className="flex items-center gap-2">
          <ActionIcon
            className={cn(
              "size-4 shrink-0",
              isError ? "text-destructive" : "text-muted-foreground",
            )}
          />
          <span className="font-semibold text-sm truncate flex-1">
            {span.action}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-auto h-6 w-6 p-0 shrink-0"
            onClick={onClose}
            aria-label="Close detail panel"
          >
            <X className="size-4" />
          </Button>
        </div>
        <div className="mt-2 flex items-center gap-2 flex-wrap">
          <Badge variant="secondary" className="font-mono">
            {formatDurationMs(span.durationMs)}
          </Badge>
          <Badge variant={badge.variant}>{badge.label}</Badge>
          <span className="ml-auto text-xs text-muted-foreground font-mono">
            Step {span.stepIdx + 1}
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Timing
          </h3>
          <div className="grid grid-cols-2 gap-2">
            <TimingTile label="Start" value={startTime} />
            <TimingTile label="End" value={endTime} />
            <TimingTile
              label="Duration"
              value={formatDurationMs(span.durationMs)}
            />
            <TimingTile label="% of Total" value={parentPct} />
          </div>
        </div>

        {hasCostTokenData && (
          <div>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              Cost &amp; Tokens
            </h3>
            <div className="grid grid-cols-2 gap-2">
              <TimingTile label="Model" value={model ?? "--"} />
              <TimingTile
                label="Cost"
                value={
                  cost_usd !== undefined ? `$${cost_usd.toFixed(4)}` : "--"
                }
              />
              <TimingTile
                label="Input Tokens"
                value={
                  token_count_in !== undefined
                    ? token_count_in.toLocaleString()
                    : "--"
                }
              />
              <TimingTile
                label="Output Tokens"
                value={
                  token_count_out !== undefined
                    ? token_count_out.toLocaleString()
                    : "--"
                }
              />
            </div>
            {showRates && (
              <p className="text-xs text-muted-foreground mt-1.5">
                Input: ${rateIn!.toFixed(2)}/1K tokens&nbsp;|&nbsp;Output: $
                {rateOut!.toFixed(2)}/1K tokens
              </p>
            )}
          </div>
        )}

        <Tabs defaultValue={isError ? "terminal" : "io"}>
          <TabsList className="w-full">
            <TabsTrigger value="io" className="flex-1 text-xs">
              I/O
            </TabsTrigger>
            <TabsTrigger value="diffs" className="flex-1 text-xs">
              {diffCount > 0 ? `Diffs (${diffCount})` : "Diffs"}
            </TabsTrigger>
            <TabsTrigger value="terminal" className="flex-1 text-xs">
              Terminal
            </TabsTrigger>
          </TabsList>

          {/* I/O tab — Formatted / Raw sub-tabs */}
          <TabsContent value="io">
            <Tabs defaultValue="formatted">
              <TabsList className="w-full mt-2">
                <TabsTrigger value="formatted" className="flex-1 text-xs">
                  Formatted
                </TabsTrigger>
                <TabsTrigger value="raw" className="flex-1 text-xs">
                  Raw
                </TabsTrigger>
              </TabsList>

              <TabsContent value="formatted">
                <div className="mt-2 space-y-3 max-h-64 overflow-auto rounded border p-3 bg-muted">
                  <div>
                    <p className="text-xs font-semibold text-muted-foreground mb-1">
                      Input
                    </p>
                    <KVList data={span.params} />
                  </div>
                  <div className="border-t pt-3">
                    <p className="text-xs font-semibold text-muted-foreground mb-1">
                      Output
                    </p>
                    <KVList data={span.observation} />
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="raw">
                <pre className="mt-2 text-xs font-mono bg-muted text-muted-foreground p-3 rounded border max-h-64 overflow-auto">
                  {JSON.stringify(
                    { params: span.params, observation: span.observation },
                    null,
                    2,
                  )}
                </pre>
              </TabsContent>
            </Tabs>
          </TabsContent>

          <TabsContent value="diffs">
            <div
              className="mt-2 rounded border overflow-hidden"
              style={{ minHeight: 200 }}
            >
              <DiffViewer files={fileDiffs} />
            </div>
          </TabsContent>

          {/* Terminal tab */}
          <TabsContent value="terminal">
            <div className="mt-2">
              {isError ? (
                <div className="rounded border-l-4 border-destructive bg-secondary p-3 border">
                  <h3 className="text-xs font-semibold text-destructive uppercase tracking-wide mb-2">
                    Terminal Output
                  </h3>
                  {hasTerminalOutput ? (
                    <TerminalOutputBlocks
                      stdout={stdout}
                      stderr={stderr}
                      prominent
                    />
                  ) : (
                    <p className="text-xs text-muted-foreground italic">
                      No terminal output
                    </p>
                  )}
                </div>
              ) : (
                <div className="rounded border bg-muted p-3">
                  {hasTerminalOutput ? (
                    <TerminalOutputBlocks
                      stdout={stdout}
                      stderr={stderr}
                      prominent={false}
                    />
                  ) : (
                    <p className="text-xs text-muted-foreground italic">
                      No terminal output
                    </p>
                  )}
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

interface TimingTileProps {
  label: string;
  value: string;
}

function TimingTile({ label, value }: TimingTileProps) {
  return (
    <div className="rounded bg-muted px-2 py-1.5">
      <p className="text-xs uppercase tracking-wide text-muted-foreground mb-0.5">
        {label}
      </p>
      <p className="text-xs font-mono truncate">{value}</p>
    </div>
  );
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
    <div className="space-y-2">
      {stdout !== null && (
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
            stdout
          </p>
          <pre
            className={cn(
              "text-xs font-mono rounded p-2 overflow-auto whitespace-pre-wrap wrap-break-word bg-muted",
              prominent ? "max-h-48" : "max-h-32",
            )}
          >
            {stdout}
          </pre>
        </div>
      )}
      {stderr !== null && (
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
            stderr
          </p>
          <pre
            className={cn(
              "text-xs font-mono rounded p-2 overflow-auto whitespace-pre-wrap wrap-break-word bg-muted text-destructive",
              prominent ? "max-h-48" : "max-h-32",
            )}
          >
            {stderr}
          </pre>
        </div>
      )}
    </div>
  );
}

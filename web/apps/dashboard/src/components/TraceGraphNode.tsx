// ---------------------------------------------------------------------------
// TraceGraphNode — Custom React Flow action node card
// ---------------------------------------------------------------------------

import {
  AlertCircle,
  CheckCircle2,
  FileText,
  FilePen,
  FolderOpen,
  HelpCircle,
  Loader2,
  ScrollText,
  Search,
  Send,
  Terminal,
  TestTubes,
} from "lucide-react";
import { Handle, Position } from "@xyflow/react";
import type { NodeProps, Node } from "@xyflow/react";

import type { ActionNodeData } from "@/lib/graph-layout";
import { formatDurationMs, getActionColor } from "@/lib/trace-utils";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Action icon map — matches TraceDetailPanel.tsx pattern
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// ActionNode — the custom node card rendered by React Flow
// ---------------------------------------------------------------------------

type ActionNodeType = Node<ActionNodeData, "action">;

export function ActionNode({ data }: NodeProps<ActionNodeType>) {
  const { action, status, durationMs, isActive, isSelected } = data;
  const ActionIcon = getActionIcon(action);
  const color = getActionColor(action);

  let borderClass: string;
  let StatusIcon: React.ElementType | null = null;
  let statusIconClass = "";

  if (isActive) {
    borderClass = cn(color.border, "border-2");
    StatusIcon = Loader2;
    statusIconClass = "animate-spin text-current";
  } else if (status === "error") {
    borderClass = "border-destructive border-2";
    StatusIcon = AlertCircle;
    statusIconClass = "text-destructive";
  } else if (status === "timeout") {
    borderClass = "border-destructive border";
    StatusIcon = AlertCircle;
    statusIconClass = "text-muted-foreground";
  } else if (status === "success" || status === "completed") {
    borderClass = "";
    StatusIcon = CheckCircle2;
    statusIconClass = "text-primary";
  } else {
    borderClass = "";
    StatusIcon = null;
    statusIconClass = "";
  }

  // Pending nodes (future use): dim entire card
  const cardOpacity = status === "running" && !isActive ? "opacity-70" : "";

  return (
    <>
      {/* Target handle — left side for LR layout */}
      <Handle
        type="target"
        position={Position.Left}
        className="w-2! h-2! bg-muted-foreground! border-0!"
      />

      {/* Node card */}
      <div
        className={cn(
          "bg-card rounded-xl px-3 py-2 min-w-50 select-none shadow-sm",
          borderClass,
          isSelected && "ring-2 ring-primary",
          cardOpacity,
        )}
        style={{ width: 220 }}
      >
        {/* Top row: action icon + action label */}
        <div className="flex items-center gap-2">
          <ActionIcon className={cn("size-3.5 shrink-0", color.text)} />
          <span className="text-sm font-medium text-foreground truncate flex-1">
            {action}
          </span>
          {isActive && (
            <Loader2
              className={cn(
                "size-3 shrink-0 ml-auto",
                color.text,
                "animate-spin",
              )}
            />
          )}
        </div>

        {/* Bottom row: duration + status icon */}
        <div className="flex items-center justify-between mt-1">
          <span className="text-xs font-mono text-muted-foreground">
            {formatDurationMs(durationMs)}
          </span>
          {StatusIcon && !isActive && (
            <StatusIcon className={cn("size-3 shrink-0", statusIconClass)} />
          )}
        </div>
      </div>

      {/* Source handle — right side for LR layout */}
      <Handle
        type="source"
        position={Position.Right}
        className="w-2! h-2! bg-muted-foreground! border-0!"
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// nodeTypes — MUST be at module scope (not inside a component)
// to prevent React Flow from remounting all nodes on every render.
// ---------------------------------------------------------------------------

export const nodeTypes = { action: ActionNode };

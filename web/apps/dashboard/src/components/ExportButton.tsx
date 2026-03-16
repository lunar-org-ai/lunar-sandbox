import { Download, FileJson, FileSpreadsheet } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { downloadCsv, downloadJson } from "@/lib/export-utils";

// ---------------------------------------------------------------------------
// ExportButton — reusable export dropdown with JSON/CSV format picker
// ---------------------------------------------------------------------------

interface ExportButtonProps {
  /** Full data object exported as JSON */
  data: unknown;
  /** Base filename (no extension) */
  filename: string;
  /** Rows for CSV export; if omitted, CSV option is disabled */
  csvRows?: Record<string, unknown>[];
  disabled?: boolean;
}

export function ExportButton({
  data,
  filename,
  csvRows,
  disabled = false,
}: ExportButtonProps) {
  function handleJson() {
    downloadJson(data, filename);
  }

  function handleCsv() {
    if (!csvRows) return;
    downloadCsv(csvRows, filename);
  }

  const hasCsvRows = csvRows !== undefined && csvRows.length > 0;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="secondary"
          size="sm"
          disabled={disabled}
          className="flex items-center gap-1.5 h-7 text-xs"
        >
          <Download className="size-3.5" />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={handleJson}>
          <FileJson className="size-4" />
          Export as JSON
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleCsv} disabled={!hasCsvRows}>
          <FileSpreadsheet className="size-4" />
          Export as CSV
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

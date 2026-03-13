import { useState } from 'react'
import { Download } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { downloadCsv, downloadJson } from '@/lib/export-utils'

// ---------------------------------------------------------------------------
// ExportButton — reusable export dropdown with JSON/CSV format picker
// ---------------------------------------------------------------------------

interface ExportButtonProps {
  /** Full data object exported as JSON */
  data: unknown
  /** Base filename (no extension) */
  filename: string
  /** Rows for CSV export; if omitted, CSV option is disabled */
  csvRows?: Record<string, unknown>[]
  disabled?: boolean
}

export function ExportButton({
  data,
  filename,
  csvRows,
  disabled = false,
}: ExportButtonProps) {
  const [open, setOpen] = useState(false)

  function handleJson() {
    downloadJson(data, filename)
    setOpen(false)
  }

  function handleCsv() {
    if (!csvRows) return
    downloadCsv(csvRows, filename)
    setOpen(false)
  }

  const hasCsvRows = csvRows !== undefined && csvRows.length > 0

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          className="flex items-center gap-1.5"
        >
          <Download className="size-3.5" />
          Export
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-44 p-1" align="end">
        <div className="flex flex-col">
          <button
            type="button"
            onClick={handleJson}
            className="w-full rounded px-3 py-2 text-sm text-left hover:bg-zinc-800 transition-colors"
          >
            Export as JSON
          </button>
          <button
            type="button"
            onClick={handleCsv}
            disabled={!hasCsvRows}
            className={`w-full rounded px-3 py-2 text-sm text-left transition-colors ${
              hasCsvRows
                ? 'hover:bg-zinc-800'
                : 'text-zinc-500 cursor-not-allowed'
            }`}
          >
            Export as CSV
          </button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

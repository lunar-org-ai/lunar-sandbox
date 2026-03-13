import { useState } from 'react'

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  fetchEpisodes,
  fetchBatches,
  fetchTelemetryRuns,
} from '@/lib/api'
import { downloadJson, downloadCsv, flattenEpisodeForCsv } from '@/lib/export-utils'

// ---------------------------------------------------------------------------
// FormatPicker — inline radio group for JSON / CSV selection
// ---------------------------------------------------------------------------

type ExportFormat = 'json' | 'csv'

interface FormatPickerProps {
  value: ExportFormat
  onChange: (v: ExportFormat) => void
}

function FormatPicker({ value, onChange }: FormatPickerProps) {
  return (
    <div className="flex items-center gap-4">
      <label className="flex items-center gap-1.5 cursor-pointer text-sm text-zinc-300">
        <input
          type="radio"
          name="format"
          value="json"
          checked={value === 'json'}
          onChange={() => onChange('json')}
          className="accent-zinc-400"
        />
        JSON
      </label>
      <label className="flex items-center gap-1.5 cursor-pointer text-sm text-zinc-300">
        <input
          type="radio"
          name="format"
          value="csv"
          checked={value === 'csv'}
          onChange={() => onChange('csv')}
          className="accent-zinc-400"
        />
        CSV
      </label>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Episodes export card
// ---------------------------------------------------------------------------

function EpisodesExportCard() {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [taskName, setTaskName] = useState('')
  const [outcome, setOutcome] = useState('all')
  const [format, setFormat] = useState<ExportFormat>('json')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleExport() {
    setLoading(true)
    setError(null)
    try {
      const params: Parameters<typeof fetchEpisodes>[0] = {
        limit: 1000,
      }
      if (taskName.trim()) params.task_name = taskName.trim()
      if (outcome !== 'all') params.outcome = outcome
      if (dateFrom) params.date_from = Math.floor(new Date(dateFrom).getTime() / 1000)
      if (dateTo) params.date_to = Math.floor(new Date(dateTo).getTime() / 1000)

      const result = await fetchEpisodes(params)
      const filename = `episodes-${new Date().toISOString().slice(0, 10)}`

      if (format === 'json') {
        downloadJson(result.items, filename)
      } else {
        const rows = result.items.map((ep) =>
          flattenEpisodeForCsv(ep as Record<string, unknown>),
        )
        downloadCsv(rows, filename)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Episodes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs text-zinc-400 uppercase tracking-wide">Date from</label>
            <Input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="bg-zinc-900 border-zinc-700 text-zinc-200"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-zinc-400 uppercase tracking-wide">Date to</label>
            <Input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="bg-zinc-900 border-zinc-700 text-zinc-200"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-zinc-400 uppercase tracking-wide">Task name</label>
            <Input
              type="text"
              placeholder="Filter by task name"
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
              className="bg-zinc-900 border-zinc-700 text-zinc-200 placeholder:text-zinc-500"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-zinc-400 uppercase tracking-wide">Outcome</label>
            <Select value={outcome} onValueChange={setOutcome}>
              <SelectTrigger className="bg-zinc-900 border-zinc-700 text-zinc-200">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="pass">Passed</SelectItem>
                <SelectItem value="fail">Failed</SelectItem>
                <SelectItem value="error">Error</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex items-center justify-between flex-wrap gap-3">
          <FormatPicker value={format} onChange={setFormat} />
          <Button onClick={handleExport} disabled={loading} size="sm">
            {loading ? 'Exporting...' : 'Export Episodes'}
          </Button>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Batches export card
// ---------------------------------------------------------------------------

function BatchesExportCard() {
  const [format, setFormat] = useState<ExportFormat>('json')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleExport() {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchBatches({ limit: 1000 })
      const filename = `batches-${new Date().toISOString().slice(0, 10)}`

      if (format === 'json') {
        downloadJson(result.items, filename)
      } else {
        const rows = result.items.map((b) => b as Record<string, unknown>)
        downloadCsv(rows, filename)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Batches</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <FormatPicker value={format} onChange={setFormat} />
          <Button onClick={handleExport} disabled={loading} size="sm">
            {loading ? 'Exporting...' : 'Export All Batches'}
          </Button>
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Telemetry export card
// ---------------------------------------------------------------------------

function TelemetryExportCard() {
  const [format, setFormat] = useState<ExportFormat>('json')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleExport() {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchTelemetryRuns({ limit: 1000 })
      const filename = `telemetry-${new Date().toISOString().slice(0, 10)}`

      if (format === 'json') {
        downloadJson(result.items, filename)
      } else {
        const rows = result.items.map((r) => r as Record<string, unknown>)
        downloadCsv(rows, filename)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Telemetry</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <FormatPicker value={format} onChange={setFormat} />
          <Button onClick={handleExport} disabled={loading} size="sm">
            {loading ? 'Exporting...' : 'Export Telemetry'}
          </Button>
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Export page
// ---------------------------------------------------------------------------

export default function Export() {
  return (
    <div className="max-w-3xl mx-auto p-8 space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Export Data</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Download runs, batches, and telemetry data as JSON or CSV.
        </p>
      </div>

      <EpisodesExportCard />
      <BatchesExportCard />
      <TelemetryExportCard />
    </div>
  )
}

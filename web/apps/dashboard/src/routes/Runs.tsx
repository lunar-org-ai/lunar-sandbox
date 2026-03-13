import { useState, useEffect, useCallback } from 'react'
import { useNavigate, Link } from 'react-router'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table'
import { formatDistanceToNow } from 'date-fns'
import { ArrowUpDown } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { StatusBadge } from '@/components/StatusBadge'
import { fetchEpisodes, type EpisodeSummary } from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(ms: number): string {
  if (ms <= 0) return '--'
  const totalSeconds = Math.floor(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds}s`
  return `${minutes}m ${seconds}s`
}

function formatCost(usd: number | null | undefined): string {
  if (usd == null) return '--'
  return `$${usd.toFixed(2)}`
}

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

function buildColumns(navigate: ReturnType<typeof useNavigate>): ColumnDef<EpisodeSummary>[] {
  // Prevent unused var warning -- navigate is passed for row click, not per-column
  void navigate
  return [
    {
      accessorKey: 'task_name',
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8 font-medium"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
        >
          Task
          <ArrowUpDown className="ml-1 size-3 opacity-60" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="text-sm font-mono">{row.getValue('task_name')}</span>
      ),
    },
    {
      accessorKey: 'outcome',
      header: 'Outcome',
      cell: ({ row }) => (
        <StatusBadge status={row.getValue('outcome')} type="outcome" />
      ),
    },
    {
      accessorKey: 'score',
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8 font-medium"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
        >
          Score
          <ArrowUpDown className="ml-1 size-3 opacity-60" />
        </Button>
      ),
      cell: ({ row }) => {
        const score: number | null = row.getValue('score')
        return (
          <span className="text-right block">
            {score != null ? score.toFixed(2) : '--'}
          </span>
        )
      },
    },
    {
      accessorKey: 'duration_ms',
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8 font-medium"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
        >
          Duration
          <ArrowUpDown className="ml-1 size-3 opacity-60" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="text-right block">{formatDuration(row.getValue('duration_ms'))}</span>
      ),
    },
    {
      accessorKey: 'cost_usd',
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8 font-medium"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
        >
          Cost
          <ArrowUpDown className="ml-1 size-3 opacity-60" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="text-right block">{formatCost(row.getValue('cost_usd'))}</span>
      ),
    },
    {
      accessorKey: 'started_at',
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8 font-medium"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
        >
          Date
          <ArrowUpDown className="ml-1 size-3 opacity-60" />
        </Button>
      ),
      cell: ({ row }) => {
        const ts: number = row.getValue('started_at')
        if (!ts) return <span className="text-right block text-neutral-400">--</span>
        return (
          <span className="text-right block text-neutral-400 text-xs">
            {formatDistanceToNow(new Date(ts * 1000), { addSuffix: true })}
          </span>
        )
      },
    },
  ]
}

// ---------------------------------------------------------------------------
// Runs page
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50

export default function Runs() {
  const navigate = useNavigate()

  // Filter state
  const [outcomeFilters, setOutcomeFilters] = useState<Set<string>>(new Set())
  const [taskSearch, setTaskSearch] = useState('')
  const [debouncedTask, setDebouncedTask] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [scoreMin, setScoreMin] = useState('')

  // Debounce task search
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedTask(taskSearch), 300)
    return () => clearTimeout(timer)
  }, [taskSearch])

  // Data state
  const [episodes, setEpisodes] = useState<EpisodeSummary[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)

  // Table sorting state
  const [sorting, setSorting] = useState<SortingState>([{ id: 'started_at', desc: true }])

  // Fetch data when filters or pagination change
  const loadEpisodes = useCallback(async () => {
    setLoading(true)
    setFetchError(null)
    try {
      const params: Parameters<typeof fetchEpisodes>[0] = {
        offset,
        limit: PAGE_SIZE,
      }
      if (debouncedTask) params.task_name = debouncedTask
      if (outcomeFilters.size > 0) params.outcome = Array.from(outcomeFilters).join(',')
      if (dateFrom) params.date_from = Math.floor(new Date(dateFrom).getTime() / 1000)
      if (dateTo) params.date_to = Math.floor(new Date(dateTo).getTime() / 1000)
      if (scoreMin !== '') params.score_min = parseFloat(scoreMin)

      // Map TanStack sort state to API params
      if (sorting.length > 0) {
        params.sort_by = sorting[0].id
        params.sort_order = sorting[0].desc ? 'desc' : 'asc'
      }

      const data = await fetchEpisodes(params)
      setEpisodes(data.items)
      setTotal(data.total)
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : 'Failed to load runs.')
    } finally {
      setLoading(false)
    }
  }, [debouncedTask, outcomeFilters, dateFrom, dateTo, scoreMin, offset, sorting])

  useEffect(() => {
    loadEpisodes()
  }, [loadEpisodes])

  // Reset to first page when filters change (except offset itself)
  useEffect(() => {
    setOffset(0)
  }, [debouncedTask, outcomeFilters, dateFrom, dateTo, scoreMin])

  // Toggle outcome filter chip
  function toggleOutcome(outcome: string) {
    setOutcomeFilters((prev) => {
      const next = new Set(prev)
      if (next.has(outcome)) next.delete(outcome)
      else next.add(outcome)
      return next
    })
  }

  // Column definitions (stable reference via useMemo-like approach)
  const columns = buildColumns(navigate)

  const table = useReactTable({
    data: episodes,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    state: { sorting },
    onSortingChange: setSorting,
    manualSorting: true, // server-side sort
  })

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="p-6 space-y-4">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Run History</h1>
        <p className="text-sm text-neutral-400 mt-1">Browse and filter past evaluation runs.</p>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 items-center">
        {/* Outcome chips */}
        {(['pass', 'fail', 'error'] as const).map((outcome) => (
          <Button
            key={outcome}
            variant="outline"
            size="sm"
            onClick={() => toggleOutcome(outcome)}
            className={
              outcomeFilters.has(outcome)
                ? outcome === 'pass'
                  ? 'bg-green-500/10 text-green-400 border-green-500/40'
                  : outcome === 'fail'
                  ? 'bg-red-500/10 text-red-400 border-red-500/40'
                  : 'bg-orange-500/10 text-orange-400 border-orange-500/40'
                : ''
            }
          >
            {outcome}
          </Button>
        ))}

        {/* Task name search */}
        <Input
          type="text"
          placeholder="Filter by task..."
          value={taskSearch}
          onChange={(e) => setTaskSearch(e.target.value)}
          className="h-8 w-48 text-sm"
        />

        {/* Date range */}
        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          className="h-8 w-36 text-sm"
          title="From date"
        />
        <Input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          className="h-8 w-36 text-sm"
          title="To date"
        />

        {/* Score threshold */}
        <Input
          type="number"
          placeholder="Min score"
          value={scoreMin}
          onChange={(e) => setScoreMin(e.target.value)}
          step="0.1"
          min="0"
          max="1"
          className="h-8 w-28 text-sm"
        />

        {/* Clear filters */}
        {(outcomeFilters.size > 0 || taskSearch || dateFrom || dateTo || scoreMin) && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 text-neutral-400 hover:text-neutral-200"
            onClick={() => {
              setOutcomeFilters(new Set())
              setTaskSearch('')
              setDateFrom('')
              setDateTo('')
              setScoreMin('')
            }}
          >
            Clear
          </Button>
        )}
      </div>

      {/* Error */}
      {fetchError && (
        <p className="text-sm text-red-400">Error: {fetchError}</p>
      )}

      {/* Table */}
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : episodes.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <p className="text-neutral-400 text-sm">No runs found. Adjust filters or launch a new experiment.</p>
          <Link
            to="/launcher"
            className="mt-3 text-sm text-blue-400 hover:text-blue-300 underline underline-offset-4"
          >
            Go to Launcher
          </Link>
        </div>
      ) : (
        <>
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id} className="border-neutral-800 hover:bg-transparent">
                  {headerGroup.headers.map((header) => (
                    <TableHead key={header.id} className="text-neutral-400">
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.map((row) => {
                const episode = row.original
                return (
                  <TableRow
                    key={row.id}
                    onClick={() => navigate(`/runs/${episode.episode_id}`)}
                    className="cursor-pointer hover:bg-neutral-800/50 border-neutral-800"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>

          {/* Pagination */}
          <div className="flex items-center justify-between text-sm text-neutral-400 pt-2">
            <span>
              Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

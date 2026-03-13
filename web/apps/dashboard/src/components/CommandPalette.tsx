import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import {
  Activity,
  Download,
  Home,
  List,
  Play,
  Rocket,
  Search,
  Square,
} from 'lucide-react'

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from '@/components/ui/command'
import {
  fetchBatches,
  fetchEpisodes,
  fetchSandboxes,
  stopSandbox,
  type BatchSummary,
  type EpisodeSummary,
  type SandboxInfo,
} from '@/lib/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Mode = 'default' | 'stop-sandbox'

interface CommandPaletteProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

// ---------------------------------------------------------------------------
// Debounce hook
// ---------------------------------------------------------------------------

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

// ---------------------------------------------------------------------------
// CommandPalette
// ---------------------------------------------------------------------------

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate()
  const [, setSearchParams] = useSearchParams()

  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<Mode>('default')

  // Search results state
  const [episodeResults, setEpisodeResults] = useState<EpisodeSummary[]>([])
  const [batchResults, setBatchResults] = useState<BatchSummary[]>([])
  const [sandboxResults, setSandboxResults] = useState<SandboxInfo[]>([])
  const [sandboxList, setSandboxList] = useState<SandboxInfo[]>([])
  const [searching, setSearching] = useState(false)

  const debouncedQuery = useDebounce(query, 300)

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      setQuery('')
      setMode('default')
      setEpisodeResults([])
      setBatchResults([])
      setSandboxResults([])
    }
  }, [open])

  // Async search when query >= 2 chars
  useEffect(() => {
    if (mode !== 'default') return
    if (debouncedQuery.length < 2) {
      setEpisodeResults([])
      setBatchResults([])
      setSandboxResults([])
      return
    }

    let cancelled = false
    setSearching(true)

    const q = debouncedQuery.toLowerCase()

    Promise.allSettled([
      fetchEpisodes({ task_name: debouncedQuery, limit: 5 }),
      fetchBatches({ limit: 20 }),
      fetchSandboxes(),
    ]).then(([episodesResult, batchesResult, sandboxesResult]) => {
      if (cancelled) return

      if (episodesResult.status === 'fulfilled') {
        setEpisodeResults(episodesResult.value.items ?? [])
      }

      if (batchesResult.status === 'fulfilled') {
        const batches = batchesResult.value.items ?? []
        setBatchResults(
          batches.filter(
            (b) =>
              b.run_id?.toLowerCase().includes(q) ||
              b.task_name?.toLowerCase().includes(q),
          ),
        )
      }

      if (sandboxesResult.status === 'fulfilled') {
        const sandboxes = sandboxesResult.value.sandboxes ?? []
        setSandboxResults(
          sandboxes.filter(
            (s) =>
              s.sandbox_id?.toLowerCase().includes(q) ||
              s.fingerprint?.toLowerCase().includes(q),
          ),
        )
      }

      setSearching(false)
    })

    return () => {
      cancelled = true
    }
  }, [debouncedQuery, mode])

  // Fetch sandboxes for stop-sandbox mode
  const fetchSandboxListRef = useRef(false)
  useEffect(() => {
    if (mode !== 'stop-sandbox') return
    if (fetchSandboxListRef.current) return
    fetchSandboxListRef.current = true

    fetchSandboxes()
      .then((data) => {
        setSandboxList(data.sandboxes ?? [])
      })
      .catch(() => {
        setSandboxList([])
      })
  }, [mode])

  // Reset sandbox list fetch guard when mode changes away
  useEffect(() => {
    if (mode !== 'stop-sandbox') {
      fetchSandboxListRef.current = false
    }
  }, [mode])

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  const close = useCallback(() => onOpenChange(false), [onOpenChange])

  const go = useCallback(
    (path: string) => {
      navigate(path)
      close()
    },
    [navigate, close],
  )

  const switchView = useCallback(
    (view: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('view', view)
        return next
      })
      close()
    },
    [setSearchParams, close],
  )

  const handleStopSandboxFlow = useCallback(async () => {
    setMode('stop-sandbox')
    setQuery('')
  }, [])

  const handleStopSandbox = useCallback(
    async (sandboxId: string) => {
      try {
        await stopSandbox(sandboxId)
      } catch {
        // best effort
      }
      close()
    },
    [close],
  )

  // ---------------------------------------------------------------------------
  // Render: stop-sandbox sub-mode
  // ---------------------------------------------------------------------------

  if (mode === 'stop-sandbox') {
    const runningSandboxes = sandboxList.filter((s) => s.status === 'running')
    return (
      <CommandDialog open={open} onOpenChange={onOpenChange} showCloseButton={false}>
        <CommandInput
          placeholder="Select sandbox to stop..."
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          {runningSandboxes.length === 0 ? (
            <CommandEmpty>No running sandboxes.</CommandEmpty>
          ) : (
            <CommandGroup heading="Running Sandboxes">
              {runningSandboxes
                .filter((s) =>
                  query.length === 0
                    ? true
                    : s.sandbox_id?.toLowerCase().includes(query.toLowerCase()),
                )
                .map((s) => (
                  <CommandItem
                    key={s.sandbox_id}
                    value={s.sandbox_id}
                    onSelect={() => handleStopSandbox(s.sandbox_id)}
                  >
                    <Square className="size-4 text-red-400" />
                    <span className="font-mono text-xs">{s.sandbox_id}</span>
                    <span className="text-xs text-zinc-500 ml-2">{s.fingerprint?.slice(0, 12)}</span>
                  </CommandItem>
                ))}
            </CommandGroup>
          )}
          <CommandSeparator />
          <CommandGroup>
            <CommandItem
              onSelect={() => {
                setMode('default')
                setQuery('')
              }}
            >
              <span className="text-xs text-zinc-500">Back to commands</span>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    )
  }

  // ---------------------------------------------------------------------------
  // Render: default mode
  // ---------------------------------------------------------------------------

  const hasSearchResults =
    debouncedQuery.length >= 2 &&
    (episodeResults.length > 0 || batchResults.length > 0 || sandboxResults.length > 0)

  const showEmpty =
    debouncedQuery.length >= 2 && !searching && !hasSearchResults

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} showCloseButton={false}>
      <CommandInput
        placeholder="Type a command or search..."
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        {showEmpty && <CommandEmpty>No results found.</CommandEmpty>}

        {/* Navigation group — always visible */}
        <CommandGroup heading="Navigation">
          <CommandItem value="nav-home" onSelect={() => go('/')}>
            <Home className="size-4" />
            Dashboard
            <CommandShortcut>G H</CommandShortcut>
          </CommandItem>
          <CommandItem value="nav-launcher" onSelect={() => go('/launcher')}>
            <Play className="size-4" />
            New Run
            <CommandShortcut>G L</CommandShortcut>
          </CommandItem>
          <CommandItem value="nav-runs" onSelect={() => go('/runs')}>
            <List className="size-4" />
            Runs
            <CommandShortcut>G R</CommandShortcut>
          </CommandItem>
          <CommandItem value="nav-pool" onSelect={() => go('/pool')}>
            <Activity className="size-4" />
            Pool Health
            <CommandShortcut>G P</CommandShortcut>
          </CommandItem>
          <CommandItem value="nav-export" onSelect={() => go('/export')}>
            <Download className="size-4" />
            Export
            <CommandShortcut>G E</CommandShortcut>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        {/* Actions group */}
        <CommandGroup heading="Actions">
          <CommandItem value="action-launch" onSelect={() => go('/launcher')}>
            <Rocket className="size-4" />
            Launch Experiment
          </CommandItem>
          <CommandItem value="action-stop-sandbox" onSelect={handleStopSandboxFlow}>
            <Square className="size-4 text-red-400" />
            Stop Sandbox
          </CommandItem>
          <CommandItem value="action-export" onSelect={() => go('/export')}>
            <Download className="size-4" />
            Export Data
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        {/* Views group */}
        <CommandGroup heading="Views">
          <CommandItem value="view-timeline" onSelect={() => switchView('timeline')}>
            <List className="size-4" />
            Timeline View
            <CommandShortcut>1</CommandShortcut>
          </CommandItem>
          <CommandItem value="view-graph" onSelect={() => switchView('graph')}>
            <Activity className="size-4" />
            Graph View
            <CommandShortcut>2</CommandShortcut>
          </CommandItem>
          <CommandItem value="view-split" onSelect={() => switchView('split')}>
            <Square className="size-4" />
            Split View
            <CommandShortcut>3</CommandShortcut>
          </CommandItem>
        </CommandGroup>

        {/* Search results — only when query >= 2 chars */}
        {debouncedQuery.length >= 2 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Search Results">
              {searching && (
                <CommandItem value="searching" disabled>
                  <Search className="size-4 animate-pulse" />
                  Searching...
                </CommandItem>
              )}

              {episodeResults.map((ep) => (
                <CommandItem
                  key={`ep-${ep.episode_id}`}
                  value={`ep-${ep.episode_id}`}
                  onSelect={() => go(`/runs/${ep.episode_id}`)}
                >
                  <Play className="size-4" />
                  <span className="font-mono text-xs truncate max-w-[200px]">{ep.episode_id}</span>
                  <span className="text-xs text-zinc-500 ml-1">{ep.task_name}</span>
                </CommandItem>
              ))}

              {batchResults.map((b) => (
                <CommandItem
                  key={`batch-${b.run_id}`}
                  value={`batch-${b.run_id}`}
                  onSelect={() => go(`/batches/${b.run_id}`)}
                >
                  <List className="size-4" />
                  <span className="font-mono text-xs truncate max-w-[200px]">{b.run_id}</span>
                  <span className="text-xs text-zinc-500 ml-1">{b.task_name}</span>
                </CommandItem>
              ))}

              {sandboxResults.map((s) => (
                <CommandItem
                  key={`sb-${s.sandbox_id}`}
                  value={`sb-${s.sandbox_id}`}
                  onSelect={() => go(`/sandboxes/${s.sandbox_id}`)}
                >
                  <Activity className="size-4" />
                  <span className="font-mono text-xs truncate max-w-[200px]">{s.sandbox_id}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  )
}

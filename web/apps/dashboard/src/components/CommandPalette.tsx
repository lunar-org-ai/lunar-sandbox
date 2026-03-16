import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import {
  Activity,
  Download,
  Home,
  List,
  Play,
  Rocket,
  Search,
  Square,
} from "lucide-react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import {
  fetchBatches,
  fetchEpisodes,
  fetchSandboxes,
  stopSandbox,
  type BatchSummary,
  type EpisodeSummary,
  type SandboxInfo,
} from "@/lib/api";

type Mode = "default" | "stop-sandbox";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate();
  const [, setSearchParams] = useSearchParams();

  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<Mode>("default");

  const [episodeResults, setEpisodeResults] = useState<EpisodeSummary[]>([]);
  const [batchResults, setBatchResults] = useState<BatchSummary[]>([]);
  const [sandboxResults, setSandboxResults] = useState<SandboxInfo[]>([]);
  const [sandboxList, setSandboxList] = useState<SandboxInfo[]>([]);
  const [searching, setSearching] = useState(false);

  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setMode("default");
      setEpisodeResults([]);
      setBatchResults([]);
      setSandboxResults([]);
    }
  }, [open]);

  useEffect(() => {
    if (mode !== "default") return;
    if (debouncedQuery.length < 2) {
      setEpisodeResults([]);
      setBatchResults([]);
      setSandboxResults([]);
      return;
    }

    let cancelled = false;
    setSearching(true);

    const q = debouncedQuery.toLowerCase();

    Promise.allSettled([
      fetchEpisodes({ task_name: debouncedQuery, limit: 5 }),
      fetchBatches({ limit: 20 }),
      fetchSandboxes(),
    ]).then(([episodesResult, batchesResult, sandboxesResult]) => {
      if (cancelled) return;

      if (episodesResult.status === "fulfilled") {
        setEpisodeResults(episodesResult.value.items ?? []);
      }

      if (batchesResult.status === "fulfilled") {
        const batches = batchesResult.value.items ?? [];
        setBatchResults(
          batches.filter(
            (b) =>
              b.batch_id?.toLowerCase().includes(q) ||
              b.benchmark_name?.toLowerCase().includes(q),
          ),
        );
      }

      if (sandboxesResult.status === "fulfilled") {
        const sandboxes = sandboxesResult.value.sandboxes ?? [];
        setSandboxResults(
          sandboxes.filter(
            (s) =>
              s.sandbox_id?.toLowerCase().includes(q) ||
              s.fingerprint?.toLowerCase().includes(q),
          ),
        );
      }

      setSearching(false);
    });

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, mode]);

  const fetchSandboxListRef = useRef(false);
  useEffect(() => {
    if (mode !== "stop-sandbox") return;
    if (fetchSandboxListRef.current) return;
    fetchSandboxListRef.current = true;

    fetchSandboxes()
      .then((data) => {
        setSandboxList(data.sandboxes ?? []);
      })
      .catch(() => {
        setSandboxList([]);
      });
  }, [mode]);

  useEffect(() => {
    if (mode !== "stop-sandbox") {
      fetchSandboxListRef.current = false;
    }
  }, [mode]);

  const close = useCallback(() => onOpenChange(false), [onOpenChange]);

  const go = useCallback(
    (path: string) => {
      navigate(path);
      close();
    },
    [navigate, close],
  );

  const switchView = useCallback(
    (view: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("view", view);
        return next;
      });
      close();
    },
    [setSearchParams, close],
  );

  const handleStopSandboxFlow = useCallback(async () => {
    setMode("stop-sandbox");
    setQuery("");
  }, []);

  const handleStopSandbox = useCallback(
    async (sandboxId: string) => {
      try {
        await stopSandbox(sandboxId);
      } catch {
        // best effort
      }
      close();
    },
    [close],
  );

  if (mode === "stop-sandbox") {
    const runningSandboxes = sandboxList.filter((s) => s.state === "Running");
    return (
      <CommandDialog
        open={open}
        onOpenChange={onOpenChange}
        showCloseButton={false}
      >
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
                    <Square className="size-4" />
                    <span className="font-mono text-xs">{s.sandbox_id}</span>
                    <span className="text-xs text-muted-foreground ml-2">
                      {s.fingerprint?.slice(0, 12)}
                    </span>
                  </CommandItem>
                ))}
            </CommandGroup>
          )}
          <CommandSeparator />
          <CommandGroup>
            <CommandItem
              onSelect={() => {
                setMode("default");
                setQuery("");
              }}
            >
              <span className="text-xs text-muted-foreground">
                Back to commands
              </span>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    );
  }

  const hasSearchResults =
    debouncedQuery.length >= 2 &&
    (episodeResults.length > 0 ||
      batchResults.length > 0 ||
      sandboxResults.length > 0);

  const showEmpty =
    debouncedQuery.length >= 2 && !searching && !hasSearchResults;

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      showCloseButton={false}
    >
      <CommandInput
        placeholder="Type a command or search..."
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        {showEmpty && <CommandEmpty>No results found.</CommandEmpty>}

        <CommandGroup heading="Navigation">
          <CommandItem value="nav-home" onSelect={() => go("/")}>
            <Home className="size-4" />
            Dashboard
            <CommandShortcut>G H</CommandShortcut>
          </CommandItem>
          <CommandItem value="nav-launcher" onSelect={() => go("/launcher")}>
            <Play className="size-4" />
            New Run
            <CommandShortcut>G L</CommandShortcut>
          </CommandItem>
          <CommandItem value="nav-runs" onSelect={() => go("/runs")}>
            <List className="size-4" />
            Runs
            <CommandShortcut>G R</CommandShortcut>
          </CommandItem>
          <CommandItem value="nav-pool" onSelect={() => go("/pool")}>
            <Activity className="size-4" />
            Pool Health
            <CommandShortcut>G P</CommandShortcut>
          </CommandItem>
          <CommandItem value="nav-export" onSelect={() => go("/export")}>
            <Download className="size-4" />
            Export
            <CommandShortcut>G E</CommandShortcut>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Actions">
          <CommandItem value="action-launch" onSelect={() => go("/launcher")}>
            <Rocket className="size-4" />
            Launch Experiment
          </CommandItem>
          <CommandItem
            value="action-stop-sandbox"
            onSelect={handleStopSandboxFlow}
          >
            <Square className="size-4" />
            Stop Sandbox
          </CommandItem>
          <CommandItem value="action-export" onSelect={() => go("/export")}>
            <Download className="size-4" />
            Export Data
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Views">
          <CommandItem
            value="view-timeline"
            onSelect={() => switchView("timeline")}
          >
            <List className="size-4" />
            Timeline View
            <CommandShortcut>1</CommandShortcut>
          </CommandItem>
          <CommandItem value="view-graph" onSelect={() => switchView("graph")}>
            <Activity className="size-4" />
            Graph View
            <CommandShortcut>2</CommandShortcut>
          </CommandItem>
          <CommandItem value="view-split" onSelect={() => switchView("split")}>
            <Square className="size-4" />
            Split View
            <CommandShortcut>3</CommandShortcut>
          </CommandItem>
        </CommandGroup>

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
                  <span className="font-mono text-xs truncate max-w-50">
                    {ep.episode_id}
                  </span>
                  <span className="text-xs text-muted-foreground ml-1">
                    {ep.task_name}
                  </span>
                </CommandItem>
              ))}

              {batchResults.map((b) => (
                <CommandItem
                  key={`batch-${b.batch_id}`}
                  value={`batch-${b.batch_id}`}
                  onSelect={() => go(`/batches/${b.batch_id}`)}
                >
                  <List className="size-4" />
                  <span className="max-w-50 truncate font-mono text-xs">
                    {b.batch_id}
                  </span>
                  <span className="ml-1 text-xs text-muted-foreground">
                    {b.benchmark_name || "Benchmark"}
                  </span>
                </CommandItem>
              ))}

              {sandboxResults.map((s) => (
                <CommandItem
                  key={`sb-${s.sandbox_id}`}
                  value={`sb-${s.sandbox_id}`}
                  onSelect={() => go(`/sandboxes/${s.sandbox_id}`)}
                >
                  <Activity className="size-4" />
                  <span className="font-mono text-xs truncate max-w-50">
                    {s.sandbox_id}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}

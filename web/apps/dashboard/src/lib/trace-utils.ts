// ---------------------------------------------------------------------------
// TraceSpan – the normalized unit of work for trace timeline visualization
// ---------------------------------------------------------------------------

export interface TraceSpan {
  /** Unique identifier: episodeId + "_" + stepIdx */
  id: string
  stepIdx: number
  /** Normalized action type (from "action" or "action_type" fields) */
  action: string
  status: 'success' | 'error' | 'timeout' | 'completed' | 'running'
  /** Relative milliseconds from episode start */
  startMs: number
  durationMs: number
  params: Record<string, unknown>
  observation: Record<string, unknown>
  source: string
  /** 0 for all spans (flat for Phase 11) */
  depth: number
}

// ---------------------------------------------------------------------------
// Action types and color system
// ---------------------------------------------------------------------------

export const ACTION_TYPES = [
  'execute_command',
  'read_file',
  'write_file',
  'submit',
  'list_files',
  'search_code',
  'run_tests',
  'get_logs',
] as const

export type ActionType = (typeof ACTION_TYPES)[number]

export interface ActionColor {
  bg: string
  text: string
  border: string
}

export const ACTION_COLORS: Record<string, ActionColor> = {
  execute_command: {
    bg: 'bg-blue-500',
    text: 'text-blue-100',
    border: 'border-blue-500',
  },
  read_file: {
    bg: 'bg-emerald-500',
    text: 'text-emerald-100',
    border: 'border-emerald-500',
  },
  write_file: {
    bg: 'bg-violet-500',
    text: 'text-violet-100',
    border: 'border-violet-500',
  },
  submit: {
    bg: 'bg-green-500',
    text: 'text-green-100',
    border: 'border-green-500',
  },
  list_files: {
    bg: 'bg-cyan-500',
    text: 'text-cyan-100',
    border: 'border-cyan-500',
  },
  search_code: {
    bg: 'bg-amber-500',
    text: 'text-amber-100',
    border: 'border-amber-500',
  },
  run_tests: {
    bg: 'bg-orange-500',
    text: 'text-orange-100',
    border: 'border-orange-500',
  },
  get_logs: {
    bg: 'bg-slate-500',
    text: 'text-slate-100',
    border: 'border-slate-500',
  },
  unknown: {
    bg: 'bg-zinc-500',
    text: 'text-zinc-100',
    border: 'border-zinc-500',
  },
}

/** Returns the color entry for a given action, falling back to "unknown". */
export function getActionColor(action: string): ActionColor {
  return ACTION_COLORS[action] ?? ACTION_COLORS['unknown']
}

// ---------------------------------------------------------------------------
// stepsToSpans – convert REST EpisodeDetail.steps to TraceSpan[]
// ---------------------------------------------------------------------------

function parseJsonField(value: unknown): Record<string, unknown> {
  if (value == null) return {}
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>
      }
      return {}
    } catch {
      return {}
    }
  }
  if (typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return {}
}

/**
 * Converts an array of raw step records (from REST EpisodeDetail.steps)
 * into normalized TraceSpan[].
 *
 * @param steps - raw step objects from the API
 * @param episodeStartTs - Unix seconds float for the episode start time
 * @param episodeId - used to construct span IDs
 */
export function stepsToSpans(
  steps: Record<string, unknown>[],
  episodeStartTs: number,
  episodeId: string,
): TraceSpan[] {
  let accumulatedMs = 0

  return steps.map((step, idx) => {
    // Normalize action field (API may use "action" or "action_type")
    const action = ((step['action'] ?? step['action_type'] ?? 'unknown') as string)

    const params = parseJsonField(step['action_params'] ?? step['params'])
    const observation = parseJsonField(step['observation'])

    const durationMs = typeof step['duration_ms'] === 'number' ? step['duration_ms'] : 0

    // Calculate startMs relative to episode start
    let startMs: number
    if (typeof step['timestamp'] === 'number' && episodeStartTs > 0) {
      startMs = (step['timestamp'] - episodeStartTs) * 1000
    } else {
      startMs = accumulatedMs
    }
    accumulatedMs = startMs + durationMs

    const rawStatus = (step['status'] ?? 'completed') as string
    const status = (['success', 'error', 'timeout', 'completed', 'running'].includes(rawStatus)
      ? rawStatus
      : 'completed') as TraceSpan['status']

    return {
      id: `${episodeId}_${idx}`,
      stepIdx: idx,
      action,
      status,
      startMs,
      durationMs,
      params,
      observation,
      source: (step['source'] ?? '') as string,
      depth: 0,
    }
  })
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

/**
 * Returns a human-readable duration string.
 * Examples: "<1ms", "42ms", "1.2s", "1m 5s"
 */
export function formatDurationMs(ms: number): string {
  if (ms < 1) return '<1ms'
  if (ms < 1000) return `${Math.round(ms)}ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSecs = Math.floor(seconds % 60)
  return `${minutes}m ${remainingSecs}s`
}

/**
 * Formats a relative millisecond offset as a time-axis label.
 * Examples: "0.000s", "1.234s", "1:05.234"
 */
export function formatTimestamp(ms: number): string {
  const seconds = ms / 1000
  if (seconds < 60) {
    return `${seconds.toFixed(3)}s`
  }
  const minutes = Math.floor(seconds / 60)
  const remainingSecs = seconds % 60
  const secsFixed = remainingSecs.toFixed(3).padStart(6, '0')
  return `${minutes}:${secsFixed}`
}

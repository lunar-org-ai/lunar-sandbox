import type { components } from '@lunar/types/api'

// ---------------------------------------------------------------------------
// Type aliases (re-exported from generated types for convenience)
// ---------------------------------------------------------------------------

export type HealthResponse = components['schemas']['HealthResponse']
export type EpisodeSummary = components['schemas']['EpisodeSummary']
export type EpisodeDetail = components['schemas']['EpisodeDetail']
export type PaginatedEpisodes = components['schemas']['PaginatedEpisodes']
export type PoolStatus = components['schemas']['PoolStatus']
export type SandboxInfo = components['schemas']['SandboxInfo']
export type TaskSummary = components['schemas']['TaskSummary']
export type PaginatedTasks = components['schemas']['PaginatedTasks']
export type TelemetryRunSummary = components['schemas']['TelemetryRunSummary']
export type PaginatedTelemetryRuns = components['schemas']['PaginatedTelemetryRuns']
export type RunRequest = components['schemas']['RunRequest']
export type RunLaunchResponse = components['schemas']['RunLaunchResponse']

// ---------------------------------------------------------------------------
// Fetch utilities (hand-written, types-only codegen per locked decision)
// ---------------------------------------------------------------------------

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch('/api/health')
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function fetchEpisodes(params?: {
  offset?: number
  limit?: number
  task_name?: string
  outcome?: string
  date_from?: number
  date_to?: number
  score_min?: number
  sort_by?: string
  sort_order?: string
}): Promise<PaginatedEpisodes> {
  const searchParams = new URLSearchParams()
  if (params?.offset !== undefined) searchParams.set('offset', String(params.offset))
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit))
  if (params?.task_name) searchParams.set('task_name', params.task_name)
  if (params?.outcome) searchParams.set('outcome', params.outcome)
  if (params?.date_from !== undefined) searchParams.set('date_from', String(params.date_from))
  if (params?.date_to !== undefined) searchParams.set('date_to', String(params.date_to))
  if (params?.score_min !== undefined) searchParams.set('score_min', String(params.score_min))
  if (params?.sort_by) searchParams.set('sort_by', params.sort_by)
  if (params?.sort_order) searchParams.set('sort_order', params.sort_order)
  const query = searchParams.toString()
  const res = await fetch(`/api/episodes${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function fetchEpisode(episodeId: string): Promise<EpisodeDetail> {
  const res = await fetch(`/api/episodes/${encodeURIComponent(episodeId)}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function fetchSandboxes(): Promise<PoolStatus> {
  const res = await fetch('/api/sandboxes')
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function fetchSandbox(sandboxId: string): Promise<SandboxInfo> {
  const res = await fetch(`/api/sandboxes/${encodeURIComponent(sandboxId)}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function stopSandbox(sandboxId: string): Promise<{ status: string }> {
  const res = await fetch(`/api/sandboxes/${encodeURIComponent(sandboxId)}/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function launchRun(params: {
  task_name: string
  model?: string
  parallelism?: number
  timeout?: number
  env_vars?: Record<string, string>
}): Promise<RunLaunchResponse> {
  const res = await fetch('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function fetchTasks(params?: {
  offset?: number
  limit?: number
}): Promise<PaginatedTasks> {
  const searchParams = new URLSearchParams()
  if (params?.offset !== undefined) searchParams.set('offset', String(params.offset))
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit))
  const query = searchParams.toString()
  const res = await fetch(`/api/tasks${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function fetchTelemetryRuns(params?: {
  offset?: number
  limit?: number
}): Promise<PaginatedTelemetryRuns> {
  const searchParams = new URLSearchParams()
  if (params?.offset !== undefined) searchParams.set('offset', String(params.offset))
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit))
  const query = searchParams.toString()
  const res = await fetch(`/api/telemetry${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

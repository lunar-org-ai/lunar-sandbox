import type { components } from '@lunar/types/api'

// ---------------------------------------------------------------------------
// Type aliases (re-exported from generated types for convenience)
// ---------------------------------------------------------------------------

export type HealthResponse = components['schemas']['HealthResponse']
export type EpisodeSummary = components['schemas']['EpisodeSummary']
export type PaginatedEpisodes = components['schemas']['PaginatedEpisodes']
export type PoolStatus = components['schemas']['PoolStatus']
export type SandboxInfo = components['schemas']['SandboxInfo']
export type TaskSummary = components['schemas']['TaskSummary']
export type PaginatedTasks = components['schemas']['PaginatedTasks']
export type TelemetryRunSummary = components['schemas']['TelemetryRunSummary']
export type PaginatedTelemetryRuns = components['schemas']['PaginatedTelemetryRuns']

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
}): Promise<PaginatedEpisodes> {
  const searchParams = new URLSearchParams()
  if (params?.offset !== undefined) searchParams.set('offset', String(params.offset))
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit))
  if (params?.task_name) searchParams.set('task_name', params.task_name)
  const query = searchParams.toString()
  const res = await fetch(`/api/episodes${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function fetchSandboxes(): Promise<PoolStatus> {
  const res = await fetch('/api/sandboxes')
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

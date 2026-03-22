import type { components } from '@lunar/types/api'

// ---------------------------------------------------------------------------
// Type aliases (re-exported from generated types for convenience)
// ---------------------------------------------------------------------------

export type HealthResponse = components['schemas']['HealthResponse']
export type EpisodeSummary = components['schemas']['EpisodeSummary']
export type EpisodeDetail = components['schemas']['EpisodeDetail']
export type PaginatedEpisodes = components['schemas']['PaginatedEpisodes']
export type FingerprintHealth = components['schemas']['FingerprintHealth']
export type PoolHealthDetail = components['schemas']['PoolHealthDetail']
export type PoolStatus = components['schemas']['PoolStatus']
export type SandboxInfo = components['schemas']['SandboxInfo']
export type TaskSummary = components['schemas']['TaskSummary']
export type PaginatedTasks = components['schemas']['PaginatedTasks']
export type TelemetryRunSummary = components['schemas']['TelemetryRunSummary']
export type PaginatedTelemetryRuns = components['schemas']['PaginatedTelemetryRuns']
export type RunRequest = components['schemas']['RunRequest']
export type RunLaunchResponse = components['schemas']['RunLaunchResponse']
export type BatchSummary = components['schemas']['BatchSummary']
export type BatchDetail = components['schemas']['BatchDetail']
export type TaskResultSummary = components['schemas']['TaskResultSummary']
export type PaginatedBatches = components['schemas']['PaginatedBatches']

// ---------------------------------------------------------------------------
// Fetch utilities (hand-written, types-only codegen per locked decision)
// ---------------------------------------------------------------------------

const REQUEST_TIMEOUT_MS = 15_000
const MAX_RETRIES = 2
const RETRY_DELAY_MS = 1000
const RETRYABLE_STATUS = new Set([502, 503, 504])

async function fetchWithRetry(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  let lastError: Error | null = null

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

    try {
      const res = await fetch(input, { ...init, signal: controller.signal })
      clearTimeout(timeout)

      if (res.ok) return res

      // Only retry on transient server errors, not 4xx
      if (RETRYABLE_STATUS.has(res.status) && attempt < MAX_RETRIES) {
        lastError = new Error(`API error ${res.status}: ${res.statusText}`)
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS * (attempt + 1)))
        continue
      }

      const body = await res.text().catch(() => '')
      throw new Error(
        `API error ${res.status}: ${body || res.statusText}`,
      )
    } catch (err) {
      clearTimeout(timeout)

      if (err instanceof DOMException && err.name === 'AbortError') {
        lastError = new Error(`Request timed out after ${REQUEST_TIMEOUT_MS}ms`)
      } else if (err instanceof Error && err.message.startsWith('API error')) {
        throw err
      } else {
        lastError = err instanceof Error ? err : new Error(String(err))
      }

      if (attempt < MAX_RETRIES) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS * (attempt + 1)))
        continue
      }
    }
  }

  throw lastError ?? new Error('Request failed')
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetchWithRetry('/api/health')
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
  const res = await fetchWithRetry(`/api/episodes${query ? `?${query}` : ''}`)
  return res.json()
}

export async function fetchEpisode(episodeId: string): Promise<EpisodeDetail> {
  const res = await fetchWithRetry(`/api/episodes/${encodeURIComponent(episodeId)}`)
  return res.json()
}

export async function fetchSandboxes(): Promise<PoolStatus> {
  const res = await fetchWithRetry('/api/sandboxes')
  return res.json()
}

export async function fetchSandbox(sandboxId: string): Promise<SandboxInfo> {
  const res = await fetchWithRetry(`/api/sandboxes/${encodeURIComponent(sandboxId)}`)
  return res.json()
}

export async function stopSandbox(sandboxId: string): Promise<{ status: string }> {
  const res = await fetchWithRetry(`/api/sandboxes/${encodeURIComponent(sandboxId)}/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return res.json()
}

export async function launchRun(params: {
  task_name: string
  model?: string
  parallelism?: number
  timeout?: number
  env_vars?: Record<string, string>
  cpu_cores?: number
  memory_mb?: number
}): Promise<RunLaunchResponse> {
  const res = await fetchWithRetry('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
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
  const res = await fetchWithRetry(`/api/tasks${query ? `?${query}` : ''}`)
  return res.json()
}

export async function createTask(task: {
  name: string
  runtime?: string
  timeout?: number
  max_steps?: number
  instructions?: string
  test_command?: string
}): Promise<TaskSummary> {
  const res = await fetchWithRetry('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(task),
  })
  return res.json()
}

export async function deleteTask(taskName: string): Promise<void> {
  await fetchWithRetry(`/api/tasks/${encodeURIComponent(taskName)}`, {
    method: 'DELETE',
  })
}

export async function fetchTelemetryRuns(params?: {
  offset?: number
  limit?: number
}): Promise<PaginatedTelemetryRuns> {
  const searchParams = new URLSearchParams()
  if (params?.offset !== undefined) searchParams.set('offset', String(params.offset))
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit))
  const query = searchParams.toString()
  const res = await fetchWithRetry(`/api/telemetry${query ? `?${query}` : ''}`)
  return res.json()
}

export async function fetchBatches(params?: {
  offset?: number
  limit?: number
}): Promise<PaginatedBatches> {
  const searchParams = new URLSearchParams()
  if (params?.offset !== undefined) searchParams.set('offset', String(params.offset))
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit))
  const query = searchParams.toString()
  const res = await fetchWithRetry(`/api/batches${query ? `?${query}` : ''}`)
  return res.json()
}

export async function fetchBatch(batchId: string): Promise<BatchDetail> {
  const res = await fetchWithRetry(`/api/batches/${encodeURIComponent(batchId)}`)
  return res.json()
}

export async function fetchPoolHealth(): Promise<PoolHealthDetail> {
  const res = await fetchWithRetry('/api/pool/health')
  return res.json()
}

// ---------------------------------------------------------------------------
// CUA Episodes
// ---------------------------------------------------------------------------

export interface CUALaunchParams {
  instruction: string
  reward_type?: string
  agent_mode?: 'manual' | 'model'
  api_key?: string
  start_url?: string
  resolution?: string
  max_steps?: number
  time_limit?: number
  script_content?: string
  reference_image_url?: string
  screenshot_threshold?: number
}

export interface CUALaunchResponse {
  episode_id: string
  vnc_url: string
}

export interface CUAEpisodeInfo {
  episode_id: string
  task_name: string
  outcome: string
  score: number | null
  review_notes: string | null
  step_count: number
  duration_ms: number
  started_at: number
  ended_at: number | null
  episode_type: string
}

export interface CUAScoreResponse {
  episode_id: string
  score: number
  next_episode_id: string | null
}

export async function launchCUAEpisode(params: CUALaunchParams): Promise<CUALaunchResponse> {
  const res = await fetchWithRetry('/api/cua/episodes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  return res.json()
}

export async function fetchCUAEpisodes(params?: {
  offset?: number
  limit?: number
}): Promise<PaginatedEpisodes> {
  const searchParams = new URLSearchParams()
  if (params?.offset !== undefined) searchParams.set('offset', String(params.offset))
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit))
  const query = searchParams.toString()
  const res = await fetchWithRetry(`/api/cua/episodes${query ? `?${query}` : ''}`)
  return res.json()
}

export async function fetchCUAEpisodeDetail(episodeId: string): Promise<CUAEpisodeInfo> {
  const res = await fetchWithRetry(`/api/cua/episodes/${encodeURIComponent(episodeId)}`)
  return res.json()
}

export async function scoreCUAEpisode(
  episodeId: string,
  score: number,
  notes?: string,
): Promise<CUAScoreResponse> {
  const res = await fetchWithRetry(`/api/cua/episodes/${encodeURIComponent(episodeId)}/score`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ score, notes }),
  })
  return res.json()
}

export function cuaScreenshotUrl(episodeId: string, filename: string): string {
  return `/api/cua/episodes/${encodeURIComponent(episodeId)}/screenshots/${encodeURIComponent(filename)}`
}

export function cuaVncWebSocketUrl(episodeId: string): string {
  // Connect directly to the FastAPI server (port 8000) for VNC WebSocket
  // traffic. Vite's dev proxy doesn't reliably handle binary WebSocket
  // subprotocols used by the RFB/VNC protocol.
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.hostname
  const apiPort = '8000'
  return `${protocol}//${host}:${apiPort}/api/cua/vnc/${encodeURIComponent(episodeId)}`
}

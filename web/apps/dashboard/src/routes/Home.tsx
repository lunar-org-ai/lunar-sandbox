import { useState, useEffect } from 'react'
import {
  fetchHealth,
  fetchEpisodes,
  fetchSandboxes,
  fetchTasks,
  fetchTelemetryRuns,
} from '@/lib/api'
import type {
  HealthResponse,
  PaginatedEpisodes,
  PoolStatus,
  PaginatedTasks,
  PaginatedTelemetryRuns,
} from '@/lib/api'

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }) {
  const bg =
    status === 'ok'
      ? 'bg-green-600'
      : status === 'degraded'
        ? 'bg-yellow-600'
        : 'bg-red-600'
  return (
    <span className={`${bg} text-white text-xs font-medium px-2 py-0.5 rounded`}>
      {status}
    </span>
  )
}

function SectionError({ message }: { message: string }) {
  return <p className="text-red-400 text-sm">{message}</p>
}

function SectionLoading() {
  return <p className="text-neutral-500 text-sm">Loading...</p>
}

function SectionEmpty({ label }: { label: string }) {
  return <p className="text-neutral-500 text-sm">No {label} recorded yet.</p>
}

// ---------------------------------------------------------------------------
// Section components
// ---------------------------------------------------------------------------

function HealthSection() {
  const [data, setData] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchHealth()
      .then(setData)
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <SectionError message={error} />
  if (!data) return <SectionLoading />

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-sm text-neutral-300">Status:</span>
        <StatusBadge status={data.status} />
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="text-neutral-400">Engine started</dt>
        <dd>{data.engine_started ? 'Yes' : 'No'}</dd>
        <dt className="text-neutral-400">Stores available</dt>
        <dd>{data.stores_available ? 'Yes' : 'No'}</dd>
      </dl>
    </div>
  )
}

function SandboxesSection() {
  const [data, setData] = useState<PoolStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchSandboxes()
      .then(setData)
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <SectionError message={error} />
  if (!data) return <SectionLoading />

  return (
    <div className="space-y-2">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="text-neutral-400">Pool running</dt>
        <dd>{data.running ? 'Yes' : 'No'}</dd>
        <dt className="text-neutral-400">Total sandboxes</dt>
        <dd>{data.total_sandboxes}</dd>
      </dl>
      {data.sandboxes.length > 0 && (
        <table className="w-full text-sm mt-2">
          <thead>
            <tr className="text-left text-neutral-400 border-b border-neutral-700">
              <th className="pb-1">Sandbox ID</th>
              <th className="pb-1">State</th>
            </tr>
          </thead>
          <tbody>
            {data.sandboxes.map((s) => (
              <tr key={s.sandbox_id} className="border-b border-neutral-800">
                <td className="py-1 font-mono text-xs">{s.sandbox_id}</td>
                <td className="py-1">{s.state}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function EpisodesSection() {
  const [data, setData] = useState<PaginatedEpisodes | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchEpisodes({ limit: 5 })
      .then(setData)
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <SectionError message={error} />
  if (!data) return <SectionLoading />
  if (data.items.length === 0) return <SectionEmpty label="episodes" />

  return (
    <div className="space-y-2">
      <p className="text-sm text-neutral-400">Total: {data.total}</p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-neutral-400 border-b border-neutral-700">
            <th className="pb-1">Episode ID</th>
            <th className="pb-1">Task</th>
            <th className="pb-1">Outcome</th>
            <th className="pb-1">Score</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((ep) => (
            <tr key={ep.episode_id} className="border-b border-neutral-800">
              <td className="py-1 font-mono text-xs">{ep.episode_id}</td>
              <td className="py-1">{ep.task_name}</td>
              <td className="py-1">{ep.outcome}</td>
              <td className="py-1">{ep.score ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TasksSection() {
  const [data, setData] = useState<PaginatedTasks | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTasks({ limit: 10 })
      .then(setData)
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <SectionError message={error} />
  if (!data) return <SectionLoading />
  if (data.items.length === 0) return <SectionEmpty label="tasks" />

  return (
    <div className="space-y-2">
      <p className="text-sm text-neutral-400">Total: {data.total}</p>
      <ul className="text-sm space-y-1">
        {data.items.map((t) => (
          <li key={t.name} className="font-mono text-xs bg-neutral-800 px-2 py-1 rounded">
            {t.name}
          </li>
        ))}
      </ul>
    </div>
  )
}

function TelemetrySection() {
  const [data, setData] = useState<PaginatedTelemetryRuns | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTelemetryRuns({ limit: 5 })
      .then(setData)
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <SectionError message={error} />
  if (!data) return <SectionLoading />
  if (data.items.length === 0) return <SectionEmpty label="telemetry runs" />

  return (
    <div className="space-y-2">
      <p className="text-sm text-neutral-400">Total: {data.total}</p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-neutral-400 border-b border-neutral-700">
            <th className="pb-1">Run ID</th>
            <th className="pb-1">Started At</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((run) => (
            <tr key={run.run_id} className="border-b border-neutral-800">
              <td className="py-1 font-mono text-xs">{run.run_id}</td>
              <td className="py-1">
                {run.started_at
                  ? new Date(run.started_at * 1000).toLocaleString()
                  : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Home page
// ---------------------------------------------------------------------------

export default function Home() {
  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-3xl font-bold tracking-tight mb-8">Lunar Sandbox Dashboard</h1>

      <div className="grid grid-cols-1 gap-6">
        {/* Health */}
        <section className="bg-neutral-900 rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">API Health</h2>
          <HealthSection />
        </section>

        {/* Sandboxes */}
        <section className="bg-neutral-900 rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Sandbox Pool</h2>
          <SandboxesSection />
        </section>

        {/* Episodes */}
        <section className="bg-neutral-900 rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Recent Episodes</h2>
          <EpisodesSection />
        </section>

        {/* Tasks */}
        <section className="bg-neutral-900 rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Tasks</h2>
          <TasksSection />
        </section>

        {/* Telemetry */}
        <section className="bg-neutral-900 rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Telemetry Runs</h2>
          <TelemetrySection />
        </section>
      </div>
    </div>
  )
}

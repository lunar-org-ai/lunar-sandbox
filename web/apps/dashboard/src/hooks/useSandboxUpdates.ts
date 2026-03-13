import { useEffect, useState } from 'react'
import { useEventStream } from '@/hooks/useEventStream'
import { fetchSandboxes, type SandboxInfo } from '@/lib/api'

export function useSandboxUpdates() {
  const [sandboxes, setSandboxes] = useState<SandboxInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { events } = useEventStream({ topic: 'sandbox' })

  // Initial REST fetch
  useEffect(() => {
    fetchSandboxes()
      .then(data => {
        setSandboxes(data.sandboxes)
        setLoading(false)
      })
      .catch((e: Error) => {
        setError(e.message)
        setLoading(false)
      })
  }, [])

  // Merge WS sandbox_status events into state
  useEffect(() => {
    const latest = events.at(-1)
    if (!latest || latest.type !== 'sandbox_status') return

    const payload = latest.payload as {
      sandbox_id?: string
      state?: string
      cpu_percent?: number
      memory_mb?: number
    }
    if (!payload.sandbox_id) return

    setSandboxes(prev => {
      const exists = prev.some(s => s.sandbox_id === payload.sandbox_id)
      if (exists) {
        return prev.map(s =>
          s.sandbox_id === payload.sandbox_id
            ? {
                ...s,
                state: (payload.state as string) ?? s.state,
                cpu_percent: payload.cpu_percent ?? s.cpu_percent,
                memory_mb: payload.memory_mb ?? s.memory_mb,
              }
            : s
        )
      } else {
        // New sandbox appeared via WS -- add it
        return [...prev, {
          sandbox_id: payload.sandbox_id!,
          fingerprint: 'unknown',
          state: (payload.state as string) ?? 'Starting',
          cpu_percent: payload.cpu_percent ?? null,
          memory_mb: payload.memory_mb ?? null,
          started_at: null,
        } as SandboxInfo]
      }
    })
  }, [events])

  return { sandboxes, loading, error }
}

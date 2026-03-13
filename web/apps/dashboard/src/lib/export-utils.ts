// ---------------------------------------------------------------------------
// Export utilities — zero-dependency CSV/JSON serialization + download trigger
// ---------------------------------------------------------------------------

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function downloadJson(data: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  triggerDownload(blob, `${filename}.json`)
}

export function downloadCsv(rows: Record<string, unknown>[], filename: string): void {
  if (rows.length === 0) return
  const headers = Object.keys(rows[0])
  const lines = [
    headers.map((h) => JSON.stringify(h)).join(','),
    ...rows.map((row) =>
      headers
        .map((h) => {
          const v = row[h]
          if (v === null || v === undefined) return '""'
          if (typeof v === 'object') return JSON.stringify(JSON.stringify(v))
          return JSON.stringify(v)
        })
        .join(','),
    ),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
  triggerDownload(blob, `${filename}.csv`)
}

/**
 * Flatten an episode record for CSV export.
 * Removes the nested `steps` array and replaces it with a `step_count` field.
 */
export function flattenEpisodeForCsv(
  episode: Record<string, unknown>,
): Record<string, unknown> {
  const { steps, ...rest } = episode
  return {
    ...rest,
    step_count: Array.isArray(steps) ? steps.length : 0,
  }
}

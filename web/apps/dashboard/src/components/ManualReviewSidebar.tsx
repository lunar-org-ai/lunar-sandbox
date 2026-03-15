import { useState } from 'react'

import { scoreCUAEpisode } from '@/lib/api'

// ---------------------------------------------------------------------------
// ManualReviewSidebar Props
// ---------------------------------------------------------------------------

interface ManualReviewSidebarProps {
  episodeId: string
  existingScore: number | null
  existingNotes: string | null
  onScoreSubmitted: (nextEpisodeId: string | null) => void
}

// ---------------------------------------------------------------------------
// ManualReviewSidebar
// ---------------------------------------------------------------------------

export function ManualReviewSidebar({
  episodeId,
  existingScore,
  existingNotes,
  onScoreSubmitted,
}: ManualReviewSidebarProps) {
  const [score, setScore] = useState<number>(existingScore ?? 0.5)
  const [notes, setNotes] = useState<string>(existingNotes ?? '')
  const [loading, setLoading] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const alreadyReviewed = existingScore !== null

  async function handleSubmit() {
    setSubmitError(null)
    setLoading(true)
    try {
      const response = await scoreCUAEpisode(episodeId, score, notes || undefined)
      onScoreSubmitted(response.next_episode_id)
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Failed to submit score.')
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4 p-4 border-l border-border/50 w-64 shrink-0 overflow-y-auto">
      {/* Header */}
      <div>
        <h3 className="text-sm font-semibold text-foreground">Manual Review</h3>
        <p className="text-[11px] text-muted-foreground mt-0.5">
          Score this episode for reward training.
        </p>
      </div>

      {/* Previously scored badge */}
      {alreadyReviewed && (
        <div className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-400">
          <span className="font-medium">Previously scored:</span>
          <span className="font-mono tabular-nums">{existingScore!.toFixed(2)}</span>
        </div>
      )}

      {/* Score slider */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-foreground">Score</label>
          <span className="text-xs font-mono tabular-nums text-foreground/80">
            {score.toFixed(2)}
          </span>
        </div>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={score}
          onChange={(e) => setScore(Number(e.target.value))}
          className="w-full accent-blue-500 cursor-pointer"
        />
        <div className="flex justify-between text-[10px] text-muted-foreground">
          <span>0 (failure)</span>
          <span>1 (success)</span>
        </div>
      </div>

      {/* Notes textarea */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-foreground">Notes</label>
        <textarea
          className="flex w-full min-h-[80px] rounded-md border border-input bg-transparent px-3 py-2 text-xs shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:border-ring resize-none"
          placeholder="Optional review notes..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      {/* Submit error */}
      {submitError && (
        <p className="text-xs text-destructive">{submitError}</p>
      )}

      {/* Submit button */}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={loading}
        className="w-full inline-flex items-center justify-center rounded-md bg-foreground text-background text-xs font-medium h-9 px-4 transition-colors hover:bg-foreground/90 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? 'Submitting...' : alreadyReviewed ? 'Update Score' : 'Submit Score'}
      </button>
    </div>
  )
}

import { useState } from 'react'
import { useNavigate } from 'react-router'
import { ChevronDown, Play } from 'lucide-react'
import Editor from '@monaco-editor/react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'

import { launchCUAEpisode } from '@/lib/api'

// ---------------------------------------------------------------------------
// Reward type options
// ---------------------------------------------------------------------------

const AGENT_MODES = [
  { value: 'manual', label: 'Manual (view-only sandbox)' },
  { value: 'model', label: 'AI Model (Claude computer-use)' },
] as const

type AgentMode = (typeof AGENT_MODES)[number]['value']

const REWARD_TYPES = [
  { value: 'manual', label: 'Manual Review' },
  { value: 'script', label: 'Script Validation' },
  { value: 'screenshot_match', label: 'Screenshot Match' },
] as const

type RewardType = (typeof REWARD_TYPES)[number]['value']

// ---------------------------------------------------------------------------
// CUALauncher
// ---------------------------------------------------------------------------

export default function CUALauncher() {
  const navigate = useNavigate()

  // Core fields
  const [instruction, setInstruction] = useState('')
  const [agentMode, setAgentMode] = useState<AgentMode>('manual')
  const [rewardType, setRewardType] = useState<RewardType>('manual')

  // Script reward
  const [scriptContent, setScriptContent] = useState('')

  // Screenshot match reward
  const [referenceImageUrl, setReferenceImageUrl] = useState('')
  const [screenshotThreshold, setScreenshotThreshold] = useState('0.9')

  // Advanced options
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [startUrl, setStartUrl] = useState('')
  const [resolution, setResolution] = useState('')
  const [maxSteps, setMaxSteps] = useState('')
  const [timeLimit, setTimeLimit] = useState('')

  // Submission state
  const [loading, setLoading] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // ---------------------------------------------------------------------------
  // Submit
  // ---------------------------------------------------------------------------

  async function handleLaunch() {
    setValidationError(null)
    setSubmitError(null)

    if (!instruction.trim()) {
      setValidationError('Instruction is required.')
      return
    }
    if (instruction.trim().length < 10) {
      setValidationError('Instruction must be at least 10 characters.')
      return
    }

    setLoading(true)
    try {
      const response = await launchCUAEpisode({
        instruction: instruction.trim(),
        agent_mode: agentMode,
        reward_type: rewardType,
        script_content: rewardType === 'script' ? scriptContent || undefined : undefined,
        reference_image_url: rewardType === 'screenshot_match' ? referenceImageUrl.trim() || undefined : undefined,
        screenshot_threshold: rewardType === 'screenshot_match' ? parseFloat(screenshotThreshold) : undefined,
        start_url: startUrl.trim() || undefined,
        resolution: resolution.trim() || undefined,
        max_steps: maxSteps ? parseInt(maxSteps, 10) : undefined,
        time_limit: timeLimit ? parseFloat(timeLimit) : undefined,
      })
      navigate(`/cua/live/${response.episode_id}`, {
        state: { vncUrl: response.vnc_url },
      })
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Failed to launch CUA episode.')
      setLoading(false)
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Launch CUA Episode</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Configure a Computer-Using Agent task and start a desktop episode.
        </p>
      </div>

      <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
        <CardHeader className="pb-4">
          <CardTitle className="text-base font-medium">Configuration</CardTitle>
          <CardDescription className="text-xs">
            The agent will execute inside a sandboxed desktop environment.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">

          {/* Instruction */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Instruction</label>
            <textarea
              className="flex min-h-[100px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="e.g., Open the calculator app, type 123+456, and press Enter to compute the result"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
            />
            {validationError && (
              <p className="text-xs text-destructive">{validationError}</p>
            )}
          </div>

          {/* Agent mode */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Agent Mode</label>
            <Select value={agentMode} onValueChange={(v) => setAgentMode(v as AgentMode)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AGENT_MODES.map((am) => (
                  <SelectItem key={am.value} value={am.value}>
                    {am.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {agentMode === 'model'
                ? 'Claude will see the screen and interact autonomously. Requires ANTHROPIC_API_KEY on the server.'
                : 'Sandbox stays alive for you to observe or interact via the live view.'}
            </p>
          </div>

          {/* Reward type */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Reward Type</label>
            <Select value={rewardType} onValueChange={(v) => setRewardType(v as RewardType)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REWARD_TYPES.map((rt) => (
                  <SelectItem key={rt.value} value={rt.value}>
                    {rt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Script validation editor */}
          {rewardType === 'script' && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Validation Script</label>
              <p className="text-xs text-muted-foreground">
                A bash script that exits 0 on success, non-zero on failure. Exit code becomes the score.
              </p>
              <div className="rounded-md border border-border overflow-hidden">
                <Editor
                  height="200px"
                  language="bash"
                  theme="vs-dark"
                  value={scriptContent}
                  onChange={(v) => setScriptContent(v ?? '')}
                  options={{
                    minimap: { enabled: false },
                    fontSize: 13,
                    lineNumbers: 'on',
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                  }}
                />
              </div>
            </div>
          )}

          {/* Screenshot match fields */}
          {rewardType === 'screenshot_match' && (
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Reference Image URL</label>
                <Input
                  type="url"
                  placeholder="https://example.com/reference.png"
                  value={referenceImageUrl}
                  onChange={(e) => setReferenceImageUrl(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  URL of the reference screenshot to compare against.
                </p>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  Similarity Threshold: {screenshotThreshold}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={screenshotThreshold}
                  onChange={(e) => setScreenshotThreshold(e.target.value)}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>0 (any)</span>
                  <span>1 (exact)</span>
                </div>
              </div>
            </div>
          )}

          {/* Advanced options */}
          <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                className="flex items-center gap-1 px-0 text-sm text-muted-foreground hover:text-foreground"
              >
                <ChevronDown
                  className={`size-4 transition-transform ${advancedOpen ? 'rotate-180' : ''}`}
                />
                Advanced Options
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-4 pt-4">

              {/* Start URL */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Start URL</label>
                <Input
                  type="url"
                  placeholder="https://example.com"
                  value={startUrl}
                  onChange={(e) => setStartUrl(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  If set, Chromium is pre-loaded to this URL before the episode starts.
                </p>
              </div>

              {/* Resolution */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Resolution</label>
                <Input
                  type="text"
                  placeholder="1280x800"
                  value={resolution}
                  onChange={(e) => setResolution(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Desktop resolution as WxH. Leave blank for default (1280x800).
                </p>
              </div>

              {/* Max Steps */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Max Steps</label>
                <Input
                  type="number"
                  placeholder="100"
                  value={maxSteps}
                  onChange={(e) => setMaxSteps(e.target.value)}
                  min={1}
                />
                <p className="text-xs text-muted-foreground">
                  Maximum number of agent actions. Leave blank for default (100).
                </p>
              </div>

              {/* Time Limit */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Time Limit (seconds)</label>
                <Input
                  type="number"
                  placeholder="300"
                  value={timeLimit}
                  onChange={(e) => setTimeLimit(e.target.value)}
                  min={1}
                />
                <p className="text-xs text-muted-foreground">
                  Episode wall-clock timeout in seconds. Leave blank for default (300).
                </p>
              </div>

            </CollapsibleContent>
          </Collapsible>

          {/* Submit error */}
          {submitError && (
            <p className="text-sm text-destructive">{submitError}</p>
          )}

          {/* Launch button */}
          <Button
            className="w-full"
            onClick={handleLaunch}
            disabled={loading}
          >
            {loading ? (
              'Launching...'
            ) : (
              <>
                <Play className="size-4 mr-2" />
                Launch Episode
              </>
            )}
          </Button>

        </CardContent>
      </Card>
    </div>
  )
}

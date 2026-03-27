import { useState } from "react";
import { useNavigate } from "react-router";
import { ChevronDown, Play, Rocket } from "lucide-react";
import Editor from "@monaco-editor/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

import { launchCUAEpisode } from "@/lib/api";

// ---------------------------------------------------------------------------
// Reward type options
// ---------------------------------------------------------------------------

const AGENT_MODES = [
  { value: "manual", label: "Manual (view-only sandbox)" },
  { value: "model", label: "AI Model (autonomous)" },
] as const;

type AgentMode = (typeof AGENT_MODES)[number]["value"];

const PLATFORMS = [
  { value: "linux", label: "Linux (Docker)" },
  { value: "windows", label: "Windows (VM)" },
] as const;

type Platform = (typeof PLATFORMS)[number]["value"];

const MODEL_PROVIDERS = [
  { value: "anthropic", label: "Anthropic (Claude)" },
  { value: "azure_openai", label: "Azure OpenAI" },
] as const;

type ModelProvider = (typeof MODEL_PROVIDERS)[number]["value"];

const REWARD_TYPES = [
  { value: "manual", label: "Manual Review" },
  { value: "script", label: "Script Validation" },
  { value: "screenshot_match", label: "Screenshot Match" },
] as const;

type RewardType = (typeof REWARD_TYPES)[number]["value"];

// ---------------------------------------------------------------------------
// CUALauncher
// ---------------------------------------------------------------------------

export default function CUALauncher() {
  const navigate = useNavigate();

  // Core fields
  const [instruction, setInstruction] = useState("");
  const [agentMode, setAgentMode] = useState<AgentMode>("model");
  const [platform, setPlatform] = useState<Platform>("linux");
  const [modelProvider, setModelProvider] = useState<ModelProvider>("anthropic");
  const [rewardType, setRewardType] = useState<RewardType>("manual");

  // API key (for model mode)
  const [apiKey, setApiKey] = useState("");

  // Azure OpenAI settings
  const [azureEndpoint, setAzureEndpoint] = useState("");
  const [azureDeployment, setAzureDeployment] = useState("");
  const [azureApiKey, setAzureApiKey] = useState("");

  // Windows VM settings
  const [windowsSshHost, setWindowsSshHost] = useState("");
  const [windowsSshPort, setWindowsSshPort] = useState("22");
  const [windowsSshUser, setWindowsSshUser] = useState("lunar");
  const [windowsSshPassword, setWindowsSshPassword] = useState("");

  // Script reward
  const [scriptContent, setScriptContent] = useState("");

  // Screenshot match reward
  const [referenceImageUrl, setReferenceImageUrl] = useState("");
  const [screenshotThreshold, setScreenshotThreshold] = useState("0.9");

  // Advanced options
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [startUrl, setStartUrl] = useState("");
  const [resolution, setResolution] = useState("");
  const [maxSteps, setMaxSteps] = useState("");
  const [timeLimit, setTimeLimit] = useState("");

  // Submission state
  const [loading, setLoading] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Submit
  // ---------------------------------------------------------------------------

  async function handleLaunch() {
    setValidationError(null);
    setSubmitError(null);

    if (!instruction.trim()) {
      setValidationError("Instruction is required.");
      return;
    }
    if (instruction.trim().length < 10) {
      setValidationError("Instruction must be at least 10 characters.");
      return;
    }

    // Windows validation
    if (platform === "windows" && !windowsSshHost.trim()) {
      setValidationError("SSH Host is required for Windows platform.");
      return;
    }
    if (agentMode === "model" && modelProvider === "azure_openai") {
      if (!azureEndpoint.trim() || !azureDeployment.trim()) {
        setValidationError("Azure OpenAI endpoint and deployment are required.");
        return;
      }
    }

    setLoading(true);
    try {
      const response = await launchCUAEpisode({
        instruction: instruction.trim(),
        agent_mode: agentMode,
        reward_type: rewardType,
        platform,
        model_provider: agentMode === "model" ? modelProvider : undefined,
        api_key:
          agentMode === "model" && modelProvider === "anthropic" && apiKey.trim()
            ? apiKey.trim()
            : undefined,
        azure_openai_endpoint:
          agentMode === "model" && modelProvider === "azure_openai"
            ? azureEndpoint.trim() || undefined
            : undefined,
        azure_openai_deployment:
          agentMode === "model" && modelProvider === "azure_openai"
            ? azureDeployment.trim() || undefined
            : undefined,
        azure_openai_api_key:
          agentMode === "model" && modelProvider === "azure_openai" && azureApiKey.trim()
            ? azureApiKey.trim()
            : undefined,
        windows_ssh_host:
          platform === "windows" ? windowsSshHost.trim() || undefined : undefined,
        windows_ssh_port:
          platform === "windows" ? parseInt(windowsSshPort, 10) : undefined,
        windows_ssh_user:
          platform === "windows" ? windowsSshUser.trim() || undefined : undefined,
        windows_ssh_password:
          platform === "windows" && windowsSshPassword.trim()
            ? windowsSshPassword.trim()
            : undefined,
        script_content:
          rewardType === "script" ? scriptContent || undefined : undefined,
        reference_image_url:
          rewardType === "screenshot_match"
            ? referenceImageUrl.trim() || undefined
            : undefined,
        screenshot_threshold:
          rewardType === "screenshot_match"
            ? parseFloat(screenshotThreshold)
            : undefined,
        start_url: startUrl.trim() || undefined,
        resolution: resolution.trim() || undefined,
        max_steps: maxSteps ? parseInt(maxSteps, 10) : undefined,
        time_limit: timeLimit ? parseFloat(timeLimit) : undefined,
      });
      navigate(`/cua/live/${response.episode_id}`, {
        state: {
          vncUrl: response.vnc_url,
          rdpUrl: response.rdp_url,
          platform,
        },
      });
    } catch (e) {
      setSubmitError(
        e instanceof Error ? e.message : "Failed to launch CUA episode.",
      );
      setLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <Card className="gap-0 rounded-3xl bg-secondary text-secondary-foreground">
        <CardHeader className="gap-4">
          <Badge variant="default" className="w-fit">
            <Rocket className="size-3" />
            CUA Episode
          </Badge>
          <div className="space-y-1">
            <CardTitle className="text-3xl tracking-tight">
              Launch CUA Episode
            </CardTitle>
            <CardDescription className="text-base text-secondary-foreground">
              Configure a Computer-Using Agent task and start a desktop episode.
            </CardDescription>
          </div>
        </CardHeader>
      </Card>

      <Card className="gap-0 rounded-2xl">
        <CardHeader className="pb-4">
          <CardTitle className="text-base font-medium">Configuration</CardTitle>
          <CardDescription className="text-xs">
            The agent will execute inside a sandboxed desktop environment.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Instruction */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              Instruction
            </label>
            <textarea
              className="flex min-h-25 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-50"
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
            <label className="text-sm font-medium text-foreground">
              Agent Mode
            </label>
            <Select
              value={agentMode}
              onValueChange={(v) => setAgentMode(v as AgentMode)}
            >
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
              {agentMode === "model"
                ? "Claude will see the screen and interact autonomously."
                : "Sandbox stays alive for you to observe or interact via the live view."}
            </p>
          </div>

          {/* Platform */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              Platform
            </label>
            <Select
              value={platform}
              onValueChange={(v) => setPlatform(v as Platform)}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PLATFORMS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {platform === "windows"
                ? "Connects to a Windows VM via SSH. Watch live via RDP."
                : "Runs in a Docker container with noVNC live viewer."}
            </p>
          </div>

          {/* Windows VM settings */}
          {platform === "windows" && (
            <div className="space-y-4 rounded-lg border border-border p-4">
              <p className="text-sm font-medium text-foreground">
                Windows VM Connection
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5 col-span-2">
                  <label className="text-xs font-medium text-muted-foreground">
                    SSH Host
                  </label>
                  <Input
                    placeholder="e.g., 20.85.123.45"
                    value={windowsSshHost}
                    onChange={(e) => setWindowsSshHost(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    SSH Port
                  </label>
                  <Input
                    type="number"
                    placeholder="22"
                    value={windowsSshPort}
                    onChange={(e) => setWindowsSshPort(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Username
                  </label>
                  <Input
                    placeholder="lunar"
                    value={windowsSshUser}
                    onChange={(e) => setWindowsSshUser(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5 col-span-2">
                  <label className="text-xs font-medium text-muted-foreground">
                    Password
                  </label>
                  <Input
                    type="password"
                    placeholder="VM password"
                    value={windowsSshPassword}
                    onChange={(e) => setWindowsSshPassword(e.target.value)}
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                The Windows VM must have OpenSSH Server enabled and the CUA
                helper script installed.
              </p>
            </div>
          )}

          {/* Model Provider (model mode only) */}
          {agentMode === "model" && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                Model Provider
              </label>
              <Select
                value={modelProvider}
                onValueChange={(v) => setModelProvider(v as ModelProvider)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODEL_PROVIDERS.map((mp) => (
                    <SelectItem key={mp.value} value={mp.value}>
                      {mp.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Anthropic API Key */}
          {agentMode === "model" && modelProvider === "anthropic" && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                Anthropic API Key
              </label>
              <Input
                type="password"
                placeholder="sk-ant-..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Falls back to the server&apos;s ANTHROPIC_API_KEY environment variable if left blank.
              </p>
            </div>
          )}

          {/* Azure OpenAI settings */}
          {agentMode === "model" && modelProvider === "azure_openai" && (
            <div className="space-y-4 rounded-lg border border-border p-4">
              <p className="text-sm font-medium text-foreground">
                Azure OpenAI Configuration
              </p>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Endpoint
                  </label>
                  <Input
                    placeholder="https://my-resource.openai.azure.com"
                    value={azureEndpoint}
                    onChange={(e) => setAzureEndpoint(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Deployment Name
                  </label>
                  <Input
                    placeholder="computer-use-preview"
                    value={azureDeployment}
                    onChange={(e) => setAzureDeployment(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    API Key
                  </label>
                  <Input
                    type="password"
                    placeholder="Azure OpenAI API key"
                    value={azureApiKey}
                    onChange={(e) => setAzureApiKey(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Falls back to the server&apos;s AZURE_OPENAI_API_KEY environment variable if left blank.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Reward type */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              Reward Type
            </label>
            <Select
              value={rewardType}
              onValueChange={(v) => setRewardType(v as RewardType)}
            >
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
          {rewardType === "script" && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                Validation Script
              </label>
              <p className="text-xs text-muted-foreground">
                A bash script that exits 0 on success, non-zero on failure. Exit
                code becomes the score.
              </p>
              <div className="rounded-xl overflow-hidden bg-muted">
                <Editor
                  height="200px"
                  language="bash"
                  theme="vs-dark"
                  value={scriptContent}
                  onChange={(v) => setScriptContent(v ?? "")}
                  options={{
                    minimap: { enabled: false },
                    fontSize: 13,
                    lineNumbers: "on",
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                  }}
                />
              </div>
            </div>
          )}

          {/* Screenshot match fields */}
          {rewardType === "screenshot_match" && (
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  Reference Image URL
                </label>
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
                  className={`size-4 transition-transform ${advancedOpen ? "rotate-180" : ""}`}
                />
                Advanced Options
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-4 pt-4">
              {/* Start URL */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  Start URL
                </label>
                <Input
                  type="url"
                  placeholder="https://example.com"
                  value={startUrl}
                  onChange={(e) => setStartUrl(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  If set, Chromium is pre-loaded to this URL before the episode
                  starts.
                </p>
              </div>

              {/* Resolution */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  Resolution
                </label>
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
                <label className="text-sm font-medium text-foreground">
                  Max Steps
                </label>
                <Input
                  type="number"
                  placeholder="1000"
                  value={maxSteps}
                  onChange={(e) => setMaxSteps(e.target.value)}
                  min={1}
                />
                <p className="text-xs text-muted-foreground">
                  Maximum number of agent actions. Leave blank for default
                  (1000).
                </p>
              </div>

              {/* Time Limit */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  Time Limit (seconds)
                </label>
                <Input
                  type="number"
                  placeholder="300"
                  value={timeLimit}
                  onChange={(e) => setTimeLimit(e.target.value)}
                  min={1}
                />
                <p className="text-xs text-muted-foreground">
                  Episode wall-clock timeout in seconds. Leave blank for default
                  (300).
                </p>
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* Submit error */}
          {submitError && (
            <p className="text-sm text-destructive">{submitError}</p>
          )}

          {/* Launch button */}
          <Button className="w-full" onClick={handleLaunch} disabled={loading}>
            {loading ? (
              "Launching..."
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
  );
}

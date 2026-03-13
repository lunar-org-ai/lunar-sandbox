import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router'
import { ChevronDown, Play, ChevronsUpDown, Check } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandItem,
} from '@/components/ui/command'
import { Skeleton } from '@/components/ui/skeleton'

import { fetchTasks, launchRun, type TaskSummary } from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseEnvVars(raw: string): Record<string, string> | undefined {
  const lines = raw.split('\n').map((l) => l.trim()).filter(Boolean)
  if (lines.length === 0) return undefined
  const result: Record<string, string> = {}
  for (const line of lines) {
    const eqIdx = line.indexOf('=')
    if (eqIdx === -1) continue
    const key = line.slice(0, eqIdx).trim()
    const val = line.slice(eqIdx + 1).trim()
    if (key) result[key] = val
  }
  return Object.keys(result).length > 0 ? result : undefined
}

// ---------------------------------------------------------------------------
// Launcher page
// ---------------------------------------------------------------------------

export default function Launcher() {
  const navigate = useNavigate()

  // Task combobox state
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [tasksError, setTasksError] = useState<string | null>(null)
  const [comboOpen, setComboOpen] = useState(false)
  const [selectedTask, setSelectedTask] = useState<string>('')

  // Core params
  const [model, setModel] = useState('')
  const [parallelism, setParallelism] = useState('1')

  // Advanced params
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [timeout, setTimeout_] = useState('')
  const [envVarsRaw, setEnvVarsRaw] = useState('')

  // Submission state
  const [loading, setLoading] = useState(false)
  const [taskError, setTaskError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Fetch tasks on mount
  useEffect(() => {
    fetchTasks({ limit: 200 })
      .then((data) => {
        setTasks(data.items)
        setTasksLoading(false)
      })
      .catch((e: Error) => {
        setTasksError(e.message)
        setTasksLoading(false)
      })
  }, [])

  const selectedTaskObj = tasks.find((t) => t.name === selectedTask)

  async function handleRun() {
    setTaskError(null)
    setSubmitError(null)

    if (!selectedTask) {
      setTaskError('Please select a task before running.')
      return
    }

    setLoading(true)
    try {
      const response = await launchRun({
        task_name: selectedTask,
        model: model.trim() || undefined,
        parallelism: parseInt(parallelism, 10),
        timeout: timeout ? parseInt(timeout, 10) : undefined,
        env_vars: parseEnvVars(envVarsRaw),
      })
      navigate(`/runs/${response.episode_id}`)
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Failed to launch run.')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Launch Experiment</h1>
        <p className="text-neutral-400 mt-2 text-sm">
          Select a task, configure parameters, and start an evaluation run.
        </p>
      </div>

      <div className="space-y-6">
        {/* Task selector */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-neutral-200">Task</label>

          {tasksLoading ? (
            <Skeleton className="h-9 w-full" />
          ) : tasksError ? (
            <p className="text-sm text-red-400">Failed to load tasks: {tasksError}</p>
          ) : (
            <Popover open={comboOpen} onOpenChange={setComboOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={comboOpen}
                  className="w-full justify-between font-normal"
                >
                  {selectedTaskObj ? (
                    <span className="font-mono text-sm">{selectedTaskObj.name}</span>
                  ) : (
                    <span className="text-muted-foreground">Select a task...</span>
                  )}
                  <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                <Command>
                  <CommandInput placeholder="Search tasks..." />
                  <CommandList>
                    <CommandEmpty>No tasks found.</CommandEmpty>
                    {tasks.map((task) => (
                      <CommandItem
                        key={task.name}
                        value={task.name}
                        onSelect={(value) => {
                          setSelectedTask(value === selectedTask ? '' : value)
                          setComboOpen(false)
                        }}
                      >
                        <Check
                          className={
                            selectedTask === task.name
                              ? 'opacity-100 size-4 shrink-0'
                              : 'opacity-0 size-4 shrink-0'
                          }
                        />
                        <div className="flex flex-col min-w-0">
                          <span className="font-mono text-sm">{task.name}</span>
                          {task.instructions && (
                            <span className="text-xs text-neutral-400 truncate">
                              {task.instructions}
                            </span>
                          )}
                        </div>
                      </CommandItem>
                    ))}
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          )}

          {taskError && (
            <p className="text-sm text-red-400">{taskError}</p>
          )}
        </div>

        {/* Model */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-neutral-200">Model</label>
          <Input
            type="text"
            placeholder="e.g., gpt-4o, claude-sonnet-4-20250514"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
          <p className="text-xs text-neutral-500">
            Leave blank to use the backend default model.
          </p>
        </div>

        {/* Parallelism */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-neutral-200">Parallelism</label>
          <Select value={parallelism} onValueChange={setParallelism}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {['1', '2', '4', '8', '16'].map((n) => (
                <SelectItem key={n} value={n}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-neutral-500">
            Number of parallel sandbox executions.
          </p>
        </div>

        {/* Advanced options */}
        <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="flex items-center gap-1 px-0 text-sm text-neutral-400 hover:text-neutral-200">
              <ChevronDown
                className={`size-4 transition-transform ${advancedOpen ? 'rotate-180' : ''}`}
              />
              Advanced Options
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-4 pt-4">
            {/* Timeout */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-neutral-200">
                Timeout (seconds)
              </label>
              <Input
                type="number"
                placeholder="1800"
                value={timeout}
                onChange={(e) => setTimeout_(e.target.value)}
                min={1}
              />
            </div>

            {/* Env vars */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-neutral-200">
                Environment Variables
              </label>
              <textarea
                className="flex min-h-[100px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-50"
                placeholder={'KEY=VALUE\nANOTHER_KEY=another_value'}
                value={envVarsRaw}
                onChange={(e) => setEnvVarsRaw(e.target.value)}
              />
              <p className="text-xs text-neutral-500">
                One KEY=VALUE pair per line.
              </p>
            </div>
          </CollapsibleContent>
        </Collapsible>

        {/* Submit error */}
        {submitError && (
          <p className="text-sm text-red-400">{submitError}</p>
        )}

        {/* Run button */}
        <Button
          className="w-full"
          onClick={handleRun}
          disabled={loading || tasksLoading}
        >
          {loading ? (
            'Launching...'
          ) : (
            <>
              <Play className="size-4 mr-2" />
              Run
            </>
          )}
        </Button>
      </div>
    </div>
  )
}

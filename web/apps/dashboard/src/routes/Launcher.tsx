import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { AlertCircle, ChevronDown, Play, ChevronsUpDown, Check, Plus } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import { Textarea } from '@/components/ui/textarea'

import { fetchTasks, createTask, launchRun, type TaskSummary } from '@/lib/api'

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
  const [cpuCores, setCpuCores] = useState('')
  const [memoryMb, setMemoryMb] = useState('')
  const [timeout, setTimeout_] = useState('')
  const [envVarsRaw, setEnvVarsRaw] = useState('')

  // New task form
  const [showNewTask, setShowNewTask] = useState(false)
  const [newTaskName, setNewTaskName] = useState('')
  const [newTaskInstructions, setNewTaskInstructions] = useState('')
  const [newTaskTestCommand, setNewTaskTestCommand] = useState('')
  const [newTaskSaving, setNewTaskSaving] = useState(false)
  const [newTaskError, setNewTaskError] = useState<string | null>(null)

  // Submission state
  const [loading, setLoading] = useState(false)
  const [taskError, setTaskError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const loadTasks = useCallback(() => {
    setTasksLoading(true)
    fetchTasks({ limit: 100 })
      .then((data) => {
        setTasks(data.items)
        setTasksLoading(false)
      })
      .catch((e: Error) => {
        setTasksError(e.message)
        setTasksLoading(false)
      })
  }, [])

  // Fetch tasks on mount
  useEffect(() => {
    loadTasks()
  }, [loadTasks])

  async function handleCreateTask() {
    if (!newTaskName.trim()) {
      setNewTaskError('Task name is required.')
      return
    }
    setNewTaskSaving(true)
    setNewTaskError(null)
    try {
      await createTask({
        name: newTaskName.trim(),
        instructions: newTaskInstructions.trim() || undefined,
        test_command: newTaskTestCommand.trim() || undefined,
      })
      setNewTaskName('')
      setNewTaskInstructions('')
      setNewTaskTestCommand('')
      setShowNewTask(false)
      loadTasks()
    } catch (e) {
      setNewTaskError(e instanceof Error ? e.message : 'Failed to create task.')
    } finally {
      setNewTaskSaving(false)
    }
  }

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
        cpu_cores: cpuCores ? parseInt(cpuCores, 10) : undefined,
        memory_mb: memoryMb ? parseInt(memoryMb, 10) : undefined,
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
        <h1 className="text-2xl font-semibold tracking-tight">Launch Experiment</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Select a task, configure parameters, and start an evaluation run.
        </p>
      </div>

      <Card className="border-border/50 bg-card/50 backdrop-blur-sm">
        <CardHeader className="pb-4">
          <CardTitle className="text-base font-medium">Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Task selector */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Task</label>

            {tasksLoading ? (
              <Skeleton className="h-9 w-full" />
            ) : tasksError ? (
              <p className="text-sm text-destructive">Failed to load tasks: {tasksError}</p>
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
                              <span className="text-xs text-muted-foreground truncate">
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

            {!tasksLoading && !tasksError && !showNewTask && (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground"
                onClick={() => setShowNewTask(true)}
              >
                <Plus className="size-3 mr-1" />
                New Task
              </Button>
            )}

            {showNewTask && (
              <div className="space-y-3 rounded-md border border-border p-4">
                <div className="space-y-1">
                  <label className="text-xs font-medium">Name</label>
                  <Input
                    placeholder="e.g., my-eval-task"
                    value={newTaskName}
                    onChange={(e) => setNewTaskName(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium">Instructions</label>
                  <Input
                    placeholder="What should the agent do?"
                    value={newTaskInstructions}
                    onChange={(e) => setNewTaskInstructions(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium">Test Command</label>
                  <Input
                    placeholder="e.g., pytest tests/"
                    value={newTaskTestCommand}
                    onChange={(e) => setNewTaskTestCommand(e.target.value)}
                  />
                </div>
                {newTaskError && (
                  <p className="text-xs text-destructive">{newTaskError}</p>
                )}
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleCreateTask} disabled={newTaskSaving}>
                    {newTaskSaving ? 'Saving...' : 'Create'}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setShowNewTask(false)
                      setNewTaskError(null)
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {taskError && (
              <p className="text-sm text-destructive">{taskError}</p>
            )}
          </div>

          {/* Model */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Model</label>
            <Input
              type="text"
              placeholder="e.g., gpt-4o, claude-sonnet-4-20250514"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Leave blank to use the backend default model.
            </p>
          </div>

          {/* Parallelism */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Parallelism</label>
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
            <p className="text-xs text-muted-foreground">
              Number of parallel sandbox executions.
            </p>
          </div>

          {/* Advanced options */}
          <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="flex items-center gap-1 px-0 text-sm text-muted-foreground hover:text-foreground">
                <ChevronDown
                  className={`size-4 transition-transform ${advancedOpen ? 'rotate-180' : ''}`}
                />
                Advanced Options
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-4 pt-4">
              {/* CPU Cores */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  CPU Cores
                </label>
                <Input
                  type="number"
                  placeholder="e.g., 2"
                  value={cpuCores}
                  onChange={(e) => setCpuCores(e.target.value)}
                  min={1}
                />
                <p className="text-xs text-muted-foreground">
                  Number of CPU cores per sandbox. Leave blank for engine default.
                </p>
              </div>

              {/* Memory (MB) */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
                  Memory (MB)
                </label>
                <Input
                  type="number"
                  placeholder="e.g., 1024"
                  value={memoryMb}
                  onChange={(e) => setMemoryMb(e.target.value)}
                  min={64}
                  step={64}
                />
                <p className="text-xs text-muted-foreground">
                  Memory limit in megabytes per sandbox. Leave blank for engine default.
                </p>
              </div>

              {/* Timeout */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">
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
                <label className="text-sm font-medium text-foreground">
                  Environment Variables
                </label>
                <Textarea
                  className="min-h-[100px]"
                  placeholder={'KEY=VALUE\nANOTHER_KEY=another_value'}
                  value={envVarsRaw}
                  onChange={(e) => setEnvVarsRaw(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  One KEY=VALUE pair per line.
                </p>
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* Submit error */}
          {submitError && (
            <Alert variant="destructive">
              <AlertCircle className="size-4" />
              <AlertDescription>{submitError}</AlertDescription>
            </Alert>
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
        </CardContent>
      </Card>
    </div>
  )
}

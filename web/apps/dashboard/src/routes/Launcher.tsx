import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router";
import { AlertCircle, ChevronDown, Play, Plus, Rocket } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
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
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldSet,
} from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

import { fetchTasks, createTask, launchRun, type TaskSummary } from "@/lib/api";

function parseEnvVars(raw: string): Record<string, string> | undefined {
  const lines = raw
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) return undefined;
  const result: Record<string, string> = {};
  for (const line of lines) {
    const eqIdx = line.indexOf("=");
    if (eqIdx === -1) continue;
    const key = line.slice(0, eqIdx).trim();
    const val = line.slice(eqIdx + 1).trim();
    if (key) result[key] = val;
  }
  return Object.keys(result).length > 0 ? result : undefined;
}

export default function Launcher() {
  const navigate = useNavigate();

  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [tasksLoading, setTasksLoading] = useState(true);
  const [tasksError, setTasksError] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<string>("");

  const [model, setModel] = useState("");
  const [parallelism, setParallelism] = useState("1");

  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [cpuCores, setCpuCores] = useState("");
  const [memoryMb, setMemoryMb] = useState("");
  const [timeout, setTimeout_] = useState("");
  const [envVarsRaw, setEnvVarsRaw] = useState("");

  const [showNewTask, setShowNewTask] = useState(false);
  const [newTaskName, setNewTaskName] = useState("");
  const [newTaskInstructions, setNewTaskInstructions] = useState("");
  const [newTaskTestCommand, setNewTaskTestCommand] = useState("");
  const [newTaskSaving, setNewTaskSaving] = useState(false);
  const [newTaskError, setNewTaskError] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const loadTasks = useCallback(() => {
    setTasksLoading(true);
    fetchTasks({ limit: 100 })
      .then((data) => {
        setTasks(data.items);
        setTasksLoading(false);
      })
      .catch((e: Error) => {
        setTasksError(e.message);
        setTasksLoading(false);
      });
  }, []);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  async function handleCreateTask() {
    if (!newTaskName.trim()) {
      setNewTaskError("Task name is required.");
      return;
    }
    setNewTaskSaving(true);
    setNewTaskError(null);
    try {
      await createTask({
        name: newTaskName.trim(),
        instructions: newTaskInstructions.trim() || undefined,
        test_command: newTaskTestCommand.trim() || undefined,
      });
      setNewTaskName("");
      setNewTaskInstructions("");
      setNewTaskTestCommand("");
      setShowNewTask(false);
      loadTasks();
    } catch (e) {
      setNewTaskError(
        e instanceof Error ? e.message : "Failed to create task.",
      );
    } finally {
      setNewTaskSaving(false);
    }
  }

  const selectedTaskObj = useMemo(
    () => tasks.find((task) => task.name === selectedTask) ?? null,
    [tasks, selectedTask],
  );

  async function handleRun() {
    setTaskError(null);
    setSubmitError(null);

    if (!selectedTask) {
      setTaskError("Please select a task before running.");
      return;
    }

    setLoading(true);
    try {
      const response = await launchRun({
        task_name: selectedTask,
        model: model.trim() || undefined,
        parallelism: parseInt(parallelism, 10),
        timeout: timeout ? parseInt(timeout, 10) : undefined,
        env_vars: parseEnvVars(envVarsRaw),
        cpu_cores: cpuCores ? parseInt(cpuCores, 10) : undefined,
        memory_mb: memoryMb ? parseInt(memoryMb, 10) : undefined,
      });
      navigate(`/runs/${response.episode_id}`);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Failed to launch run.");
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 p-6">
      <Card className="gap-0 rounded-3xl bg-secondary text-secondary-foreground">
        <CardHeader className="gap-4">
          <Badge variant="default" className="w-fit">
            <Rocket className="size-3" />
            Experiment
          </Badge>
          <div className="space-y-1">
            <CardTitle className="text-3xl tracking-tight">
              Launch Experiment
            </CardTitle>
            <CardDescription className="text-base text-secondary-foreground">
              Choose a task, configure execution options, and start a run.
            </CardDescription>
          </div>
        </CardHeader>
      </Card>

      <Card className="gap-0 rounded-2xl">
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Run Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <FieldSet>
            <FieldGroup>
              <Field data-invalid={Boolean(taskError)}>
                <FieldLabel>Task</FieldLabel>
                {tasksLoading ? (
                  <Skeleton className="h-9 w-full" />
                ) : tasksError ? (
                  <FieldError>Failed to load tasks: {tasksError}</FieldError>
                ) : (
                  <Combobox
                    items={tasks}
                    value={selectedTaskObj}
                    onValueChange={(value) =>
                      setSelectedTask(value?.name ?? "")
                    }
                    itemToStringValue={(item) => item.name}
                  >
                    <ComboboxInput placeholder="Select a task" showClear />
                    <ComboboxContent>
                      <ComboboxEmpty>No tasks found.</ComboboxEmpty>
                      <ComboboxList>
                        {(task) => (
                          <ComboboxItem key={task.name} value={task}>
                            <div className="flex min-w-0 flex-col">
                              <span className="font-mono text-sm">
                                {task.name}
                              </span>
                              {task.instructions && (
                                <span className="truncate text-xs text-muted-foreground">
                                  {task.instructions}
                                </span>
                              )}
                            </div>
                          </ComboboxItem>
                        )}
                      </ComboboxList>
                    </ComboboxContent>
                  </Combobox>
                )}
                <FieldDescription>Select the task to execute.</FieldDescription>
                <FieldError>{taskError ?? undefined}</FieldError>
              </Field>

              {!tasksLoading && !tasksError && !showNewTask && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowNewTask(true)}
                >
                  <Plus className="size-4" />
                  New Task
                </Button>
              )}

              {showNewTask && (
                <Card className="gap-0 rounded-2xl">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm">Create Task</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <FieldGroup>
                      <Field
                        data-invalid={Boolean(
                          newTaskError && !newTaskName.trim(),
                        )}
                      >
                        <FieldLabel htmlFor="new-task-name">Name</FieldLabel>
                        <Input
                          id="new-task-name"
                          placeholder="my-eval-task"
                          value={newTaskName}
                          onChange={(e) => setNewTaskName(e.target.value)}
                        />
                      </Field>
                      <Field>
                        <FieldLabel htmlFor="new-task-instructions">
                          Instructions
                        </FieldLabel>
                        <Input
                          id="new-task-instructions"
                          placeholder="What should the agent do?"
                          value={newTaskInstructions}
                          onChange={(e) =>
                            setNewTaskInstructions(e.target.value)
                          }
                        />
                      </Field>
                      <Field>
                        <FieldLabel htmlFor="new-task-test-command">
                          Test Command
                        </FieldLabel>
                        <Input
                          id="new-task-test-command"
                          placeholder="pytest tests/"
                          value={newTaskTestCommand}
                          onChange={(e) =>
                            setNewTaskTestCommand(e.target.value)
                          }
                        />
                      </Field>
                      <FieldError>{newTaskError ?? undefined}</FieldError>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={handleCreateTask}
                          disabled={newTaskSaving}
                        >
                          {newTaskSaving ? "Saving..." : "Create"}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setShowNewTask(false);
                            setNewTaskError(null);
                          }}
                        >
                          Cancel
                        </Button>
                      </div>
                    </FieldGroup>
                  </CardContent>
                </Card>
              )}

              <Field>
                <FieldLabel htmlFor="model">Model</FieldLabel>
                <Input
                  id="model"
                  type="text"
                  placeholder="gpt-4o"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                />
                <FieldDescription>
                  Leave empty to use the backend default model.
                </FieldDescription>
              </Field>

              <Field>
                <FieldLabel htmlFor="parallelism">Parallelism</FieldLabel>
                <Select value={parallelism} onValueChange={setParallelism}>
                  <SelectTrigger id="parallelism" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["1", "2", "4", "8", "16"].map((n) => (
                      <SelectItem key={n} value={n}>
                        {n}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldDescription>
                  Number of sandbox executions running in parallel.
                </FieldDescription>
              </Field>
            </FieldGroup>
          </FieldSet>

          <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm">
                <ChevronDown
                  className={`size-4 transition-transform ${advancedOpen ? "rotate-180" : ""}`}
                />
                Advanced Options
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-4 pt-4">
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="cpu-cores">CPU Cores</FieldLabel>
                  <Input
                    id="cpu-cores"
                    type="number"
                    placeholder="2"
                    value={cpuCores}
                    onChange={(e) => setCpuCores(e.target.value)}
                    min={1}
                  />
                  <FieldDescription>
                    CPU cores per sandbox. Leave empty for default.
                  </FieldDescription>
                </Field>

                <Field>
                  <FieldLabel htmlFor="memory-mb">Memory (MB)</FieldLabel>
                  <Input
                    id="memory-mb"
                    type="number"
                    placeholder="1024"
                    value={memoryMb}
                    onChange={(e) => setMemoryMb(e.target.value)}
                    min={64}
                    step={64}
                  />
                  <FieldDescription>
                    Memory limit per sandbox in megabytes.
                  </FieldDescription>
                </Field>

                <Field>
                  <FieldLabel htmlFor="timeout">Timeout (seconds)</FieldLabel>
                  <Input
                    id="timeout"
                    type="number"
                    placeholder="1800"
                    value={timeout}
                    onChange={(e) => setTimeout_(e.target.value)}
                    min={1}
                  />
                </Field>

                <Field>
                  <FieldLabel htmlFor="env-vars">
                    Environment Variables
                  </FieldLabel>
                  <Textarea
                    id="env-vars"
                    className="min-h-24"
                    placeholder={"KEY=VALUE\nANOTHER_KEY=another_value"}
                    value={envVarsRaw}
                    onChange={(e) => setEnvVarsRaw(e.target.value)}
                  />
                  <FieldDescription>
                    Use one KEY=VALUE pair per line.
                  </FieldDescription>
                </Field>
              </FieldGroup>
            </CollapsibleContent>
          </Collapsible>

          {submitError && (
            <Alert variant="destructive" className="border-0">
              <AlertCircle className="size-4" />
              <AlertDescription>{submitError}</AlertDescription>
            </Alert>
          )}

          <Button
            className="w-full"
            onClick={handleRun}
            disabled={loading || tasksLoading}
          >
            {loading ? (
              "Launching..."
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
  );
}

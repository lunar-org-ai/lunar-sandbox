"""High-level Session API -- sandbox + tracing + AI agent integration.

Designed to make plugging in AI agents trivially easy while
auto-tracing every action to the dashboard in real-time.

Quick start with OpenAI::

    from openai import OpenAI
    from lunar_sandbox import Session, openai_adapter

    client = OpenAI()

    with Session("fix-bug") as s:
        s.agent_loop(
            task="Fix the failing tests in main.py",
            call_llm=openai_adapter(client, model="gpt-4o"),
        )
        # score is auto-detected from test results, or set manually:
        # s.finish(score=1.0)

Quick start with Anthropic::

    from anthropic import Anthropic
    from lunar_sandbox import Session, anthropic_adapter

    client = Anthropic()

    with Session("fix-bug") as s:
        s.agent_loop(
            task="Fix the failing tests",
            call_llm=anthropic_adapter(client, model="claude-sonnet-4-20250514"),
        )

Manual tool loop (any provider)::

    with Session("fix-bug") as s:
        tools = s.tools(format="openai")  # or "anthropic" or "raw"
        # ... your custom loop ...
        result = s.call_tool("run_command", {"command": "pytest"})
        s.finish(score=1.0)

Direct sandbox access (no agent)::

    with Session("setup-env") as s:
        s.run("pip install -q numpy pandas")
        s.write_file("data.csv", csv_content)
        output = s.run("python analyze.py")
        s.finish(score=1.0)
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import structlog

from lunar_sandbox.sandbox.docker_config import DockerResourceLimits, DockerSandboxConfig
from lunar_sandbox.sandbox.docker_sandbox import DockerSandbox
from lunar_sandbox.trajectory.store import TrajectoryStore

__all__ = [
    "Session",
    "openai_adapter",
    "anthropic_adapter",
]

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (provider-agnostic)
# ---------------------------------------------------------------------------

_TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "run_command",
        "description": "Execute a shell command in the sandbox. Use for running tests, installing packages, or any terminal command.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute (e.g. 'pytest', 'ls -la', 'pip install numpy').",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file in the sandbox workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to /workspace (e.g. 'main.py', 'src/utils.py').",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file in the sandbox workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to /workspace (e.g. 'main.py', 'src/utils.py').",
                },
                "content": {
                    "type": "string",
                    "description": "The full file content to write.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and directories in a sandbox directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to /workspace (default: '.').",
                    "default": ".",
                },
            },
        },
    },
]


def _tools_openai() -> list[dict[str, Any]]:
    """Return tool definitions in OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in _TOOL_DEFS
    ]


def _tools_anthropic() -> list[dict[str, Any]]:
    """Return tool definitions in Anthropic tool-use format."""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in _TOOL_DEFS
    ]


# ---------------------------------------------------------------------------
# Provider adapters
# ---------------------------------------------------------------------------

# Type for the call_llm callback:
#   call_llm(messages, tools) -> AgentResponse dict
#
# AgentResponse:
#   {
#     "content": str,                    # text response (may be empty)
#     "tool_calls": [                    # list of tool calls (may be empty)
#       {"id": str, "name": str, "arguments": dict}
#     ],
#     "stop": bool,                      # True if agent is done
#     "usage": {"total_tokens": int} | None,  # optional usage stats
#     "cost_usd": float | None,          # optional cost
#   }
CallLLM = Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]


def openai_adapter(
    client: Any,
    model: str = "gpt-4o",
    **kwargs: Any,
) -> CallLLM:
    """Wrap an OpenAI client into a ``call_llm`` callback.

    Args:
        client: An ``openai.OpenAI()`` instance.
        model: Model name (default: gpt-4o).
        **kwargs: Extra kwargs passed to ``client.chat.completions.create()``.

    Returns:
        A ``call_llm(messages, tools) -> dict`` function.

    Example::

        from openai import OpenAI
        llm = openai_adapter(OpenAI(), model="gpt-4o")
    """
    def call_llm(
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            **kwargs,
        }
        if tools:
            create_kwargs["tools"] = tools

        response = client.chat.completions.create(**create_kwargs)
        choice = response.choices[0]
        msg = choice.message

        tool_calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": args,
            })

        usage = None
        if response.usage:
            usage = {"total_tokens": response.usage.total_tokens}

        return {
            "content": msg.content or "",
            "tool_calls": tool_calls,
            "stop": choice.finish_reason == "stop",
            "usage": usage,
        }

    return call_llm


def anthropic_adapter(
    client: Any,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    **kwargs: Any,
) -> CallLLM:
    """Wrap an Anthropic client into a ``call_llm`` callback.

    Args:
        client: An ``anthropic.Anthropic()`` instance.
        model: Model name (default: claude-sonnet-4-20250514).
        max_tokens: Max tokens for response.
        **kwargs: Extra kwargs passed to ``client.messages.create()``.

    Returns:
        A ``call_llm(messages, tools) -> dict`` function.

    Example::

        from anthropic import Anthropic
        llm = anthropic_adapter(Anthropic(), model="claude-sonnet-4-20250514")
    """
    def call_llm(
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        # Anthropic separates system from messages
        system_text = ""
        api_messages = []
        for m in messages:
            if m["role"] == "system":
                system_text = m["content"]
            else:
                api_messages.append(m)

        create_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": api_messages,
            **kwargs,
        }
        if system_text:
            create_kwargs["system"] = system_text
        if tools:
            create_kwargs["tools"] = tools

        response = client.messages.create(**create_kwargs)

        content_text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })

        usage = None
        if response.usage:
            usage = {
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }

        return {
            "content": content_text,
            "tool_calls": tool_calls,
            "stop": response.stop_reason == "end_turn",
            "usage": usage,
        }

    return call_llm


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class Session:
    """Unified interface: sandbox + tracing + AI agent integration.

    Every operation is automatically recorded as a trace step
    visible in the dashboard in real-time.
    """

    __slots__ = (
        "_task_name",
        "_sandbox_id",
        "_episode_id",
        "_sandbox",
        "_store",
        "_steps",
        "_step_idx",
        "_started_at",
        "_source",
        "_dashboard_port",
        "_finished",
        "_log",
    )

    def __init__(
        self,
        task_name: str = "interactive",
        image: str = "python:3.12-slim",
        *,
        sandbox_id: str | None = None,
        episode_id: str | None = None,
        db_path: str | Path = "trajectories/trajectories.db",
        network: bool = True,
        cpus: float = 1.0,
        memory_mb: int = 512,
        env: dict[str, str] | None = None,
        source: str = "session",
        dashboard_port: int = 3000,
    ) -> None:
        self._task_name = task_name
        self._sandbox_id = sandbox_id or f"session-{uuid4().hex[:12]}"
        self._episode_id = episode_id or f"ep-{uuid4().hex[:12]}"
        self._source = source
        self._dashboard_port = dashboard_port
        self._finished = False

        self._steps: list[dict[str, Any]] = []
        self._step_idx = 0
        self._started_at = time.time()

        self._log = log.bind(
            session_sandbox=self._sandbox_id,
            session_episode=self._episode_id,
        )

        # --- Open trajectory store ---
        db = Path(db_path)
        self._store = TrajectoryStore(db)
        self._store.open()

        # --- Register initial episode (running) ---
        self._sync_episode(outcome="running", is_complete=0)

        # --- Create sandbox ---
        config = DockerSandboxConfig(
            sandbox_id=self._sandbox_id,
            image=image,
            resource_limits=DockerResourceLimits(
                cpus=cpus,
                memory_bytes=memory_mb * 1024 * 1024,
            ),
            network_enabled=network,
            extra_env=env or {},
        )
        self._sandbox = DockerSandbox(config)
        self._sandbox.create()

        self._log.info(
            "session_started",
            task=task_name,
            image=image,
            url=self.dashboard_url,
        )
        print(f"Session started: {self.dashboard_url}")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def episode_id(self) -> str:
        return self._episode_id

    @property
    def sandbox_id(self) -> str:
        return self._sandbox_id

    @property
    def dashboard_url(self) -> str:
        """URL to view this episode in the dashboard."""
        return f"http://localhost:{self._dashboard_port}/runs/{self._episode_id}"

    @property
    def sandbox(self) -> DockerSandbox:
        """Access the underlying DockerSandbox for advanced usage."""
        return self._sandbox

    @property
    def store(self) -> TrajectoryStore:
        """Access the underlying TrajectoryStore for queries/exports."""
        return self._store

    @property
    def step_count(self) -> int:
        return self._step_idx

    # ------------------------------------------------------------------
    # Tool definitions for AI agents
    # ------------------------------------------------------------------

    def tools(self, format: str = "openai") -> list[dict[str, Any]]:
        """Get tool definitions for your AI agent.

        Args:
            format: "openai", "anthropic", or "raw".

        Returns:
            List of tool definition dicts in the requested format.

        Example::

            tools = s.tools(format="openai")
            response = client.chat.completions.create(
                model="gpt-4o", messages=messages, tools=tools,
            )
        """
        if format == "openai":
            return _tools_openai()
        elif format == "anthropic":
            return _tools_anthropic()
        else:
            return [dict(t) for t in _TOOL_DEFS]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool call and record it as a trace step.

        This is the bridge between your AI agent's tool calls and
        the sandbox. Call this for each tool_call in the LLM response.

        Args:
            name: Tool name ("run_command", "read_file", "write_file", "list_files").
            arguments: Tool arguments dict.

        Returns:
            Tool result as string.

        Example::

            for tc in response.tool_calls:
                result = s.call_tool(tc.name, tc.arguments)
        """
        if name == "run_command":
            return self.run(arguments["command"])
        elif name == "read_file":
            return self.read_file(arguments["path"])
        elif name == "write_file":
            self.write_file(arguments["path"], arguments["content"])
            return f"File written: {arguments['path']}"
        elif name == "list_files":
            files = self.list_files(arguments.get("path", "."))
            return "\n".join(files)
        else:
            raise ValueError(f"Unknown tool: {name}")

    # ------------------------------------------------------------------
    # Agent loop
    # ------------------------------------------------------------------

    def agent_loop(
        self,
        task: str,
        call_llm: CallLLM,
        *,
        system: str | None = None,
        max_steps: int = 50,
        format: str = "openai",
        on_step: Callable[[int, dict[str, Any]], None] | None = None,
    ) -> str:
        """Run a complete agent loop with automatic tool execution and tracing.

        The agent will use sandbox tools (run_command, read_file, write_file,
        list_files) to complete the task. Every action is traced to the dashboard.

        Args:
            task: Task description for the agent.
            call_llm: LLM callback function. Use ``openai_adapter()`` or
                ``anthropic_adapter()`` to create one from your client.
            system: Optional system prompt (default: a coding agent prompt).
            max_steps: Maximum tool-call steps before stopping (default: 50).
            format: Message format — "openai" or "anthropic" (must match your adapter).
            on_step: Optional callback called after each step with (step_idx, response_dict).

        Returns:
            The agent's final text response.

        Example (OpenAI)::

            from openai import OpenAI
            from lunar_sandbox import Session, openai_adapter

            with Session("fix-bug") as s:
                answer = s.agent_loop(
                    task="Fix the failing tests in main.py",
                    call_llm=openai_adapter(OpenAI(), model="gpt-4o"),
                )

        Example (Anthropic)::

            from anthropic import Anthropic
            from lunar_sandbox import Session, anthropic_adapter

            with Session("fix-bug") as s:
                answer = s.agent_loop(
                    task="Fix the failing tests",
                    call_llm=anthropic_adapter(Anthropic()),
                    format="anthropic",
                )
        """
        if system is None:
            system = (
                "You are a skilled software engineer working in a sandbox environment. "
                "You have tools to run commands, read files, write files, and list directory contents. "
                "The workspace is at /workspace. "
                "Solve the task step by step. When done, respond with your final answer."
            )

        tools = self.tools(format=format)
        is_anthropic = format == "anthropic"

        if is_anthropic:
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system},
                {"role": "user", "content": task},
            ]
        else:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": task},
            ]

        final_content = ""
        steps_taken = 0

        while steps_taken < max_steps:
            response = call_llm(messages, tools)

            content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])
            is_stop = response.get("stop", False)
            usage = response.get("usage")

            # Record LLM call as a trace step
            token_count = usage.get("total_tokens") if usage else None
            cost = response.get("cost_usd")
            self.record_step(
                action="llm_call",
                params={"model": "llm", "step": steps_taken},
                result=content[:2000] if content else f"[{len(tool_calls)} tool call(s)]",
                token_usage=token_count,
                cost_usd=cost,
            )

            if on_step:
                on_step(steps_taken, response)

            if is_stop or not tool_calls:
                final_content = content
                break

            if is_anthropic:
                # Anthropic message format: assistant content blocks + tool results
                assistant_content: list[dict[str, Any]] = []
                if content:
                    assistant_content.append({"type": "text", "text": content})
                for tc in tool_calls:
                    assistant_content.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["arguments"],
                    })
                messages.append({"role": "assistant", "content": assistant_content})

                # Execute tools and build tool result blocks
                tool_results: list[dict[str, Any]] = []
                for tc in tool_calls:
                    try:
                        result = self.call_tool(tc["name"], tc["arguments"])
                    except Exception as e:
                        result = f"Error: {e}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": result[:10000],
                    })
                    steps_taken += 1
                messages.append({"role": "user", "content": tool_results})
            else:
                # OpenAI message format
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
                if tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"]),
                            },
                        }
                        for tc in tool_calls
                    ]
                messages.append(assistant_msg)

                for tc in tool_calls:
                    try:
                        result = self.call_tool(tc["name"], tc["arguments"])
                    except Exception as e:
                        result = f"Error: {e}"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result[:10000],
                    })
                    steps_taken += 1

        return final_content

    # ------------------------------------------------------------------
    # Core operations (auto-traced)
    # ------------------------------------------------------------------

    def run(self, command: str, *, timeout: int = 120) -> str:
        """Execute a shell command in the sandbox. Returns stdout.

        Args:
            command: Shell command string.
            timeout: Max seconds (default 120).

        Returns:
            stdout from the command.

        Raises:
            RuntimeError: If the command timed out.
        """
        t0 = time.time()
        result = self._sandbox.execute(command, timeout=timeout)
        duration_ms = (time.time() - t0) * 1000

        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", -1)
        timed_out = result.get("timed_out", False)

        self._record(
            action="execute_command",
            params={"command": command},
            observation={
                "stdout": stdout[:10000],
                "stderr": stderr[:5000],
                "exit_code": exit_code,
            },
            duration_ms=duration_ms,
        )

        if timed_out:
            raise RuntimeError(f"Command timed out after {timeout}s: {command}")

        return stdout

    def read_file(self, path: str) -> str:
        """Read a file from the sandbox workspace.

        Args:
            path: Path relative to /workspace, or absolute.

        Returns:
            File contents as string.
        """
        full_path = self._resolve_path(path)
        t0 = time.time()
        result = self._sandbox.execute(f"cat {full_path}", timeout=10)
        duration_ms = (time.time() - t0) * 1000

        content = result.get("stdout", "")
        exit_code = result.get("exit_code", -1)

        self._record(
            action="read_file",
            params={"path": path},
            observation={
                "stdout": content[:10000],
                "stderr": result.get("stderr", "")[:2000],
                "exit_code": exit_code,
            },
            duration_ms=duration_ms,
        )

        if exit_code != 0:
            raise FileNotFoundError(f"Cannot read {path}: {result.get('stderr', '')}")

        return content

    def write_file(self, path: str, content: str) -> None:
        """Write content to a file in the sandbox workspace.

        Uses base64 encoding for safe transfer.

        Args:
            path: Path relative to /workspace, or absolute.
            content: File content string.
        """
        full_path = self._resolve_path(path)

        # Ensure parent directory exists
        parent = str(Path(full_path).parent)
        if parent != ".":
            self._sandbox.execute(f"mkdir -p {parent}", timeout=5)

        b64 = base64.b64encode(content.encode()).decode()

        t0 = time.time()
        result = self._sandbox.execute(
            f"echo '{b64}' | base64 -d > {full_path}",
            timeout=10,
        )
        duration_ms = (time.time() - t0) * 1000

        exit_code = result.get("exit_code", -1)

        self._record(
            action="write_file",
            params={"path": path, "content_length": len(content)},
            observation={
                "stdout": f"Wrote {len(content)} bytes to {path}",
                "stderr": result.get("stderr", "")[:2000],
                "exit_code": exit_code,
            },
            duration_ms=duration_ms,
        )

        if exit_code != 0:
            raise RuntimeError(f"Cannot write {path}: {result.get('stderr', '')}")

    def list_files(self, path: str = ".") -> list[str]:
        """List files in a sandbox directory.

        Args:
            path: Directory path relative to /workspace, or absolute.

        Returns:
            List of filenames.
        """
        full_path = self._resolve_path(path)
        t0 = time.time()
        result = self._sandbox.execute(f"ls -1 {full_path}", timeout=10)
        duration_ms = (time.time() - t0) * 1000

        stdout = result.get("stdout", "")
        files = [f for f in stdout.strip().split("\n") if f]

        self._record(
            action="list_files",
            params={"path": path},
            observation={
                "stdout": stdout[:5000],
                "stderr": result.get("stderr", "")[:2000],
                "exit_code": result.get("exit_code", -1),
            },
            duration_ms=duration_ms,
        )

        return files

    def upload(self, local_path: str | Path, sandbox_path: str = ".") -> None:
        """Copy a file from the host into the sandbox."""
        full_path = self._resolve_path(sandbox_path)
        self._sandbox.copy_to(local_path, full_path)
        self._record(
            action="upload",
            params={"local_path": str(local_path), "sandbox_path": sandbox_path},
            observation={"stdout": f"Uploaded to {full_path}", "stderr": "", "exit_code": 0},
        )

    def download(self, sandbox_path: str, local_path: str | Path = ".") -> None:
        """Copy a file from the sandbox to the host."""
        full_path = self._resolve_path(sandbox_path)
        self._sandbox.copy_from(full_path, local_path)
        self._record(
            action="download",
            params={"sandbox_path": sandbox_path, "local_path": str(local_path)},
            observation={"stdout": f"Downloaded from {full_path}", "stderr": "", "exit_code": 0},
        )

    # ------------------------------------------------------------------
    # Custom step recording
    # ------------------------------------------------------------------

    def record_step(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        result: str = "",
        *,
        cost_usd: float | None = None,
        token_usage: int | None = None,
        duration_ms: float = 0.0,
    ) -> None:
        """Record a custom action step (e.g., an LLM call).

        Use this for actions that don't go through the sandbox
        (API calls, model inference, planning steps, etc.).
        """
        self._record(
            action=action,
            params=params or {},
            observation={"stdout": result[:10000], "stderr": "", "exit_code": 0},
            duration_ms=duration_ms,
            cost_usd=cost_usd,
            token_usage=token_usage,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def finish(
        self,
        *,
        outcome: str = "completed",
        score: float | None = None,
    ) -> None:
        """Finalize the episode and destroy the sandbox.

        Args:
            outcome: Episode outcome ("completed", "failed", "error").
            score: Optional score (0.0 to 1.0).
        """
        if self._finished:
            return

        self._finished = True
        ended_at = time.time()
        duration_ms = (ended_at - self._started_at) * 1000

        self._sync_episode(
            outcome=outcome,
            score=score,
            is_complete=1,
            ended_at=ended_at,
            duration_ms=duration_ms,
        )

        self._sandbox.destroy()
        self._store.close()

        self._log.info(
            "session_finished",
            outcome=outcome,
            score=score,
            steps=self._step_idx,
            duration_s=round(duration_ms / 1000, 1),
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> Session:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        if not self._finished:
            outcome = "error" if exc_type is not None else "completed"
            score = 0.0 if exc_type is not None else None
            self.finish(outcome=outcome, score=score)

    def __del__(self) -> None:
        if not self._finished:
            try:
                self.finish(outcome="abandoned")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, path: str) -> str:
        if path.startswith("/"):
            return path
        workspace = self._sandbox.config.workspace_dir
        return f"{workspace}/{path}"

    def _record(
        self,
        action: str,
        params: dict[str, Any],
        observation: dict[str, Any],
        duration_ms: float = 0.0,
        cost_usd: float | None = None,
        token_usage: int | None = None,
    ) -> None:
        step = {
            "episode_id": self._episode_id,
            "step_idx": self._step_idx,
            "timestamp": time.time(),
            "action": action,
            "action_params": params,
            "observation": observation,
            "reward": 0.0,
            "duration_ms": duration_ms,
            "cpu_time_ms": 0.0,
            "file_diff": None,
            "token_usage": token_usage,
            "cost_usd": cost_usd,
            "source": self._source,
            "state": {"cwd": "/workspace"},
        }
        self._steps.append(step)
        self._step_idx += 1

        # Sync to DB immediately for real-time dashboard
        self._sync_episode(outcome="running", is_complete=0)

    def _sync_episode(
        self,
        outcome: str,
        is_complete: int,
        score: float | None = None,
        ended_at: float | None = None,
        duration_ms: float | None = None,
    ) -> None:
        if duration_ms is None:
            duration_ms = (time.time() - self._started_at) * 1000

        self._store.ingest_episode(
            episode_metadata={
                "episode_id": self._episode_id,
                "task_name": self._task_name,
                "outcome": outcome,
                "score": score,
                "step_count": self._step_idx,
                "duration_ms": duration_ms,
                "started_at": self._started_at,
                "ended_at": ended_at,
                "is_complete": is_complete,
                "sandbox_id": self._sandbox_id,
            },
            steps=self._steps,
        )

    def __repr__(self) -> str:
        status = "finished" if self._finished else "running"
        return (
            f"Session(task={self._task_name!r}, episode={self._episode_id!r}, "
            f"steps={self._step_idx}, status={status})"
        )

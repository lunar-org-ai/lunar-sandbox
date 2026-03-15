# lunar-agentlab

## What This Is

The fastest open-source sandbox engine for evaluating and training coding agents and computer-use agents, with a real-time web platform for launching experiments and inspecting execution traces. A high-performance episode runner with sub-second resets on local hardware, paired with a React-based developer UI for visualizing agent behavior, debugging pipelines, and watching agents interact with graphical desktops in real time.

## Core Value

Episode reset time is the bottleneck -- not startup. Everything is optimized for thousands of fast evaluation loops: hot pools, layered filesystems, discard-and-reset instead of rebuild.

## Requirements

### Validated

- Sandbox engine with hot pool management by environment fingerprint -- v1.0
- Layered filesystem (base readonly -> deps cached -> task seed -> ephemeral writable diff) -- v1.0
- Local scheduler (daemon per host, unix sockets) -- v1.0
- Episode lifecycle: allocate from pool -> mount diff -> inject task -> run -> save trace -> discard diff -> reset -- v1.0
- Structured action API as canonical agent interface (8 action types) -- v1.0
- Instrumented shell backend (all captured as structured events) -- v1.0
- Coding repo environment type (repo + unit tests as reward signal) -- v1.0
- Trajectory collection (JSONL streaming, SQLite persistence, Parquet export) -- v1.0
- Benchmark runner (single task, N tasks with configurable parallelism) -- v1.0
- CLI interface (run, eval, replay, pool, telemetry) -- v1.0
- Python SDK interface (LunarEngine with async/sync APIs) -- v1.0
- Performance metrics (allocate latency, reset latency, time-to-first-action, throughput, cache hit rate) -- v1.0
- Resource limits per sandbox (CPU, RAM, time via cgroups v2) -- v1.0
- Web platform for launching and managing sandbox experiments -- v2.0
- Real-time trace visualization (timeline + graph/flow views) -- v2.0
- FastAPI backend wrapping Python SDK with WebSocket streaming -- v2.0
- Pipeline/chain execution visualization and step inspection -- v2.0
- Monorepo workspace structure (shared types, web app, API server) -- v2.0

### Active

- [ ] CUA desktop environment container (Xvfb + Openbox + Chromium + xdotool + scrot)
- [ ] CUA action types (screenshot, mouse_move, mouse_click, mouse_drag, keyboard_type, keyboard_key, scroll)
- [ ] Input injection layer (actions → xdotool commands inside container)
- [ ] Screenshot capture pipeline (base64 PNG for model input, trace storage, and replay)
- [ ] noVNC live streaming (x11vnc + websockify → noVNC embedded in web platform)
- [ ] CUA task definitions (browser URL + instruction, desktop + instruction)
- [ ] Multiple reward signals (manual review, screenshot comparison, validation scripts)
- [ ] Default CUA base image with user extensibility
- [ ] Full loop: launch CUA episode from UI → agent runs → watch live via noVNC → replay trace with screenshots

### Out of Scope

- Training loop (SFT/RL) -- v1 exports trajectories, training happens externally
- Terminal task environment -- v4+
- API workflow environment -- v4+
- OCI + crun container fast path -- v4+ (Docker sufficient for CUA)
- Firecracker microVM pools -- v4+ (not needed for CUA workloads)
- Enterprise features (auth, multi-tenancy, RBAC, secrets, compliance, audit) -- kills velocity
- Kubernetes orchestration -- v4+ for cluster management, hot path stays local
- gVisor as default runtime -- isolation overhead conflicts with performance goal
- Visual pipeline builder -- code-defined pipelines, UI-visualized is the philosophy
- LLM-as-judge evaluation UI -- scoring happens in code
- Prompt playground/editor -- platform evaluates agents, not prompts
- Multi-user collaboration -- local single-user developer tool
- Custom dashboard builder -- opinionated layouts over blank canvas
- Side-by-side run comparison -- deferred from v2.0, not blocking CUA work
- Human intervention during CUA episodes -- live observation only for v3.0

## Context

- Primary users are ML researchers, infra researchers, and agent engineers who want fast evaluation loops
- This audience accepts raw product, values performance and traces, helps form public benchmarks, generates open-source credibility
- Existing tools (SWE-bench, AgentBench, Inspect AI, METR) solve pieces but none close the full loop with performance as priority
- SWE-bench proved coding repo + unit tests is the highest-signal evaluation wedge
- Computer use (CUA) is the next evaluation frontier -- agents interacting with browsers and desktop apps
- Anthropic's computer_use API defines the interaction primitives: screenshot(), click(x,y), type(text), key(key_name)
- The critical path has zero build/pull/install/clone/boot/apt-get -- all prep happens before the run path
- Pool fingerprints define environment signatures: runtime + deps + repo base + toolchain + network policy + resource class
- **v1.0 shipped:** 23,142 lines of Python across 115 files, 523 tests, 47 requirements satisfied
- **v2.0 shipped:** 12,192 lines of TypeScript/Python across 106 files changed, 23 requirements satisfied, 54 commits
- **Tech stack:** Python 3.11+, Pydantic v2, Typer, Rich, SQLite (WAL mode), pyarrow (optional)
- **Web stack:** React 19, Tailwind CSS v4, shadcn/ui, FastAPI, WebSockets, React Flow, recharts, xterm.js, TanStack Table
- **Linux requirements:** Kernel 5.15+, cgroups v2, OverlayFS, user namespaces
- **Docker sandbox:** docker_config.py and docker_sandbox.py exist with working container lifecycle (create/start/stop/remove)
- **Known tech debt:** 7 items from v2.0 audit (CommandPalette field mismatches, hardcoded metrics topic, orphaned endpoint) -- see milestones/v2.0-MILESTONE-AUDIT.md

## Constraints

- **Performance-first**: No operation on the critical run path that isn't allocate/mount/inject/run/trace/reset
- **Local-first**: Single-node scheduler before any distributed orchestration
- **Linux namespaces/cgroups**: Primary isolation mechanism for trusted/fast path
- **Docker**: Container runtime for CUA desktop environments
- **Anthropic computer_use**: CUA action primitives must be compatible with this API
- **Python**: Primary language (SDK, CLI, scheduler -- target audience lives in Python)
- **TypeScript/React**: Web platform frontend
- **shadcn/ui**: Only UI component library for the web platform (https://ui.shadcn.com)
- **Open source**: MIT or Apache 2.0 license

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Structured action API as canonical interface | Gives observability, clean trajectories, replay, reward attribution, agent comparison | Good |
| Shell as instrumented backend, not primary interface | Agents can use terminal but everything is captured as structured events | Good |
| Optimize reset latency over startup latency | RL/benchmark workloads need thousands of episodes, reset is the real bottleneck | Good |
| Pool by environment fingerprint | Avoids warming everything, warms what has demand | Good |
| Local scheduler first, k8s later | K8s adds API hops, pod lifecycle overhead -- hot path needs daemon + unix sockets | Good |
| Coding repo as v1 environment | Clear reward signal, existing benchmarks, obvious value, filesystem-only | Good |
| Target ML researchers first, enterprise later | Avoids pulling in auth/RBAC/compliance too early, maintains velocity | Good |
| Platform gate at call time not import time | Enables macOS development workflow with Linux-only kernel operations | Good |
| Thread-safe TelemetryCollector (threading.Lock) | asyncio.to_thread runs pool ops in real OS threads, not just coroutines | Good |
| DI for telemetry, never global singleton | Clean testing, explicit wiring, no hidden state | Good |
| Seccomp default-ALLOW with specific blocks | Default-DENY too restrictive for coding sandbox (agents need most syscalls) | Good |
| Monorepo workspace for web platform | Shared types between Python API and TypeScript frontend, clean separation of concerns | Good |
| shadcn/ui as sole component library | Consistent, accessible, customizable components | Good |
| Code-defined pipelines, UI-visualized | Visual builder deferred -- start with code-first, inspect in UI | Good |
| OpenAPI codegen for type generation | Pydantic models -> OpenAPI -> TypeScript interfaces, zero manual sync | Good |
| Custom useWebSocket hook | react-use-websocket incompatible with React 19 | Good |
| Generated files committed to git | Visible in PRs, no codegen needed after clone | Good |
| Unversioned /api/* URLs | Local dev tool, API versioning unnecessary | Good |

| Docker for CUA isolation | Docker provides full desktop environment (Xvfb, browser, window manager) that namespace-only sandboxes cannot | — Pending |
| xdotool for input injection | Lightweight, well-established, no custom X11 protocol work needed | — Pending |
| noVNC for live observation | Browser-native VNC client, works with existing web platform architecture | — Pending |
| Multiple reward signals | CUA tasks lack a universal reward signal like unit tests -- support manual, screenshot match, and scripts | — Pending |

## Current Milestone: v3.0 Computer User Agent

**Goal:** Enable agents to interact with full graphical desktop environments inside sandboxes, with live observation and trace replay.

**Target features:**
- Desktop environment container with Xvfb, Openbox, Chromium
- CUA action protocol (mouse, keyboard, scroll, screenshot)
- Input injection and screenshot capture pipeline
- noVNC live streaming in web platform
- CUA task definitions (browser + desktop tasks)
- Multiple reward signals (manual, screenshot match, script validation)

---
*Last updated: 2026-03-14 after v3.0 milestone started*

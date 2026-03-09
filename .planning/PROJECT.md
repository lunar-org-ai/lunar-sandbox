# lunar-agentlab

## What This Is

The fastest open-source sandbox engine for evaluating and training coding agents. A high-performance episode runner that lets ML researchers and agent engineers benchmark agents against coding tasks, compare models/prompts/policies, collect trajectories, and measure success — all with sub-second episode resets on local hardware.

## Core Value

Episode reset time is the bottleneck — not startup. Everything is optimized for thousands of fast evaluation loops: hot pools, layered filesystems, discard-and-reset instead of rebuild.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Sandbox engine with hot pool management by environment fingerprint
- [ ] Layered filesystem (base readonly → deps cached → task seed → ephemeral writable diff)
- [ ] Local scheduler (daemon per host, unix sockets, CPU/mem pinning)
- [ ] Episode lifecycle: allocate from pool → mount diff → inject task → run → save trace → discard diff → reset
- [ ] Structured action API as canonical agent interface (execute_command, read_file, write_file, list_files, search, run_tests, submit, get_logs)
- [ ] Instrumented shell backend (stdout/stderr, exit code, cwd, duration, files touched — all captured as structured events)
- [ ] Coding repo environment type (repo + unit tests as reward signal)
- [ ] Trajectory collection (action trace, observations, command logs, file diffs, test outcomes, runtime, cost/tokens)
- [ ] Benchmark runner (single task, N tasks, compare model A vs B, compare prompt A vs B)
- [ ] CLI interface (run, eval, replay)
- [ ] Python SDK interface
- [ ] Performance metrics (allocate latency, reset latency, time-to-first-action, throughput per host, cache hit rate)
- [ ] Resource limits per sandbox (CPU, RAM, time)
- [ ] Dependency/repo caching across episodes

### Out of Scope

- Training loop (SFT/RL) — v1 exports trajectories, training happens externally
- Browser task environment — v2+
- Terminal task environment — v2+
- API workflow environment — v2+
- Custom docker sandbox environment — v2+
- Enterprise features (auth, multi-tenancy, RBAC, secrets, compliance, audit) — kills velocity
- Kubernetes orchestration — v2+ for cluster management, hot path stays local
- Web UI/dashboard — CLI and SDK are sufficient for v1 users
- gVisor as default runtime — isolation overhead conflicts with performance goal

## Context

- Primary users are ML researchers, infra researchers, and agent engineers who want fast evaluation loops
- This audience accepts raw product, values performance and traces, helps form public benchmarks, generates open-source credibility
- Existing tools (SWE-bench, AgentBench, Inspect AI, METR) solve pieces but none close the full loop with performance as priority
- SWE-bench proved coding repo + unit tests is the highest-signal evaluation wedge
- The critical path has zero build/pull/install/clone/boot/apt-get — all prep happens before the run path
- Pool fingerprints define environment signatures: runtime + deps + repo base + toolchain + network policy + resource class (e.g., py311-poetry-test, node20-playwright, ubuntu-cpp-clang)

## Constraints

- **Performance-first**: No operation on the critical run path that isn't allocate/mount/inject/run/trace/reset
- **Local-first**: Single-node scheduler before any distributed orchestration
- **Linux namespaces/cgroups**: Primary isolation mechanism for trusted/fast path
- **OCI + crun**: Container fast path when isolation needed without VM overhead
- **Firecracker**: Secure fast path via snapshot/restore for microVM pools
- **Python**: Primary language (SDK, CLI, scheduler — target audience lives in Python)
- **Open source**: MIT or Apache 2.0 license

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Structured action API as canonical interface | Gives observability, clean trajectories, replay, reward attribution, agent comparison | — Pending |
| Shell as instrumented backend, not primary interface | Agents can use terminal but everything is captured as structured events | — Pending |
| Optimize reset latency over startup latency | RL/benchmark workloads need thousands of episodes, reset is the real bottleneck | — Pending |
| Pool by environment fingerprint | Avoids warming everything, warms what has demand | — Pending |
| Local scheduler first, k8s later | K8s adds API hops, pod lifecycle overhead — hot path needs daemon + unix sockets | — Pending |
| Coding repo as v1 environment | Clear reward signal, existing benchmarks, obvious value, filesystem-only | — Pending |
| Target ML researchers first, enterprise later | Avoids pulling in auth/RBAC/compliance too early, maintains velocity | — Pending |

---
*Last updated: 2026-03-09 after initialization*

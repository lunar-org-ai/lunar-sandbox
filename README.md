# LunarSandbox

Linux namespace sandboxes with OverlayFS, cgroups v2, and seccomp-bpf for AI agent evaluation.

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** (Python package manager)
- **Node.js 18+** and **[pnpm](https://pnpm.io/)**
- **Docker** (required for CUA sandbox image)
- **Linux** with kernel support for namespaces, OverlayFS, cgroups v2, and seccomp-bpf

## Quick Start

```bash
# One-command setup: installs Python deps, Node deps, and builds the CUA Docker image
make setup
```

This runs:

1. `uv sync` — installs Python dependencies
2. `cd web && pnpm install` — installs frontend dependencies
3. `docker build` — builds the `lunar-cua:latest` Docker image

## Development

### Running the Dev Servers

```bash
# Start both FastAPI backend (port 8000) and Vite frontend (port 3000) concurrently
make dev
```

This launches:

- **API**: `uvicorn lunar_sandbox.api.app:app --reload` on `http://localhost:8000`
- **Dashboard**: `vite --port 3000` on `http://localhost:3000`

### Running Individually

```bash
# Backend only
uv run uvicorn lunar_sandbox.api.app:app --reload --host 0.0.0.0 --port 8000

# Frontend only
cd web && pnpm --filter dashboard dev
```

### CLI

```bash
uv run lunar --help
```

## Testing

### Python Tests

```bash
# Run all tests
make test

# Or directly with pytest
uv run pytest

# With coverage
uv run pytest --cov

# Specific test file
uv run pytest tests/test_health.py

# Specific test
uv run pytest tests/test_health.py::test_health_endpoint -v
```

### Frontend

```bash
# Lint (ESLint)
make lint

# TypeScript type check
cd web/apps/dashboard && npx tsc --noEmit

# Production build
cd web && pnpm build
```

## Code Generation

TypeScript API types are generated from FastAPI/Pydantic schemas:

```bash
make codegen
```

This exports the OpenAPI spec and generates `web/packages/types/src/api.d.ts`.

## Project Structure

```text
.
├── src/lunar_sandbox/         # Python backend
│   ├── api/                   # FastAPI app, routers, schemas
│   ├── cli/                   # Typer CLI
│   ├── cua/                   # Computer-Use Agent module
│   └── docker/cua/            # CUA sandbox Dockerfile
├── tests/                     # Python test suite (pytest)
│   ├── unit/                  # Unit tests
│   └── test_*.py              # Integration tests
├── web/                       # Frontend monorepo (pnpm workspace)
│   ├── apps/dashboard/        # React + Vite dashboard (shadcn/ui)
│   └── packages/types/        # Shared TypeScript types (OpenAPI-generated)
├── scripts/                   # Build and codegen scripts
├── Makefile                   # Project commands
└── pyproject.toml             # Python project config
```

## Build

```bash
# Frontend production build
cd web && pnpm build

# CUA Docker image
make docker-cua

# Clean build artifacts
make clean
```

## Tech Stack

| Layer    | Stack                                                   |
| -------- | ------------------------------------------------------- |
| Backend  | Python 3.12, FastAPI, Pydantic, uvicorn, structlog      |
| Frontend | React 19, Vite 6, TypeScript, Tailwind CSS 4, shadcn/ui |
| Testing  | pytest, pytest-cov, ESLint                              |
| Tooling  | uv, pnpm, Docker                                        |

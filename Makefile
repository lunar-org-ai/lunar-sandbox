.PHONY: setup dev codegen lint test clean docker-cua

# One-command setup for fresh clones
setup:
	uv sync
	cd web && pnpm install
	$(MAKE) docker-cua

# Build the CUA Docker image
docker-cua:
	docker build -t lunar-cua:latest src/lunar_sandbox/docker/cua/

# Start both FastAPI + Vite dev servers
dev:
	cd web && pnpm dev

# Regenerate TypeScript types from Pydantic models
codegen:
	uv run python scripts/export_openapi.py
	cd web && pnpm exec openapi-typescript packages/types/openapi.json -o packages/types/src/api.d.ts

# Run Python tests
test:
	uv run pytest

# Run frontend lints
lint:
	cd web && pnpm --filter dashboard lint

# Clean build artifacts
clean:
	rm -rf web/apps/dashboard/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

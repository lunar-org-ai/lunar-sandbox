"""Export OpenAPI schema from the FastAPI app without running the server.

This script imports the FastAPI app, calls app.openapi() to get the
auto-generated OpenAPI 3.1 schema, and writes it to
web/packages/types/openapi.json for consumption by openapi-typescript.

Usage: uv run python scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path

# Ensure src/ is on the path for the src layout
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lunar_sandbox.api.app import app

schema = app.openapi()
output = Path(__file__).parent.parent / "web" / "packages" / "types" / "openapi.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(schema, indent=2) + "\n")
print(f"OpenAPI schema written to {output}")

"""Export OpenAPI schema from the FastAPI app without running the server.

This script imports the FastAPI app, calls app.openapi() to get the
auto-generated OpenAPI 3.1 schema, and writes it to
web/packages/types/openapi.json for consumption by openapi-typescript.

WebSocket models (like WsEnvelope) are not automatically included by
FastAPI because they are not referenced in any HTTP endpoint.  We
inject them into the ``components/schemas`` section so the codegen
pipeline produces TypeScript types for them too.

Usage: uv run python scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path

# Ensure src/ is on the path for the src layout
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lunar_sandbox.api.app import app
from lunar_sandbox.api.schemas import WsEnvelope

schema = app.openapi()

# Inject WebSocket-only models into OpenAPI components
_ws_models = [WsEnvelope]
components = schema.setdefault("components", {})
schemas = components.setdefault("schemas", {})
for model in _ws_models:
    schemas[model.__name__] = model.model_json_schema()

output = Path(__file__).parent.parent / "web" / "packages" / "types" / "openapi.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(schema, indent=2) + "\n")
print(f"OpenAPI schema written to {output}")

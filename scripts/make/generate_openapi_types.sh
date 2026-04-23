#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
UI_DIR="$PROJECT_ROOT/ui"
OPENAPI_JSON=$(mktemp "${TMPDIR:-/tmp}/openapi-XXXXXX.json")
OUTPUT="$UI_DIR/src/generated/api.ts"

# Ensure temp file is cleaned up even on failure
trap 'rm -f "$OPENAPI_JSON"' EXIT

# Export OpenAPI spec from FastAPI app (no running server needed)
cd "$PROJECT_ROOT"
poetry run python -c "
import json, sys
from analysi.main import app
with open(sys.argv[1], 'w') as f:
    json.dump(app.openapi(), f, indent=2)
" "$OPENAPI_JSON"

# Generate TypeScript types
mkdir -p "$(dirname "$OUTPUT")"
npx openapi-typescript "$OPENAPI_JSON" -o "$OUTPUT"

echo "Generated TypeScript types at $OUTPUT"

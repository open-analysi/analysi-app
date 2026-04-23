#!/usr/bin/env python3
"""
Verify CLI commands reference API routes that actually exist.

Parses cli-config.yaml and hand-written CLI commands, then checks every
(method, path) pair against the FastAPI OpenAPI schema. Exits non-zero
if any CLI path references a route that doesn't exist in the API.

Usage:
    poetry run python scripts/code_quality_tools/check_cli_api_sync.py
"""

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLI_DIR = REPO_ROOT / "cli"
CONFIG_PATH = CLI_DIR / "cli-config.yaml"
COMMANDS_DIR = CLI_DIR / "src" / "commands"

# Hand-written commands that call the API directly (not via cli-config.yaml).
# Each entry: (topic, command_file, method_pattern, path_pattern)
# We extract paths by regex from the TypeScript source.
HAND_WRITTEN_COMMANDS = [
    "alerts/analyze.ts",
    "alerts/watch.ts",
    "alerts/validate.ts",
    "tasks/run.ts",
    "tasks/run-adhoc.ts",
    "tasks/create.ts",
    "tasks/update.ts",
    "tasks/compile.ts",
    "workflows/run.ts",
    "workflows/compose.ts",
    "workflows/delete.ts",
    "workflow-runs/watch.ts",
    "integrations/run-tool.ts",
    "tools/list.ts",
    "tools/get.ts",
    "packs/install.ts",
    "packs/list.ts",
    "packs/uninstall.ts",
]

# Paths in hand-written commands that are internal polling/status endpoints,
# not direct CLI-config routes. These use dynamic path construction and are
# checked indirectly (e.g., /task-runs/{id} is already in the config).
HAND_WRITTEN_SKIP_PATTERNS = {
    # Polling endpoints constructed at runtime
    "/task-runs/",
    "/workflow-runs/",
    # Status/progress endpoints hit by watch commands
    "/alerts/{alert_id}/analyze",
    "/alerts/{alert_id}/analysis",
}


def get_openapi_routes() -> set[tuple[str, str]]:
    """Import the FastAPI app and extract all (method, path) pairs.

    Returns paths normalized: /v1/{tenant}/alerts → /alerts
    Path parameters are kept as-is: /alerts/{alert_id} stays /alerts/{alert_id}
    """
    # Avoid triggering database connections during import
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
    os.environ.setdefault("ANALYSI_VAULT_ADDR", "http://localhost:8200")
    os.environ.setdefault("ANALYSI_VAULT_TOKEN", "dummy")

    from analysi.main import app

    schema = app.openapi()
    routes = set()

    for path, methods in schema.get("paths", {}).items():
        # Strip /v1/{tenant} prefix to match CLI paths
        normalized = re.sub(r"^/v1/\{[^}]+\}", "", path)
        if not normalized:
            normalized = "/"

        for method in methods:
            if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                routes.add((method.upper(), normalized))

    return routes


def get_cli_config_routes() -> list[tuple[str, str, str]]:
    """Parse cli-config.yaml and return (method, path, label) tuples."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    routes = []
    for topic, topic_config in config.get("commands", {}).items():
        for op_name, op in topic_config.get("operations", {}).items():
            method = op["method"].upper()
            path = op["path"]
            label = f"cli-config.yaml → {topic} {op_name}"
            routes.append((method, path, label))

    return routes


def get_hand_written_routes() -> list[tuple[str, str, str]]:
    """Extract API paths from hand-written TypeScript commands via regex."""
    routes = []

    # Patterns to match API paths in TypeScript
    # Matches: 'POST', '/some/path'  or  "GET", "/some/path"
    path_pattern = re.compile(
        r"""['"](\bGET|POST|PUT|PATCH|DELETE\b)['"]"""
        r"""[^'"]*?['"]([/][a-zA-Z0-9_/{}\-]+)['"]"""
    )

    for cmd_file in HAND_WRITTEN_COMMANDS:
        filepath = COMMANDS_DIR / cmd_file
        if not filepath.exists():
            continue

        content = filepath.read_text()

        for match in path_pattern.finditer(content):
            method = match.group(1).upper()
            path = match.group(2)

            # Skip internal polling paths
            if any(skip in path for skip in HAND_WRITTEN_SKIP_PATTERNS):
                continue

            # Skip paths that are clearly not API routes
            if not path.startswith("/"):
                continue

            label = f"hand-written → {cmd_file}"
            routes.append((method, path, label))

    return routes


def normalize_path_for_comparison(cli_path: str) -> str:
    """Normalize CLI path template vars for comparison with OpenAPI paths.

    CLI uses {integration_id}, {alert_id}, etc.
    OpenAPI uses {id}, {integration_id}, {alert_id}, etc.
    We normalize both to a canonical form for matching.
    """
    # Replace any {word} with a wildcard marker for comparison
    return re.sub(r"\{[^}]+\}", "{*}", cli_path)


def main() -> int:
    print("CLI ↔ API sync check")
    print("=" * 60)

    # Get API routes from OpenAPI schema
    try:
        api_routes = get_openapi_routes()
    except Exception as e:
        print(f"\n  ERROR: Could not load OpenAPI schema: {e}")
        print("  Hint: Run from the repo root with `poetry run python ...`")
        return 1

    # Normalize API routes for comparison
    api_normalized: dict[str, set[str]] = {}  # normalized_path → {methods}
    for method, path in api_routes:
        norm = normalize_path_for_comparison(path)
        api_normalized.setdefault(norm, set()).add(method)

    # Collect CLI routes
    config_routes = get_cli_config_routes()
    hand_written_routes = get_hand_written_routes()
    all_cli_routes = config_routes + hand_written_routes

    # Check each CLI route exists in the API
    errors = []
    checked = 0

    for method, path, label in all_cli_routes:
        checked += 1
        norm = normalize_path_for_comparison(path)

        if norm not in api_normalized:
            errors.append((method, path, label, "path not found in API"))
        elif method not in api_normalized[norm]:
            available = ", ".join(sorted(api_normalized[norm]))
            errors.append(
                (method, path, label, f"method mismatch (API has: {available})")
            )

    # Report
    print(f"\n  API routes:     {len(api_routes)}")
    print(
        f"  CLI routes:     {checked} ({len(config_routes)} config, {len(hand_written_routes)} hand-written)"
    )

    if errors:
        print(f"\n  ERRORS: {len(errors)} stale CLI route(s)\n")
        for method, path, label, reason in errors:
            print(f"    ✗ {method} {path}")
            print(f"      {label}")
            print(f"      Reason: {reason}\n")
        return 1

    print("\n  ✓ All CLI routes match the API")
    return 0


if __name__ == "__main__":
    sys.exit(main())

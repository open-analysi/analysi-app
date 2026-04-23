"""Auto-generate the api.md chat skill from the FastAPI OpenAPI schema.

Usage:
    poetry run python scripts/generate_chat_skills/generate_api_skill.py

This imports the FastAPI app and calls app.openapi() to extract all endpoints,
then generates a concise markdown reference grouped by domain. No server is
started — just the schema is read.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "analysi"
    / "chat"
    / "skills"
    / "api.md"
)

# Tags (or path prefixes) to exclude from the generated output
SKIP_TAGS = {"health", "admin"}

# OpenAPI path parameter {tenant} → {tenant_id} for readability
TENANT_REWRITE = ("{tenant}", "{tenant_id}")

# Ordering preference for sections (unlisted tags go alphabetically at the end)
SECTION_ORDER = [
    "alerts",
    "alert-routing",
    "tasks",
    "task-execution",
    "task-assist",
    "task-feedback",
    "task-building-runs",
    "task-generations",
    "workflows",
    "workflow-execution",
    "integrations",
    "integration-execution",
    "knowledge-units",
    "skills",
    "content-reviews",
    "credentials",
    "kdg",
    "chat",
    "control-events",
    "control-event-channels",
    "control-event-rules",
    "audit-trail",
    "api-keys",
    "members",
    "users",
    "artifacts",
]

# Human-friendly section titles (tag → title). Unlisted tags get title-cased.
SECTION_TITLES: dict[str, str] = {
    "alerts": "Alerts",
    "alert-routing": "Alert Routing & Analysis Groups",
    "tasks": "Tasks",
    "task-execution": "Task Execution",
    "task-assist": "Task Assist",
    "task-feedback": "Task Feedback",
    "task-building-runs": "Task Building Runs",
    "task-generations": "Task Generations",
    "workflows": "Workflows",
    "workflow-execution": "Workflow Execution",
    "integrations": "Integrations",
    "integration-execution": "Integration Execution",
    "knowledge-units": "Knowledge Units",
    "skills": "Skills",
    "content-reviews": "Content Reviews",
    "credentials": "Credentials",
    "kdg": "Knowledge Graph",
    "chat": "Chat",
    "control-events": "Control Events",
    "control-event-channels": "Control Event Channels",
    "control-event-rules": "Control Event Rules",
    "audit-trail": "Audit Trail",
    "api-keys": "API Keys",
    "members": "Members & Invitations",
    "users": "Users",
    "artifacts": "Artifacts",
}

# HTTP method ordering within a section
METHOD_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_path(path: str) -> str:
    """Rewrite {tenant} → {tenant_id} for readability."""
    return path.replace(TENANT_REWRITE[0], TENANT_REWRITE[1])


def _endpoint_sort_key(entry: dict) -> tuple:
    """Sort endpoints: by path, then by HTTP method order."""
    return (entry["path"], METHOD_ORDER.get(entry["method"], 99))


def _tag_sort_key(tag: str) -> tuple:
    """Sort tags by explicit order, then alphabetically."""
    try:
        idx = SECTION_ORDER.index(tag)
    except ValueError:
        idx = len(SECTION_ORDER)
    return (idx, tag)


def _section_title(tag: str) -> str:
    return SECTION_TITLES.get(tag, tag.replace("-", " ").title())


def _summary_or_description(details: dict) -> str:
    """Extract a one-line description from an OpenAPI operation."""
    summary = details.get("summary", "")
    if summary:
        return summary
    desc = details.get("description", "")
    # Take only the first line/sentence
    first_line = desc.split("\n")[0].strip()
    # Truncate at first period if very long
    if len(first_line) > 120:
        dot = first_line.find(".")
        if dot > 0:
            first_line = first_line[: dot + 1]
    return first_line or "—"


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------


def extract_endpoints(schema: dict) -> dict[str, list[dict]]:
    """Group endpoints by tag from the OpenAPI schema.

    Returns {tag: [{"method": ..., "path": ..., "description": ...}, ...]}.
    """
    groups: dict[str, list[dict]] = defaultdict(list)

    for path, methods in schema.get("paths", {}).items():
        for method, details in methods.items():
            tags = details.get("tags", [])

            # Skip excluded tags
            if any(t in SKIP_TAGS for t in tags):
                continue

            # Endpoints with no tags: try to derive from path
            if not tags:
                # e.g. /v1/{tenant} → skip (root endpoint)
                segments = [s for s in path.split("/") if s and not s.startswith("{")]
                if len(segments) <= 2:  # /v1/{tenant} only
                    tag = "tenant-info"
                else:
                    tag = segments[2] if len(segments) > 2 else "other"
            else:
                tag = tags[0]

            entry = {
                "method": method.upper(),
                "path": _normalise_path(path),
                "description": _summary_or_description(details),
            }
            groups[tag].append(entry)

    # Sort endpoints within each group
    for tag in groups:
        groups[tag].sort(key=_endpoint_sort_key)

    return groups


def generate_markdown(groups: dict[str, list[dict]]) -> str:
    """Render grouped endpoints into a markdown document."""
    lines: list[str] = []

    lines.append(
        "<!-- AUTO-GENERATED by scripts/generate_chat_skills/generate_api_skill.py"
        " — do not edit -->"
    )
    lines.append("")
    lines.append("# Analysi REST API Reference")
    lines.append("")
    lines.append("All endpoints require authentication and are scoped to a tenant.")
    lines.append("Base path: `/v1/{tenant_id}/`")
    lines.append("")
    lines.append("## Response Format (Sifnos Envelope)")
    lines.append("")
    lines.append(
        "Every response wraps data in: "
        '`{"data": <payload>, "meta": {"request_id": "...", ...}}`'
    )
    lines.append("")
    lines.append("- **Lists** include `total`, `limit`, `offset` in `meta`")
    lines.append(
        '- **Errors** return standard HTTP status codes with `{"detail": "..."}`'
    )
    lines.append(
        "- **Async operations** return `202 Accepted` with a run ID "
        "(poll the status endpoint)"
    )
    lines.append("")

    sorted_tags = sorted(groups.keys(), key=_tag_sort_key)

    for tag in sorted_tags:
        endpoints = groups[tag]
        title = _section_title(tag)

        lines.append("---")
        lines.append("")
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Method | Path | Description |")
        lines.append("|--------|------|-------------|")

        for ep in endpoints:
            method = ep["method"]
            path = f"`{ep['path']}`"
            desc = ep["description"]
            lines.append(f"| {method} | {path} | {desc} |")

        lines.append("")

    # Final newline
    if lines and lines[-1] != "":
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Import the FastAPI app (does NOT start the server)
    from analysi.main import app

    schema = app.openapi()

    groups = extract_endpoints(schema)

    if not groups:
        print("ERROR: No endpoints found in OpenAPI schema.", file=sys.stderr)
        sys.exit(1)

    markdown = generate_markdown(groups)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")

    # Summary
    total = sum(len(eps) for eps in groups.values())
    print(f"Generated {OUTPUT_PATH}")
    print(f"  {len(groups)} sections, {total} endpoints")


if __name__ == "__main__":
    main()

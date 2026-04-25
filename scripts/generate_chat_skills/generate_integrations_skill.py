"""Auto-generate the integrations.md chat skill from integration manifest.json files.

Usage:
    poetry run python scripts/generate_chat_skills/generate_integrations_skill.py

This scans all manifest.json files under the integrations framework directory
and generates a concise markdown reference grouped by archetype. No server is
started — just the manifest files are read.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MANIFESTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "analysi"
    / "integrations"
    / "framework"
    / "integrations"
)

OUTPUT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "analysi"
    / "chat"
    / "skills"
    / "integrations.md"
)

# Archetype display order. Unlisted archetypes go alphabetically at the end.
ARCHETYPE_ORDER = [
    "AI",
    "SIEM",
    "EDR",
    "ThreatIntel",
    "TicketingSystem",
    "Communication",
    "IdentityProvider",
    "NetworkSecurity",
    "VulnerabilityManagement",
    "EmailSecurity",
    "Geolocation",
    "DNS",
    "Lakehouse",
    "DatabaseEnrichment",
    "ForensicsTools",
    "Sandbox",
]

# Human-friendly archetype descriptions
ARCHETYPE_DESCRIPTIONS: dict[str, str] = {
    "AI": "LLM providers for reasoning and embeddings",
    "SIEM": "Security event ingestion and querying",
    "EDR": "Endpoint detection and response",
    "ThreatIntel": "Threat intelligence feeds and lookups",
    "TicketingSystem": "Incident and ticket management",
    "Communication": "Team messaging and notifications",
    "Notification": "Team messaging and notifications",
    "IdentityProvider": "User and identity management",
    "NetworkSecurity": "Firewalls and network tools",
    "VulnerabilityManagement": "Vulnerability scanning",
    "EmailSecurity": "Email gateway security",
    "Geolocation": "IP and location data",
    "DNS": "Domain name resolution services",
    "Lakehouse": "Data warehouse and lake",
    "DatabaseEnrichment": "Database lookup services",
    "ForensicsTools": "Digital forensics",
    "Sandbox": "Malware analysis sandboxes",
    "CloudProvider": "Cloud platform services",
    "AgenticFramework": "AI agent orchestration",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _archetype_sort_key(archetype: str) -> tuple:
    """Sort archetypes by explicit order, then alphabetically."""
    try:
        idx = ARCHETYPE_ORDER.index(archetype)
    except ValueError:
        idx = len(ARCHETYPE_ORDER)
    return (idx, archetype)


def _extract_auth_fields(manifest: dict) -> str:
    """Extract credential field names from credential_schema.

    Returns a comma-separated string like "api_key" or "username, password"
    or "none" for integrations that don't require credentials.
    """
    if manifest.get("requires_credentials") is False:
        return "none"

    schema = manifest.get("credential_schema", {})
    props = schema.get("properties", {})
    if not props:
        return "none"

    fields = list(props.keys())
    if not fields:
        return "none"

    return ", ".join(fields)


def _partition_actions(actions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split actions into tools and connectors.

    After Project Symi Phase 2, uses categories instead of type field.
    Actions with connector categories (health_monitoring, alert_ingestion, etc.)
    are treated as connectors; all others are tools.

    Returns (tools, connectors).
    """
    from analysi.integrations.framework.models import CONNECTOR_CATEGORIES

    tools = []
    connectors = []
    for action in actions:
        categories = set(action.get("categories", []))
        if categories & CONNECTOR_CATEGORIES:
            connectors.append(action)
        else:
            tools.append(action)
    return tools, connectors


def _shorten_description(desc: str, max_len: int = 60) -> str:
    """Shorten a description to max_len, cutting at a natural boundary.

    Strips nested parentheses to avoid unbalanced parens in the output.
    """
    # Remove parenthetical asides that would cause nesting issues
    desc = re.sub(r"\s*\([^)]*\)", "", desc)

    if len(desc) <= max_len:
        return desc

    # Try to cut at a natural boundary
    for sep in [". ", " — ", " - ", ", "]:
        idx = desc.find(sep)
        if 0 < idx < max_len:
            return desc[:idx]

    return desc[: max_len - 3] + "..."


def _format_tool_list(tools: list[dict]) -> str:
    """Format tool list as 'cy_name (description), ...' — concise."""
    parts = []
    for tool in tools:
        cy_name = tool.get("cy_name", tool.get("id", "?"))
        desc = tool.get("description", tool.get("name", ""))
        desc = _shorten_description(desc)
        parts.append(f"`{cy_name}` ({desc})")
    return ", ".join(parts)


def _format_connector_list(connectors: list[dict]) -> str:
    """Format connector list as 'id, ...'."""
    ids = [c.get("id", "?") for c in connectors]
    return ", ".join(ids)


# ---------------------------------------------------------------------------
# Core: load manifests
# ---------------------------------------------------------------------------


def load_manifests() -> list[dict]:
    """Load and return all manifest.json files, sorted by name."""
    manifests = []
    for manifest_path in sorted(MANIFESTS_DIR.glob("*/manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifests.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            print(
                f"WARNING: skipping {manifest_path}: {exc}",
                file=sys.stderr,
            )
    return manifests


# ---------------------------------------------------------------------------
# Core: generate markdown
# ---------------------------------------------------------------------------


def generate_markdown(manifests: list[dict]) -> str:
    """Render integration manifests into a markdown document."""
    lines: list[str] = []

    # --- Header ---
    lines.append(
        "<!-- AUTO-GENERATED by scripts/generate_chat_skills/"
        "generate_integrations_skill.py — do not edit -->"
    )
    lines.append("")
    lines.append("# Integrations")
    lines.append("")
    lines.append(
        "Analysi connects to external security tools via integrations. "
        "Each integration has an archetype that defines its role."
    )
    lines.append("")

    # --- Build archetype → integrations mapping ---
    archetype_map: dict[str, list[dict]] = defaultdict(list)
    for m in manifests:
        for arch in m.get("archetypes", []):
            archetype_map[arch].append(m)

    # --- Archetypes summary table ---
    lines.append("## Archetypes")
    lines.append("")
    lines.append("| Archetype | Description | Integrations |")
    lines.append("|-----------|-------------|--------------|")

    sorted_archetypes = sorted(archetype_map.keys(), key=_archetype_sort_key)
    for arch in sorted_archetypes:
        desc = ARCHETYPE_DESCRIPTIONS.get(arch, arch)
        names = sorted(
            {m["name"] for m in archetype_map[arch]},
        )
        names_str = ", ".join(names)
        lines.append(f"| {arch} | {desc} | {names_str} |")

    lines.append("")

    # --- Per-integration sections ---
    lines.append("## Available Integrations")
    lines.append("")

    # Sort integrations: by primary archetype order, then by name
    def _integration_sort_key(m: dict) -> tuple:
        primary = m.get("archetypes", ["ZZZ"])[0]
        return (_archetype_sort_key(primary), m.get("name", ""))

    sorted_manifests = sorted(manifests, key=_integration_sort_key)

    for m in sorted_manifests:
        name = m.get("name", m.get("id", "Unknown"))
        archetypes = ", ".join(m.get("archetypes", []))
        auth = _extract_auth_fields(m)
        actions = m.get("actions", [])
        tools, connectors = _partition_actions(actions)

        lines.append(f"### {name}")
        lines.append(f"- **Archetype**: {archetypes}")
        lines.append(f"- **Auth**: {auth}")

        if tools:
            lines.append(f"- **Tools**: {_format_tool_list(tools)}")
        if connectors:
            lines.append(f"- **Connectors**: {_format_connector_list(connectors)}")

        # Archetype mappings — show what generic capabilities this provides
        arch_mappings = m.get("archetype_mappings", {})
        if arch_mappings:
            all_capabilities = []
            for _arch, mapping in arch_mappings.items():
                all_capabilities.extend(mapping.keys())
            if all_capabilities:
                caps_str = ", ".join(f"`{c}`" for c in all_capabilities)
                lines.append(f"- **Capabilities**: {caps_str}")

        lines.append("")

    # --- Footer ---
    lines.append("## Integration Usage in Cy Scripts")
    lines.append("")
    lines.append(
        "Tools are called with fully qualified names: "
        "`app::{integration_id}::{cy_name}`"
    )
    lines.append("")
    lines.append("Examples:")
    lines.append("- `app::virustotal::ip_reputation` — look up IP reputation")
    lines.append("- `app::splunk::spl_run` — run a Splunk SPL query")
    lines.append("- `app::crowdstrike::quarantine_device` — isolate a compromised host")
    lines.append("- `app::slack::send_message` — post a message to a Slack channel")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    manifests = load_manifests()

    if not manifests:
        print(
            f"ERROR: No manifest.json files found in {MANIFESTS_DIR}.",
            file=sys.stderr,
        )
        sys.exit(1)

    markdown = generate_markdown(manifests)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")

    # Summary
    total_tools = 0
    total_connectors = 0
    for m in manifests:
        tools, connectors = _partition_actions(m.get("actions", []))
        total_tools += len(tools)
        total_connectors += len(connectors)

    print(f"Generated {OUTPUT_PATH}")
    print(
        f"  {len(manifests)} integrations, "
        f"{total_tools} tools, "
        f"{total_connectors} connectors"
    )


if __name__ == "__main__":
    main()

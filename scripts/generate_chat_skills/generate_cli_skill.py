"""Auto-generate the cli.md chat skill from the CLI config YAML.

Usage:
    poetry run python scripts/generate_chat_skills/generate_cli_skill.py

This reads cli/cli-config.yaml and generates a concise markdown reference
for the Analysi CLI, grouped by command topic. No server is started.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML is required. Install it with:\n    poetry add pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = REPO_ROOT / "cli" / "cli-config.yaml"

OUTPUT_PATH = REPO_ROOT / "src" / "analysi" / "chat" / "skills" / "cli.md"

# Hand-written commands that exist in the CLI but are NOT in cli-config.yaml.
# Sourced from cli/CLAUDE.md "Hand-written commands" list.
# Format: {topic: [{name, description, args_hint}]}
HAND_WRITTEN_COMMANDS: dict[str, list[dict[str, str]]] = {
    "auth": [
        {
            "name": "login",
            "description": "Interactive login (server URL, tenant, credentials)",
        },
        {
            "name": "logout",
            "description": "Log out and remove stored credentials",
        },
    ],
    "config": [
        {
            "name": "show",
            "description": "Show current configuration",
        },
    ],
    "status": [
        {
            "name": "",
            "description": (
                "Dashboard showing alert counts by severity, "
                "recent run statuses, and integration health"
            ),
        },
    ],
    "alerts": [
        {
            "name": "analyze",
            "description": "Start analysis on an alert with live progress",
            "args_hint": "<alert_id>",
        },
        {
            "name": "watch",
            "description": "Attach to a running analysis with live progress",
            "args_hint": "<analysis_id>",
        },
        {
            "name": "validate",
            "description": "Validate alert JSON against NAS schema",
            "args_hint": "@alert.json",
        },
    ],
    "tasks": [
        {
            "name": "create",
            "description": "Create a task from a Cy script",
            "args_hint": "--script @script.cy",
        },
        {
            "name": "update",
            "description": "Update task script, directive, or description",
            "args_hint": "<task_id> --script @new.cy",
        },
        {
            "name": "compile",
            "description": "Type-check a Cy script without executing",
            "args_hint": "--script @script.cy",
        },
        {
            "name": "run-adhoc",
            "description": "Run an ad-hoc Cy script with live progress",
            "args_hint": "--script @script.cy",
        },
    ],
    "workflows": [
        {
            "name": "compose",
            "description": "Create workflow from array composition format",
            "args_hint": "--data @composition.json",
        },
    ],
    "workflow-runs": [
        {
            "name": "watch",
            "description": "Attach to a running workflow with live progress",
            "args_hint": "<run_id>",
        },
    ],
    "integrations": [
        {
            "name": "run-tool",
            "description": "Execute an integration tool with JSON args",
            "args_hint": "<id> <tool> --data '{...}'",
        },
    ],
    "tools": [
        {
            "name": "get",
            "description": "Get tool details by fully qualified name",
            "args_hint": "<fqn>",
        },
    ],
    "packs": [
        {
            "name": "install",
            "description": "Install a content pack into a tenant",
            "args_hint": "<pack> [--dry-run]",
        },
        {
            "name": "list",
            "description": "List installed content packs with component counts",
        },
        {
            "name": "uninstall",
            "description": "Uninstall a content pack (removes all its components)",
            "args_hint": "<pack>",
        },
    ],
    "platform": [
        {
            "name": "tenants create",
            "description": "Create a new tenant with optional owner",
            "args_hint": "<id> [--owner-email <email>]",
        },
        {
            "name": "tenants list",
            "description": "List all tenants (platform admin only)",
        },
        {
            "name": "tenants describe",
            "description": "Show tenant details including component counts",
            "args_hint": "<id>",
        },
        {
            "name": "tenants delete",
            "description": "Delete a tenant and cascade all data",
            "args_hint": "<id> --confirm <id>",
        },
        {
            "name": "provision",
            "description": "Provision a tenant with content packs",
            "args_hint": "<tenant> --packs foundation,examples",
        },
    ],
}

# Topic ordering. Unlisted topics go alphabetically at the end.
TOPIC_ORDER = [
    "auth",
    "status",
    "config",
    "alerts",
    "tasks",
    "workflows",
    "integrations",
    "task-runs",
    "workflow-runs",
    "tools",
    "packs",
    "platform",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _topic_sort_key(topic: str) -> tuple:
    """Sort topics by explicit order, then alphabetically."""
    try:
        idx = TOPIC_ORDER.index(topic)
    except ValueError:
        idx = len(TOPIC_ORDER)
    return (idx, topic)


def _format_command(cli_name: str, topic: str, op_name: str) -> str:
    """Build the full command string, e.g. 'analysi alerts list'."""
    if op_name:
        return f"`{cli_name} {topic} {op_name}`"
    return f"`{cli_name} {topic}`"


def _format_args(args: dict) -> str:
    """Format positional args as '<arg1> <arg2>'."""
    if not args:
        return ""
    parts = []
    for arg_name, _arg_def in args.items():
        parts.append(f"<{arg_name}>")
    return " " + " ".join(parts)


def _format_flags_summary(flags: dict) -> str:
    """Format flags as a short summary for the description column."""
    if not flags:
        return ""

    flag_names = []
    for flag_name, flag_def in flags.items():
        if isinstance(flag_def, dict) and flag_def.get("required"):
            flag_names.append(f"--{flag_name}")
        else:
            flag_names.append(f"[--{flag_name}]")

    if len(flag_names) <= 3:
        return " " + " ".join(flag_names)
    # Show first 2 and indicate more
    return " " + " ".join(flag_names[:2]) + " ..."


def _build_flag_details(flags: dict) -> list[str]:
    """Build detailed flag documentation lines."""
    if not flags:
        return []

    rows = []
    for flag_name, flag_def in flags.items():
        if not isinstance(flag_def, dict):
            continue
        desc = flag_def.get("description", "")
        flag_type = flag_def.get("type", "string")
        default = flag_def.get("default")
        options = flag_def.get("options")

        extra_parts = []
        if flag_type != "string":
            extra_parts.append(flag_type)
        if default is not None:
            extra_parts.append(f"default: {default}")
        if options:
            extra_parts.append(f"options: {', '.join(str(o) for o in options)}")

        extra = ""
        if extra_parts:
            extra = f" ({'; '.join(extra_parts)})"

        rows.append(f"| `--{flag_name}` | {desc}{extra} |")

    return rows


# ---------------------------------------------------------------------------
# Core: load config and merge hand-written commands
# ---------------------------------------------------------------------------


def load_config(config_path: Path) -> dict:
    """Load the CLI config YAML."""
    if not config_path.exists():
        print(
            f"ERROR: CLI config not found at {config_path}\n"
            "Make sure cli/cli-config.yaml exists in the repo root.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        text = config_path.read_text(encoding="utf-8")
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        print(
            f"ERROR: Failed to parse {config_path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


def build_topic_map(
    config: dict,
) -> dict[str, dict]:
    """Build a map of topic → {description, operations} merging YAML + hand-written.

    Returns:
        {topic_name: {
            "description": str,
            "operations": [{name, description, args, flags, hand_written}]
        }}
    """
    commands = config.get("commands", {})
    topic_map: dict[str, dict] = {}

    # 1. Load YAML-defined commands
    for topic, topic_def in commands.items():
        operations = []
        for op_name, op_def in topic_def.get("operations", {}).items():
            operations.append(
                {
                    "name": op_name,
                    "description": op_def.get("description", ""),
                    "args": op_def.get("args", {}),
                    "flags": op_def.get("flags", {}),
                    "hand_written": False,
                }
            )

        topic_map[topic] = {
            "description": topic_def.get("description", ""),
            "operations": operations,
        }

    # 2. Merge hand-written commands
    for topic, hw_ops in HAND_WRITTEN_COMMANDS.items():
        if topic not in topic_map:
            topic_map[topic] = {
                "description": "",
                "operations": [],
            }

        existing_names = {op["name"] for op in topic_map[topic]["operations"]}

        for hw in hw_ops:
            if hw["name"] in existing_names:
                # Already defined in YAML (e.g., alerts analyze) — the YAML
                # version is the generated command; the hand-written version
                # overrides it in the actual CLI.  Keep the hand-written
                # description since it's more user-oriented.
                for op in topic_map[topic]["operations"]:
                    if op["name"] == hw["name"]:
                        op["description"] = hw["description"]
                        op["hand_written"] = True
                        if "args_hint" in hw:
                            op["args_hint"] = hw["args_hint"]
                        break
            else:
                topic_map[topic]["operations"].append(
                    {
                        "name": hw["name"],
                        "description": hw["description"],
                        "args": {},
                        "flags": {},
                        "hand_written": True,
                        "args_hint": hw.get("args_hint", ""),
                    }
                )

    return topic_map


# ---------------------------------------------------------------------------
# Core: generate markdown
# ---------------------------------------------------------------------------


def generate_markdown(config: dict, topic_map: dict[str, dict]) -> str:
    """Render the CLI skill markdown."""
    cli_name = config.get("cli", {}).get("name", "analysi")
    lines: list[str] = []

    # --- Header ---
    lines.append(
        "<!-- AUTO-GENERATED by scripts/generate_chat_skills/"
        "generate_cli_skill.py — do not edit -->"
    )
    lines.append("")
    lines.append("# Analysi CLI")
    lines.append("")
    lines.append(
        "The Analysi CLI (`analysi`) is a command-line tool for interacting "
        "with the Analysi Security Platform API. It is built on oclif and "
        "supports table, JSON, and CSV output formats."
    )
    lines.append("")

    # --- Installation ---
    lines.append("## Installation and Authentication")
    lines.append("")
    lines.append("```bash")
    lines.append("# Install dependencies")
    lines.append("make cli-install")
    lines.append("")
    lines.append("# Build the CLI")
    lines.append("make cli-build")
    lines.append("")
    lines.append("# Log in (interactive prompt for server URL, tenant, credentials)")
    lines.append("analysi auth login")
    lines.append("```")
    lines.append("")
    lines.append(
        "Credentials are stored at `~/.config/analysi/credentials.json` "
        "with `0600` permissions. The default tenant is set during login "
        "and can be overridden per-command with `--tenant` or the "
        "`ANALYSI_TENANT_ID` environment variable."
    )
    lines.append("")

    # --- Commands by topic ---
    lines.append("## Commands")
    lines.append("")

    sorted_topics = sorted(topic_map.keys(), key=_topic_sort_key)

    for topic in sorted_topics:
        topic_info = topic_map[topic]
        topic_desc = topic_info["description"]
        operations = topic_info["operations"]

        lines.append(f"### {topic}")
        if topic_desc:
            lines.append(f"_{topic_desc}_")
        lines.append("")

        lines.append("| Command | Description |")
        lines.append("|---------|-------------|")

        for op in operations:
            op_name = op["name"]
            desc = op["description"]

            # Build command column
            if op_name:
                cmd = f"`{cli_name} {topic} {op_name}"
            else:
                cmd = f"`{cli_name} {topic}"

            # Add positional args
            if op.get("args_hint"):
                cmd += f" {op['args_hint']}"
            elif op.get("args"):
                for arg_name in op["args"]:
                    cmd += f" <{arg_name}>"

            cmd += "`"

            lines.append(f"| {cmd} | {desc} |")

        lines.append("")

        # Flags detail table for operations that have flags
        ops_with_flags = [op for op in operations if op.get("flags")]
        if ops_with_flags:
            for op in ops_with_flags:
                flag_rows = _build_flag_details(op["flags"])
                if flag_rows:
                    lines.append(f"**`{cli_name} {topic} {op['name']}` flags:**")
                    lines.append("")
                    lines.append("| Flag | Description |")
                    lines.append("|------|-------------|")
                    lines.extend(flag_rows)
                    lines.append("")

    # --- Output Formats ---
    lines.append("## Output Formats")
    lines.append("")
    lines.append("All commands support three output formats via `--output` (or `-o`):")
    lines.append("")
    lines.append(
        "- **table** (default) -- Formatted with smart column selection, "
        "relative timestamps, and colorized status/severity."
    )
    lines.append("- **json** -- Raw JSON with exact timestamps for scripting.")
    lines.append("- **csv** -- CSV with headers for spreadsheet import.")
    lines.append("")
    lines.append("Additional flags:")
    lines.append("- `--fields col1,col2` -- Override column selection")
    lines.append("- `--no-header` -- Suppress table/CSV headers (scripting)")
    lines.append("- `--out <file>` -- Write output to a file")
    lines.append("- `--verbose` / `-v` -- Show request URL, query params, timing")
    lines.append("")

    # --- Common Workflows ---
    lines.append("## Common Workflows")
    lines.append("")
    lines.append("```bash")
    lines.append("# Export high-severity alerts as CSV")
    lines.append(
        "analysi alerts list --severity high --output csv --out high_alerts.csv"
    )
    lines.append("")
    lines.append("# Pipe alert IDs to another tool")
    lines.append(
        "analysi alerts list --output csv --fields alert_id --no-header | xargs ..."
    )
    lines.append("")
    lines.append("# Run a task with file input and save JSON output")
    lines.append(
        "analysi tasks run <task_id> --data @input.json --output json --out result.json"
    )
    lines.append("")
    lines.append("# Check all integration health")
    lines.append(
        "analysi integrations list --output json "
        "| jq '.[].id' "
        "| xargs -I{} analysi integrations health {}"
    )
    lines.append("```")
    lines.append("")

    # --- Common User Questions ---
    lines.append("## Common User Questions")
    lines.append("")
    lines.append(
        '- "How do I install the CLI?" -- '
        "Run `make cli-install && make cli-build`. "
        "Then `analysi auth login` to authenticate."
    )
    lines.append(
        '- "How do I switch tenants?" -- '
        "Use `--tenant <id>` on any command, or set "
        "`ANALYSI_TENANT_ID`."
    )
    lines.append(
        '- "How do I provide input data?" -- '
        'Use `--data \'{"key":"val"}\'` for inline JSON or '
        "`--data @filepath.json` to read from a file."
    )
    lines.append(
        '- "Why does the table only show some columns?" -- '
        "Auto-selects up to 8 columns. "
        "Use `--fields col1,col2,...` to override."
    )
    lines.append(
        '- "How do I get machine-readable output?" -- '
        "Use `--output json` or `--output csv`."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    config = load_config(CONFIG_PATH)

    commands = config.get("commands", {})
    if not commands:
        print(
            "ERROR: No commands found in CLI config.",
            file=sys.stderr,
        )
        sys.exit(1)

    topic_map = build_topic_map(config)
    markdown = generate_markdown(config, topic_map)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")

    # Summary
    total_ops = sum(len(info["operations"]) for info in topic_map.values())
    total_yaml = sum(
        1
        for info in topic_map.values()
        for op in info["operations"]
        if not op.get("hand_written")
    )
    total_hw = total_ops - total_yaml

    print(f"Generated {OUTPUT_PATH}")
    print(
        f"  {len(topic_map)} topics, {total_ops} commands "
        f"({total_yaml} from YAML, {total_hw} hand-written)"
    )


if __name__ == "__main__":
    main()

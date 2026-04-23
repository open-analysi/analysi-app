# Analysi CLI

Command-line interface for the [Analysi Security Platform](https://github.com/analysi). Manage alerts, tasks, workflows, and integrations from your terminal.

## Install

```bash
# From the project root
make cli-install   # npm install
make cli-build     # compile TypeScript
```

## Authenticate

```bash
analysi auth login
```

Interactive prompt asks for API URL, API key, and default tenant. Credentials are stored at `~/.config/analysi/credentials.json`.

## Usage

```bash
# Platform overview
analysi status

# List alerts
analysi alerts list
analysi alerts list --severity high --limit 10

# Get alert details
analysi alerts get <alert_id>
analysi alerts get <alert_id> --output json

# Search alerts
analysi alerts search --q "SQL injection"

# Trigger analysis
analysi alerts analyze <alert_id>

# List and inspect tasks
analysi tasks list
analysi tasks get <task_id>
analysi tasks run <task_id> --data @input.json

# Workflows
analysi workflows list
analysi workflows run <workflow_id> --data '{"alert_id": "..."}'

# Check integration health
analysi integrations list
analysi integrations health <integration_id>
analysi integrations runs <integration_id>

# Execution history
analysi task-runs list --status failed
analysi workflow-runs list --workflow_id <id>
analysi workflow-runs status <workflow_run_id>
```

## Output Formats

```bash
# Table (default) — human-readable with colors
analysi alerts list

# JSON — full data, pipe to jq
analysi alerts list --output json | jq '.[].title'

# CSV — spreadsheet-friendly
analysi alerts list --output csv > alerts.csv
```

## Useful Flags

| Flag | Short | What it does |
|------|-------|-------------|
| `--output` | `-o` | Output format: `table`, `json`, `csv` |
| `--fields` | | Pick specific columns: `--fields id,title,severity` |
| `--no-header` | | Suppress headers (useful for `wc -l`, `cut`, etc.) |
| `--out` | | Write to file: `--out report.json` |
| `--verbose` | `-v` | Show HTTP method, URL, timing |
| `--tenant` | `-t` | Override tenant (or set `ANALYSI_TENANT_ID`) |
| `--limit` | | Max results (default 25) |
| `--offset` | | Pagination offset |

## Scripting Examples

```bash
# Count high-severity alerts
analysi alerts list --severity high --output csv --no-header | wc -l

# Get all alert IDs
analysi alerts list --output csv --fields alert_id --no-header

# Export integration health to JSON
analysi status --output json --out status.json

# Debug a failing request
analysi alerts get bad-id --verbose
```

## Shell Completions

```bash
analysi autocomplete        # setup instructions
analysi autocomplete zsh    # generate for zsh
```

## Status Dashboard

`analysi status` shows a compact overview of the platform:

```
  Analysi Platform Status
  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

  📋 Alerts
     Status:   4 completed
     Severity: 3 high  1 medium

  ⚡ Task Runs
     50 completed

  ⚡ Workflow Runs
     9 completed

  🔌 Integrations
     ● Splunk Enterprise — Success rate: 100.0%
     ● VirusTotal — Success rate: 95.2%
     ● Slack Communication — Success rate: 100.0%
```

## Architecture

```
cli-config.yaml → generate-commands.ts → oclif command files → base-command.ts → API
```

Most commands are generated from a single YAML config file. Adding a new command is a YAML edit + `make cli-generate && make cli-build`.

See [CLAUDE.md](./CLAUDE.md) for development details.

## Commands

| Command | Description |
|---------|-------------|
| `status` | Platform dashboard |
| `auth login` | Interactive authentication |
| `alerts list` | List alerts with filters |
| `alerts get` | Get alert details |
| `alerts search` | Search alerts by query |
| `alerts analyze` | Start alert analysis |
| `tasks list` | List tasks |
| `tasks get` | Get task details |
| `tasks run` | Execute a task |
| `workflows list` | List workflows |
| `workflows get` | Get workflow details |
| `workflows run` | Execute a workflow |
| `integrations list` | List integrations |
| `integrations get` | Get integration details |
| `integrations health` | Check integration health |
| `integrations runs` | List integration runs |
| `task-runs list` | List task execution runs |
| `task-runs get` | Get task run details |
| `workflow-runs list` | List workflow execution runs |
| `workflow-runs get` | Get workflow run details |
| `workflow-runs status` | Get workflow run status |

## License

See the project root LICENSE file.

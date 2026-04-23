# Agent Source Files

Golden copies of agents managed in this repo. Edit these directly.

## Workflow

```bash
# 1. Edit the agent
vi agents/source/cybersec-task-builder.md

# 2. Assemble into production/
make package-agents

# 3. Commit both
git add agents/source/ agents/dist/
git commit -m "Update cybersec-task-builder agent"
```

## Agents

| Agent | Purpose |
|-------|---------|
| `cybersec-task-builder.md` | Builds Cy script tasks for security workflows |
| `cy-script-segment-tester.md` | Tests Cy script segments for correctness |
| `runbook-to-task-proposals.md` | Proposes tasks from runbook analysis |
| `splunk-spl-writer-basic.md` | Composes SPL queries for Cy scripts |
| `workflow-builder.md` | Assembles tasks into workflow pipelines |
| `runbook-match-agent.md` | Builds a runbook for a particular alert |


## See Also

- `agents/dist/` — assembled output for Docker deployment
- `scripts/agents_management/` — packaging scripts and config

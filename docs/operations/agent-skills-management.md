# Agent and Skills Management

This guide explains how to manage agents and skills for the Analysi alert processing system.

## Overview

The alert-worker container uses Claude Code agents to generate workflows from security alerts.

- **Agents**: Live in `agents/dist/` (committed to git), copied into containers at build time
- **Skills**: Shipped in the `foundation` content pack (`content/foundation/skills/`, committed to git). Installed per-tenant via `analysi packs install foundation`, which uploads each skill to the backend and persists it in the `knowledge_modules` table. At runtime, `DatabaseResourceStore` reads skills from that table.

> **Note**: `analysi-demo-loader` is **not** involved in skill distribution. It is only used for lab services, integration credentials, and replaying alert scenarios. Skills, tasks, KUs, workflows, KDG edges, and control event rules all ship via the packs system (Project Delos — see `docs/projects/delos.md` and `content/CLAUDE.md`).

## Directory Structure

```
agents/
├── source/               # Editable source agents (local agents registered in skilltree.yaml)
├── production/           # Production agents (deployed to alert-worker, includes remote agents)
│   ├── cy-script-segment-tester.md
│   ├── cybersec-task-builder.md
│   ├── runbook-match-agent.md
│   ├── runbook-to-task-proposals.md
│   ├── splunk-spl-writer-basic.md
│   └── workflow-builder.md
└── dev/                  # Development-only agents (not deployed)
```

`agents/source/` contains local agent source files referenced by `skilltree.yaml`. `agents/dist/` is the deployment artifact — it includes both local agents (copied from source) and remote agents (installed by skilltree from other repos).

## Development Workflows

### Normal Development (Using Committed Files)

Most of the time, you just build and deploy using files already committed to git:

```bash
# Build alert worker with production agents
make rebuild-alert-worker
```

No packaging step needed — Docker uses files already in the repository.

### Updating Agents from External Sources

When agents change in their external source locations (`~/.claude/agents`, etc.):

```bash
# 1. Package latest from external sources into agents/dist/
make package-agents

# 2. Review what changed
git status
git diff agents/dist/

# 3. Commit the updates
git add agents/dist/
git commit -m "Update production agents"

# 4. Rebuild with new files
make rebuild-alert-worker
```

### Working with Local Development Files

For local testing with custom agent directories:

```bash
# Override agent directory at runtime
ANALYSI_ALERT_PROCESSING_AGENT_DIR=/custom/agents poetry run python ...
```

## Runtime Agent Resolution

At runtime, the system searches for agents in this order (see `src/analysi/agentic_orchestration/config.py`):

1. `ANALYSI_ALERT_PROCESSING_AGENT_DIR` (if set) — single override directory
2. `/app/agents` — in Docker container (copied from `agents/dist/` by Dockerfile)
3. `{PROJECT_ROOT}/agents/dist` — in local dev

First match wins.

## Container Packaging

The Dockerfile (`deployments/docker/alerts-worker/Dockerfile`) copies agents in two steps:

```dockerfile
# 1. Copy to /app/agents (for Python code's get_agent_path())
COPY agents/dist /app/agents

# 2. Copy to ~/.claude/agents (for Claude Code CLI discovery)
RUN mkdir -p /home/appuser/.claude/agents && \
    cp -r /app/agents/* /home/appuser/.claude/agents/
```

## CI Verification

The CI pipeline (`smoke-test` job) verifies agent files are correctly present inside the alerts-worker container after Kind cluster deployment. See `.github/workflows/ci.yml` — "Verify agent files in alerts-worker container" step.

## Troubleshooting

### Agent Not Found Error

```
FileNotFoundError: Agent 'runbook-match-agent.md' not found in: /app/agents, ...
```

**Solutions:**
1. Verify agent exists: `ls agents/dist/runbook-match-agent.md`
2. Re-package if needed: `make package-agents`
3. Commit and rebuild: `git add agents/dist/ && git commit && make rebuild-alert-worker`

### Wrong Agent Version Used

The system uses the **first match** in the search order. To debug:

```python
from analysi.agentic_orchestration.config import get_agent_path
path = get_agent_path("runbook-match-agent.md")
print(f"Using: {path}")
```

If wrong version is found:
- Check override: `echo $ANALYSI_ALERT_PROCESSING_AGENT_DIR`
- Verify production agents: `ls agents/dist/`
- Re-package if needed: `make package-agents`

## Environment Variables Reference

### Runtime Configuration

- `ANALYSI_ALERT_PROCESSING_AGENT_DIR` — override agent search directory (single path)

## Related Documentation

- **Packaging Script**: `scripts/agents_management/package.py`
- **Source of Truth**: `skilltree.yaml` (prod vs dev dependencies)
- **Runtime Configuration**: `src/analysi/agentic_orchestration/CLAUDE.md`
- **Naming Conventions**: `CLAUDE.md` (Environment Variable Naming Convention section)

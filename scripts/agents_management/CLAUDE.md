# Agent & Skill Packaging

## Overview

`skilltree.yaml` is the single source of truth. Production dependencies (`group: prod`) are packaged into deployment directories. Dev dependencies are only used locally.

| What | Target | Command |
|------|--------|---------|
| Prod agents | `agents/dist/` | `make package-agents` |
| Prod skills | `content/foundation/skills/` | `make package-skills` |
| Check sync | — | `make check-skills` |

## How It Works

`package.py` reads `skilltree list --json` to discover prod dependencies, resolves each to its file on disk, and copies it to the deployment directory.

- **Local deps** (`source: ./agents/source/...` or `./skills/...`) — used directly
- **Remote deps** (`source: github.com/...`) — resolved from `.claude/skills/` or `.claude/agents/` where skilltree installs them

## Adding a New Agent or Skill

1. Add it to `skilltree.yaml` under `dependencies:` (not `dev-dependencies:`)
2. Run `skilltree install`
3. Run `make package-agents` or `make package-skills`
4. Commit the output

```bash
# Example: add a new prod agent
# 1. Edit skilltree.yaml, then:
skilltree install
make package-agents
git add agents/dist/ && git commit -m "Add new-agent"
```

## Skills

Skills are copied with underscore-renamed directories (e.g., `task-builder` → `task_builder/`). Each target directory's `manifest.json` is regenerated on every sync from the SKILL.md frontmatter (`name`, `description`, `version`) — do not hand-edit or commit manifests in `content/foundation/skills/`. Without a manifest, the pack installer silently skips the skill, so keep SKILL.md frontmatter complete in the source.

## Why Commit to Git?

1. **Reproducible Builds** — same commit = same agents and skills
2. **CI/CD Friendly** — no external dependencies during Docker build
3. **Version Control** — track exactly which versions were deployed
4. **Explicit Updates** — developers choose when to incorporate changes

## Related Documentation

- **Agent Source**: `agents/source/README.md`
- **Packaging Script**: `package.py` (unified, with `agents`/`skills`/`all` subcommands)
- **Runtime Config**: `src/analysi/agentic_orchestration/CLAUDE.md`

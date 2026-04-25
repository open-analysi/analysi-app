# Scripts Directory Guidelines

## Organization

Scripts are organized by domain into subdirectories. Do not add loose scripts at the root level.

```
scripts/
  agents_management/      # Agent/skill packaging
  ci/                     # CI/CD helper scripts
  code_quality_tools/     # Linters, audits, metrics
  database/               # Database maintenance (partitions, migrations)
  debugging/              # Inspection and debugging tools
  generate_chat_skills/   # Auto-generate chat skills from OpenAPI/manifests/CLI
  k8s/                    # Kubernetes cluster management (kind, kubectl, helm)
  make/                   # Shell scripts backing Makefile targets
  monitoring/             # System monitoring utilities
  observability/          # Monitoring stack management
  smoke_tests/            # Post-deploy health verification
```

## Naming

- Use lowercase with hyphens: `verify-integrations.sh`, not `verifyIntegrations.sh`
- Name scripts by what they do, not by project or phase
- For subdirectory scripts, drop the domain prefix: `scripts/k8s/local.sh`, not `scripts/k8s/k8s-local.sh`

## Conventions

- Start with `#!/usr/bin/env bash` and `set -euo pipefail`
- Use `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"` for relative paths
- Derive `REPO_ROOT` from script location, don't assume `pwd`
- Scripts called from the Makefile should not require arguments — use environment variables
- Add a usage comment at the top: `# Usage: local.sh [up|down|status]`

## Container Image Policy

**NEVER** include `docker push` in any script. Analysi images are private. Local scripts build and load images directly (e.g., `kind load docker-image`). Registry publishing is handled exclusively by CI/CD workflows in `.github/workflows/`.

## Adding New Scripts

1. Pick the right subdirectory (create one if no existing category fits)
2. Add a Makefile target if the script is a developer-facing command
3. Keep scripts focused — one script per concern

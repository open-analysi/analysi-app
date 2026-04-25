# Scripts Directory

Utility scripts for development, testing, debugging, and operations.

## Directory Structure

```
scripts/
  agents_management/       # Agent/skill packaging for Docker
  ci/                      # CI/CD helper scripts
  code_quality_tools/      # Linters, audits, metrics, benchmarks
  database/                # Database maintenance (partitions)
  debugging/               # Inspection and debugging tools
  generate_chat_skills/    # Auto-generate chat skills from OpenAPI/manifests/CLI
  k8s/                     # Kubernetes cluster management
  make/                    # Shell scripts backing Makefile targets
  monitoring/              # System monitoring (thermal exporter)
  observability/           # Monitoring stack management
  smoke_tests/             # Post-deploy health verification
```

## Quick Start

### Workflow Debugging

```bash
# List recent workflow executions
poetry run python scripts/debugging/inspect_workflow_execution.py --list

# Inspect specific workflow run
poetry run python scripts/debugging/inspect_workflow_execution.py --run-id <id>
```

- [inspect_workflow docs](debugging/README_inspect_workflow.md)

### Database Maintenance

```bash
make list-partitions       # Show partition counts
make clean-partitions      # Clean old test partitions
make validate-partitions   # Validate partition counts
```

### Code Quality

```bash
make code-quality          # Run all checks
make benchmark-api         # Benchmark API response times
make count-lines           # Track codebase size
```

## Adding New Scripts

1. Pick the right subdirectory (create one if no existing category fits)
2. Add a Makefile target if the script is a developer-facing command
3. Keep scripts focused — one script per concern
4. Add a README if the script needs usage documentation

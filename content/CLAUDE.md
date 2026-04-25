# Content Packs

Built-in content that ships with the Analysi platform. Each subdirectory is a **pack** — a directory of JSON/Cy files with a `manifest.json` at the root.

## Packs

| Pack | Purpose |
|------|---------|
| `foundation` | Core platform capabilities every tenant needs — alert pipeline tasks, integration tools, skills, knowledge units, KDG edges, control event rules |
| `examples` | Attack-specific investigations, demo workflows, and learning content — not required for platform operation |

## Pack Format

```
content/<pack-name>/
  manifest.json              # Required: name, version, description, type
  tasks/*.json + *.cy        # Task definitions + Cy scripts (paired by filename)
  skills/*/                  # Skill directories (each with manifest.json + SKILL.md)
  knowledge_units/*.json     # KU files (contain tables/documents/indexes arrays)
  workflows/*.json           # Workflow definitions
  knowledge_dependency_graph/edges.json   # KDG edges
  control_event_rules/*.json # Automation rules
```

## Installation

```bash
analysi packs install foundation -t <tenant>   # Install foundation pack
analysi packs install examples -t <tenant>     # Install examples (requires foundation first)
analysi packs list -t <tenant>                 # List installed packs
analysi packs uninstall examples -t <tenant>   # Remove a pack
```

Cross-pack dependencies are resolved automatically — workflows in `examples` can reference tasks from `foundation`.

## Content Attribution

Every component gets an `app` field set to the pack name during install. This enables:
- `GET /v1/{tenant}/packs` — aggregate installed packs with component counts
- `DELETE /v1/{tenant}/packs/{name}` — uninstall all components from a pack
- Filtering by pack on list endpoints: `?app=foundation`

## Categories Convention

Every component's `categories` array must start with the pack name (`Foundation` or `Examples`). Additional domain-specific categories follow. The CLI installer also adds the pack name at install time as a safety net.

```json
"categories": ["Foundation", "Threat Intelligence", "AbuseIPDB", "IP Analysis"]
```

## Content Placement Rules

**Foundation** — generic, reusable, integration-agnostic where possible:
- Alert pipeline tasks (`alert_context_generation`, `alert_disposition_determination`, etc.)
- Integration tool tasks (Splunk search, VirusTotal lookup, AD/LDAP queries)
- Skills and knowledge units
- KDG edges and control event rules

**Examples** — specific, educational, or demo-oriented:
- Attack-specific investigations (ProxyNotShell, SQL injection, CVE-specific)
- Demo EDR tasks (`echo_edr_*`)
- All workflows (investigation workflows are opinionated compositions)
- Playground/demo tasks

## Source of Truth

Content ships with the platform and can be installed via the CLI (`analysi packs install <name>`) without an external dependency.

## Contributing Content

1. Add files to the appropriate pack directory following the format above
2. Task files come in pairs: `my_task.json` (metadata) + `my_task.cy` (script)
3. Skill directories must contain `manifest.json` and `SKILL.md` at minimum
4. Run `make cli-test` to verify pack reader discovers your content
5. Test installation: create a test tenant, install the pack, verify component counts

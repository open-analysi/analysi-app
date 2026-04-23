# Skills

```
skills/
  source/   Edit here. Golden copies of prod skills managed in this repo.
            Packaged into content/foundation/skills/ by `make package-skills`.
  dev/      Dev-only skills (never shipped). For local Claude Code use.
```

Skills live in `skilltree.yaml`:
- `dependencies:` → prod skills (both local under `./skills/source/` and remote from vibes/cy-language)
- `dev-dependencies:` → dev-only skills (local under `./skills/dev/` or remote)

Remote prod skills are resolved at install time; only local prod skills live on disk under `skills/source/`.

## Naming convention: `{name}-integration`

Skills named with the `-integration` suffix document how to use a specific
Analysi integration (e.g., `tor-integration` accompanies the Tor exit-node
integration). They live alongside other prod skills under `skills/source/` and
ship in the foundation pack.

Use this suffix only for skills whose sole purpose is teaching agents/analysts
how to call a specific integration's actions — not for general domain skills
(e.g., `cybersecurity-analyst`, `splunk-skill`) or for the integration code
itself (which lives under `src/analysi/integrations/`).

Not every integration needs an accompanying skill — add one only when there is
non-trivial usage guidance worth shipping.

## Adding a new skill

**Prod (local):** add under `dependencies:` in `skilltree.yaml`, place source
under `skills/source/<name>/`, then:
```bash
skilltree install
make package-skills
git add skilltree.yaml skilltree.lock skills/source/<name>/ content/foundation/skills/
```

**Dev-only (local):** add under `dev-dependencies:` in `skilltree.yaml`, place
source under `skills/dev/<name>/`, then `skilltree install`.

See `scripts/agents_management/CLAUDE.md` for the full packaging flow.

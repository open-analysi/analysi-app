# Foundation Skills — Auto-Generated

**Do NOT edit, add, or delete files in this directory by hand.**

These skill directories are the payload of the `foundation` content pack. They are auto-generated from the project-root `skills/` directory by `make package-skills` (see `scripts/agents_management/package.py`).

## How to modify a skill

1. Edit the source in `skills/<skill-name>/` at the project root.
2. Run `make package-skills` to sync into this directory (directory names get hyphens → underscores).
3. Commit both `skills/` and `content/foundation/skills/` together.
4. The pre-commit hook `check-skills` (a.k.a. `check-foundation-skills`) will catch drift.

## How this gets into the running platform

```
skills/<name>/  (source of truth)
  → make package-skills
  → content/foundation/skills/<name>/  (this directory)
  → analysi packs install foundation -t <tenant>
  → POST /skills/import → knowledge_modules table
  → DatabaseResourceStore reads at runtime
```

## Adding a new skill

1. Add the skill under `skills/<skill-name>/` at the project root.
2. Register it in `skilltree.yml` under `dependencies:` (group `prod`).
3. Run `skilltree install && make package-skills`.
4. Commit.

## See also

- `content/CLAUDE.md` — pack format and content placement rules
- `docs/projects/delos.md` — content packs design
- `scripts/agents_management/CLAUDE.md` — packaging internals
- `docs/operations/agent-skills-management.md` — operations guide

# Project Delos — Content Packs & Platform Management

## Key Points

- **Content Packs**: Portable bundles of tasks, skills, KUs, workflows, KDG edges, and control event rules. Installed via the CLI, tagged with the `app` field on Component and Workflow. No new tables — pack state is derived from `app` values.
- **Two built-in packs**: `foundation` (core security tasks, skills, KUs — every tenant needs this) and `examples` (sample workflows and toy tasks for learning). Ship under `content/` in the repo.
- **External packs**: Customers can author their own packs as `.tgz`/`.zip` archives. The CLI unpacks and calls existing REST APIs — no new upload endpoint.
- **Content trust model**: Built-in packs skip validation (already committed and reviewed). External packs require full content validation for `admin` and `owner` roles. Only `platform_admin` can bypass validation on external content.
- **Platform management**: New `/platform/v1/` API prefix for cross-tenant operations — tenant CRUD, platform health, queue stats. Gated on `platform_admin` (Keycloak realm role).
- **Tenant table**: New `tenant` PostgreSQL table makes tenants first-class entities. Currently tenants are implicit (referenced by string but no central registry). Existing `tenant_id` columns are not converted to FKs in v1.
- **Tenant lifecycle**: Explicit `create` (with `--dry-run` validation), `describe`, `delete` (cascade-deletes everything including in-flight work). The `default` tenant is a convention, not a special-cased entity.
- **API reorganization**: `/admin/v1/` is retired. Bulk-delete endpoints move to `/v1/{tenant}/` gated on `owner`. Platform operations move to `/platform/v1/` gated on `platform_admin`.
- **CLI structure**: `analysi packs install/list/uninstall` for tenant-scoped operations. `analysi platform tenants/provision/health` for platform operations.
- **Install semantics**: Fail on conflict by default, `--force` to overwrite. Uninstall detects user-modified components and refuses unless `--force`.
- **`--reset` provision**: `platform provision <tenant> --packs X --reset` deletes the entire tenant and recreates it before installing packs.
- **Spec**: `docs/specs/ContentPacks.md`

## Terminology

| Term | Definition |
|------|-----------|
| **Content Pack** | A directory or archive containing tasks, skills, KUs, workflows, KDG edges, and control event rules with a `manifest.json`. Installed into a tenant via the CLI. |
| **Built-in pack** | A pack that ships with the repo under `content/`. Trusted — content validation is skipped during installation. |
| **External pack** | A pack provided as a `.tgz`/`.zip` archive from outside the repo. Untrusted — goes through full content validation unless installed by `platform_admin`. |
| **`app` field** | A `VARCHAR(100)` on Component (existing) and Workflow (new migration). Set to the pack name during installation. Used to query installed packs and support uninstall. |
| **`foundation`** | The core built-in pack. Security automation tasks, essential skills, reference KUs. The platform feels empty without it. |
| **`examples`** | Optional built-in pack. Sample workflows and toy tasks demonstrating platform patterns. |
| **Platform admin** | Cross-tenant operator role assigned via Keycloak realm role. Can create/delete tenants, provision packs across tenants, bypass validation on external packs, monitor platform health. Not stored in the `memberships` table. |
| **Tenant admin** | The `admin` role within a tenant. Manages integrations, resources, and users. Can install packs (built-in: skip validation; external: with validation). |
| **Tenant owner** | The `owner` role within a tenant. Same pack installation capabilities as admin. Additionally manages member roles and removals. |
| **`/platform/v1/`** | New API prefix for platform-scoped operations (tenant CRUD, health, queue stats). Replaces the platform-scoped portions of the retired `/admin/v1/` prefix. |
| **`tenant` table** | New PostgreSQL table making tenants first-class entities. Previously tenants were implicit string references with no central registry. |
| **Tenant lifecycle** | Explicit create (with `--dry-run`) → provision → describe → delete. Tenant delete cascade-removes all data unconditionally, requires `--confirm <name>`. |

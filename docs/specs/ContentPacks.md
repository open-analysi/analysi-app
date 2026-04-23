+++
version = "1.0"
date = "2026-03-23"
status = "active"

[[changelog]]
version = "1.0"
date = "2026-03-23"
summary = "Portable content bundles (Project Delos)"
+++

# Content Packs - v1

## Overview

Content Packs are portable, installable bundles of platform content — tasks, skills, knowledge units, workflows, KDG edges, and control event rules. They solve two problems:

1. **Empty platform on first startup.** New users run `make up` and get an empty shell. Foundation content (core security tasks, skills, essential KUs) should be installable with a single command — no external repos, no platform admin credentials.

2. **No packaging model for reusable content.** Tasks, skills, and workflows that belong together have no formal grouping. The `app` field on Component exists but is unused (`"default"` everywhere). There's no way to install, list, or remove a coherent set of content as a unit.

Content Packs are **lightweight and file-based**. There is no `packs` table or runtime entity. A pack is a directory (or archive) of JSON/Cy files. The CLI unpacks it and calls existing REST APIs to create the components. The `app` field on each component is set to the pack name, enabling list and uninstall queries.

---

## Scope

### In Scope (v1)

- `content/` directory in the repo with two built-in packs: `foundation` and `examples`
- CLI commands: `packs install`, `packs list`, `packs uninstall`
- Pack format: directory/archive with tasks, skills, KUs, workflows, KDG edges, control event rules
- Migration: add `app` field to `workflow` table
- Content trust model: built-in packs skip validation, external packs require validation
- Platform CLI commands: `platform tenants create/list/delete/describe`, `platform provision`
- API prefix reorganization: `/admin/v1/` bulk-delete endpoints move to tenant-scoped routes
- Tenant lifecycle: explicit create, describe, delete (replaces implicit tenant creation)

### Out of Scope (v1)

- Pack versioning or upgrade-in-place semantics
- Pack dependency declarations (e.g., "examples requires foundation")
- Marketplace / pack registry
- Automatic pack installation on tenant creation (document the CLI commands instead)
- UI for pack management

---

## Content Trust Model

Trust depends on **where the content comes from**, not just who's installing it.

### Content Sources

**Built-in packs** ship with the repo under `content/`. They are committed, reviewed, and tested. Content validation (Cy script checks, skill structure validation) is **skipped** because the content is already trusted.

**External packs** are provided as `.tgz` or `.zip` archives from outside the repo. They go through **full content validation** — Cy script syntax, skill manifest checks, schema validation — to prevent malicious or broken content.

### Role × Source Matrix

| | Built-in packs | External packs |
|---|---|---|
| **admin** | Install, skip validation | Install, **with validation** |
| **owner** | Install, skip validation | Install, **with validation** |
| **platform_admin** | Install, skip validation | Install, **skip validation** |

- `admin` and `owner` have identical pack installation capabilities
- Only `platform_admin` can bypass validation on external content — they are the platform operator and accept that responsibility
- Roles below `admin` (analyst, viewer) cannot install packs

---

## Role Clarification

The existing role model is unchanged. This spec clarifies the intended scope of each role.

### Tenant-Scoped Roles

| Role | Purpose |
|------|---------|
| **viewer** | Read-only access to tenant resources |
| **analyst** | Create and execute tasks, workflows, alerts |
| **admin** | Manage integrations, delete resources, invite users, **install content packs** |
| **owner** | Tenant governance — member role changes, member removal, install content packs |

`admin` vs `owner`: The difference is **people management**. Owner controls who is in the tenant and what roles they have. Admin manages resources and day-to-day operations. For pack installation, they are equivalent.

### Platform-Scoped Role

| Role | Purpose |
|------|---------|
| **platform_admin** | Cross-tenant operator. Creates/deletes tenants, provisions content across tenants, bypasses validation on external packs, monitors platform health. Assigned via Keycloak realm role, not the memberships table. |

### System Role

| Role | Purpose |
|------|---------|
| **system** | Background workers. Tenant-scoped API keys with explicit permissions. Cannot install packs. |

---

## Install Semantics

### Install Behavior

- **Default:** Fail on conflict if a component with the same `cy_name` + `tenant_id` already exists. Report which components are blocking.
- **`--force`:** Overwrite existing components that conflict. Enables re-running after content updates.

This keeps installation safe by default — a user won't accidentally overwrite customized components. The `--force` flag provides the escape hatch for reprovisioning.

### Uninstall Behavior

Uninstall removes all components tagged with the pack's `app` name.

- **Default:** Check for user modifications (components where `updated_by != created_by` or `updated_at` significantly after `created_at`). If modified components are found, list them and refuse.
- **`--force`:** Delete everything including modified components.

### Integration Dependencies

Tasks in a pack may reference integration tools (e.g., `app::virustotal::ip_lookup`). The pack does **not** declare or enforce integration dependencies. If an integration is not configured, the task fails at runtime — same behavior as today. Visibility into which tasks need which integrations is a separate platform feature, not pack-specific.

---

## CLI Commands

### Tenant-Scoped (existing auth context)

```bash
# Install a built-in pack (ships with repo)
analysi packs install foundation
analysi packs install examples

# Install an external pack (from archive)
analysi packs install ./my-custom-pack.tgz

# Force install (overwrite existing components)
analysi packs install foundation --force

# List installed packs in current tenant
analysi packs list

# Uninstall a pack (remove all components tagged with that app name)
analysi packs uninstall examples

# Force uninstall (including user-modified components)
analysi packs uninstall examples --force
```

The CLI resolves built-in pack names to `content/<name>/` in the repo. For archives, it unpacks to a temp directory. In both cases, it reads the manifest, then calls REST APIs in dependency order.

### Platform-Scoped (requires platform_admin)

```bash
# Authenticate as platform admin
analysi platform auth login

# Tenant lifecycle
analysi platform tenants create acme-corp
analysi platform tenants list
analysi platform tenants describe acme-corp
analysi platform tenants delete acme-corp --confirm acme-corp

# Provision packs into a specific tenant
analysi platform provision acme-corp --packs foundation,examples

# Wipe and re-provision
analysi platform provision acme-corp --packs foundation --reset

# Platform health
analysi platform health
analysi platform queue stats
```

`platform provision` does the same thing as `packs install` — unpacks files, calls REST APIs — but targets a specified tenant using platform_admin credentials.

---

## Tenant Lifecycle

Currently tenants appear implicitly — there is no `tenant` table in PostgreSQL. This spec introduces:

1. A `tenant` table to make tenants first-class entities in the database.
2. Explicit tenant management via `/platform/v1/` endpoints, gated on `platform_admin`.

### Tenant Table (New)

```sql
CREATE TABLE tenant (
    id VARCHAR(255) PRIMARY KEY,           -- tenant identifier (e.g., "acme-corp")
    name VARCHAR(255) NOT NULL,            -- display name
    status VARCHAR(50) NOT NULL DEFAULT 'active',  -- active, suspended
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
```

All existing tables that reference `tenant_id` as a string column remain unchanged — the `tenant.id` is the same string value. The new table provides a single source of truth for which tenants exist and allows platform-level queries (list all tenants, validate tenant exists before operations).

### The `default` Tenant

The `default` tenant is created by init scripts as a convenience for local development. It is **not** a hard-coded or protected concept — it can be deleted and recreated like any other tenant. The name `default` is a convention, not a contract.

### Tenant Create

Requires a `tenant_id` (the string identifier). The tenant name is validated before creation. Supports a `--dry-run` flag that validates the tenant ID (format, uniqueness) without actually creating it.

```bash
analysi platform tenants create acme-corp --dry-run    # validate only
analysi platform tenants create acme-corp              # create for real
```

The API equivalent:

```
POST /platform/v1/tenants?dry_run=true    # validate, return 200 if valid
POST /platform/v1/tenants                 # create
```

On create: insert `tenant` row, create system API key, set up default configuration.

### Operations

| Operation | What Happens |
|-----------|-------------|
| **create** | Validate tenant ID, insert tenant record, create system API key, set up default configuration. Supports `--dry-run`. |
| **provision** | Install specified packs into the tenant (calls REST APIs with pack content) |
| **describe** | Show tenant metadata, member count, installed packs, component counts |
| **delete** | Cascade delete **all** tenant data unconditionally — the tenant row itself, components, workflows, runs (including in-flight), alerts, analyses, KDG edges, control event rules, memberships, API keys. Requires `--confirm <tenant-name>` as a safety measure. |

Tenant delete removes everything including running task runs, active workflow executions, and paused HITL analyses. There is no "active work" guard — this matches the current demo-loader behavior and provides a clean-slate reset.

### `--reset` on Provision

`platform provision <tenant> --packs foundation --reset` deletes the entire tenant and recreates it before installing packs. This is equivalent to delete + create + provision as a single command.

### Getting Started (Single-Tenant / Local)

```bash
make up                              # start the platform
analysi auth login                   # login to default tenant
analysi packs install foundation     # install core content
```

No platform admin needed. The `default` tenant exists from init scripts. Three commands to a working system.

### Multi-Tenant Provisioning

```bash
analysi platform auth login
analysi platform tenants create acme-corp
analysi platform provision acme-corp --packs foundation,examples
```

---

## Pack Format

Reuses the structure from `analysi-demo-loader/datasets/static_components/`. A pack is a directory with this layout:

```
<pack-name>/
  manifest.json              # Pack metadata and loading order
  tasks/                     # Task definitions (JSON + .cy scripts)
  skills/                    # Skill packages (directory with SKILL.md + manifest.json)
  knowledge_units/           # KU definitions (tables, documents, indexes)
  workflows/                 # Workflow definitions (JSON with nodes/edges)
  knowledge_dependency_graph/ # KDG edge definitions
  control_event_rules/       # Control event rule definitions
```

### manifest.json

```json
{
  "name": "foundation",
  "version": "1.0.0",
  "description": "Core security tasks, skills, and knowledge units",
  "type": "built-in"
}
```

The `type` field indicates trust level:
- `"built-in"` — ships with the repo, validation skipped
- `"external"` — user-provided, validation enforced (unless platform_admin)

### Loading Order

The CLI installs components in dependency order:

1. Knowledge Units (documents, tables, indexes)
2. Tasks (may reference KU tools)
3. Skills (reference KU documents)
4. Workflows (compose tasks)
5. KDG edges (link components)
6. Control event rules (reference tasks/workflows by cy_name)

This matches the existing demo-loader ordering.

---

## Built-In Packs

### foundation

Core content every tenant needs. The platform feels empty without this.

- Security automation tasks (triage, enrichment, investigation)
- Core skills (task-builder, workflow-builder)
- Essential knowledge units (critical asset tables, reference documents)
- KDG edges connecting tasks to their KU dependencies
- Control event rules for standard post-disposition actions

### examples

Sample content for learning and getting started. Optional.

- Example workflows demonstrating common patterns
- Toy tasks showing how to write Cy scripts
- Sample control event rules

---

## Schema Changes

### Migration: Create `tenant` Table

Tenants are currently implicit — referenced by `tenant_id` strings across tables but with no central registry. This migration creates one:

```sql
CREATE TABLE tenant (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Seed the default tenant for backwards compatibility
INSERT INTO tenant (id, name) VALUES ('default', 'Default');
```

Existing `tenant_id` columns on other tables are **not** converted to foreign keys in v1 — that would be a large migration with partition implications. The `tenant` table serves as the source of truth for tenant existence; application-level validation enforces consistency.

### Migration: Add `app` to Workflow

Workflows do not inherit from Component and currently have no `app` field. A migration adds it:

```sql
ALTER TABLE workflow ADD COLUMN app VARCHAR(100) NOT NULL DEFAULT 'default';
CREATE INDEX idx_workflow_app ON workflow(app);
```

This allows workflows to be tagged with the pack that created them, enabling `packs list` and `packs uninstall` to include workflows.

### No Packs Table

There is no `packs` table. Pack state is derived from the `app` field across components and workflows:

```sql
-- List installed packs for a tenant
SELECT app, COUNT(*) as component_count
FROM component
WHERE tenant_id = :tenant_id AND app != 'default'
GROUP BY app

UNION ALL

SELECT app, COUNT(*) as component_count
FROM workflow
WHERE tenant_id = :tenant_id AND app != 'default'
GROUP BY app;
```

---

## API Changes

### Existing APIs (no changes)

Pack installation calls existing endpoints:
- `POST /v1/{tenant}/tasks`
- `POST /v1/{tenant}/knowledge-units/{type}`
- `POST /v1/{tenant}/skills/import`
- `POST /v1/{tenant}/workflows`
- `POST /v1/{tenant}/kdg/edges`
- `POST /v1/{tenant}/control-event-rules`

The `app` field is set on each request body to the pack name.

### New: Packs Query Endpoint

A lightweight endpoint to support `packs list`:

```
GET /v1/{tenant}/packs
```

Returns distinct `app` values with component counts. Requires `viewer` or above.

Response:
```json
{
  "data": [
    {
      "name": "foundation",
      "components": {"tasks": 34, "skills": 5, "knowledge_units": 12, "workflows": 0}
    },
    {
      "name": "examples",
      "components": {"tasks": 2, "skills": 0, "knowledge_units": 0, "workflows": 3}
    }
  ],
  "meta": {"total": 2, "request_id": "..."}
}
```

### New: Platform Tenant Management

New endpoints under a platform-scoped prefix (requires `platform_admin`):

```
POST   /platform/v1/tenants                    # Create tenant (supports ?dry_run=true)
GET    /platform/v1/tenants                    # List tenants (replaces /admin/v1/tenants-with-schedules)
GET    /platform/v1/tenants/{tenant_id}        # Describe tenant
DELETE /platform/v1/tenants/{tenant_id}        # Delete tenant + all data
GET    /platform/v1/health/db                  # Database health (moved from /admin/v1/)
GET    /platform/v1/queue/stats                # Analysis queue stats (moved from /admin/v1/)
```

`GET /platform/v1/tenants` is the proper replacement for the stopgap `GET /admin/v1/tenants-with-schedules`. It returns all tenants from the new `tenant` table with optional filters (e.g., `?status=active`, `?has_schedules=true`).

### API Prefix Reorganization

The current `/admin/v1/` prefix conflates platform operations with tenant-scoped destructive operations. This spec reorganizes them:

**Bulk-delete endpoints → tenant-scoped, gated on `owner` role:**

| Current | Proposed |
|---------|----------|
| `DELETE /admin/v1/{tenant}/task-runs` | `DELETE /v1/{tenant}/task-runs` |
| `DELETE /admin/v1/{tenant}/workflow-runs` | `DELETE /v1/{tenant}/workflow-runs` |
| `DELETE /admin/v1/{tenant}/all-runs` | `DELETE /v1/{tenant}/runs` |
| `DELETE /admin/v1/{tenant}/analysis-groups` | `DELETE /v1/{tenant}/analysis-groups` |
| `DELETE /admin/v1/{tenant}/workflow-generations` | `DELETE /v1/{tenant}/workflow-generations` |
| `DELETE /admin/v1/{tenant}/alert-analyses` | `DELETE /v1/{tenant}/alert-analyses` |
| `DELETE /admin/v1/{tenant}/alert-routing-rules` | `DELETE /v1/{tenant}/alert-routing-rules` |
| `DELETE /admin/v1/{tenant}/audit-trail` | `DELETE /v1/{tenant}/audit-trail` |
| `DELETE /admin/v1/{tenant}/analysis-queue` | `DELETE /v1/{tenant}/analysis-queue` |

These are tenant-scoped operations that don't require cross-tenant access. Gating on `owner` instead of `platform_admin` allows tenant owners to manage their own data.

**Platform operations → `/platform/v1/`, gated on `platform_admin`:**

| Current | Proposed |
|---------|----------|
| `GET /admin/v1/analysis-queue/stats` | `GET /platform/v1/queue/stats` |
| `GET /admin/v1/health/db` | `GET /platform/v1/health/db` |
| `GET /admin/v1/tenants-with-schedules` | `GET /platform/v1/tenants` (with `?has_schedules=true` filter) |
| `POST /admin/v1/trigger-alert-pull` | `POST /platform/v1/trigger-alert-pull` |

**Dev utilities → tenant-scoped, gated on `admin` role:**

| Current | Proposed |
|---------|----------|
| `POST /admin/v1/{tenant}/alerts/convert` | `POST /v1/{tenant}/alerts/convert` |
| `POST /admin/v1/{tenant}/alerts/batch-convert` | `POST /v1/{tenant}/alerts/batch-convert` |

The `/admin/v1/` prefix is retired.

---

## What Stays in the Demo-Loader

The demo-loader project (`analysi-demo-loader`) retains:

- **Integration configurations with API keys** — environment-specific secrets (Splunk, VirusTotal, etc.)
- **Alert scenarios** — Splunk events, EDR data, test alerts for demonstration
- **LDAP population** — dev infrastructure
- **Echo EDR server data** — dev/test fixtures

Everything else — tasks, skills, workflows, KUs, KDG edges, control event rules — moves into built-in packs under `content/` in the main repo.

The demo-loader authenticates as `platform_admin` and targets specific tenants. Its workflow becomes:

```bash
# Platform provisioning (replaces bulk of demo-loader)
analysi platform tenants delete demo --confirm demo
analysi platform tenants create demo
analysi platform provision demo --packs foundation,examples

# Demo-loader handles the rest (env-specific)
demo-loader integrations load --tenant demo    # configs + API keys
demo-loader scenarios load --tenant demo       # alert scenarios + events
```

---

## File Locations

| Component | Path |
|-----------|------|
| Built-in packs | `content/foundation/`, `content/examples/` |
| CLI pack commands | `cli/src/commands/packs/` |
| CLI platform commands | `cli/src/commands/platform/` |
| Packs query endpoint | `src/analysi/routers/packs.py` |
| Platform tenant endpoints | `src/analysi/routers/platform.py` |
| Workflow `app` migration | `migrations/flyway/sql/V{next}__add_app_to_workflow.sql` |
| Pack format spec | This document |

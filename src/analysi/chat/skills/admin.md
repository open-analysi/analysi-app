# Administration and Settings

This document covers the administrative features of the Analysi platform: role-based access control, tenant management, audit trail, control events, API keys, and configuration.

## RBAC: Roles and Permissions

Analysi uses role-based access control (Project Mikonos). Users are assigned roles within each tenant through memberships. A user can belong to multiple tenants with different roles in each.

### Roles (least to most privileged)

1. **viewer** -- Read-only access to tasks, workflows, alerts, integrations, KUs, skills, control events, audit trail, and API keys. Can use chat.
2. **analyst** -- Everything viewer can do, plus: create/update/execute tasks and workflows, create/update alerts, create/update KUs, execute integrations, create/revoke API keys.
3. **admin** -- Everything analyst can do, plus: delete tasks/workflows/alerts/KUs, full integration CRUD, skill CRUD, control event management, member management (read and invite).
4. **owner** -- Everything admin can do, plus: update and remove members.
5. **platform_admin** -- Bypasses all permission checks entirely. Reserved for platform operators. Not in the standard permission map -- handled at the enforcement layer.

There is also a **system** role used by automated workers (ARQ jobs, internal services). It has a curated set of permissions for pipeline operations and intentionally does not inherit from viewer. System keys never get platform_admin to prevent privilege escalation.

### Permission Model

Permissions are `(resource, action)` pairs. Resources include: `tasks`, `workflows`, `alerts`, `integrations`, `knowledge_units`, `skills`, `control_events`, `audit_trail`, `api_keys`, `users`, `members`, `chat`. Actions include: `read`, `create`, `update`, `delete`, `execute`, `invite`.

Role resolution: local membership is the source of truth (not JWT claims, which may be stale). When a user authenticates, their roles are looked up from the `memberships` table. Multi-role resolution uses the union of all role permission sets.

Both the REST API and MCP API enforce permissions through parallel paths that must stay in sync. REST uses `require_permission()` FastAPI dependencies; MCP uses `check_mcp_permission()` per-tool.

## Tenant Management

Tenants are the primary isolation boundary. Every API path is scoped by tenant: `/v1/{tenant}/...`. Each tenant has its own:
- Tasks, workflows, KUs, skills
- Alerts and analysis pipelines
- Integrations and credentials
- Members and roles
- Audit trail
- Control event rules

Users are associated with tenants via the `memberships` table. A user can be a member of multiple tenants. The `tenant_id` is included in every database query to enforce isolation.

### Members

- Admins can list members and send invitations.
- Owners can additionally update member roles and remove members.
- Invitations are single-use, time-limited tokens. The invited user accepts the invitation to join the tenant with the assigned role.

See the **api** skill for endpoint details.

## Audit Trail

The Activity Audit Trail tracks all user and system actions for compliance and investigation. It is append-only and partitioned monthly by `created_at` with a 365-day retention period (configurable via Helm).

Each audit event records:
- `actor_id` -- UUID of the user who performed the action
- `actor_type` -- "user", "system", "api_key", or "workflow"
- `source` -- subsystem: "rest_api", "mcp", "ui", or "internal"
- `action` -- what happened (e.g., "workflow.execute", "api_key.created", "hitl.question_answered", "chat.message_sent")
- `resource_type` -- affected resource type (e.g., "workflow", "alert", "api_key", "conversation")
- `resource_id` -- ID of the affected resource
- `details` -- JSONB with additional structured context
- `ip_address`, `user_agent`, `request_id` -- request metadata

### Audit API

Supported filters: `actor_id`, `source`, `action` (supports prefix matching with `%`), `resource_type`, `resource_id`, `from_date`, `to_date`. Results are ordered newest-first.

Viewer role and above can read audit events. The `actor_id` is always set from the authenticated user's identity (cannot be spoofed by the client).

## Control Events

The control event bus (Project Tilos) is a transactional outbox pattern for automation triggers. When something happens in the platform (e.g., an alert analysis completes, a disposition is set), a control event is emitted. Rules map events to tasks or workflows.

### How it works

1. **Producers** insert a `control_events` row (status: "pending") in the same DB transaction as the business state change.
2. **Consumer cron** (`consume_control_events`) polls every 5-10 seconds, claims pending events with `FOR UPDATE SKIP LOCKED`.
3. **Fan-out channels** (e.g., `disposition:ready`, `analysis:failed`) look up matching rules in `control_event_rules` and enqueue one ARQ job per rule.
4. **Internal channels** (e.g., `workflow:ready`, `human:responded`) have hardcoded single handlers.
5. Delivery is at-least-once; targets must be idempotent using `event_id`.

### Control Event Rules

Rules bind a `(tenant, channel)` pair to a task or workflow target. When an event arrives on that channel, the target is executed with the event payload as input.

Rule fields:
- `channel` -- event channel to listen on (e.g., "disposition:ready")
- `target_type` -- "task" or "workflow"
- `target_id` -- UUID of the target task or workflow
- `name` -- human-readable rule name
- `enabled` -- toggle on/off
- `config` -- JSONB for additional configuration

## API Keys

API keys provide programmatic access to the Analysi API without JWT tokens. They are used for CLI authentication, CI/CD pipelines, and service-to-service calls.

Key properties:
- The plaintext secret is shown exactly once at creation time and never stored (only the SHA-256 hash is persisted).
- Keys are scoped to a tenant and optionally to a user.
- Keys can have limited scopes (JSONB array) restricting which operations they can perform.
- Keys have an optional `expires_at` for automatic expiration.
- `key_prefix` (first 8-16 chars) is stored for identification in logs.
- `last_used_at` is updated on each use.

All API key lifecycle events (created, revoked) are recorded in the audit trail.

System keys (where `user_id` is NULL) operate under the `system` role, not `platform_admin`. This is an intentional security boundary -- system keys get only the permissions explicitly listed in `_SYSTEM_PERMS`, preventing privilege escalation.

## Common User Questions

- "How do I invite a team member?" -- As an admin or owner, use the Members API to create an invitation with the desired role. The invited user receives a token to accept.
- "How do I set up an automation rule?" -- Create a control event rule binding a channel (e.g., "disposition:ready") to a task or workflow. When events arrive on that channel, your target executes automatically.
- "How do I create an API key for CI/CD?" -- Use the API keys endpoint to create a key with appropriate scopes. Copy the plaintext secret immediately -- it will not be shown again.
- "Who did what and when?" -- Query the audit trail API with filters for actor, action, resource, and date range.
- "What roles can delete things?" -- Only admin and above can delete tasks, workflows, alerts, KUs, and integrations. Analysts can create and update but not delete.
- "How do I change someone's role?" -- Only the owner role can update member roles. Use the Members API to change the role assignment.

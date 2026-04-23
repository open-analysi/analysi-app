---
name: integrations-developer
description: Build new third-party integrations for the Naxos framework. Use when adding connectors to external tools (SIEM, EDR, threat intel, ticketing), writing IntegrationAction subclasses, creating manifest.json files, or understanding the archetype system. NOT for using integrations from Cy scripts (use task-builder for that).
dependencies:
  - task-builder
---

# Building Integrations for Analysi

## Overview

Integrations connect Analysi to external security tools (Splunk, VirusTotal, AbuseIPDB, ServiceNow, etc.) using the **Naxos framework**. Each integration is a self-contained package with a manifest, action classes, and optional schemas.

## When to Use This Skill

- Adding a new third-party integration
- Modifying an existing integration's actions
- Understanding manifest.json structure
- Working with the archetype system
- Debugging integration execution or credential injection

**Do NOT use for:** Calling integrations from Cy scripts or Tasks (use `task-builder` instead).

## Integration Package Structure

```
src/analysi/integrations/framework/integrations/{name}/
├── __init__.py           # Exports action classes
├── manifest.json         # Declares actions, schemas, archetypes
└── actions.py            # IntegrationAction subclasses
```

## Quick Start: Adding a New Integration

### 1. Create the manifest

```json
{
  "id": "your_integration",
  "app": "your_integration",
  "name": "Your Integration",
  "version": "1.0.0",
  "description": "Connect to Your Service",
  "archetypes": ["ThreatIntel"],
  "priority": 50,
  "requires_credentials": true,

  "integration_id_config": {
    "default": "your-integration-main",
    "pattern": "^[a-z0-9][a-z0-9-]*$",
    "placeholder": "your-integration-main",
    "display_name": "Integration ID",
    "description": "Unique identifier for this integration instance"
  },

  "archetype_mappings": {
    "ThreatIntel": {
      "lookup_ip": "lookup_ip"
    }
  },

  "credential_schema": {
    "type": "object",
    "properties": {
      "api_key": {
        "type": "string",
        "display_name": "API Key",
        "description": "API authentication key",
        "format": "password",
        "required": true
      }
    }
  },
  "settings_schema": {
    "type": "object",
    "properties": {
      "base_url": {
        "type": "string",
        "display_name": "Base URL",
        "description": "API base URL",
        "default": "https://api.example.com"
      },
      "timeout": {
        "type": "integer",
        "display_name": "Request Timeout",
        "description": "HTTP request timeout in seconds",
        "default": 30
      }
    }
  },
  "actions": [
    {
      "id": "lookup_ip",
      "name": "Lookup IP Reputation",
      "description": "Check IP against threat intelligence",
      "categories": ["threat_intel"],
      "cy_name": "lookup_ip",
      "enabled": true,
      "params_schema": {
        "type": "object",
        "properties": {
          "ip": {"type": "string"}
        },
        "required": ["ip"]
      }
    },
    {
      "id": "health_check",
      "name": "Health Check",
      "description": "Verify API connectivity",
      "categories": ["health_monitoring"],
      "cy_name": "health_check",
      "enabled": true
    }
  ]
}
```

**Key fields:**
- `categories` (list) — classifies the action (NOT `type` or `purpose` — those are deprecated/ignored)
- `cy_name` — simple name like `"lookup_ip"` (NOT `"app::lookup_ip"` — namespace added automatically)
- `archetypes` — which Archetype enum values this integration serves (PascalCase: `"ThreatIntel"`, not `"THREAT_INTEL"`)
- `archetype_mappings` — maps abstract archetype methods to concrete action IDs (REQUIRED)
- `priority` — higher = preferred when multiple integrations serve the same archetype (1-100)
- `requires_credentials` — set to `false` for free/public services that don't need authentication (default: `true`)
- `enabled` — per-action toggle (default: `true`)

### 2. Write action classes

Action class names follow the convention: `action_id` → PascalCase + `Action` suffix.
E.g., `lookup_ip` → `LookupIpAction`, `health_check` → `HealthCheckAction`.

```python
from typing import Any

from analysi.integrations.framework.base import IntegrationAction


class HealthCheckAction(IntegrationAction):
    """Check API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result("Missing API key", error_type="ConfigurationError")

        response = await self.http_request(
            url=f"{self.settings.get('base_url', 'https://api.example.com')}/v1/status",
            headers={"X-API-Key": api_key},
        )
        return self.success_result(data={"healthy": True})


class LookupIpAction(IntegrationAction):
    """Look up IP reputation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result("Missing required parameter: ip", error_type="ValidationError")

        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result("Missing API key", error_type="ConfigurationError")

        try:
            response = await self.http_request(
                url=f"{self.settings.get('base_url', 'https://api.example.com')}/v1/lookup",
                params={"ip": ip},
                headers={"X-API-Key": api_key},
            )
            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("ip_not_found", ip=ip)
                return self.success_result(not_found=True, data={"ip": ip})
            self.log_error("lookup_ip_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("lookup_ip_failed", error=e)
            return self.error_result(e)
```

**Available on `self`:**
- `self.credentials` — tenant-scoped secrets from Vault
- `self.settings` — tenant-scoped configuration
- `self.integration_id`, `self.action_id`
- `self.tenant_id`, `self.job_id`, `self.run_id` (from ctx)
- `self.http_request()` — async HTTP with built-in retry via `integration_retry_policy` (retries 5xx, 429, network errors with exponential backoff)
- `self.success_result()` / `self.error_result()` — standardized responses with timestamp, integration_id, action_id
- `self.get_timeout()`, `self.get_verify_ssl()`, `self.get_http_headers()`
- `self.log_info()`, `self.log_error()`, `self.log_warning()`, `self.log_debug()` — structured logging with bound context

### CRITICAL: Framework helpers you MUST use

**For HTTP calls — ALWAYS use `self.http_request()`, NEVER raw `httpx.AsyncClient`:**

`self.http_request()` wraps httpx with `integration_retry_policy` (from `analysi.common.retry_config`), which provides:
- Automatic retry with exponential backoff (3 attempts, 2-10s waits)
- Retries on 5xx, 429, `ConnectError`, `TimeoutException`
- Immediate failure on 4xx (except 429) — no wasted retries
- Structured debug logging for every request/response
- SSL verification and timeout from integration settings
- Auth header merging via `get_http_headers()`

```python
# CORRECT — uses framework retry, logging, SSL, timeout
response = await self.http_request(
    url=f"{base_url}/v1/lookup",
    params={"ip": ip},
    headers={"X-API-Key": api_key},
)

# WRONG — no retry, no logging, no framework integration
async with httpx.AsyncClient() as client:
    response = await client.get(url)
```

**For sync libraries (ldap3, paramiko, boto3) — use `asyncio.to_thread()` + `sdk_retry_policy`:**

```python
from analysi.common.retry_config import sdk_retry_policy

@sdk_retry_policy()
def sync_operation():
    conn = ldap3.Connection(server)
    conn.bind()
    return conn.search(...)

result = await asyncio.to_thread(sync_operation)
```

**For return values — ALWAYS use `self.success_result()` / `self.error_result()`:**

These add `timestamp`, `integration_id`, and `action_id` automatically, ensuring a consistent response envelope across all integrations.

```python
# CORRECT
return self.success_result(data={"ip": ip, "score": 85})
return self.error_result("Missing API key", error_type="ConfigurationError")
return self.error_result(exception)  # auto-extracts error_type from class name

# WRONG — missing timestamp, integration_id, action_id
return {"status": "success", "data": {...}}
return {"status": "error", "error": "...", "error_type": "..."}
```

### CRITICAL: Cy-Boundary Contract (prevents Cy-side regressions)

Your action's return value is **normalized by the Cy executor adapter** (`services/task_execution.py`) before Cy scripts see it. Writing an action without understanding this contract produces surprises for every task author who calls you. The contract:

**1. Errors raise in Cy.** An `error_result(...)` return becomes a `RuntimeError` at the Cy boundary. Cy scripts cannot branch on error values — they either catch with `try / catch` or the task fails. Corollary: **never return `error_result(...)` for expected-empty lookup outcomes** — use the `not_found=True` idiom instead (see "Not-Found Handling for Lookup/Get Actions" below).

**2. Envelope metadata is invisible to Cy.** The keys `status`, `timestamp`, `integration_id`, `action_id` are stripped before handoff. Do not rely on them existing in the Cy-visible result. Do not add new envelope-style keys (e.g., `_meta`, `_version`) expecting them to reach Cy — they'll pass through but violate convention.

**3. `data` is unwrapped; siblings are merged into it.** Two common shapes:

```python
# Normal lookup — resource found:
return self.success_result(data={"ip": "1.2.3.4", "score": 85})
# Cy sees: {"ip": "1.2.3.4", "score": 85}

# Not-found lookup — sibling flag decorates the payload:
return self.success_result(not_found=True, data={"ip": "1.2.3.4"})
# Cy sees: {"not_found": True, "ip": "1.2.3.4"}
```

Implications for action authors:
- **Put the core business payload in `data`.** This is the thing the caller asked for.
- **Siblings (`kwargs` to `success_result`) are for boolean/scalar flags that decorate the payload** — `not_found`, `cached`, `truncated`, `rate_limited`. Use sparingly. Only set the flag when it's true (don't pass `not_found=False`).
- **Do not name a sibling the same as a key inside `data`.** On conflict, `data` wins and the sibling is silently shadowed. (e.g., `success_result(data={"cached": True}, cached=False)` — Cy sees `cached=True` from `data`.)
- **If `data` is a list or scalar, siblings are dropped.** Don't rely on `not_found=True` reaching Cy when `data=[]`. Return `data={"items": [], "not_found": True}` instead.

**4. Shape consistency across actions.** Cy tasks compose multiple integrations; an author calling `app::vendorA::lookup(...)` and `app::vendorB::lookup(...)` expects comparable result shapes. If every vendor invents its own field naming (`result.malicious` vs `result.is_malicious` vs `result.verdict.malicious`), composition gets painful. Follow existing conventions in similar integrations (check `content/foundation/tasks/*.cy` for how your integration will be consumed).

**5. Required: test that exercises the Cy-side shape.** For every action, add a unit test that pipes raw action output through the shared adapter simulator and asserts what Cy sees:

```python
from tests.utils.cy_boundary import apply_cy_adapter

async def test_lookup_ip_cy_side_shape(self):
    """Assert the Cy-visible shape of a successful lookup."""
    action = _make_action(LookupIpAction, credentials=CREDS)
    with patch.object(action, "http_request", new_callable=AsyncMock,
                      return_value=_mock_http_response({"score": 85})):
        raw = await action.execute(ip="1.2.3.4")

    cy_result = apply_cy_adapter(raw)

    assert cy_result["score"] == 85        # core payload reaches Cy
    assert "status" not in cy_result       # envelope stripped
    assert "data" not in cy_result         # data unwrapped

async def test_lookup_ip_not_found_reaches_cy(self):
    """Assert the `not_found=True` idiom survives the Cy boundary."""
    action = _make_action(LookupIpAction, credentials=CREDS)
    with patch.object(action, "http_request", new_callable=AsyncMock,
                      side_effect=_make_http_error(404)):
        raw = await action.execute(ip="1.2.3.4")

    cy_result = apply_cy_adapter(raw)
    assert cy_result["not_found"] is True   # sibling flag reaches Cy as a top-level field
    assert cy_result["ip"] == "1.2.3.4"     # echoed query param from data
```

`apply_cy_adapter` (in `tests/utils/cy_boundary.py`) mirrors the production adapter in `services/task_execution.py`. Using it keeps every integration's Cy-side tests in sync with the real boundary behavior.

**6. When in doubt, read the contract.** The canonical Cy-side behavior is documented in the task-builder skill: `skills/source/task-builder/references/integration_usage_guide.md` → "⚠️ CRITICAL: Cy-Boundary Shape vs MCP Shape". Read it when designing any new action's return shape.

### CRITICAL: Not-Found Handling for Lookup/Get Actions

**Lookup, get, search, and query actions MUST return `success` with `not_found=True` when the resource doesn't exist.** Returning `{"status": "error"}` for a missing resource crashes Cy scripts. A "not found" is a successful query with an empty result, not an error.

This applies to: HTTP 404, DNS NXDOMAIN/NoAnswer, GraphQL empty results, API-specific not-found responses (e.g., Slack `user_not_found`).

**This does NOT apply to:** containment actions (isolate, block, quarantine) or write actions (create, update, delete) — for those, 404 IS an error because the target must exist.

```python
# HTTP API pattern
try:
    response = await self.http_request(url=f"{base_url}/v1/items/{item_id}")
    return self.success_result(data=response.json())
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        self.log_info("item_not_found", item_id=item_id)
        return self.success_result(not_found=True, data={"item_id": item_id})
    self.log_error("get_item_failed", error=e)
    return self.error_result(e)

# Shared helper pattern (when helper raises Exception with message)
except Exception as e:
    if "Resource not found" in str(e):
        return self.success_result(not_found=True, data={"item_id": item_id})
    return self.error_result(e)

# DNS pattern
except dns.resolver.NXDOMAIN:
    return {"status": "success", "not_found": True, "domain": domain,
            "message": f"Domain not found: {domain}"}
except dns.resolver.NoAnswer:
    return {"status": "success", "not_found": True, "domain": domain,
            "records": [], "message": f"No {record_type} records for {domain}"}

# GraphQL pattern (Wiz-style)
if not result.get("data") or not result["data"].get("issue"):
    return self.success_result(not_found=True, data={"issue_id": issue_id})
```

**Every lookup/get action MUST have a test for the not-found path.** Example:
```python
async def test_lookup_404_returns_not_found(self):
    action = _make_action(LookupIpAction, credentials=CREDS)
    with patch.object(action, "http_request", new_callable=AsyncMock,
                      side_effect=_make_http_error(404)):
        result = await action.execute(ip="192.168.1.1")
    assert result["status"] == "success"
    assert result["not_found"] is True
```

### CRITICAL: Credential Schema vs Settings Schema

**Secrets go in `credential_schema`** (stored in Vault, encrypted). **Everything else goes in `settings_schema`** (stored in the database).

| Goes in `credential_schema` | Goes in `settings_schema` |
|---|---|
| API keys, tokens, passwords | Base URLs, hostnames |
| Client secrets | Account IDs, tenant IDs |
| Private keys, certificates | Timeout, verify_ssl |
| Bot tokens | Organization IDs, environment |

Always add `"format": "password"` to secret fields in `credential_schema`. Non-secret configuration like URLs, hostnames, and account identifiers must NOT be stored in Vault — it wastes Vault round-trips for public information.

```json
"credential_schema": {
  "properties": {
    "api_key": {"type": "string", "format": "password", "required": true}
  }
},
"settings_schema": {
  "properties": {
    "base_url": {"type": "string", "default": "https://api.example.com"},
    "timeout": {"type": "integer", "default": 30}
  }
}
```

**For auth headers — override `get_http_headers()`:**

This merges auth headers into every `self.http_request()` call automatically:

```python
def get_http_headers(self) -> dict[str, str]:
    api_key = self.credentials.get("api_key", "")
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}
```

### 3. Register in `__init__.py`

```python
"""Your Integration package."""
```

The framework auto-discovers integrations by scanning for `manifest.json` files. Action classes are loaded automatically by matching `action_id` to class names (e.g., `lookup_ip` → `LookupIpAction`). No manual registration needed.

## Archetype System

Archetypes classify what an integration *does*, enabling archetype-based routing (e.g., "find me any ThreatIntel provider that can look up IPs").

Available archetypes (PascalCase in manifests): `AI`, `SIEM`, `EDR`, `SOAR`, `ThreatIntel`, `TicketingSystem`, `Communication`, `Notification`, `CloudProvider`, `NetworkSecurity`, `IdentityProvider`, `VulnerabilityManagement`, `Sandbox`, `EmailSecurity`, `CloudStorage`, `DatabaseEnrichment`, `ForensicsTools`, `Geolocation`, `Lakehouse`, `DNS`, `AgenticFramework`, `AlertSource`

See `references/archetypes.md` for detailed archetype patterns and routing.

## Multi-Tenancy

All integrations are stateless — credentials and settings are injected per-tenant at execution time. Never store state in class variables.

See `references/multi_tenancy.md` for patterns and anti-patterns.

## REST API Endpoints

All under `/v1/{tenant}/integrations`:

| Endpoint | Description |
|----------|-------------|
| `GET /registry` | List available integration types |
| `GET /registry/{type}` | Get integration type details |
| `GET /registry/{type}/actions` | List actions for a type |
| `GET /registry/{type}/actions/{action_id}` | Get action details |
| `POST` | Create integration instance |
| `GET` | List configured integrations |
| `GET /{id}` | Get integration details |
| `PATCH /{id}` | Update integration |
| `DELETE /{id}` | Delete integration |
| `GET /{id}/health` | Run health check |
| `POST /{id}/enable` | Enable integration |
| `POST /{id}/disable` | Disable integration |
| `POST /{id}/credentials` | Add credentials |
| `POST /{id}/tools/{action_id}/execute` | Execute an action |

## Key Files

| Component | Path |
|-----------|------|
| Base class | `src/analysi/integrations/framework/base.py` |
| Archetype enum | `src/analysi/integrations/framework/models.py` |
| Registry | `src/analysi/integrations/framework/registry.py` |
| Auto-discovery | `src/analysi/integrations/framework/registry.py` |
| Router (CRUD) | `src/analysi/routers/integrations.py` |
| Router (execution) | `src/analysi/routers/integration_execution.py` |
| Example: VirusTotal | `src/analysi/integrations/framework/integrations/virustotal/` |
| Example: AbuseIPDB | `src/analysi/integrations/framework/integrations/abuseipdb/` |

## References

- `references/adding_integrations.md` — Step-by-step guide with detailed examples
- `references/archetypes.md` — Archetype system, routing, and capability patterns
- `references/multi_tenancy.md` — Tenant isolation, credential injection, testing

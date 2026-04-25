# Adding New Integrations Guide (Naxos Framework)

This guide explains how to add new third-party integrations to the analysi platform using the **Naxos framework**. We'll use VirusTotal as the reference example.

## Overview

The Naxos framework is a manifest-driven integration architecture where:
- **Manifest.json** is the single source of truth
- **Actions** are self-contained Python classes
- **Auto-discovery** - no manual registration needed
- **JSON schema validation** - no hardcoded Pydantic models

Adding a new integration involves:
1. Creating the integration directory structure
2. Writing the manifest.json file
3. Implementing action classes
4. Writing tests
5. (Optional) Adding Cy language bindings

## Step 1: Create Directory Structure

Create a new directory for your integration:

```bash
mkdir -p src/analysi/integrations/framework/integrations/your_integration
cd src/analysi/integrations/framework/integrations/your_integration
```

Your directory should contain:
```
your_integration/
├── __init__.py           # Empty file for Python package
├── manifest.json         # Integration definition (single source of truth)
└── actions.py           # Action implementations
```

## Step 2: Create manifest.json

The manifest defines everything about your integration - credentials, settings, actions, and schemas.

### Basic Structure

```json
{
  "id": "your_integration",
  "app": "your_integration",
  "name": "Your Integration",
  "version": "1.0.0",
  "description": "Brief description of what this integration does",
  "archetypes": ["ThreatIntel"],
  "priority": 80,
  "requires_credentials": true,

  "integration_id_config": {
    "default": "your-integration-main",
    "pattern": "^[a-z0-9][a-z0-9-]*$",
    "placeholder": "your-integration-main",
    "display_name": "Integration ID",
    "description": "Unique identifier for this integration"
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
      "id": "health_check",
      "name": "Health Check",
      "description": "Check connectivity to API",
      "categories": ["health_monitoring"],
      "cy_name": "health_check",
      "enabled": true
    },
    {
      "id": "lookup_ip",
      "name": "IP Lookup",
      "description": "Look up IP address reputation",
      "categories": ["threat_intel", "enrichment"],
      "cy_name": "lookup_ip",
      "enabled": true
    }
  ],

  "default_schedules": [
    {
      "action_id": "health_check",
      "schedule": "every/5m",
      "enabled": true
    }
  ]
}
```

### VirusTotal Example

See `src/analysi/integrations/framework/integrations/virustotal/manifest.json`:

```json
{
  "id": "virustotal",
  "app": "virustotal",
  "name": "VirusTotal",
  "version": "1.0.0",
  "description": "VirusTotal threat intelligence integration",
  "archetypes": ["ThreatIntel"],
  "priority": 80,

  "integration_id_config": {
    "default": "virustotal-main",
    "pattern": "^[a-z0-9][a-z0-9-]*$",
    "placeholder": "virustotal-main",
    "display_name": "Integration ID",
    "description": "Unique identifier for this integration"
  },

  "archetype_mappings": {
    "ThreatIntel": {
      "lookup_ip": "ip_reputation",
      "lookup_domain": "domain_reputation"
    }
  },

  "credential_schema": {
    "type": "object",
    "properties": {
      "api_key": {
        "type": "string",
        "display_name": "API Key",
        "description": "VirusTotal API key",
        "format": "password",
        "required": true
      }
    }
  },

  "settings_schema": {
    "type": "object",
    "properties": {
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
      "id": "health_check",
      "name": "Health Check",
      "description": "Check connectivity to VirusTotal API",
      "categories": ["health_monitoring"],
      "cy_name": "health_check",
      "enabled": true
    },
    {
      "id": "ip_reputation",
      "name": "IP Reputation",
      "description": "Get reputation information for an IP address",
      "categories": ["threat_intel", "enrichment"],
      "cy_name": "ip_reputation",
      "enabled": true
    },
    {
      "id": "domain_reputation",
      "name": "Domain Reputation",
      "description": "Get reputation information for a domain",
      "categories": ["threat_intel", "enrichment"],
      "cy_name": "domain_reputation",
      "enabled": true
    }
  ]
}
```

### Manifest Fields Reference

- **id**: Internal integration identifier (snake_case)
- **app**: Application name (usually same as id)
- **name**: Display name for UI
- **version**: Semantic version
- **description**: Brief description
- **archetypes**: Categories like ["ThreatIntel", "EDR", "SIEM"]
- **priority**: Execution priority (higher = first)
- **integration_id_config**: UI hints for integration_id field
- **credential_schema**: JSON schema for required credentials
- **settings_schema**: JSON schema for configuration (non-secret)
- **archetype_mappings**: Maps abstract archetype methods to concrete action IDs (REQUIRED)
- **requires_credentials**: Set to `false` for free/public services (default: `true`)
- **actions**: List of actions, classified by `categories`
- **default_schedules**: Auto-created schedules

### Action Classification

All actions use `categories` (a list of strings) for classification. Common categories:
- `health_monitoring` — health check actions
- `threat_intel`, `enrichment` — lookup/enrichment actions
- `response` — containment/remediation actions
- `investigation` — forensic/query actions
- `alert_ingestion`, `alert_normalization` — alert pipeline actions

> **Note:** The `type` and `purpose` fields are deprecated and ignored by the framework. Use `categories` instead.

## Step 3: Implement Actions

Create `actions.py` with action classes that inherit from `IntegrationAction`.

### Basic Structure

Class names follow the convention: `action_id` → PascalCase + `Action` suffix.
E.g., `lookup_ip` → `LookupIpAction`, `health_check` → `HealthCheckAction`.

```python
"""Your Integration actions."""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://api.yourservice.com/v1"


class HealthCheckAction(IntegrationAction):
    """Health check for API connectivity."""

    def get_http_headers(self) -> dict[str, str]:
        """Add auth headers for all requests."""
        api_key = self.credentials.get("api_key", "")
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                "Missing API key in credentials",
                error_type="ConfigurationError",
                data={"healthy": False},
            )

        base_url = self.settings.get("base_url", DEFAULT_BASE_URL)

        try:
            await self.http_request(url=f"{base_url}/status")
            return self.success_result(data={"healthy": True})
        except Exception as e:
            return self.error_result(e, data={"healthy": False})


class LookupIpAction(IntegrationAction):
    """Look up IP address reputation."""

    def get_http_headers(self) -> dict[str, str]:
        api_key = self.credentials.get("api_key", "")
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def execute(self, **kwargs) -> dict[str, Any]:
        ip_address = kwargs.get("ip_address")
        if not ip_address:
            return self.error_result(
                "ip_address parameter is required",
                error_type="ValidationError",
            )

        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                "Missing API key in credentials",
                error_type="ConfigurationError",
            )

        base_url = self.settings.get("base_url", DEFAULT_BASE_URL)

        try:
            response = await self.http_request(url=f"{base_url}/ip/{ip_address}")
            return self.success_result(data=response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    data={"not_found": True, "ip_address": ip_address}
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)
```

### VirusTotal Example

See `src/analysi/integrations/framework/integrations/virustotal/actions.py` for a complete implementation with:
- Validation helper functions
- Retry logic with tenacity
- Multiple action types
- Error handling

### Action Implementation Rules

1. **Inherit from IntegrationAction**
   ```python
   class YourAction(IntegrationAction):
   ```

2. **Implement execute() method**
   ```python
   async def execute(self, **kwargs) -> dict[str, Any]:
   ```

3. **Access credentials and settings**
   ```python
   api_key = self.credentials.get("api_key")
   timeout = self.settings.get("timeout", 30)
   ```

4. **Return standardized result** using helpers
   ```python
   return self.success_result(data={...})
   return self.error_result("Error message", error_type="ValidationError")
   return self.error_result(exception)  # auto-extracts type
   ```

5. **Use `self.http_request()` for HTTP calls** (has built-in retry)
   ```python
   response = await self.http_request(
       url="https://api.example.com/v1/lookup",
       method="GET",  # default
       params={"ip": ip},
       headers={"X-API-Key": api_key},
   )
   ```

6. **Override `get_http_headers()` for auth** (merged into every request)
   ```python
   def get_http_headers(self) -> dict[str, str]:
       api_key = self.credentials.get("api_key", "")
       return {"Authorization": f"Bearer {api_key}"} if api_key else {}
   ```

## Step 4: Write Tests

### Unit Tests

Create `tests/unit/third_party_integrations/your_integration/test_actions.py`:

```python
"""Unit tests for Your Integration actions."""

import pytest
from unittest.mock import AsyncMock, MagicMock

import httpx

from analysi.integrations.framework.integrations.your_integration.actions import (
    HealthCheckAction,
    LookupIpAction,
)


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response for http_request mock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


@pytest.mark.asyncio
async def test_health_check_success():
    """Test successful health check."""
    action = HealthCheckAction(
        integration_id="test",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={"api_key": "test-key"},
    )

    mock_response = _json_response({"healthy": True})
    action.http_request = AsyncMock(return_value=mock_response)

    result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    action.http_request.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="test",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={},  # Missing API key
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert "api_key" in result["error"].lower()
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_lookup_ip_success():
    """Test successful IP lookup."""
    action = LookupIpAction(
        integration_id="test",
        action_id="lookup_ip",
        settings={"timeout": 30},
        credentials={"api_key": "test-key"},
    )

    mock_response = _json_response({
        "ip": "1.1.1.1",
        "reputation": 100,
        "malicious": 0,
    })
    action.http_request = AsyncMock(return_value=mock_response)

    result = await action.execute(ip_address="1.1.1.1")

    assert result["status"] == "success"
    assert result["data"]["ip"] == "1.1.1.1"
    action.http_request.assert_called_once()
```

### Integration Tests

Create integration tests if your integration requires external services (usually just test manifest loading):

```python
"""Integration tests for Your Integration."""

import pytest
from analysi.integrations.framework.loader import IntegrationLoader


@pytest.mark.asyncio
async def test_manifest_loads():
    """Test that manifest loads correctly."""
    loader = IntegrationLoader()
    integrations = await loader.load_all()

    assert "your_integration" in integrations

    manifest = integrations["your_integration"]
    assert manifest.id == "your_integration"
    assert manifest.name == "Your Integration"
    assert len(manifest.actions) > 0
```

## Step 5: Test Your Integration

### Auto-discovery Verification

The integration should be automatically discovered:

```bash
# Start backend API
docker-compose up analysi-api

# Check if integration appears in registry
curl http://localhost:8001/v1/registry

# Should see your integration in the list
```

### Create Integration Instance

```bash
# 1. Create integration instance
curl -X POST "http://localhost:8001/v1/default/integrations" \
  -H "Content-Type: application/json" \
  -d '{
    "integration_id": "my-test",
    "integration_type": "your_integration",
    "name": "My Test Integration",
    "enabled": true,
    "settings": {
      "timeout": 30
    }
  }'

# 2. Create credential
curl -X POST "http://localhost:8001/v1/default/integrations/my-test/credentials" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "your_integration",
    "account": "my-test",
    "secret": "your-api-key-here",
    "is_primary": true,
    "purpose": "admin"
  }'

# 3. Run health check
curl "http://localhost:8001/v1/default/integrations/my-test/health"

# 4. Execute an action
curl -X POST "http://localhost:8001/v1/default/integrations/my-test/tools/lookup_ip/execute" \
  -H "Content-Type: application/json" \
  -d '{"ip": "8.8.8.8"}'
```

### Run Tests

```bash
# Unit tests only
poetry run pytest tests/unit/third_party_integrations/your_integration/ -v

# All tests
poetry run pytest
```

## Step 6: Add Cy Language Bindings (Optional)

If your integration provides tools for Cy scripts, actions with `cy_name` are automatically exposed.

### Example from manifest.json:

```json
{
  "id": "lookup_ip",
  "name": "IP Lookup",
  "categories": ["threat_intel"],
  "cy_name": "lookup_ip",
  "enabled": true
}
```

### Usage in Cy:

```cy
result = lookup_ip(ip_address="1.1.1.1")
print(result.data.reputation)
```

No additional code needed - the framework automatically:
1. Discovers tools with `cy_name`
2. Creates Cy function bindings
3. Handles parameter passing and execution

## Best Practices

### 1. Manifest Design
- ✅ Use descriptive names and descriptions
- ✅ Set reasonable defaults
- ✅ Use JSON schema validation properly
- ✅ Group related actions logically

### 2. Action Implementation
- ✅ Always validate inputs
- ✅ Return structured, consistent results
- ✅ Handle errors gracefully
- ✅ Use retry logic for network operations
- ✅ Log errors with context

### 3. Security
- ✅ Never log credentials
- ✅ Use `format: "password"` for secrets in schema
- ✅ Validate all user inputs
- ✅ Use HTTPS for API calls

### 4. Testing
- ✅ Test both success and failure cases
- ✅ Mock external API calls
- ✅ Test credential validation
- ✅ Verify error messages are helpful

### 5. Documentation
- ✅ Clear action descriptions in manifest
- ✅ Document all parameters
- ✅ Include usage examples
- ✅ Explain error codes

## Common Patterns

### Validation Helper Functions

```python
def _validate_ip(ip_address: str) -> tuple[bool, str]:
    """Validate IP address format.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not ip_address or not isinstance(ip_address, str):
        return False, "IP address must be a non-empty string"

    # Validation logic
    return True, ""
```

### CRITICAL: Always use `self.http_request()` — NEVER raw `httpx.AsyncClient`

`self.http_request()` wraps httpx with `integration_retry_policy` (from `analysi.common.retry_config`), providing automatic retry with exponential backoff (3 attempts, 2-10s), retries on 5xx/429/network errors, structured logging, and SSL/timeout from settings. Raw `httpx.AsyncClient` bypasses ALL of this.

```python
# CORRECT — retry, logging, SSL, timeout all handled
response = await self.http_request(url=f"{base_url}/v1/lookup", params={"ip": ip})

# WRONG — no retry, no logging, no framework integration
async with httpx.AsyncClient() as client:
    response = await client.get(url)
```

Similarly, always return results via `self.success_result()` / `self.error_result()` — they add `timestamp`, `integration_id`, and `action_id` automatically.

**Complete pattern:**

```python
async def execute(self, **kwargs) -> dict[str, Any]:
    try:
        response = await self.http_request(
            url=f"{base_url}/v1/lookup",
            params={"ip": ip},
        )
        return self.success_result(data=response.json())
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # 404 must NOT crash Cy scripts — return success with not_found flag
            return self.success_result(data={"not_found": True, "ip": ip})
        return self.error_result(e)
    except Exception as e:
        return self.error_result(e)
```

### No-Credential Integrations

For free/public services (e.g., public DNS, Tor exit node lists), set `requires_credentials: false` in the manifest:

```json
{
  "id": "global_dns",
  "requires_credentials": false,
  "credential_schema": {},
  "settings_schema": { ... }
}
```

Actions should work without any credentials:
```python
async def execute(self, **kwargs) -> dict[str, Any]:
    # No credential validation needed
    domain = kwargs.get("domain")
    if not domain:
        return self.error_result("Missing parameter: domain", error_type="ValidationError")
    # ... proceed with public API call
```

## Reference Implementations

- **VirusTotal**: Complete threat intelligence integration
  - `src/analysi/integrations/framework/integrations/virustotal/`
  - Multiple tool actions, validation helpers
  - Uses `self.http_request()` for all API calls (retry via framework)

- **Splunk**: Complex SIEM integration
  - `src/analysi/integrations/framework/integrations/splunk/`
  - Multiple actions (14+)
  - Alert pulling and OCSF normalization

- **Echo EDR**: Simple EDR integration
  - `src/analysi/integrations/framework/integrations/echo_edr/`
  - Basic structure
  - Health monitoring

- **Global DNS**: No-credential integration
  - `src/analysi/integrations/framework/integrations/global_dns/`
  - `requires_credentials: false` pattern
  - Pure code, no API key needed

## Troubleshooting

### Integration not appearing in registry
- Check manifest.json syntax (valid JSON)
- Verify __init__.py exists
- Check logs for loading errors
- Ensure directory is in correct location

### Actions not executing
- Verify action IDs match manifest
- Check credentials are provided
- Review action logs for errors
- Test with simplified parameters

### Validation errors
- Check JSON schema syntax
- Verify required fields marked correctly
- Test with schema validator online

## Support

For questions or issues:
1. Check reference implementations
2. Review Naxos framework documentation
3. Consult test files for examples
4. Ask the team for architectural decisions

# Test Speedup Patterns

Reference material from our 83% unit test speedup achievement (77s → 13s).

## Pattern 1: Tenacity Retry Decorator Mocking

**Problem**: Functions decorated with `@retry(wait=wait_exponential(min=2, max=10))` cause 2-10 second delays in tests.

**Solution**: Patch the retry decorator's wait strategy to use `wait_fixed(0)`.

```python
from tenacity import wait_fixed
from analysi.integrations.framework.integrations.maxmind.actions import (
    _make_maxmind_request,  # Import the decorated function
)

# ✅ CORRECT approach
with patch.object(_make_maxmind_request.retry, "wait", wait_fixed(0)):
    result = await action.execute()

# ❌ WRONG approach (doesn't work!)
with patch("tenacity.nap.sleep", return_value=None):
    result = await action.execute()
```

**Applied to**:
- MaxMind: `_make_maxmind_request` (6 tests, 24s → 0.04s)
- Integration API Client: `get_credential`, `update_health_status` (4 tests, 16s → 0.08s)
- Echo EDR: `_make_request` (2 tests, 8s → 0.03s)
- OpenAI: `_make_request` (2 tests, 8s → 0.03s)
- SentinelOne: `_make_sentinelone_request` (1 test, 4s → <0.01s)

**Source Pattern** (from tenacity documentation via Context7):
```python
# When testing functions with retry decorators:
# 1. Import the decorated function
# 2. Use patch.object on function.retry.wait
# 3. Replace with wait_fixed(0)
```

## Pattern 2: Asyncio Sleep Mocking

**Problem**: Polling loops with `await asyncio.sleep(interval)` cause real delays in tests.

**Solution**: Mock `asyncio.sleep` with `AsyncMock`.

```python
from unittest.mock import AsyncMock, patch

# ✅ CORRECT approach
with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
    result = await polling_function()

# Optionally verify sleep was called
assert mock_sleep.called
```

**Applied to**:
- Okta: Push notification polling (1 test, 5s → <0.01s)
- Sumo Logic: Job status polling (2 tests, 4s → <0.01s)

**Common Pattern**:
```python
# tests/unit/third_party_integrations/okta/test_actions.py:196-202
with patch("httpx.AsyncClient", return_value=mock_client), \
     patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
    result = await action.execute(email="test@example.com", factortype="push")

assert result["status"] == "success"
assert mock_sleep.called  # Verify polling happened
```

## Pattern 3: Direct Method Mocking

**Problem**: Internal methods with retry decorators called by public methods cause delays.

**Solution**: Mock the internal method directly using `patch.object`.

```python
from unittest.mock import AsyncMock, patch

# ✅ CORRECT approach
with patch.object(instance, "_internal_api_method", new_callable=AsyncMock):
    await instance.public_method()
    instance._internal_api_method.assert_called_once()
```

**Applied to**:
- Alert Analysis Pipeline: `_update_step_progress_api` (1 test, 4s → <0.01s)

**Example**:
```python
# tests/unit/alert_analysis/test_pipeline.py:151-158
# Mock the API call to avoid retry delays
with patch.object(self.pipeline, "_update_step_progress_api", new_callable=AsyncMock):
    await self.pipeline._update_step_progress("pre_triage", "completed")

    self.pipeline._update_step_progress_api.assert_called_once_with(
        "pre_triage", True, None
    )
```

## Pattern 4: Proper HTTPx Exception Types

**Problem**: Using generic `Exception` in side_effect can trigger unexpected retry behavior.

**Solution**: Use specific httpx exception types.

```python
import httpx

# ✅ CORRECT approach - use specific exceptions
mock_client.get.side_effect = httpx.TimeoutException("Timeout")
mock_client.get.side_effect = httpx.ConnectError("Connection failed")
mock_client.get.side_effect = httpx.HTTPStatusError(
    "Error",
    request=MagicMock(),
    response=MagicMock(status_code=500)
)

# ❌ WRONG approach - generic exceptions
mock_client.get.side_effect = Exception("Timeout")  # May trigger retry delays
```

**Applied to**:
- SentinelOne: Changed `Exception` to `httpx.HTTPStatusError` (1 test, 4s → <0.01s)

**Example**:
```python
# tests/unit/third_party_integrations/sentinelone/test_actions.py:118-125
import httpx

mock_client.get.side_effect = httpx.HTTPStatusError(
    "API error",
    request=MagicMock(),
    response=MagicMock(status_code=500)
)
```

## Pattern 5: Mock Framework/Registry Loading

**Problem**: Loading integration manifests or framework components causes I/O overhead.

**Solution**: Mock the registry service to avoid file I/O.

```python
from unittest.mock import MagicMock, patch

# ✅ CORRECT approach
with patch("analysi.services.integration_registry_service.IntegrationRegistryService") as mock_registry:
    mock_framework = MagicMock()
    mock_framework.list_integrations.return_value = []
    mock_registry.return_value.framework = mock_framework

    # Now fast - no file I/O
    result = await load_tool_registry_async(session, tenant_id)
```

**Applied to**:
- Cy Tool Registry: Avoided loading all integration manifests (1 test, 0.55s → 0.02s)

**Example**:
```python
# tests/unit/services/test_cy_tool_registry.py
with patch("analysi.services.integration_registry_service.IntegrationRegistryService") as mock_registry:
    mock_framework = MagicMock()
    mock_framework.list_integrations.return_value = []
    mock_registry.return_value.framework = mock_framework

    tool_registry = await load_tool_registry_async(mock_session, "default")
```

## Quick Reference: What to Mock

| Symptom | Root Cause | Solution | Pattern # |
|---------|-----------|----------|-----------|
| Test takes 2-10s | Tenacity retry decorator | Mock retry.wait with wait_fixed(0) | 1 |
| Test waits in loop | asyncio.sleep in polling | Mock asyncio.sleep with AsyncMock | 2 |
| Internal API delays | Private method with retry | Mock the internal method directly | 3 |
| Unexpected retries | Generic Exception type | Use specific httpx exceptions | 4 |
| Slow test startup | Loading manifests/files | Mock registry/framework loading | 5 |

## Best Practices

1. **Always import the decorated function** when mocking retry decorators
2. **Use specific exception types** from httpx (not generic Exception)
3. **Mock at the right level**: retry.wait for decorators, asyncio.sleep for loops
4. **Verify mocks were called** to ensure test is actually testing behavior
5. **Run `pytest --durations=20`** regularly to find slow tests early

## Research Source

These patterns were validated using Context7 library documentation:
- Tenacity: https://github.com/jd/tenacity (retry mocking pattern)
- pytest-httpx: https://github.com/colin-b/pytest_httpx (exception types)

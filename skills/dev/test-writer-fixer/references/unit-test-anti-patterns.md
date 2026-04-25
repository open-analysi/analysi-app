# Unit Test Anti-Patterns

Common mistakes to avoid when writing unit tests in this project.

## Anti-Pattern 1: Real Delays in Tests

❌ **NEVER** let unit tests wait for real time to pass.

```python
# ❌ BAD - test takes 5 seconds
async def test_polling():
    while not condition:
        await asyncio.sleep(1)  # Real 1-second wait!
    assert result == expected

# ✅ GOOD - test is instant
async def test_polling():
    with patch("asyncio.sleep", new_callable=AsyncMock):
        while not condition:
            await asyncio.sleep(1)  # Mocked - no wait
        assert result == expected
```

**Impact**: Okta test went from 5s → <0.01s by mocking asyncio.sleep.

## Anti-Pattern 2: Wrong Tenacity Mocking

❌ **NEVER** use `patch("tenacity.nap.sleep")` - it doesn't work!

```python
# ❌ BAD - doesn't actually prevent retry delays
with patch("tenacity.nap.sleep", return_value=None):
    await function_with_retry()  # Still waits 2-10 seconds!

# ✅ GOOD - correctly mocks retry wait
from tenacity import wait_fixed
from module import function_with_retry

with patch.object(function_with_retry.retry, "wait", wait_fixed(0)):
    await function_with_retry()  # Instant retries
```

**Impact**: MaxMind tests still took 4s each until we used the correct pattern from Context7.

## Anti-Pattern 3: Generic Exception Types

❌ **NEVER** use generic `Exception` when testing HTTP failures.

```python
# ❌ BAD - may trigger unexpected retry behavior
mock_client.get.side_effect = Exception("Timeout")

# ✅ GOOD - use specific httpx exception types
import httpx
mock_client.get.side_effect = httpx.TimeoutException("Timeout")
mock_client.get.side_effect = httpx.ConnectError("Connection failed")
mock_client.get.side_effect = httpx.HTTPStatusError(
    "Error", request=MagicMock(), response=MagicMock(status_code=500)
)
```

**Impact**: SentinelOne test went from 4s → <0.01s by using HTTPStatusError.

## Anti-Pattern 4: SQLite for Tests

❌ **NEVER** use SQLite for tests in this project.

```python
# ❌ BAD - SQLite doesn't support PostgreSQL features
@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    # Will fail on ARRAY types, UUIDs, ENUMs, etc.
```

**Why**: Our models use PostgreSQL-specific features:
- ARRAY types
- UUID types
- ENUM types
- JSON operators

**Solution**: All tests use the `analysi_test` PostgreSQL database.

## Anti-Pattern 5: Expecting NotImplementedError

❌ **NEVER** write tests that expect `NotImplementedError`.

```python
# ❌ BAD - defeats the purpose of TDD
def test_feature():
    with pytest.raises(NotImplementedError):
        result = unimplemented_function()

# ✅ GOOD - let it fail naturally, then implement
def test_feature():
    result = unimplemented_function()
    assert result == expected_value
```

**Per CLAUDE.md**: "never expect NotImplementedError in unit tests. Let them fail as per TDD guideline"

## Anti-Pattern 6: File I/O in Unit Tests

❌ **AVOID** loading real files/manifests in unit tests when possible.

```python
# ❌ SLOW - loads all integration manifests from disk
tool_registry = await load_tool_registry_async(session, tenant_id)
# Takes 0.55s due to file I/O

# ✅ FAST - mocks the registry service
with patch("...IntegrationRegistryService") as mock_registry:
    mock_framework = MagicMock()
    mock_framework.list_integrations.return_value = []
    mock_registry.return_value.framework = mock_framework

    tool_registry = await load_tool_registry_async(session, tenant_id)
    # Takes 0.02s - no file I/O
```

**Impact**: Cy Tool Registry test went from 0.55s → 0.02s (27x speedup).

## Anti-Pattern 7: Hardcoded Integration IDs

❌ **AVOID** using the same integration ID across all tests.

```python
# ❌ BAD - tests can interfere with each other
def test_1():
    create_integration(integration_id="test-int")

def test_2():
    create_integration(integration_id="test-int")  # Conflict!

# ✅ GOOD - unique IDs per test
from uuid import uuid4

def test_1():
    integration_id = f"test-int-{uuid4().hex[:8]}"
    create_integration(integration_id=integration_id)

def test_2():
    integration_id = f"test-int-{uuid4().hex[:8]}"
    create_integration(integration_id=integration_id)  # No conflict
```

**Per code quality tools**: Hardcoded integration IDs are a critical flakiness pattern.

## Anti-Pattern 8: Missing `@pytest.mark.integration`

❌ **NEVER** forget to mark integration tests.

```python
# ❌ BAD - integration test not marked
@pytest.mark.asyncio
class TestIntegrationAPI:
    async def test_full_workflow(self, integration_test_session):
        ...

# ✅ GOOD - properly marked
@pytest.mark.asyncio
@pytest.mark.integration
class TestIntegrationAPI:
    async def test_full_workflow(self, integration_test_session):
        ...
```

**Per CLAUDE.md**: "Always add `@pytest.mark.integration` for integration tests"

## Anti-Pattern 9: Test Naming with Implementation Phases

❌ **AVOID** naming tests with their implementation phase.

```python
# ❌ BAD - phase numbers in test names
test_phase_6_1_web_app_apis.py

# ✅ GOOD - descriptive names
test_web_app_apis.py
test_integration_api.py
```

**Per CLAUDE.md**: "do not name unit tests with their implementation phase"

## Anti-Pattern 10: Timezone-Naive Timestamps

❌ **NEVER** use timezone-naive datetime objects.

```python
# ❌ BAD - naive datetime
from datetime import datetime
timestamp = datetime.now()

# ✅ GOOD - timezone-aware
from datetime import datetime, timezone
timestamp = datetime.now(timezone.utc)
```

**Per CLAUDE.md**: "Always use timezone aware timestamps in this project"

## Quick Reference: Before Committing Tests

Before committing new tests, verify:

- [ ] No real delays (`asyncio.sleep`, retry decorators)
- [ ] Using PostgreSQL, not SQLite
- [ ] Using specific httpx exception types
- [ ] Integration tests marked with `@pytest.mark.integration`
- [ ] Unique IDs for test data (no hardcoded "test-int")
- [ ] No `pytest.raises(NotImplementedError)`
- [ ] Descriptive test names (no phase numbers)
- [ ] Timezone-aware timestamps
- [ ] Run `pytest --durations=20` to check for slow tests

## Code Quality Tools

Use these commands before committing:

```bash
# Find slow tests
pytest --durations=20

# Detect flakiness patterns
make detect-flakiness

# Run comprehensive test hygiene audit
make audit-test-hygiene

# CI check (fails build if critical issues)
make code-quality-ci
```

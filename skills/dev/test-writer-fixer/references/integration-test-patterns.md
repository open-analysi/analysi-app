# Integration Test Patterns

Detailed patterns for writing integration tests in this project, based on project decisions and real implementations.

## Core Pattern: Workflow Execution Testing

**From Decision 2 in DECISIONS.md** - How to test actual workflow execution without race conditions.

### The Problem

When workflows are started via API (`POST /workflows/{id}/run`), they create background tasks that run in separate database sessions. Test data committed in test sessions isn't visible to these background tasks, causing:

1. Test starts workflow (gets 202 response)
2. Background execution task can't see test data
3. Test immediately checks for results but finds none
4. Test fails even though workflow logic is correct

### The Solution: Manual Execution Pattern

```python
@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowExecution:
    """Test actual workflow execution."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> tuple[AsyncClient, AsyncSession]:
        """Create HTTP client AND return session for manual execution."""
        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # Return BOTH client and session
            yield (c, integration_test_session)

        app.dependency_overrides.clear()

    async def test_workflow_execution(self, client):
        """Test workflow executes and produces results."""
        # Unpack client and session from fixture
        http_client, session = client

        tenant_id = f"tenant-{uuid4().hex[:8]}"

        # 1. Create workflow/templates/test data via API
        workflow_id = await self._create_test_workflow(http_client, tenant_id)

        # 2. CRITICAL: Commit test data so background task can see it
        await session.commit()

        # 3. Start workflow via API
        response = await http_client.post(
            f"/v1/{tenant_id}/workflows/{workflow_id}/run",
            json={"input_data": {"value": 42}}
        )
        assert response.status_code == 202
        workflow_run_id = response.json()["workflow_run_id"]

        # 4. Manually trigger execution using same session
        from analysi.services.workflow_execution import WorkflowExecutor
        executor = WorkflowExecutor(session)
        await executor.monitor_execution(workflow_run_id)
        await session.commit()

        # 5. Verify results via API
        details = await http_client.get(
            f"/v1/{tenant_id}/workflow-runs/{workflow_run_id}"
        )
        assert details.status_code == 200
        data = details.json()
        assert data["status"] == "completed"
        assert data["output"] == expected_output
```

### Key Requirements

1. **Tuple Fixture**: Return `(AsyncClient, AsyncSession)` not just client
2. **Unpack in Test**: `http_client, session = client`
3. **Commit Before**: `await session.commit()` after creating test data
4. **Manual Execution**: Use `WorkflowExecutor(session).monitor_execution()`
5. **Commit After**: `await session.commit()` after execution

### When to Use This Pattern

✅ **Use manual execution when**:
- Verifying workflow execution completes correctly
- Checking workflow output data/results
- Validating complex workflow patterns (fan-in, pipelines, parallel execution)
- Testing end-to-end workflow behavior

❌ **Don't use manual execution when**:
- Only verifying API responses (202, 404, validation errors)
- Only checking workflow creation/validation
- Testing workflow configuration endpoints
- Testing immediate status checks

### Why This Works

- **Reliability**: Eliminates race conditions in test execution
- **Deterministic**: Tests run synchronously, making debugging easier
- **Isolation**: Each test gets its own session and execution context
- **Production similarity**: Uses same execution logic as production, just triggered manually

## Pattern: Integration Action Testing with Retry Decorators

Integration tests that call real integration actions need to handle retry decorators properly.

### Example: Testing Splunk Integration

```python
@pytest.mark.asyncio
@pytest.mark.integration
class TestSplunkIntegration:
    """Test Splunk integration with real HTTP calls."""

    async def test_health_check_with_invalid_credentials(
        self, integration_test_session
    ):
        """Test health check fails gracefully with bad credentials."""
        from tenacity import wait_fixed
        from analysi.integrations.framework.integrations.splunk.actions import (
            HealthCheckAction,
            _make_splunk_request,
        )

        # Arrange
        action = HealthCheckAction(
            integration_id="test-splunk",
            action_id="health_check",
            credentials={
                "username": "invalid",
                "password": "invalid",
            },
            settings={
                "base_url": "https://invalid.splunk.example.com",
            },
        )

        # Act - patch retry to avoid 2-10 second delays
        with patch.object(_make_splunk_request.retry, "wait", wait_fixed(0)):
            result = await action.execute()

        # Assert
        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"
```

**Key Points**:
1. Import the decorated function (`_make_splunk_request`)
2. Use `patch.object(function.retry, "wait", wait_fixed(0))`
3. Even in integration tests, we don't want real retry delays
4. Test verifies the action handles errors correctly

## Pattern: Database Operations with Unique IDs

**From DECISIONS.md Decision 7** - Avoid hardcoded IDs that cause test conflicts.

```python
@pytest.mark.asyncio
@pytest.mark.integration
class TestIntegrationCRUD:
    """Test integration CRUD operations."""

    async def test_create_and_list(self, integration_test_session):
        """Test creating integration and listing it."""
        from uuid import uuid4

        # Use unique IDs to avoid conflicts
        tenant_id = f"tenant-{uuid4().hex[:8]}"
        integration_id = f"splunk-{uuid4().hex[:8]}"

        # Create
        integration = Integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            name="Test Splunk",
            integration_type="splunk",
            enabled=True,
            settings={"base_url": "https://splunk.test.com"},
        )

        integration_test_session.add(integration)
        await integration_test_session.commit()
        await integration_test_session.refresh(integration)

        # List
        result = await integration_test_session.execute(
            select(Integration).where(Integration.tenant_id == tenant_id)
        )
        integrations = result.scalars().all()

        assert len(integrations) == 1
        assert integrations[0].integration_id == integration_id
```

**Why Unique IDs**:
- Tests can run in parallel without conflicts
- No cleanup needed between tests
- Easier debugging (IDs are randomized)
- Matches real-world usage (UUIDs everywhere)

## Pattern: API Client Fixture with Session Access

The standard pattern for integration tests that need both HTTP client and database session.

```python
@pytest.fixture
async def client(
    self, integration_test_session
) -> tuple[AsyncClient, AsyncSession]:
    """Create async HTTP client with test database override.

    Returns tuple of (http_client, session) for tests that need
    manual workflow execution or direct database access.
    """
    # Override database dependency
    async def override_get_db():
        yield integration_test_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Return tuple: (client, session)
        yield (c, integration_test_session)

    # Clean up
    app.dependency_overrides.clear()
```

**Usage**:
```python
async def test_something(self, client):
    # Unpack tuple
    http_client, session = client

    # Use HTTP client for API calls
    response = await http_client.get("/v1/tenant/resources")

    # Use session for manual execution or verification
    await session.commit()
    result = await session.execute(select(Model))
```

## Pattern: Valkey/Redis Database Isolation

**From DECISIONS.md Decision 7** - Use DB 100+ for all testing.

```python
@pytest.fixture
async def valkey_client():
    """Create Valkey client using test database (100+)."""
    from analysi.common.valkey_config import ValkeyDBConfig

    # Automatically uses DB 100+ in test environment
    redis = await aioredis.from_url(
        "redis://localhost:6379",
        db=ValkeyDBConfig.TEST_ALERT_PROCESSING,  # DB 100
        decode_responses=True,
    )

    yield redis

    # Cleanup
    await redis.flushdb()
    await redis.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_alert_queue(valkey_client):
    """Test alert queue operations."""
    # Test uses DB 100, production uses DB 0
    # No conflicts possible!

    await valkey_client.lpush("alerts", "test_alert")
    result = await valkey_client.rpop("alerts")

    assert result == "test_alert"
```

**Database Allocation**:
- **Production**: DB 0-99
- **Testing**: DB 100+
- **Clear separation**: Impossible to confuse production and test data

## Checklist: Before Committing Integration Tests

- [ ] Marked with `@pytest.mark.integration`
- [ ] Uses `integration_test_session` fixture
- [ ] Uses unique IDs with `uuid4().hex[:8]`
- [ ] Overrides `get_db` dependency for API tests
- [ ] Cleans up dependency overrides
- [ ] If testing workflow execution: uses manual execution pattern (NOT asyncio.sleep!)
- [ ] If testing workflow execution: fixture returns `(client, session)` tuple
- [ ] If testing workflow execution: commits before execution
- [ ] Uses Valkey DB 100+ (not 0-99)
- [ ] Patches retry decorators with `wait_fixed(0)`
- [ ] Uses timezone-aware timestamps
- [ ] PostgreSQL only (no SQLite)

## Common Mistakes

### Mistake 1: Not Committing Before Workflow Execution

```python
# ❌ BAD - background task can't see test data
async def test_workflow(self, client):
    http_client, session = client

    workflow_id = await create_workflow(http_client)
    # Missing: await session.commit()

    response = await http_client.post(f"/.../workflows/{workflow_id}/run")
    # Background task fails - can't see workflow!

# ✅ GOOD - commit before execution
async def test_workflow(self, client):
    http_client, session = client

    workflow_id = await create_workflow(http_client)
    await session.commit()  # CRITICAL

    response = await http_client.post(f"/.../workflows/{workflow_id}/run")
```

### Mistake 2: Using Simple Client Fixture for Workflow Tests

```python
# ❌ BAD - can't access session for manual execution
@pytest.fixture
async def client(self, integration_test_session):
    # ... setup ...
    yield client  # Returns only client, not session!

# ✅ GOOD - return tuple
@pytest.fixture
async def client(self, integration_test_session):
    # ... setup ...
    yield (client, integration_test_session)  # Tuple!
```

### Mistake 3: Hardcoded Integration IDs

```python
# ❌ BAD - tests conflict with each other
async def test_1(self):
    create_integration(integration_id="test-int")

async def test_2(self):
    create_integration(integration_id="test-int")  # Collision!

# ✅ GOOD - unique IDs
from uuid import uuid4

async def test_1(self):
    integration_id = f"test-int-{uuid4().hex[:8]}"
    create_integration(integration_id=integration_id)

async def test_2(self):
    integration_id = f"test-int-{uuid4().hex[:8]}"
    create_integration(integration_id=integration_id)  # No collision
```

### Mistake 4: Using asyncio.sleep() Instead of Manual Execution

```python
# ❌ BAD - race condition, flaky test
async def test_workflow_execution(self, client):
    """This test will randomly fail!"""
    http_client, session = client

    # Start workflow
    response = await http_client.post(f"/.../workflows/{wf_id}/run")
    workflow_run_id = response.json()["workflow_run_id"]

    # Hope workflow finishes in 2 seconds 🤞
    await asyncio.sleep(2)

    # Check status - might still be 'pending'!
    status = await http_client.get(f"/.../workflow-runs/{workflow_run_id}/status")
    assert status.json()["status"] == "completed"  # FLAKY!

# ✅ GOOD - deterministic execution
async def test_workflow_execution(self, client):
    """Reliable test with manual execution."""
    http_client, session = client

    # Start workflow
    response = await http_client.post(f"/.../workflows/{wf_id}/run")
    workflow_run_id = response.json()["workflow_run_id"]

    # Synchronously execute - no race condition
    from analysi.services.workflow_execution import WorkflowExecutor
    executor = WorkflowExecutor(session)
    await executor.monitor_execution(workflow_run_id)
    await session.commit()

    # Status is guaranteed to be final
    status = await http_client.get(f"/.../workflow-runs/{workflow_run_id}/status")
    assert status.json()["status"] == "completed"  # RELIABLE!
```

**Why asyncio.sleep() causes flakiness**:
- Background workers may not run in test environment
- Arbitrary sleep duration might be too short or too long
- Tests fail intermittently with `status='pending'`
- Impossible to debug when sleep "almost" works

**Why manual execution is better**:
- Synchronous - workflow completes before status check
- Deterministic - same behavior every run
- Fast - no arbitrary delays
- Debuggable - step through execution logic

## Quick Reference: Integration Test Types

| Test Type | Pattern | Fixture | Manual Execution? |
|-----------|---------|---------|-------------------|
| API endpoints (CRUD) | Standard | `client: AsyncClient` | No |
| Database operations | Standard | `integration_test_session` | No |
| Workflow execution | Manual execution | `client: tuple[AsyncClient, AsyncSession]` | Yes |
| Queue operations | Valkey isolation | `valkey_client` (DB 100+) | No |
| Integration actions | Retry mocking | `integration_test_session` | No |

## Further Reading

- `DECISIONS.md` Decision 2: Workflow Testing Pattern
- `DECISIONS.md` Decision 7: Valkey Database Allocation
- `references/test-speedup-patterns.md`: Retry decorator mocking
- `references/unit-test-anti-patterns.md`: Common mistakes

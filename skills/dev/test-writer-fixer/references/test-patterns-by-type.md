# Test Patterns by Test Type

Organized patterns for different types of tests in this project.

## Unit Test Patterns

### Pattern: Testing Integration Actions

```python
"""Unit tests for integration actions."""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from tenacity import wait_fixed

from analysi.integrations.framework.integrations.service.actions import (
    HealthCheckAction,
    _make_request,  # Import decorated function for mocking
)


@pytest.fixture
def mock_credentials():
    """Mock credentials for the service."""
    return {
        "api_key": "test_api_key",
        "api_secret": "test_secret",
    }


@pytest.fixture
def mock_settings():
    """Mock settings for the service."""
    return {
        "base_url": "https://api.test.com",
        "timeout": 30,
    }


@pytest.fixture
def health_check_action(mock_credentials, mock_settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction(
        integration_id="test-service",
        action_id="health_check",
        credentials=mock_credentials,
        settings=mock_settings,
    )


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    # Arrange
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "ok"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response

    # Act
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await health_check_action.execute()

    # Assert
    assert result["status"] == "success"
    assert result["healthy"] is True
    mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_timeout(health_check_action):
    """Test health check with timeout."""
    # Arrange
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.side_effect = httpx.TimeoutException("Request timed out")

    # Act - patch retry wait to avoid delays
    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch.object(_make_request.retry, "wait", wait_fixed(0)):
        result = await health_check_action.execute()

    # Assert
    assert result["status"] == "error"
    assert "timed out" in result["error"].lower()


@pytest.mark.asyncio
async def test_health_check_connection_error(health_check_action):
    """Test health check with connection error."""
    # Arrange
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectError("Connection failed")

    # Act - patch retry wait to avoid delays
    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch.object(_make_request.retry, "wait", wait_fixed(0)):
        result = await health_check_action.execute()

    # Assert
    assert result["status"] == "error"
    assert "connection" in result["error"].lower()


@pytest.mark.asyncio
async def test_health_check_invalid_credentials(health_check_action):
    """Test health check with invalid credentials."""
    # Arrange
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "Unauthorized",
        request=MagicMock(),
        response=MagicMock(status_code=401)
    )

    # Act - patch retry wait to avoid delays
    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch.object(_make_request.retry, "wait", wait_fixed(0)):
        result = await health_check_action.execute()

    # Assert
    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"
```

**Key Points**:
1. Import the decorated function (`_make_request`) for mocking retries
2. Use specific httpx exception types (TimeoutException, ConnectError, HTTPStatusError)
3. Mock retry.wait with wait_fixed(0) to avoid delays
4. Use fixtures for reusable test data
5. Follow Arrange-Act-Assert pattern

### Pattern: Testing Polling Operations

```python
"""Test polling operations with asyncio.sleep."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_polling_until_complete(action):
    """Test polling until job completes."""
    # Arrange
    mock_status_responses = [
        {"state": "PENDING"},
        {"state": "RUNNING"},
        {"state": "COMPLETED"},
    ]

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.side_effect = [
        MagicMock(json=lambda: resp) for resp in mock_status_responses
    ]

    # Act - mock asyncio.sleep to avoid real delays
    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await action.execute(job_id="test-job")

    # Assert
    assert result["status"] == "success"
    assert result["state"] == "COMPLETED"
    assert mock_sleep.call_count == 2  # Called twice before completion


@pytest.mark.asyncio
async def test_polling_timeout(action):
    """Test polling with timeout."""
    # Arrange
    mock_response = MagicMock()
    mock_response.json.return_value = {"state": "RUNNING"}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response

    # Act - patch timeout to be very short and mock sleep
    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("module.POLLING_MAX_TIME", 0.1), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        result = await action.execute(job_id="test-job")

    # Assert
    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
```

**Key Points**:
1. Mock `asyncio.sleep` with `new_callable=AsyncMock`
2. Patch timeout constants to short values for tests
3. Verify sleep was called correct number of times

### Pattern: Testing Pipeline/Orchestration

```python
"""Test pipeline orchestration."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
class TestPipeline:
    """Test multi-step pipeline."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pipeline = Pipeline(tenant_id="test-tenant")

    async def test_complete_pipeline_execution(self):
        """Test complete pipeline execution."""
        # Arrange
        mock_db = AsyncMock()
        self.pipeline.db = mock_db

        # Mock step execution
        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(self.pipeline, "_execute_step") as mock_execute:
                mock_execute.return_value = {"result": "step_output"}

                # Act
                result = await self.pipeline.execute()

                # Assert
                assert result is not None
                assert mock_execute.call_count == 5  # All 5 steps

    async def test_step_progress_tracking(self):
        """Test that step progress is tracked correctly."""
        # Arrange
        mock_db = AsyncMock()
        self.pipeline.db = mock_db

        # Mock the API call to avoid retry delays
        with patch.object(
            self.pipeline, "_update_step_progress_api", new_callable=AsyncMock
        ) as mock_api:
            # Act
            await self.pipeline._update_step_progress("step1", "completed")

            # Assert
            mock_api.assert_called_once_with("step1", True, None)
```

**Key Points**:
1. Mock internal API methods to avoid retry delays
2. Use `patch.object` for instance methods
3. Test orchestration logic separately from step implementation

## Integration Test Patterns

### Pattern: Testing REST API Endpoints

```python
"""Integration tests for API endpoints."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestAPIEndpoints:
    """Test REST API endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[AsyncClient, None]:
        """Create an async HTTP client with test database."""
        # Override database dependency
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        # Clean up
        app.dependency_overrides.clear()

    async def test_list_resources(self, client: AsyncClient):
        """Test GET /resources lists resources."""
        response = await client.get("/v1/test-tenant/resources")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_create_resource(self, client: AsyncClient):
        """Test POST /resources creates resource."""
        response = await client.post(
            "/v1/test-tenant/resources",
            json={
                "name": "Test Resource",
                "type": "test",
            },
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == "Test Resource"
```

**Key Points**:
1. Always mark with `@pytest.mark.integration`
2. Use `integration_test_session` fixture for database
3. Override `get_db` dependency to use test database
4. Clean up dependency overrides after test
5. Use unique tenant IDs or resource IDs to avoid conflicts

### Pattern: Testing Database Operations

```python
"""Integration tests for database operations."""

import pytest
from uuid import uuid4

from analysi.models import Integration


@pytest.mark.asyncio
@pytest.mark.integration
class TestDatabaseOperations:
    """Test database CRUD operations."""

    async def test_create_and_retrieve(self, integration_test_session):
        """Test creating and retrieving record."""
        # Arrange
        tenant_id = f"tenant-{uuid4().hex[:8]}"
        integration_id = f"int-{uuid4().hex[:8]}"

        integration = Integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            name="Test Integration",
            integration_type="test",
        )

        # Act
        integration_test_session.add(integration)
        await integration_test_session.commit()
        await integration_test_session.refresh(integration)

        # Retrieve
        result = await integration_test_session.get(
            Integration,
            (tenant_id, integration_id)
        )

        # Assert
        assert result is not None
        assert result.name == "Test Integration"
```

**Key Points**:
1. Use unique IDs (uuid4) to avoid conflicts
2. Use `integration_test_session` fixture
3. Commit and refresh after adding records
4. PostgreSQL only - no SQLite

## Quick Reference

| Test Type | Fixture | Marker | Database |
|-----------|---------|--------|----------|
| Unit | pytest fixtures | `@pytest.mark.asyncio` | Mock or none |
| Integration | `integration_test_session` | `@pytest.mark.asyncio` + `@pytest.mark.integration` | PostgreSQL (analysi_test) |

## Common Fixtures

- `mock_credentials`: Mock API credentials
- `mock_settings`: Mock integration settings
- `integration_test_session`: PostgreSQL test database session
- `client`: AsyncClient with test database override

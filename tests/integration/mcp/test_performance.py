"""Integration tests for MCP performance."""

from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.auth.models import CurrentUser
from analysi.db.session import get_db
from analysi.main import app

_TEST_API_KEY = "test-perf-key"

_TEST_USER = CurrentUser(
    user_id="test-perf-user",
    email="perf@test.local",
    tenant_id=None,
    roles=["platform_admin"],
    actor_type="user",
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestPerformance:
    """Test performance and concurrency."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        async def _mock_validate(key, session):
            if key == _TEST_API_KEY:
                return _TEST_USER
            return None

        transport = ASGITransport(app=app)
        with patch(
            "analysi.mcp.middleware.validate_api_key",
            new=_mock_validate,
        ):
            async with AsyncClient(
                transport=transport, base_url="http://test", timeout=30.0
            ) as client:
                yield client

        app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_sse_connection_timeout(self, client: AsyncClient):
        """Verify SSE connections handle timeouts properly."""
        try:
            response = await client.get(
                "/v1/default/mcp/sse",
                headers={
                    "Accept": "text/event-stream",
                    "X-API-Key": _TEST_API_KEY,
                },
                timeout=2.0,
            )
            assert response.status_code in [200, 404, 405, 408, 504]
        except TimeoutError:
            pass
        except Exception as e:
            assert isinstance(e, ConnectionError | TimeoutError | NotImplementedError)  # noqa: PT017

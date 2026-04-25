"""Regression tests for health endpoint error sanitization.

/health/db must not leak internal DB exception details (connection strings,
stack traces, backend versions) in its JSON response. The raw error is
recon material for attackers.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from analysi.auth.dependencies import require_platform_admin
from analysi.auth.models import CurrentUser


def _platform_admin():
    return CurrentUser(
        user_id="test",
        email="test@test.local",
        tenant_id=None,
        roles=["platform_admin"],
        actor_type="user",
    )


@pytest.fixture
def app():
    """Create test app with health routers (including /health/db)."""
    from analysi.routers.health import admin_health_router, router

    app = FastAPI()
    app.include_router(router)
    app.include_router(admin_health_router)
    # Bypass auth for unit tests
    app.dependency_overrides[require_platform_admin] = _platform_admin
    return app


class TestHealthDbEndpointSanitization:
    """Verify /health/db does not leak exception details."""

    @pytest.mark.asyncio
    async def test_db_error_does_not_leak_exception_details(self, app):
        """When DB is down, error message must be generic, not str(e)."""
        from analysi.db import session as session_module

        # Simulate a DB connection error with internal details
        internal_error = (
            'connection to server at "10.0.1.5", port 5432 failed: '
            'FATAL: password authentication failed for user "backend_user"'
        )

        async def failing_db():
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(side_effect=Exception(internal_error))
            yield mock_session

        app.dependency_overrides[session_module.get_db] = failing_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health/db")

        body = resp.json()
        data = body["data"]
        assert data["status"] == "unhealthy"

        # The response must NOT contain the raw exception
        error_value = data.get("error", "")
        assert "10.0.1.5" not in error_value, (
            f"Health endpoint leaks internal IP: {error_value}"
        )
        assert "backend_user" not in error_value, (
            f"Health endpoint leaks DB username: {error_value}"
        )
        assert "password" not in error_value, (
            f"Health endpoint leaks password info: {error_value}"
        )

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_healthy_db_returns_normal_response(self, app):
        """When DB is healthy, response is normal."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            from analysi.db import session as session_module

            async def healthy_db():
                mock_session = AsyncMock()
                mock_result = AsyncMock()
                mock_result.scalar.return_value = 1
                mock_session.execute = AsyncMock(return_value=mock_result)
                yield mock_session

            app.dependency_overrides[session_module.get_db] = healthy_db

            resp = await client.get("/health/db")

        body = resp.json()
        data = body["data"]
        assert data["status"] == "healthy"
        assert data["database"] == "connected"

        app.dependency_overrides.clear()

"""Integration tests for auth infrastructure.

Tests:
- Health/probe endpoints return 200 without auth (always exempt)
- require_current_user enforces 401 when no credential provided
- platform_admin override works correctly in autouse fixture
"""

from collections.abc import AsyncGenerator

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from analysi.auth.dependencies import get_current_user, require_current_user
from analysi.auth.models import CurrentUser
from analysi.main import app


@pytest.mark.integration
class TestHealthProbeEndpoints:
    """Health and probe endpoints must be accessible without authentication."""

    @pytest.fixture
    async def client(self) -> AsyncGenerator[AsyncClient]:
        """Client against the real app — auth override from autouse fixture applies."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    async def test_healthz_returns_200_without_auth_basic(self, client):
        response = await client.get("/healthz")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["status"] == "ok"
        assert "request_id" in body["meta"]

    async def test_healthz_returns_200_without_auth(self, client):
        response = await client.get("/healthz")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["status"] == "ok"
        assert "request_id" in body["meta"]

    async def test_readyz_returns_200_without_auth(self, client):
        response = await client.get("/readyz")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["status"] == "ok"
        assert "request_id" in body["meta"]


@pytest.mark.integration
class TestRequireCurrentUserDependency:
    """require_current_user enforces 401 when no user resolved."""

    @pytest.fixture
    def protected_app(self) -> FastAPI:
        """Minimal FastAPI app with a single protected route for testing."""
        test_app = FastAPI()

        @test_app.get("/protected")
        async def protected_route(
            user: CurrentUser = Depends(require_current_user),
        ):
            return {"user_id": user.user_id, "is_admin": user.is_platform_admin}

        return test_app

    @pytest.fixture
    async def unauthed_client(
        self, protected_app: FastAPI
    ) -> AsyncGenerator[AsyncClient]:
        """Client with NO auth override — get_current_user always returns None."""
        # Override get_current_user to return None (no token, no key)
        protected_app.dependency_overrides[get_current_user] = lambda: None
        async with AsyncClient(
            transport=ASGITransport(app=protected_app), base_url="http://test"
        ) as ac:
            yield ac
        protected_app.dependency_overrides.clear()

    @pytest.fixture
    async def authed_client(
        self, protected_app: FastAPI
    ) -> AsyncGenerator[AsyncClient]:
        """Client with a platform_admin user injected."""
        test_user = CurrentUser(
            user_id="admin-id",
            email="admin@analysi.io",
            tenant_id=None,
            roles=["platform_admin"],
            actor_type="user",
        )
        protected_app.dependency_overrides[get_current_user] = lambda: test_user
        async with AsyncClient(
            transport=ASGITransport(app=protected_app), base_url="http://test"
        ) as ac:
            yield ac
        protected_app.dependency_overrides.clear()

    async def test_protected_endpoint_returns_401_without_auth(self, unauthed_client):
        response = await unauthed_client.get("/protected")
        assert response.status_code == 401

    async def test_protected_endpoint_returns_200_with_platform_admin(
        self, authed_client
    ):
        response = await authed_client.get("/protected")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "admin-id"
        assert data["is_admin"] is True

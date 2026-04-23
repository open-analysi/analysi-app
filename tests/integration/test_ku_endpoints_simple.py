"""Simple integration tests for Knowledge Unit API endpoints."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestTableKUEndpoints:
    """Test Table Knowledge Unit endpoints."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        # Clean up the override
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_table_ku_endpoint(self, client: AsyncClient):
        """POST /v1/{tenant}/knowledge-units/tables"""
        payload = {
            "name": "Security Allowlist",
            "description": "Allowed IP addresses",
            "content": {"ips": ["192.168.1.1"]},
        }

        response = await client.post(
            "/v1/test-tenant/knowledge-units/tables",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "Security Allowlist"
        assert data["ku_type"] == "table"
        assert data["content"]["ips"] == ["192.168.1.1"]
        assert "id" in data
        assert data["namespace"] == "/"

    @pytest.mark.asyncio
    async def test_create_table_ku_with_explicit_namespace(self, client: AsyncClient):
        """POST /v1/{tenant}/knowledge-units/tables with explicit namespace."""
        payload = {
            "name": "Scoped Allowlist",
            "description": "Namespaced table",
            "content": {"ips": ["10.0.0.1"]},
            "namespace": "/my_skill/",
        }

        response = await client.post(
            "/v1/test-tenant/knowledge-units/tables",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "Scoped Allowlist"
        assert data["namespace"] == "/my_skill/"

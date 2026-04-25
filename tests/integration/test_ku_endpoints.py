"""Integration tests for Knowledge Unit API endpoints with proper fixtures."""

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
            "description": "Allowed IP addresses and ports",
            "content": {
                "rules": [
                    {"ip": "192.168.1.1", "port": 443},
                    {"ip": "10.0.0.1", "port": 22},
                ]
            },
            "row_count": 2,
            "column_count": 2,
        }

        response = await client.post(
            "/v1/test-tenant/knowledge-units/tables",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "Security Allowlist"
        assert data["ku_type"] == "table"
        assert data["content"]["rules"][0]["ip"] == "192.168.1.1"
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_get_table_ku_endpoint(self, client: AsyncClient):
        """GET /v1/{tenant}/knowledge-units/tables/{id}"""
        # Create a table first
        create_response = await client.post(
            "/v1/test-tenant/knowledge-units/tables",
            json={"name": "Test Table", "content": {"data": "test"}},
        )
        table_id = create_response.json()["data"]["id"]

        # Get it
        response = await client.get(
            f"/v1/test-tenant/knowledge-units/tables/{table_id}"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Test Table"
        assert data["id"] == table_id

    @pytest.mark.asyncio
    async def test_list_table_kus_endpoint(self, client: AsyncClient):
        """GET /v1/{tenant}/knowledge-units/tables"""
        # Create multiple tables
        for i in range(2):
            await client.post(
                "/v1/test-tenant/knowledge-units/tables",
                json={"name": f"Table {i}", "content": {}},
            )

        # List them
        response = await client.get("/v1/test-tenant/knowledge-units/tables")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) >= 2

"""Test that KU API properly handles cy_name field."""

import uuid

import pytest
from httpx import AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestKUCyNameAPI:
    """Test cy_name handling in Knowledge Unit API."""

    @pytest.fixture
    def tenant_id(self):
        """Create unique tenant ID for each test."""
        return f"test-tenant-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def client(self, integration_test_session):
        """Create test client with session override."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        from httpx import ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_table_ku_with_explicit_cy_name(self, client, tenant_id):
        """Test creating a Table KU with explicitly provided cy_name."""
        ku_data = {
            "name": "Security Events Table",
            "cy_name": "security_events_table",
            "description": "Table containing security events",
            "schema": {"columns": ["timestamp", "event_type", "severity"]},
            "content": {"rows": []},
        }

        response = await client.post(
            f"/v1/{tenant_id}/knowledge-units/tables", json=ku_data
        )

        assert response.status_code == 201
        created_ku = response.json()["data"]
        assert created_ku["cy_name"] == "security_events_table"
        assert created_ku["name"] == "Security Events Table"
        print(f"Table KU created with cy_name: {created_ku['cy_name']}")

    @pytest.mark.asyncio
    async def test_create_document_ku_auto_generates_cy_name(self, client, tenant_id):
        """Test that Document KU auto-generates cy_name when not provided."""
        ku_data = {
            "name": "Incident Response Playbook",
            "content": "# Incident Response\n\nStep 1: Identify...",
            "description": "Playbook for incident response",
        }

        response = await client.post(
            f"/v1/{tenant_id}/knowledge-units/documents", json=ku_data
        )

        assert response.status_code == 201
        created_ku = response.json()["data"]
        # Auto-generated from name
        assert created_ku["cy_name"] == "incident_response_playbook"
        assert created_ku["name"] == "Incident Response Playbook"
        print(f"Document KU auto-generated cy_name: {created_ku['cy_name']}")

    @pytest.mark.asyncio
    async def test_duplicate_ku_cy_name_fails(self, client, tenant_id):
        """Test that duplicate cy_name results in conflict."""
        ku_data1 = {
            "name": "First KU",
            "cy_name": "unique_ku_name",
            "content": "First content",
        }

        # Create first KU
        response1 = await client.post(
            f"/v1/{tenant_id}/knowledge-units/documents", json=ku_data1
        )
        assert response1.status_code == 201

        # Try to create second KU with same cy_name
        ku_data2 = {
            "name": "Second KU",
            "cy_name": "unique_ku_name",  # Same cy_name
            "content": "Second content",
        }

        response2 = await client.post(
            f"/v1/{tenant_id}/knowledge-units/documents", json=ku_data2
        )
        assert response2.status_code == 409  # Conflict
        error = response2.json()
        assert "already exists" in str(error)

    @pytest.mark.asyncio
    async def test_list_kus_includes_cy_name(self, client, tenant_id):
        """Test that listing KUs includes cy_name field."""
        # Create a table KU
        ku_data = {
            "name": "Test Table",
            "cy_name": "test_table_list",
            "schema": {"columns": ["id", "value"]},
            "content": {"rows": []},
        }

        response = await client.post(
            f"/v1/{tenant_id}/knowledge-units/tables", json=ku_data
        )
        assert response.status_code == 201

        # List KUs
        response = await client.get(f"/v1/{tenant_id}/knowledge-units/tables")
        assert response.status_code == 200
        ku_list = response.json()

        assert "data" in ku_list
        kus = ku_list["data"]

        # Find our created KU
        test_ku = next(
            (ku for ku in kus if ku.get("cy_name") == "test_table_list"), None
        )
        assert test_ku is not None
        assert test_ku["name"] == "Test Table"
        print("Listed KUs include cy_name field")

    @pytest.mark.asyncio
    async def test_update_ku_cy_name(self, client, tenant_id):
        """Test updating a KU's cy_name."""
        # Create document KU
        ku_data = {
            "name": "Original Document",
            "cy_name": "original_doc",
            "content": "Original content",
        }

        response = await client.post(
            f"/v1/{tenant_id}/knowledge-units/documents", json=ku_data
        )
        assert response.status_code == 201
        ku_id = response.json()["data"]["id"]

        # Update cy_name
        update_data = {"cy_name": "updated_doc"}

        response = await client.put(
            f"/v1/{tenant_id}/knowledge-units/documents/{ku_id}", json=update_data
        )
        assert response.status_code == 200
        updated_ku = response.json()["data"]
        assert updated_ku["cy_name"] == "updated_doc"
        assert updated_ku["name"] == "Original Document"  # Name unchanged
        print("KU cy_name updated successfully")

    @pytest.mark.asyncio
    async def test_invalid_cy_name_format_rejected(self, client, tenant_id):
        """Test that invalid cy_name format is rejected."""
        invalid_cy_names = [
            "CamelCase",  # Must be lowercase
            "with-dashes",  # Only underscores allowed
            "123_starts_with_number",  # Must start with letter
            "has spaces",  # No spaces
        ]

        for invalid_name in invalid_cy_names:
            ku_data = {
                "name": "Test KU",
                "cy_name": invalid_name,
                "content": "test content",
            }

            response = await client.post(
                f"/v1/{tenant_id}/knowledge-units/documents", json=ku_data
            )
            assert response.status_code == 422, f"Should reject cy_name: {invalid_name}"
            print(f"Invalid cy_name rejected: {invalid_name}")

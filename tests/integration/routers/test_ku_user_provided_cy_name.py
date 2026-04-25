"""Test that KU creation properly handles user-provided cy_name field."""

import uuid

import pytest
from httpx import AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestKUUserProvidedCyName:
    """Test user-provided cy_name handling in Knowledge Unit API."""

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
    async def test_create_table_ku_with_user_provided_cy_name(self, client, tenant_id):
        """Test creating a Table KU with user-provided cy_name - would catch UnboundLocalError."""
        ku_data = {
            "name": "User Provided Table",
            "cy_name": "user_provided_table_cy",
            "description": "Table with user-provided cy_name",
            "schema": {"columns": ["id", "value"]},
            "content": {"rows": []},
        }

        response = await client.post(
            f"/v1/{tenant_id}/knowledge-units/tables", json=ku_data
        )

        assert response.status_code == 201, f"Failed: {response.text}"
        created_ku = response.json()["data"]
        assert created_ku["cy_name"] == "user_provided_table_cy"
        assert created_ku["name"] == "User Provided Table"

    @pytest.mark.asyncio
    async def test_create_document_ku_with_user_provided_cy_name(
        self, client, tenant_id
    ):
        """Test creating a Document KU with user-provided cy_name - would catch UnboundLocalError."""
        ku_data = {
            "name": "User Provided Document",
            "cy_name": "user_provided_doc_cy",
            "content": "Document with user-provided cy_name",
            "description": "Test document",
        }

        response = await client.post(
            f"/v1/{tenant_id}/knowledge-units/documents", json=ku_data
        )

        assert response.status_code == 201, f"Failed: {response.text}"
        created_ku = response.json()["data"]
        assert created_ku["cy_name"] == "user_provided_doc_cy"
        assert created_ku["name"] == "User Provided Document"

    @pytest.mark.asyncio
    async def test_create_multiple_kus_with_unique_cy_names(self, client, tenant_id):
        """Test creating multiple KUs with different user-provided cy_names."""
        # Create first table KU
        ku_data1 = {
            "name": "First Table",
            "cy_name": "first_table_cy",
            "schema": {"columns": ["col1"]},
            "content": {"rows": []},
        }

        response1 = await client.post(
            f"/v1/{tenant_id}/knowledge-units/tables", json=ku_data1
        )
        assert response1.status_code == 201

        # Create second table KU with different cy_name
        ku_data2 = {
            "name": "Second Table",
            "cy_name": "second_table_cy",
            "schema": {"columns": ["col2"]},
            "content": {"rows": []},
        }

        response2 = await client.post(
            f"/v1/{tenant_id}/knowledge-units/tables", json=ku_data2
        )
        assert response2.status_code == 201

        # Create document KU with yet another cy_name
        ku_data3 = {
            "name": "Test Document",
            "cy_name": "test_document_cy",
            "content": "Some content",
        }

        response3 = await client.post(
            f"/v1/{tenant_id}/knowledge-units/documents", json=ku_data3
        )
        assert response3.status_code == 201

        # Verify all three were created with correct cy_names
        list_response = await client.get(f"/v1/{tenant_id}/knowledge-units")
        assert list_response.status_code == 200
        kus = list_response.json()["data"]

        cy_names = [ku["cy_name"] for ku in kus]
        assert "first_table_cy" in cy_names
        assert "second_table_cy" in cy_names
        assert "test_document_cy" in cy_names

    @pytest.mark.asyncio
    async def test_reject_duplicate_user_provided_cy_name(self, client, tenant_id):
        """Test that duplicate user-provided cy_name is rejected with 409."""
        ku_data = {
            "name": "Original Table",
            "cy_name": "duplicate_test_cy",
            "schema": {"columns": ["col1"]},
            "content": {"rows": []},
        }

        # Create first KU
        response1 = await client.post(
            f"/v1/{tenant_id}/knowledge-units/tables", json=ku_data
        )
        assert response1.status_code == 201

        # Try to create second KU with same cy_name but different name
        ku_data2 = {
            "name": "Different Table",
            "cy_name": "duplicate_test_cy",  # Same cy_name
            "schema": {"columns": ["col2"]},
            "content": {"rows": []},
        }

        response2 = await client.post(
            f"/v1/{tenant_id}/knowledge-units/tables", json=ku_data2
        )
        assert response2.status_code == 409
        error = response2.json()
        assert "already exists" in str(error).lower()

    @pytest.mark.asyncio
    async def test_mixed_auto_and_user_provided_cy_names(self, client, tenant_id):
        """Test mixing auto-generated and user-provided cy_names."""
        # Create KU without cy_name (auto-generated)
        ku_data1 = {
            "name": "Auto Generated Table",
            "schema": {"columns": ["col1"]},
            "content": {"rows": []},
        }

        response1 = await client.post(
            f"/v1/{tenant_id}/knowledge-units/tables", json=ku_data1
        )
        assert response1.status_code == 201
        auto_cy_name = response1.json()["data"]["cy_name"]
        assert auto_cy_name == "auto_generated_table"  # Generated from name

        # Create KU with explicit cy_name
        ku_data2 = {
            "name": "Explicit Table",
            "cy_name": "my_custom_cy_name",
            "schema": {"columns": ["col2"]},
            "content": {"rows": []},
        }

        response2 = await client.post(
            f"/v1/{tenant_id}/knowledge-units/tables", json=ku_data2
        )
        assert response2.status_code == 201
        assert response2.json()["data"]["cy_name"] == "my_custom_cy_name"

        # Verify both exist
        list_response = await client.get(f"/v1/{tenant_id}/knowledge-units/tables")
        assert list_response.status_code == 200
        kus = list_response.json()["data"]
        assert len(kus) == 2

        cy_names = [ku["cy_name"] for ku in kus]
        assert "auto_generated_table" in cy_names
        assert "my_custom_cy_name" in cy_names

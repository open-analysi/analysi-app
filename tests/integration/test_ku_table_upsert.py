"""Integration test for KU table upsert functionality."""

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID
from analysi.services.knowledge_unit import KnowledgeUnitService


@pytest.mark.integration
@pytest.mark.asyncio
class TestKUTableUpsert:
    """Test that creating a KU table with the same name updates instead of errors."""

    @pytest.fixture
    async def client(self, integration_test_session):
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        # Create async test client
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

        # Clean up overrides
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_table_twice_updates_instead_of_errors(
        self, client, integration_test_session
    ):
        """Test that creating a table with the same name twice updates it instead of throwing an error."""
        test_client = client
        test_session = integration_test_session
        test_tenant = "test-tenant-upsert"
        table_name = "Test Upsert Table"

        # First creation - should create new table
        first_data = {
            "name": table_name,
            "description": "First version of the table",
            "schema": {
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "value", "type": "string"},
                ]
            },
            "content": {
                "rows": [{"id": 1, "value": "first"}, {"id": 2, "value": "second"}]
            },
            "row_count": 2,
            "column_count": 2,
            "visible": True,
            "system_only": False,
            "created_by": str(SYSTEM_USER_ID),
            "categories": ["test"],
            "app": "test",
        }

        response = await test_client.post(
            f"/v1/{test_tenant}/knowledge-units/tables", json=first_data
        )

        # Should succeed with 201 Created
        assert response.status_code == 201
        first_table = response.json()["data"]
        first_table_id = first_table["id"]
        assert first_table["name"] == table_name
        assert first_table["row_count"] == 2
        assert len(first_table["content"]["rows"]) == 2

        # Second creation with same name - should update existing table
        second_data = {
            "name": table_name,  # Same name!
            "description": "Updated version of the table",
            "schema": {
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "value", "type": "string"},
                    {"name": "status", "type": "string"},  # New column
                ]
            },
            "content": {
                "rows": [
                    {"id": 1, "value": "updated_first", "status": "active"},
                    {"id": 2, "value": "updated_second", "status": "active"},
                    {"id": 3, "value": "third", "status": "new"},
                ]
            },
            "row_count": 3,
            "column_count": 3,
            "visible": True,
            "system_only": True,  # Changed
            "created_by": str(SYSTEM_USER_ID),  # Changed
            "categories": ["test", "updated"],  # Changed
            "app": "test",
        }

        response = await test_client.post(
            f"/v1/{test_tenant}/knowledge-units/tables", json=second_data
        )

        # Should succeed (either 200 OK or 201 Created depending on implementation)
        assert response.status_code in [200, 201]
        second_table = response.json()["data"]

        # Should have the same ID (same table, just updated)
        assert second_table["id"] == first_table_id
        assert second_table["name"] == table_name

        # Should have updated content
        assert second_table["row_count"] == 3
        assert second_table["column_count"] == 3
        assert len(second_table["content"]["rows"]) == 3
        assert second_table["description"] == "Updated version of the table"
        assert second_table["system_only"] is True
        assert "updated" in second_table["categories"]

        # Verify through the service that there's only one table with this name
        ku_service = KnowledgeUnitService(test_session)
        table = await ku_service.get_table_by_name(test_tenant, table_name)
        assert table is not None
        assert str(table.component.id) == first_table_id
        assert table.row_count == 3
        assert table.component.system_only is True

    @pytest.mark.asyncio
    async def test_rapid_sequential_creates_handle_gracefully(
        self, client, integration_test_session
    ):
        """Test that rapid sequential creates of the same table are handled gracefully."""
        test_client = client
        test_session = integration_test_session
        test_tenant = "test-tenant-sequential"
        table_name = "Test Sequential Table"

        table_ids = []

        # Rapidly create the same table 5 times in sequence
        for version in range(1, 6):
            data = {
                "name": table_name,
                "description": f"Version {version}",
                "schema": {
                    "columns": [
                        {"name": "id", "type": "integer"},
                        {"name": "version", "type": "integer"},
                        {
                            "name": f"field_{version}",
                            "type": "string",
                        },  # Different schema each time
                    ]
                },
                "content": {
                    "rows": [
                        {
                            "id": version,
                            "version": version,
                            f"field_{version}": f"value_{version}",
                        }
                    ]
                },
                "row_count": version,  # Different row count
                "column_count": 3,
                "visible": True,
                "created_by": str(SYSTEM_USER_ID),
                "categories": ["sequential", "test", f"v{version}"],
                "app": "test",
            }

            response = await test_client.post(
                f"/v1/{test_tenant}/knowledge-units/tables", json=data
            )

            # First should create (201), rest should update (200 or 201 due to upsert)
            assert response.status_code in [200, 201], (
                f"Request {version} failed: {response.status_code} - {response.text}"
            )

            result = response.json()["data"]
            table_ids.append(result["id"])

            # Verify the update happened
            if version > 1:
                assert result["row_count"] == version, (
                    f"Row count not updated to {version}"
                )

        # All requests should have operated on the same table
        unique_ids = set(table_ids)
        assert len(unique_ids) == 1, f"Multiple tables created: {unique_ids}"

        # Verify final state through service
        ku_service = KnowledgeUnitService(test_session)
        table = await ku_service.get_table_by_name(test_tenant, table_name)
        assert table is not None

        # Should have the last version's data
        assert table.row_count == 5
        assert "v5" in table.component.categories

    @pytest.mark.asyncio
    async def test_system_table_update_preserves_system_fields(
        self, client, integration_test_session
    ):
        """Test that system tables can be updated and system fields are preserved."""
        test_client = client
        test_tenant = "test-tenant-system"
        table_name = "System Table"

        # Create a system table
        first_data = {
            "name": table_name,
            "description": "System managed table",
            "schema": {
                "columns": [
                    {"name": "metric", "type": "string"},
                    {"name": "value", "type": "number"},
                ]
            },
            "content": {"rows": [{"metric": "cpu", "value": 45.2}]},
            "row_count": 1,
            "column_count": 2,
            "visible": True,
            "system_only": True,
            "created_by": str(SYSTEM_USER_ID),
            "categories": ["monitoring", "system"],
            "app": "monitoring",
        }

        response = await test_client.post(
            f"/v1/{test_tenant}/knowledge-units/tables", json=first_data
        )
        assert response.status_code == 201
        first_table = response.json()["data"]

        # Update the system table with new data
        update_data = {
            "name": table_name,
            "description": "Updated system table",
            "schema": {
                "columns": [
                    {"name": "metric", "type": "string"},
                    {"name": "value", "type": "number"},
                    {"name": "timestamp", "type": "string"},
                ]
            },
            "content": {
                "rows": [
                    {
                        "metric": "cpu",
                        "value": 67.8,
                        "timestamp": "2025-01-01T12:00:00Z",
                    },
                    {
                        "metric": "memory",
                        "value": 45.2,
                        "timestamp": "2025-01-01T12:00:00Z",
                    },
                ]
            },
            "row_count": 2,
            "column_count": 3,
            "visible": True,
            "system_only": True,
            "created_by": str(SYSTEM_USER_ID),
            "categories": ["monitoring", "system", "updated"],
            "app": "monitoring",
        }

        response = await test_client.post(
            f"/v1/{test_tenant}/knowledge-units/tables", json=update_data
        )
        assert response.status_code in [200, 201]
        updated_table = response.json()["data"]

        # Should be the same table
        assert updated_table["id"] == first_table["id"]

        # Should have updated content
        assert updated_table["row_count"] == 2
        assert len(updated_table["content"]["rows"]) == 2

        # System fields should be preserved/updated correctly
        assert updated_table["system_only"] is True
        assert updated_table["created_by"] == str(SYSTEM_USER_ID)
        assert "updated" in updated_table["categories"]

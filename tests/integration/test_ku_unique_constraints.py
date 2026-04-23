"""
Integration tests for KU upsert behavior.

Tests that duplicate names trigger updates instead of errors.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.knowledge_unit import KUType
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestKUUniqueConstraints:
    """Test upsert behavior and unique constraints for Knowledge Units."""

    @pytest.mark.asyncio
    async def test_upsert_updates_duplicate_names(
        self, integration_test_session: AsyncSession
    ):
        """Test that creating two tables with same name performs an upsert."""
        tenant_id = "test-tenant"
        table_name = "Unique Table Name"

        repo = KnowledgeUnitRepository(integration_test_session)

        # Create first table
        table1 = await repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,
                "description": "First table",
                "content": {"rows": [{"id": 1}]},
                "row_count": 1,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()
        original_id = table1.component_id

        # Create second table with same name - should update the existing one
        table2 = await repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,  # Same name
                "description": "Second table",
                "content": {"rows": [{"id": 2}]},
                "row_count": 2,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()

        # Should be the same table (upsert)
        assert table2.component_id == original_id
        assert table2.component.description == "Second table"
        assert table2.row_count == 2
        assert table2.content["rows"][0]["id"] == 2

    @pytest.mark.asyncio
    async def test_different_tenants_can_have_same_names(
        self, integration_test_session: AsyncSession
    ):
        """Test that different tenants can have KUs with identical names."""
        tenant1 = "tenant-1"
        tenant2 = "tenant-2"
        shared_name = "Shared Table Name"

        repo = KnowledgeUnitRepository(integration_test_session)

        # Create table in tenant 1
        table1 = await repo.create_table_ku(
            tenant1,
            {
                "name": shared_name,
                "description": "Tenant 1 table",
                "content": {"rows": [{"tenant": 1}]},
                "row_count": 1,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()

        # Create table with same name in tenant 2 - should succeed
        table2 = await repo.create_table_ku(
            tenant2,
            {
                "name": shared_name,  # Same name, different tenant
                "description": "Tenant 2 table",
                "content": {"rows": [{"tenant": 2}]},
                "row_count": 1,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()

        # Both tables should exist
        assert table1.component_id != table2.component_id
        assert table1.component.tenant_id == tenant1
        assert table2.component.tenant_id == tenant2
        assert table1.component.name == table2.component.name == shared_name

    @pytest.mark.asyncio
    async def test_different_types_can_have_same_names(
        self, integration_test_session: AsyncSession
    ):
        """Test that a table and document can share the same name."""
        tenant_id = "test-tenant"
        shared_name = "Shared Resource Name"

        repo = KnowledgeUnitRepository(integration_test_session)

        # Create table
        table = await repo.create_table_ku(
            tenant_id,
            {
                "name": shared_name,
                "description": "A table",
                "content": {"rows": [{"type": "table"}]},
                "row_count": 1,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()

        # Create document with same name - should succeed
        document = await repo.create_document_ku(
            tenant_id,
            {
                "name": shared_name,  # Same name, different KU type
                "description": "A document",
                "content": "Document content",
                "doc_format": "text",
            },
        )
        await integration_test_session.commit()

        # Both should exist
        assert table.component_id != document.component_id
        assert table.component.name == document.component.name == shared_name
        assert table.component.ku_type == KUType.TABLE
        assert document.component.ku_type == KUType.DOCUMENT

    @pytest.mark.asyncio
    async def test_can_create_different_named_tables_same_tenant(
        self, integration_test_session: AsyncSession
    ):
        """Test that we can create multiple tables with different names in same tenant."""
        tenant_id = "test-tenant"

        repo = KnowledgeUnitRepository(integration_test_session)

        # Create multiple tables with different names
        table1 = await repo.create_table_ku(
            tenant_id,
            {
                "name": "Table One",
                "description": "First table",
                "content": {"rows": []},
                "row_count": 0,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()

        table2 = await repo.create_table_ku(
            tenant_id,
            {
                "name": "Table Two",
                "description": "Second table",
                "content": {"rows": []},
                "row_count": 0,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()

        table3 = await repo.create_table_ku(
            tenant_id,
            {
                "name": "Table Three",
                "description": "Third table",
                "content": {"rows": []},
                "row_count": 0,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()

        # All should exist with different IDs
        assert table1.component_id != table2.component_id != table3.component_id
        assert table1.component.name == "Table One"
        assert table2.component.name == "Table Two"
        assert table3.component.name == "Table Three"

    @pytest.mark.asyncio
    async def test_constraint_includes_ku_type(
        self, integration_test_session: AsyncSession
    ):
        """Test that the unique constraint properly includes ku_type field."""
        tenant_id = "test-tenant"
        name = "Test Resource"

        repo = KnowledgeUnitRepository(integration_test_session)

        # Create a table
        table = await repo.create_table_ku(
            tenant_id,
            {
                "name": name,
                "description": "A table",
                "content": {"rows": []},
                "row_count": 0,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()
        table_id = table.component_id

        # Verify ku_type is set
        assert table.component.ku_type == KUType.TABLE

        # Create a document with same name - should work due to different ku_type
        doc = await repo.create_document_ku(
            tenant_id,
            {
                "name": name,
                "description": "A document",
                "content": "Content",
                "doc_format": "text",
            },
        )
        await integration_test_session.commit()

        # Verify ku_type is set
        assert doc.component.ku_type == KUType.DOCUMENT

        # Create another table with same name - should update existing table
        another_table = await repo.create_table_ku(
            tenant_id,
            {
                "name": name,  # Same name and type
                "description": "Another table",
                "content": {"rows": [{"updated": True}]},
                "row_count": 1,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()

        # Should have updated the existing table
        assert another_table.component_id == table_id
        assert another_table.component.description == "Another table"
        assert another_table.row_count == 1

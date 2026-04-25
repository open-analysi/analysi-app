"""Integration tests for the components.ku_type column added by the baseline migration."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.knowledge_unit import KUType


@pytest.mark.asyncio
@pytest.mark.integration
class TestComponentsKuType:
    """Test the components.ku_type column."""

    @pytest.mark.asyncio
    async def test_ku_type_column_added(self, integration_test_session: AsyncSession):
        """Verify ku_type column is added to component table."""
        # Use raw SQL to check column existence
        result = await integration_test_session.execute(
            text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'components'
                AND column_name = 'ku_type'
            """)
        )
        column_info = result.first()

        # Check ku_type column exists
        assert column_info is not None
        assert column_info.column_name == "ku_type"
        assert (
            column_info.is_nullable == "YES"
        )  # Should be nullable for non-KU components
        assert "character" in column_info.data_type.lower()

    @pytest.mark.asyncio
    async def test_existing_data_migrated(self, integration_test_session: AsyncSession):
        """Verify existing KUs have ku_type populated correctly."""
        # This test verifies that the UPDATE statement in the migration worked
        # Create a KU and check its ku_type is set
        from analysi.repositories.knowledge_unit import KnowledgeUnitRepository

        tenant_id = "migration-test"
        repo = KnowledgeUnitRepository(integration_test_session)

        # Create a table KU
        table = await repo.create_table_ku(
            tenant_id,
            {
                "name": "Migration Test Table",
                "description": "Test table for migration",
                "content": [{"id": 1}],
                "row_count": 1,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()

        # Query the component directly to check ku_type
        result = await integration_test_session.execute(
            text("SELECT ku_type FROM components WHERE id = :id"),
            {"id": str(table.component_id)},
        )
        ku_type_value = result.scalar()

        assert ku_type_value == KUType.TABLE

    @pytest.mark.asyncio
    async def test_unique_constraint_created(
        self, integration_test_session: AsyncSession
    ):
        """Verify unique constraint on (tenant_id, namespace, name, ku_type) is enforced.

        The unique constraint covers (tenant_id, namespace, name, ku_type).
        """
        result = await integration_test_session.execute(
            text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'components'
                AND constraint_type = 'UNIQUE'
                AND constraint_name = 'uq_component_tenant_ns_name_ku_type'
            """)
        )
        constraint_row = result.first()

        assert constraint_row is not None
        assert constraint_row.constraint_name == "uq_component_tenant_ns_name_ku_type"

    @pytest.mark.asyncio
    async def test_index_created(self, integration_test_session: AsyncSession):
        """Verify performance index on (tenant_id, namespace, ku_type, name) exists.

        The performance index covers idx_component_tenant_ns_ku_type_name.
        """
        result = await integration_test_session.execute(
            text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'components'
                AND indexname = 'idx_component_tenant_ns_ku_type_name'
            """)
        )
        index_row = result.first()

        assert index_row is not None
        assert "tenant_id" in index_row.indexdef
        assert "namespace" in index_row.indexdef
        assert "ku_type" in index_row.indexdef
        assert "name" in index_row.indexdef

    @pytest.mark.asyncio
    async def test_ku_type_null_for_tasks(self, integration_test_session: AsyncSession):
        """Verify that ku_type remains NULL for non-KU components (tasks)."""
        from analysi.repositories.task import TaskRepository

        tenant_id = "migration-test"
        task_repo = TaskRepository(integration_test_session)

        # Create a task
        task = await task_repo.create(
            {
                "tenant_id": tenant_id,
                "name": "Test Task",
                "description": "Task to verify ku_type is NULL",
                "cy_code": "return 42",
            }
        )
        await integration_test_session.commit()

        # Query the component directly
        result = await integration_test_session.execute(
            text("SELECT ku_type FROM components WHERE id = :id"),
            {"id": str(task.component_id)},
        )
        ku_type_value = result.scalar()

        # Should be NULL for tasks
        assert ku_type_value is None

    @pytest.mark.asyncio
    async def test_constraint_allows_same_name_different_types(
        self, integration_test_session: AsyncSession
    ):
        """Verify constraint allows same name for different KU types."""
        from analysi.repositories.knowledge_unit import KnowledgeUnitRepository

        tenant_id = "migration-test-2"
        name = "Shared Name"
        repo = KnowledgeUnitRepository(integration_test_session)

        # Create table with the name
        table = await repo.create_table_ku(
            tenant_id,
            {
                "name": name,
                "description": "Table with shared name",
                "content": [],
                "row_count": 0,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()

        # Create document with same name - should succeed
        doc = await repo.create_document_ku(
            tenant_id,
            {
                "name": name,
                "description": "Document with shared name",
                "content": "Content",
                "doc_format": "text",
            },
        )
        await integration_test_session.commit()

        # Both should exist
        assert table.component.name == name
        assert doc.component.name == name
        assert table.component.ku_type == KUType.TABLE
        assert doc.component.ku_type == KUType.DOCUMENT

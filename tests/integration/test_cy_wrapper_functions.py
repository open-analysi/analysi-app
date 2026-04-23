"""
Integration tests for Cy-compatible wrapper functions.

Tests the wrapper functions that provide positional-only arguments for Cy scripts.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.cy_ku_functions import create_cy_ku_functions


@pytest.mark.asyncio
@pytest.mark.integration
class TestCyWrapperFunctions:
    """Test Cy-compatible wrapper functions with positional arguments."""

    @pytest.mark.asyncio
    async def test_table_read_wrapper(self, integration_test_session: AsyncSession):
        """Test table_read wrapper accepts single positional argument."""
        tenant_id = "wrapper-test"
        table_name = "Test Table"
        table_data = [{"id": 1, "value": "test"}]

        # Create table
        repo = KnowledgeUnitRepository(integration_test_session)
        await repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,
                "description": "Test table",
                "content": {"rows": table_data},
                "row_count": 1,
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Get wrapper functions
        functions = create_cy_ku_functions(
            integration_test_session, tenant_id, {"tenant_id": tenant_id}
        )

        # Call wrapper with positional argument (Cy-style)
        table_read = functions["table_read"]
        result = await table_read(table_name)

        assert result == table_data

    @pytest.mark.asyncio
    async def test_table_read_via_id_wrapper(
        self, integration_test_session: AsyncSession
    ):
        """Test table_read_via_id wrapper for UUID-based access."""
        tenant_id = "wrapper-test-uuid"
        table_data = [{"id": 1, "data": "uuid-test"}]

        # Create table
        repo = KnowledgeUnitRepository(integration_test_session)
        table = await repo.create_table_ku(
            tenant_id,
            {
                "name": "UUID Table",
                "description": "Test UUID access",
                "content": {"rows": table_data},
                "row_count": 1,
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Get wrapper functions
        functions = create_cy_ku_functions(
            integration_test_session, tenant_id, {"tenant_id": tenant_id}
        )

        # Call wrapper with UUID (positional)
        table_read_via_id = functions["table_read_via_id"]
        result = await table_read_via_id(str(table.component_id))

        assert result == table_data

    @pytest.mark.asyncio
    async def test_table_write_wrapper(self, integration_test_session: AsyncSession):
        """Test table_write wrapper with three positional arguments."""
        tenant_id = "wrapper-write-test"
        table_name = "Write Test Table"
        initial_data = [{"id": 1, "old": "data"}]
        new_data = [{"id": 2, "new": "data"}]

        # Create table
        repo = KnowledgeUnitRepository(integration_test_session)
        await repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,
                "description": "Test write",
                "content": {"rows": initial_data},
                "row_count": 1,
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Get wrapper functions
        functions = create_cy_ku_functions(
            integration_test_session, tenant_id, {"tenant_id": tenant_id}
        )

        # Call write wrapper with positional arguments (Cy-style)
        table_write = functions["table_write"]
        success = await table_write(table_name, new_data, "replace")

        assert success is True

        # Verify data was replaced
        table_read = functions["table_read"]
        result = await table_read(table_name)
        assert result == new_data

    @pytest.mark.asyncio
    async def test_document_read_wrapper(self, integration_test_session: AsyncSession):
        """Test document_read wrapper with single positional argument."""
        tenant_id = "wrapper-doc-test"
        doc_name = "Test Document"
        doc_content = "This is document content"

        # Create document
        repo = KnowledgeUnitRepository(integration_test_session)
        await repo.create_document_ku(
            tenant_id,
            {
                "name": doc_name,
                "description": "Test doc",
                "content": doc_content,
                "doc_format": "text",
            },
        )
        await integration_test_session.commit()

        # Get wrapper functions
        functions = create_cy_ku_functions(
            integration_test_session, tenant_id, {"tenant_id": tenant_id}
        )

        # Call wrapper with positional argument
        document_read = functions["document_read"]
        result = await document_read(doc_name)

        assert result == doc_content

    @pytest.mark.asyncio
    async def test_all_wrapper_functions_present(
        self, integration_test_session: AsyncSession
    ):
        """Test that all expected wrapper functions are present."""
        tenant_id = "wrapper-check"

        functions = create_cy_ku_functions(
            integration_test_session, tenant_id, {"tenant_id": tenant_id}
        )

        # Check all expected functions are present
        expected_functions = [
            "table_read",
            "table_read_via_id",
            "table_write",
            "table_write_via_id",
            "document_read",
            "document_read_via_id",
        ]

        for func_name in expected_functions:
            assert func_name in functions
            assert callable(functions[func_name])

    @pytest.mark.asyncio
    async def test_wrapper_append_mode(self, integration_test_session: AsyncSession):
        """Test table_write wrapper with append mode."""
        tenant_id = "wrapper-append-test"
        table_name = "Append Test"
        initial_data = [{"id": 1, "value": "first"}]
        append_data = [{"id": 2, "value": "second"}]

        # Create table with initial data
        repo = KnowledgeUnitRepository(integration_test_session)
        await repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,
                "description": "Test append",
                "content": {"rows": initial_data},
                "row_count": 1,
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Get wrapper functions
        functions = create_cy_ku_functions(
            integration_test_session, tenant_id, {"tenant_id": tenant_id}
        )

        # Append data using wrapper
        table_write = functions["table_write"]
        success = await table_write(table_name, append_data, "append")
        assert success is True

        # Verify both datasets are present
        table_read = functions["table_read"]
        result = await table_read(table_name)
        assert len(result) == 2
        assert result[0]["value"] == "first"
        assert result[1]["value"] == "second"

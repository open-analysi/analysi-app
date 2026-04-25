"""
Integration tests for Cy Script Knowledge Unit Access.

These tests MUST use actual database operations to verify persistence.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.cy_ku_functions import CyKUFunctions


@pytest.mark.asyncio
@pytest.mark.integration
class TestCyKUAccessIntegration:
    """End-to-end tests for Cy script KU access with real database."""

    @pytest.mark.asyncio
    async def test_cy_script_reads_table_by_name(
        self, integration_test_session: AsyncSession
    ):
        """
        Create a table "Asset List", execute Cy script with table_read("Asset List"),
        verify correct data returned. This test MUST use actual database and verify all data persistence.
        """
        tenant_id = "test-tenant"
        table_name = "Asset List"
        table_data = [
            {"id": 1, "name": "Server-1", "ip": "10.0.0.1", "status": "active"},
            {"id": 2, "name": "Server-2", "ip": "10.0.0.2", "status": "inactive"},
            {"id": 3, "name": "Server-3", "ip": "10.0.0.3", "status": "active"},
        ]

        # Create table in database using repository
        repo = KnowledgeUnitRepository(integration_test_session)
        await repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,
                "description": "Test asset list",
                "content": {"rows": table_data},  # Store as dict with rows key
                "row_count": len(table_data),
                "column_count": 4,
            },
        )
        await integration_test_session.commit()

        # Create Cy KU functions
        execution_context = {"tenant_id": tenant_id}
        cy_functions = CyKUFunctions(
            integration_test_session, tenant_id, execution_context
        )

        # Execute table_read
        result = await cy_functions.table_read(name=table_name)

        # Verify data was correctly read
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["name"] == "Server-1"
        assert result[1]["ip"] == "10.0.0.2"
        assert result[2]["status"] == "active"

    @pytest.mark.asyncio
    async def test_cy_script_writes_table_replace_mode(
        self, integration_test_session: AsyncSession
    ):
        """
        Create a table with initial data, execute Cy script with table_write("Asset List", new_data, mode="replace"),
        then read back and verify data was completely replaced. This test MUST use actual database operations.
        """
        tenant_id = "test-tenant"
        table_name = "Asset List Replace"
        initial_data = [
            {"id": 1, "name": "Old-Server-1"},
            {"id": 2, "name": "Old-Server-2"},
        ]
        new_data = [
            {"id": 10, "name": "New-Server-1", "location": "DC1"},
            {"id": 20, "name": "New-Server-2", "location": "DC2"},
        ]

        # Create initial table
        repo = KnowledgeUnitRepository(integration_test_session)
        await repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,
                "description": "Test replace mode",
                "content": {"rows": initial_data},
                "row_count": len(initial_data),
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Create Cy KU functions
        execution_context = {"tenant_id": tenant_id}
        cy_functions = CyKUFunctions(
            integration_test_session, tenant_id, execution_context
        )

        # Write with replace mode
        write_result = await cy_functions.table_write(
            name=table_name, data=new_data, mode="replace"
        )
        assert write_result is True
        await integration_test_session.commit()

        # Read back and verify replacement
        read_result = await cy_functions.table_read(name=table_name)
        assert len(read_result) == 2
        assert read_result[0]["id"] == 10
        assert read_result[0]["name"] == "New-Server-1"
        assert read_result[0].get("location") == "DC1"
        # Old data should be gone
        assert not any(row.get("name", "").startswith("Old-") for row in read_result)

    @pytest.mark.asyncio
    async def test_cy_script_writes_table_append_mode(
        self, integration_test_session: AsyncSession
    ):
        """
        Create a table with initial data, execute Cy script with table_write("Asset List", new_data, mode="append"),
        then read back and verify data was appended. This test MUST verify data persistence in database.
        """
        tenant_id = "test-tenant"
        table_name = "Asset List Append"
        initial_data = [
            {"id": 1, "name": "Existing-1"},
            {"id": 2, "name": "Existing-2"},
        ]
        append_data = [
            {"id": 3, "name": "Appended-1"},
            {"id": 4, "name": "Appended-2"},
        ]

        # Create initial table
        repo = KnowledgeUnitRepository(integration_test_session)
        await repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,
                "description": "Test append mode",
                "content": {"rows": initial_data},
                "row_count": len(initial_data),
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Create Cy KU functions
        execution_context = {"tenant_id": tenant_id}
        cy_functions = CyKUFunctions(
            integration_test_session, tenant_id, execution_context
        )

        # Write with append mode
        write_result = await cy_functions.table_write(
            name=table_name, data=append_data, mode="append"
        )
        assert write_result is True
        await integration_test_session.commit()

        # Read back and verify both old and new data exist
        read_result = await cy_functions.table_read(name=table_name)
        assert len(read_result) == 4
        # Check existing data is still there
        assert any(row["name"] == "Existing-1" for row in read_result)
        assert any(row["name"] == "Existing-2" for row in read_result)
        # Check appended data is there
        assert any(row["name"] == "Appended-1" for row in read_result)
        assert any(row["name"] == "Appended-2" for row in read_result)

    @pytest.mark.asyncio
    async def test_cy_script_read_write_integration(
        self, integration_test_session: AsyncSession
    ):
        """
        Complete integration test: Create table, write data with Cy script,
        read it back with another Cy script, verify round-trip consistency. MUST use real database.
        """
        tenant_id = "test-tenant"
        table_name = "Round Trip Test"
        test_data = [
            {"id": 1, "product": "Widget A", "price": 19.99, "in_stock": True},
            {"id": 2, "product": "Widget B", "price": 29.99, "in_stock": False},
            {"id": 3, "product": "Widget C", "price": 39.99, "in_stock": True},
        ]

        # Create empty table
        repo = KnowledgeUnitRepository(integration_test_session)
        await repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,
                "description": "Round trip test",
                "content": {"rows": []},
                "row_count": 0,
                "column_count": 4,
            },
        )
        await integration_test_session.commit()

        # Create Cy KU functions
        execution_context = {"tenant_id": tenant_id}
        cy_functions = CyKUFunctions(
            integration_test_session, tenant_id, execution_context
        )

        # Write data
        write_result = await cy_functions.table_write(
            name=table_name, data=test_data, mode="replace"
        )
        assert write_result is True
        await integration_test_session.commit()

        # Read data back
        read_result = await cy_functions.table_read(name=table_name)

        # Verify round-trip consistency
        assert len(read_result) == len(test_data)
        for i, row in enumerate(read_result):
            assert row["id"] == test_data[i]["id"]
            assert row["product"] == test_data[i]["product"]
            assert row["price"] == test_data[i]["price"]
            assert row["in_stock"] == test_data[i]["in_stock"]

    @pytest.mark.asyncio
    async def test_cy_script_reads_document_by_name(
        self, integration_test_session: AsyncSession
    ):
        """
        Create a document "Security Policy", execute Cy script with document_read("Security Policy"),
        verify content.
        """
        tenant_id = "test-tenant"
        doc_name = "Security Policy"
        doc_content = """# Security Policy

        This document outlines our security procedures:
        1. All access must be authenticated
        2. Data must be encrypted at rest
        3. Regular security audits are mandatory
        """

        # Create document in database
        repo = KnowledgeUnitRepository(integration_test_session)
        await repo.create_document_ku(
            tenant_id,
            {
                "name": doc_name,
                "description": "Company security policy",
                "content": doc_content,
                "doc_format": "markdown",
                "word_count": len(doc_content.split()),
            },
        )
        await integration_test_session.commit()

        # Create Cy KU functions
        execution_context = {"tenant_id": tenant_id}
        cy_functions = CyKUFunctions(
            integration_test_session, tenant_id, execution_context
        )

        # Read document
        result = await cy_functions.document_read(name=doc_name)

        # Verify content
        assert isinstance(result, str)
        assert "Security Policy" in result
        assert "authenticated" in result
        assert "encrypted" in result

    @pytest.mark.asyncio
    async def test_cy_script_reads_table_by_uuid(
        self, integration_test_session: AsyncSession
    ):
        """Test UUID-based access as fallback method."""
        tenant_id = "test-tenant"
        table_data = [{"id": 1, "value": "test"}]

        # Create table
        repo = KnowledgeUnitRepository(integration_test_session)
        table_ku = await repo.create_table_ku(
            tenant_id,
            {
                "name": "UUID Test Table",
                "description": "Test UUID access",
                "content": {"rows": table_data},
                "row_count": 1,
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Get the component ID
        table_id = str(table_ku.component_id)

        # Create Cy KU functions
        execution_context = {"tenant_id": tenant_id}
        cy_functions = CyKUFunctions(
            integration_test_session, tenant_id, execution_context
        )

        # Read by UUID
        result = await cy_functions.table_read(id=table_id)

        # Verify data
        assert len(result) == 1
        assert result[0]["value"] == "test"

    @pytest.mark.asyncio
    async def test_cy_script_handles_missing_ku(
        self, integration_test_session: AsyncSession
    ):
        """Test Cy script error handling when KU doesn't exist."""
        tenant_id = "test-tenant"
        execution_context = {"tenant_id": tenant_id}
        cy_functions = CyKUFunctions(
            integration_test_session, tenant_id, execution_context
        )

        # Try to read non-existent table
        with pytest.raises(ValueError, match="not found"):
            await cy_functions.table_read(name="Non-Existent Table")

        # Try to read non-existent document
        with pytest.raises(ValueError, match="not found"):
            await cy_functions.document_read(name="Non-Existent Document")

    @pytest.mark.asyncio
    async def test_cy_script_respects_data_limits(
        self, integration_test_session: AsyncSession
    ):
        """Test that large KUs are properly truncated based on limits."""
        tenant_id = "test-tenant"
        table_name = "Large Table"

        # Create large table
        large_data = [{"id": i, "data": f"row-{i}"} for i in range(100)]
        repo = KnowledgeUnitRepository(integration_test_session)
        await repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,
                "description": "Large table for testing limits",
                "content": {"rows": large_data},
                "row_count": len(large_data),
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Create Cy KU functions
        execution_context = {"tenant_id": tenant_id}
        cy_functions = CyKUFunctions(
            integration_test_session, tenant_id, execution_context
        )

        # Read with max_rows limit
        result = await cy_functions.table_read(name=table_name, max_rows=10)

        # Should only return limited rows
        assert len(result) <= 10

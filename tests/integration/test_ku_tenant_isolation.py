"""
Integration tests for KU tenant isolation.

Tests multi-tenant isolation for Knowledge Unit access.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.cy_ku_functions import CyKUFunctions


@pytest.mark.asyncio
@pytest.mark.integration
class TestKUTenantIsolation:
    """Test tenant isolation for Knowledge Unit access."""

    @pytest.mark.asyncio
    async def test_tenant_cannot_access_other_tenant_ku(
        self, integration_test_session: AsyncSession
    ):
        """Verify strict tenant isolation in KU access."""
        tenant1 = "tenant-alpha"
        tenant2 = "tenant-beta"
        table_name = "Isolated Table"

        repo = KnowledgeUnitRepository(integration_test_session)

        # Create table in tenant1
        await repo.create_table_ku(
            tenant1,
            {
                "name": table_name,
                "description": "Tenant 1's private table",
                "content": {"rows": [{"id": 1, "data": "tenant1-data"}]},
                "row_count": 1,
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Try to access from tenant2 - should not find it
        table2_lookup = await repo.get_table_by_name(tenant2, table_name)
        assert table2_lookup is None

        # Create table with same name in tenant2
        await repo.create_table_ku(
            tenant2,
            {
                "name": table_name,
                "description": "Tenant 2's private table",
                "content": {"rows": [{"id": 2, "data": "tenant2-data"}]},
                "row_count": 1,
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Verify each tenant sees only their own table
        tenant1_table = await repo.get_table_by_name(tenant1, table_name)
        tenant2_table = await repo.get_table_by_name(tenant2, table_name)

        assert tenant1_table is not None
        assert tenant2_table is not None
        assert tenant1_table.component_id != tenant2_table.component_id
        assert tenant1_table.content["rows"][0]["data"] == "tenant1-data"
        assert tenant2_table.content["rows"][0]["data"] == "tenant2-data"

    @pytest.mark.asyncio
    async def test_cy_script_tenant_context_enforced(
        self, integration_test_session: AsyncSession
    ):
        """Test that Cy scripts can only access KUs from their execution tenant."""
        tenant1 = "tenant-x"
        tenant2 = "tenant-y"
        shared_name = "Shared Name Table"

        repo = KnowledgeUnitRepository(integration_test_session)

        # Create tables with same name in both tenants
        await repo.create_table_ku(
            tenant1,
            {
                "name": shared_name,
                "description": "Tenant X table",
                "content": {"rows": [{"tenant": "X", "value": 100}]},
                "row_count": 1,
                "column_count": 2,
            },
        )

        await repo.create_table_ku(
            tenant2,
            {
                "name": shared_name,
                "description": "Tenant Y table",
                "content": {"rows": [{"tenant": "Y", "value": 200}]},
                "row_count": 1,
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Create Cy functions for tenant1
        execution_context1 = {"tenant_id": tenant1}
        cy_functions1 = CyKUFunctions(
            integration_test_session, tenant1, execution_context1
        )

        # Create Cy functions for tenant2
        execution_context2 = {"tenant_id": tenant2}
        cy_functions2 = CyKUFunctions(
            integration_test_session, tenant2, execution_context2
        )

        # Each should only see their own data
        result1 = await cy_functions1.table_read(name=shared_name)
        result2 = await cy_functions2.table_read(name=shared_name)

        assert result1[0]["tenant"] == "X"
        assert result1[0]["value"] == 100
        assert result2[0]["tenant"] == "Y"
        assert result2[0]["value"] == 200

    @pytest.mark.asyncio
    async def test_document_tenant_isolation(
        self, integration_test_session: AsyncSession
    ):
        """Test that documents are also properly isolated by tenant."""
        tenant1 = "docs-tenant-1"
        tenant2 = "docs-tenant-2"
        doc_name = "Company Policy"

        repo = KnowledgeUnitRepository(integration_test_session)

        # Create document in tenant1
        await repo.create_document_ku(
            tenant1,
            {
                "name": doc_name,
                "description": "Tenant 1 policy",
                "content": "Policy for Tenant 1: All data is private",
                "doc_format": "text",
            },
        )
        await integration_test_session.commit()

        # Try to access from tenant2 - should not find it
        doc2_lookup = await repo.get_document_by_name(tenant2, doc_name)
        assert doc2_lookup is None

        # Create document with same name in tenant2
        await repo.create_document_ku(
            tenant2,
            {
                "name": doc_name,
                "description": "Tenant 2 policy",
                "content": "Policy for Tenant 2: Security first",
                "doc_format": "text",
            },
        )
        await integration_test_session.commit()

        # Verify isolation via Cy functions
        execution_context1 = {"tenant_id": tenant1}
        cy_functions1 = CyKUFunctions(
            integration_test_session, tenant1, execution_context1
        )

        execution_context2 = {"tenant_id": tenant2}
        cy_functions2 = CyKUFunctions(
            integration_test_session, tenant2, execution_context2
        )

        content1 = await cy_functions1.document_read(name=doc_name)
        content2 = await cy_functions2.document_read(name=doc_name)

        assert "Tenant 1" in content1
        assert "private" in content1
        assert "Tenant 2" in content2
        assert "Security" in content2

    @pytest.mark.asyncio
    async def test_cross_tenant_uuid_access_blocked(
        self, integration_test_session: AsyncSession
    ):
        """Test that even with a valid UUID from another tenant, access is blocked."""
        tenant1 = "uuid-tenant-1"
        tenant2 = "uuid-tenant-2"

        repo = KnowledgeUnitRepository(integration_test_session)

        # Create table in tenant1
        table = await repo.create_table_ku(
            tenant1,
            {
                "name": "Private Table",
                "description": "Should not be accessible by other tenants",
                "content": {"rows": [{"secret": "tenant1-secret"}]},
                "row_count": 1,
                "column_count": 1,
            },
        )
        await integration_test_session.commit()

        # Get the UUID
        table_uuid = str(table.component_id)

        # Try to access via UUID from tenant2
        execution_context2 = {"tenant_id": tenant2}
        cy_functions2 = CyKUFunctions(
            integration_test_session, tenant2, execution_context2
        )

        # Should fail even with valid UUID
        with pytest.raises(ValueError, match="not found"):
            await cy_functions2.table_read(id=table_uuid)

"""Integration tests for Knowledge Unit repository."""

import pytest

from analysi.repositories.knowledge_unit import KnowledgeUnitRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestKnowledgeUnitRepository:
    """Test Knowledge Unit repository operations with database."""

    @pytest.mark.asyncio
    async def test_create_table_ku_with_component(self, integration_test_session):
        """Create Table KU with Component inheritance."""
        repo = KnowledgeUnitRepository(integration_test_session)

        data = {
            "name": "Security Allowlist",
            "description": "Allowed IP addresses",
            "content": {"ips": ["192.168.1.1"]},
            "row_count": 1,
            "column_count": 1,
        }

        # TDD: This should FAIL until we implement create_table_ku
        table_ku = await repo.create_table_ku("test-tenant", data)

        # These assertions will fail until we implement the method
        assert table_ku.id is not None
        assert table_ku.component.name == "Security Allowlist"
        assert table_ku.component.tenant_id == "test-tenant"
        assert table_ku.component.kind == "ku"
        assert table_ku.content == {"ips": ["192.168.1.1"]}

    @pytest.mark.asyncio
    async def test_create_document_ku_with_component(self, integration_test_session):
        """Create Document KU with Component inheritance."""
        repo = KnowledgeUnitRepository(integration_test_session)

        data = {
            "name": "Security Policy",
            "description": "Company security guidelines",
            "content": "Policy content here...",
            "document_type": "markdown",
            "word_count": 100,
        }

        doc_ku = await repo.create_document_ku("test-tenant", data)

        assert doc_ku.id is not None
        assert doc_ku.component.name == "Security Policy"
        assert doc_ku.component.tenant_id == "test-tenant"
        assert doc_ku.component.kind == "ku"
        assert doc_ku.content == "Policy content here..."
        assert doc_ku.document_type == "markdown"

    @pytest.mark.asyncio
    async def test_create_index_ku_with_component(self, integration_test_session):
        """Create Index KU with Component inheritance."""
        repo = KnowledgeUnitRepository(integration_test_session)

        data = {
            "name": "Security Docs Index",
            "description": "Vector index for docs",
            "index_type": "vector",
            "vector_database": "pinecone",
            "embedding_model": "text-embedding-ada-002",
        }

        index_ku = await repo.create_index_ku("test-tenant", data)

        assert index_ku.id is not None
        assert index_ku.component.name == "Security Docs Index"
        assert index_ku.component.tenant_id == "test-tenant"
        assert index_ku.component.kind == "ku"
        assert index_ku.index_type == "vector"
        assert index_ku.build_status == "pending"

    @pytest.mark.asyncio
    async def test_get_ku_by_id_and_tenant(self, integration_test_session):
        """Retrieve KU with tenant isolation."""
        repo = KnowledgeUnitRepository(integration_test_session)

        # Create a KU first
        data = {"name": "Test Table", "content": {}}
        created_ku = await repo.create_table_ku("tenant-1", data)

        # Get by correct tenant (using Component ID)
        retrieved = await repo.get_ku_by_id(created_ku.component.id, "tenant-1")
        assert retrieved is not None
        assert retrieved.id == created_ku.id

        # Try to get with wrong tenant - should return None
        wrong_tenant = await repo.get_ku_by_id(created_ku.component.id, "tenant-2")
        assert wrong_tenant is None

    @pytest.mark.asyncio
    async def test_update_ku_component_fields(self, integration_test_session):
        """Update both Component and KU-specific fields."""
        repo = KnowledgeUnitRepository(integration_test_session)

        # Create a Table KU
        data = {"name": "Original Name", "content": {"v": 1}}
        ku = await repo.create_table_ku("test-tenant", data)

        # Update both Component fields (name) and KU fields (content)
        update_data = {
            "name": "Updated Name",
            "description": "New description",
            "content": {"v": 2},
            "row_count": 5,
        }

        updated = await repo.update_ku(ku, update_data)

        assert updated.component.name == "Updated Name"
        assert updated.component.description == "New description"
        assert updated.content == {"v": 2}
        assert updated.row_count == 5

    @pytest.mark.asyncio
    async def test_delete_ku_cascades_to_component(self, integration_test_session):
        """Verify cascade delete behavior."""
        repo = KnowledgeUnitRepository(integration_test_session)

        # Create a KU
        data = {"name": "To Delete", "content": {}}
        ku = await repo.create_table_ku("test-tenant", data)
        component_id = ku.component.id

        # Delete it (using Component ID)
        success = await repo.delete_ku(component_id, "test-tenant")
        assert success is True

        # Try to get it - should be None
        deleted = await repo.get_ku_by_id(component_id, "test-tenant")
        assert deleted is None

    @pytest.mark.asyncio
    async def test_list_kus_with_pagination(self, integration_test_session):
        """List KUs with limit/offset."""
        repo = KnowledgeUnitRepository(integration_test_session)

        # Create multiple KUs
        for i in range(5):
            await repo.create_table_ku(
                "test-tenant",
                {"name": f"Table {i}", "content": {}},
            )

        # List with pagination
        results, meta = await repo.list_kus("test-tenant", skip=0, limit=3)
        assert len(results) == 3
        assert meta["total"] >= 5

        # Get next page
        results2, meta2 = await repo.list_kus("test-tenant", skip=3, limit=3)
        assert len(results2) == 2
        assert meta2["total"] >= 5

    @pytest.mark.asyncio
    async def test_search_kus_by_name_description(self, integration_test_session):
        """Search across Component fields."""
        repo = KnowledgeUnitRepository(integration_test_session)

        # Create KUs with searchable content
        await repo.create_table_ku(
            "test-tenant",
            {"name": "Security Allowlist", "description": "IP addresses"},
        )
        await repo.create_document_ku(
            "test-tenant",
            {"name": "Policy Doc", "description": "Security guidelines"},
        )
        await repo.create_table_ku(
            "test-tenant",
            {"name": "Config Table", "description": "System settings"},
        )

        # Search for "security"
        results, meta = await repo.search_kus("test-tenant", "security")
        assert len(results) == 2
        assert all(
            "security" in r.component.name.lower()
            or "security" in r.component.description.lower()
            for r in results
        )

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, integration_test_session):
        """Verify tenant isolation in all operations."""
        repo = KnowledgeUnitRepository(integration_test_session)

        # Create KUs for different tenants
        ku1 = await repo.create_table_ku(
            "tenant-1", {"name": "Tenant1 Table", "content": {}}
        )
        ku2 = await repo.create_table_ku(
            "tenant-2", {"name": "Tenant2 Table", "content": {}}
        )

        # List should only show tenant's own KUs
        tenant1_kus, _ = await repo.list_kus("tenant-1")
        tenant2_kus, _ = await repo.list_kus("tenant-2")

        assert all(ku.component.tenant_id == "tenant-1" for ku in tenant1_kus)
        assert all(ku.component.tenant_id == "tenant-2" for ku in tenant2_kus)

        # Cross-tenant access should fail
        assert await repo.get_ku_by_id(ku1.id, "tenant-2") is None
        assert await repo.get_ku_by_id(ku2.id, "tenant-1") is None

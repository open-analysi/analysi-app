"""Integration tests for Knowledge Unit service."""

import pytest

from analysi.schemas.knowledge_unit import (
    DocumentKUCreate,
    IndexKUCreate,
    TableKUCreate,
    TableKUUpdate,
)
from analysi.services.knowledge_unit import KnowledgeUnitService


@pytest.mark.asyncio
@pytest.mark.integration
class TestKnowledgeUnitService:
    """Test Knowledge Unit service business logic with database."""

    @pytest.mark.asyncio
    async def test_create_table_with_jsonb_content(self, integration_test_session):
        """Create Table with JSONB data validation."""
        service = KnowledgeUnitService(integration_test_session)

        table_data = TableKUCreate(
            name="IP Allowlist",
            description="Allowed IP addresses",
            content={
                "rules": [
                    {"ip": "192.168.1.1", "port": 443, "protocol": "https"},
                    {"ip": "10.0.0.1", "port": 22, "protocol": "ssh"},
                ]
            },
            row_count=2,
            column_count=3,
        )

        table = await service.create_table("test-tenant", table_data)

        assert table.component.name == "IP Allowlist"
        assert table.content["rules"][0]["ip"] == "192.168.1.1"
        assert table.row_count == 2
        assert table.column_count == 3

    @pytest.mark.asyncio
    async def test_create_document_with_metadata(self, integration_test_session):
        """Create Document with proper metadata."""
        service = KnowledgeUnitService(integration_test_session)

        doc_data = DocumentKUCreate(
            name="Incident Response Plan",
            description="How to handle security incidents",
            content="# Incident Response\n\n1. Detect\n2. Respond\n3. Recover",
            document_type="markdown",
            metadata={
                "version": "2.0",
                "last_review": "2024-01-15",
                "owner": "security-team",
            },
        )

        doc = await service.create_document("test-tenant", doc_data)

        assert doc.component.name == "Incident Response Plan"
        assert doc.document_type == "markdown"
        assert doc.doc_metadata["version"] == "2.0"
        assert "# Incident Response" in doc.content

    @pytest.mark.asyncio
    async def test_create_index_management_only(self, integration_test_session):
        """Create Index for management (no build)."""
        service = KnowledgeUnitService(integration_test_session)

        index_data = IndexKUCreate(
            name="Security KB Index",
            description="Vector index for security knowledge base",
            index_type="vector",
            vector_database="pinecone",
            embedding_model="text-embedding-ada-002",
            chunking_config={
                "chunk_size": 500,
                "chunk_overlap": 50,
            },
        )

        index = await service.create_index("test-tenant", index_data)

        assert index.component.name == "Security KB Index"
        assert index.index_type == "vector"
        assert index.build_status == "pending"  # Not built yet
        assert index.chunking_config["chunk_size"] == 500

    @pytest.mark.asyncio
    async def test_update_ku_business_logic(self, integration_test_session):
        """Update with business rule validation."""
        service = KnowledgeUnitService(integration_test_session)

        # Create a table first
        table = await service.create_table(
            "test-tenant",
            TableKUCreate(name="Original", content={"v": 1}),
        )

        # Update it
        update_data = TableKUUpdate(
            name="Updated Table",
            content={"v": 2, "new_field": "value"},
            row_count=10,
        )

        updated = await service.update_table(
            table.component.id, "test-tenant", update_data
        )

        assert updated.component.name == "Updated Table"
        assert updated.content["v"] == 2
        assert updated.content["new_field"] == "value"
        assert updated.row_count == 10

    @pytest.mark.asyncio
    async def test_delete_ku_permission_checks(self, integration_test_session):
        """Delete with proper authorization."""
        service = KnowledgeUnitService(integration_test_session)

        # Create a document
        doc = await service.create_document(
            "tenant-1",
            DocumentKUCreate(name="Test Doc", content="Content"),
        )

        # Delete with correct tenant (using Component ID)
        success = await service.delete_ku(doc.component.id, "tenant-1")
        assert success is True

        # Verify it's gone
        deleted = await service.get_document(doc.component.id, "tenant-1")
        assert deleted is None

    @pytest.mark.asyncio
    async def test_list_kus_by_type(self, integration_test_session):
        """Filter KUs by ku_type."""
        service = KnowledgeUnitService(integration_test_session)
        tenant = "test-tenant"

        # Create different types
        await service.create_table(tenant, TableKUCreate(name="Table1", content={}))
        await service.create_table(tenant, TableKUCreate(name="Table2", content={}))
        await service.create_document(
            tenant, DocumentKUCreate(name="Doc1", content="text")
        )
        await service.create_index(
            tenant, IndexKUCreate(name="Index1", index_type="vector")
        )

        # List only tables
        tables, meta = await service.list_tables(tenant)
        assert len(tables) == 2
        assert all(t.component.name.startswith("Table") for t in tables)

        # List only documents
        docs, meta = await service.list_documents(tenant)
        assert len(docs) == 1
        assert docs[0].component.name == "Doc1"

        # List only indexes
        indexes, meta = await service.list_indexes(tenant)
        assert len(indexes) == 1
        assert indexes[0].component.name == "Index1"

    @pytest.mark.asyncio
    async def test_search_with_query_string(self, integration_test_session):
        """Full-text search implementation."""
        service = KnowledgeUnitService(integration_test_session)
        tenant = "test-tenant"

        # Create KUs with searchable content
        await service.create_table(
            tenant,
            TableKUCreate(
                name="Firewall Rules",
                description="Network security configuration",
                content={},
            ),
        )
        await service.create_document(
            tenant,
            DocumentKUCreate(
                name="Compliance Guide",
                description="Security compliance requirements",
                content="SOC2 compliance details...",
            ),
        )
        await service.create_table(
            tenant,
            TableKUCreate(
                name="User Permissions",
                description="Access control matrix",
                content={},
            ),
        )

        # Search for "security"
        results, meta = await service.search_kus(tenant, "security")
        assert len(results) == 2  # Firewall Rules and Compliance Guide
        assert meta["total"] == 2

        # Search for "compliance"
        results2, meta2 = await service.search_kus(tenant, "compliance")
        assert len(results2) == 1
        assert results2[0].component.name == "Compliance Guide"

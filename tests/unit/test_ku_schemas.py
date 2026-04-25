"""Unit tests for Knowledge Unit schemas."""

import pytest
from pydantic import ValidationError

from analysi.models.auth import SYSTEM_USER_ID
from analysi.schemas.knowledge_unit import (
    DocumentKUCreate,
    IndexKUCreate,
    TableKUCreate,
    TableKUResponse,
    TableKUUpdate,
)


class TestTableKUSchemas:
    """Test Table Knowledge Unit schemas."""

    def test_table_ku_create_schema_validation(self):
        """Validate TableKUCreate schema with required fields."""
        # Valid creation
        table_ku = TableKUCreate(
            name="Security Allowlist",
            description="List of allowed IPs",
            content={"ips": ["192.168.1.1", "10.0.0.1"]},
            row_count=2,
            column_count=1,
            created_by=str(SYSTEM_USER_ID),
        )
        assert table_ku.name == "Security Allowlist"
        assert table_ku.content == {"ips": ["192.168.1.1", "10.0.0.1"]}

        # Test with minimal required fields
        minimal = TableKUCreate(name="Test Table", created_by=str(SYSTEM_USER_ID))
        assert minimal.name == "Test Table"
        assert minimal.content == {}  # Default empty dict

    def test_table_ku_create_invalid_fields(self):
        """Test validation errors for invalid Table KU data."""
        # Name too short
        with pytest.raises(ValidationError) as exc_info:
            TableKUCreate(name="", created_by=str(SYSTEM_USER_ID))
        assert "at least 1 character" in str(exc_info.value).lower()

        # Negative row count
        with pytest.raises(ValidationError) as exc_info:
            TableKUCreate(name="Test", row_count=-1, created_by=str(SYSTEM_USER_ID))
        assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_table_ku_update_partial_fields(self):
        """Ensure update schema allows partial updates."""
        update = TableKUUpdate(content={"new": "data"})
        assert update.content == {"new": "data"}
        assert update.name is None
        assert update.row_count is None

        # Update only name
        update2 = TableKUUpdate(name="Updated Name")
        assert update2.name == "Updated Name"
        assert update2.content is None


class TestDocumentKUSchemas:
    """Test Document Knowledge Unit schemas."""

    def test_document_ku_create_schema_validation(self):
        """Validate DocumentKUCreate schema."""
        doc_ku = DocumentKUCreate(
            name="Security Policy",
            description="Company security guidelines",
            content="This is the security policy content...",
            document_type="markdown",
            metadata={"version": "1.0", "author": "security-team"},
            created_by=str(SYSTEM_USER_ID),
        )
        assert doc_ku.name == "Security Policy"
        assert doc_ku.document_type == "markdown"
        assert doc_ku.metadata["version"] == "1.0"

    def test_document_ku_minimal_fields(self):
        """Test Document KU with minimal required fields."""
        doc = DocumentKUCreate(name="Test Doc", created_by=str(SYSTEM_USER_ID))
        assert doc.name == "Test Doc"
        assert doc.content is None
        assert doc.metadata is None


class TestIndexKUSchemas:
    """Test Index Knowledge Unit schemas."""

    def test_index_ku_create_schema_validation(self):
        """Validate IndexKUCreate schema."""
        index_ku = IndexKUCreate(
            name="Security Docs Index",
            description="Vector index for security documentation",
            index_type="vector",
            vector_database="pinecone",
            embedding_model="text-embedding-ada-002",
            created_by=str(SYSTEM_USER_ID),
        )
        assert index_ku.name == "Security Docs Index"
        assert index_ku.index_type == "vector"
        assert index_ku.vector_database == "pinecone"

    def test_index_ku_type_validation(self):
        """Test index_type field validation."""
        # Valid types
        for idx_type in ["vector", "fulltext", "hybrid"]:
            index = IndexKUCreate(
                name="Test", index_type=idx_type, created_by=str(SYSTEM_USER_ID)
            )
            assert index.index_type == idx_type

        # Invalid type
        with pytest.raises(ValidationError):
            IndexKUCreate(
                name="Test", index_type="invalid", created_by=str(SYSTEM_USER_ID)
            )


class TestKUResponseSchemas:
    """Test Knowledge Unit response schemas."""

    def test_ku_response_flattening(self):
        """Verify Component fields are properly flattened in response."""
        from datetime import UTC, datetime
        from uuid import uuid4

        # Test TableKUResponse
        table_response = TableKUResponse(
            id=uuid4(),
            tenant_id="test-tenant",
            ku_type="table",
            name="Test Table",
            description="Test description",
            version="1.0.0",
            status="enabled",
            visible=False,
            system_only=False,
            app="default",
            categories=[],
            created_by=str(SYSTEM_USER_ID),
            table_schema={},  # Field is table_schema, serializes as "schema"
            content={"data": "test"},
            row_count=1,
            column_count=1,
            file_path=None,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
            last_used_at=None,
        )
        assert table_response.tenant_id == "test-tenant"
        assert table_response.ku_type == "table"
        assert table_response.name == "Test Table"

    def test_invalid_ku_type_rejected(self):
        """Verify invalid ku_type values are rejected."""
        from datetime import UTC, datetime
        from uuid import uuid4

        # TableKUResponse must have ku_type="table"
        with pytest.raises(ValidationError):
            TableKUResponse(
                id=uuid4(),
                tenant_id="test",
                ku_type="document",  # Wrong type
                name="Test",
                description="",
                schema={},
                content={},
                row_count=0,
                column_count=0,
                file_path=None,
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            )

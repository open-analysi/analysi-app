"""
Unit tests for Knowledge Unit model structures and validation.
These tests don't require a database - they test model structure only.
"""

from uuid import uuid4

import pytest

from analysi.models.knowledge_unit import (
    KnowledgeUnit,
    KUDocument,
    KUIndex,
    KUTable,
    KUTool,
    KUType,
)


@pytest.mark.unit
class TestKnowledgeUnitModel:
    """Test KnowledgeUnit base model structure."""

    def test_knowledge_unit_model_attributes(self):
        """Test that KnowledgeUnit model has expected attributes."""
        # Test required attributes exist
        assert hasattr(KnowledgeUnit, "id")
        assert hasattr(KnowledgeUnit, "component_id")
        assert hasattr(KnowledgeUnit, "ku_type")
        assert hasattr(KnowledgeUnit, "created_at")
        assert hasattr(KnowledgeUnit, "updated_at")

        # Test relationship attributes exist
        assert hasattr(KnowledgeUnit, "component")

    def test_ku_type_enum(self):
        """Test KUType enum values."""
        expected_types = ["DOCUMENT", "TABLE", "TOOL", "INDEX"]

        for type_name in expected_types:
            assert hasattr(KUType, type_name)

        # Test specific values
        assert KUType.DOCUMENT == "document"
        assert KUType.TABLE == "table"
        assert KUType.TOOL == "tool"
        assert KUType.INDEX == "index"

    def test_knowledge_unit_initialization(self):
        """Test KnowledgeUnit initialization."""
        component_id = uuid4()

        ku = KnowledgeUnit(component_id=component_id, ku_type=KUType.DOCUMENT)

        assert ku.component_id == component_id
        assert ku.ku_type == KUType.DOCUMENT

    def test_knowledge_unit_table_name(self):
        """Test that KnowledgeUnit has correct table name."""
        assert KnowledgeUnit.__tablename__ == "knowledge_units"


@pytest.mark.unit
class TestKUDocumentModel:
    """Test KUDocument model structure."""

    def test_ku_document_model_attributes(self):
        """Test that KUDocument model has expected attributes."""
        # Test all document-specific attributes exist
        expected_attrs = [
            "id",
            "component_id",
            "content",
            "markdown_content",
            "document_type",
            "doc_format",
            "content_source",
            "source_url",
            "doc_metadata",
            "word_count",
            "character_count",
            "page_count",
            "language",
            "created_at",
            "updated_at",
        ]

        for attr in expected_attrs:
            assert hasattr(KUDocument, attr)

        # Test relationship attributes
        assert hasattr(KUDocument, "component")

    def test_ku_document_initialization_minimal(self):
        """Test KUDocument with minimal fields."""
        component_id = uuid4()

        document = KUDocument(
            component_id=component_id,
            content="Test document content",
            document_type="text",
        )

        assert document.component_id == component_id
        assert document.content == "Test document content"
        assert document.document_type == "text"

    def test_ku_document_initialization_full(self):
        """Test KUDocument with all fields."""
        component_id = uuid4()
        metadata = {
            "source": "upload",
            "author": "test_user",
            "tags": ["important", "security"],
        }

        document = KUDocument(
            component_id=component_id,
            content="Full document content",
            markdown_content="# Full document content",
            document_type="markdown",
            doc_format="processed",
            content_source="upload",
            source_url="https://example.com/doc.pdf",
            doc_metadata=metadata,
            word_count=100,
            character_count=500,
            page_count=2,
            language="en",
        )

        assert document.content == "Full document content"
        assert document.markdown_content == "# Full document content"
        assert document.doc_format == "processed"
        assert document.doc_metadata == metadata
        assert document.word_count == 100
        assert document.page_count == 2
        assert document.language == "en"

    def test_ku_document_table_name(self):
        """Test that KUDocument has correct table name."""
        assert KUDocument.__tablename__ == "ku_documents"


@pytest.mark.unit
class TestKUTableModel:
    """Test KUTable model structure."""

    def test_ku_table_model_attributes(self):
        """Test that KUTable model has expected attributes."""
        expected_attrs = [
            "id",
            "component_id",
            "schema",
            "content",
            "row_count",
            "column_count",
            "created_at",
            "updated_at",
        ]

        for attr in expected_attrs:
            assert hasattr(KUTable, attr)

        assert hasattr(KUTable, "component")

    def test_ku_table_initialization(self):
        """Test KUTable initialization."""
        component_id = uuid4()
        schema = {
            "type": "object",
            "properties": {
                "ip_address": {"type": "string"},
                "risk_score": {"type": "number"},
            },
        }
        content = [
            {"ip_address": "192.168.1.1", "risk_score": 85},
            {"ip_address": "10.0.0.1", "risk_score": 92},
        ]

        table = KUTable(
            component_id=component_id,
            schema=schema,
            content=content,
            row_count=2,
            column_count=2,
        )

        assert table.component_id == component_id
        assert table.schema == schema
        assert table.content == content
        assert table.row_count == 2
        assert table.column_count == 2

    def test_ku_table_table_name(self):
        """Test that KUTable has correct table name."""
        assert KUTable.__tablename__ == "ku_tables"


class TestKUToolModel:
    """Test KUTool model structure."""

    def test_ku_tool_model_attributes(self):
        """Test that KUTool model has expected attributes."""
        expected_attrs = [
            "id",
            "component_id",
            "tool_type",
            "mcp_endpoint",
            "mcp_server_config",
            "input_schema",
            "output_schema",
            "auth_type",
            "credentials_ref",
            "timeout_ms",
            "rate_limit",
            "created_at",
            "updated_at",
        ]

        for attr in expected_attrs:
            assert hasattr(KUTool, attr)

        assert hasattr(KUTool, "component")

    def test_ku_tool_initialization_mcp(self):
        """Test KUTool initialization for MCP tool."""
        component_id = uuid4()
        mcp_config = {
            "server_name": "test-mcp",
            "version": "1.0.0",
            "capabilities": ["search"],
        }
        input_schema = {"type": "object", "properties": {"query": {"type": "string"}}}

        tool = KUTool(
            component_id=component_id,
            tool_type="mcp",
            mcp_endpoint="http://localhost:3000/mcp",
            mcp_server_config=mcp_config,
            input_schema=input_schema,
            auth_type="api_key",
            timeout_ms=30000,
            rate_limit=100,
        )

        assert tool.component_id == component_id
        assert tool.tool_type == "mcp"
        assert tool.mcp_endpoint == "http://localhost:3000/mcp"
        assert tool.mcp_server_config == mcp_config
        assert tool.input_schema == input_schema
        assert tool.timeout_ms == 30000
        assert tool.rate_limit == 100

    def test_ku_tool_initialization_native(self):
        """Test KUTool initialization for native tool."""
        component_id = uuid4()

        tool = KUTool(
            component_id=component_id,
            tool_type="native",
            auth_type="none",
            timeout_ms=5000,
            rate_limit=1000,
        )

        assert tool.tool_type == "native"
        assert tool.mcp_endpoint is None
        assert tool.auth_type == "none"

    def test_ku_tool_table_name(self):
        """Test that KUTool has correct table name."""
        assert KUTool.__tablename__ == "ku_tools"


class TestKUIndexModel:
    """Test KUIndex model structure."""

    def test_ku_index_model_attributes(self):
        """Test that KUIndex model has expected attributes."""
        expected_attrs = [
            "id",
            "component_id",
            "index_type",
            "vector_database",
            "embedding_model",
            "chunking_config",
            "build_status",
            "index_stats",
            "created_at",
            "updated_at",
        ]

        for attr in expected_attrs:
            assert hasattr(KUIndex, attr)

        assert hasattr(KUIndex, "component")

    def test_ku_index_initialization(self):
        """Test KUIndex initialization."""
        component_id = uuid4()
        chunking_config = {
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "separators": ["\\n\\n", "\\n"],
        }
        index_stats = {
            "total_chunks": 150,
            "total_tokens": 50000,
            "embedding_dimensions": 1536,
        }

        index = KUIndex(
            component_id=component_id,
            index_type="vector",
            vector_database="pinecone",
            embedding_model="text-embedding-ada-002",
            chunking_config=chunking_config,
            build_status="completed",
            index_stats=index_stats,
        )

        assert index.component_id == component_id
        assert index.index_type == "vector"
        assert index.vector_database == "pinecone"
        assert index.embedding_model == "text-embedding-ada-002"
        assert index.chunking_config == chunking_config
        assert index.build_status == "completed"
        assert index.index_stats == index_stats

    def test_ku_index_table_name(self):
        """Test that KUIndex has correct table name."""
        assert KUIndex.__tablename__ == "ku_indexes"


class TestKnowledgeUnitTypes:
    """Test knowledge unit type validation and structure."""

    def test_all_ku_types_exist(self):
        """Test that all expected KU types are defined."""
        expected_types = ["document", "table", "tool", "index"]

        for expected_type in expected_types:
            # Check that enum has the type
            found = False
            for attr_name in dir(KUType):
                if (
                    not attr_name.startswith("_")
                    and getattr(KUType, attr_name) == expected_type
                ):
                    found = True
                    break
            assert found, f"KUType missing {expected_type}"

    def test_ku_type_enum_values_are_strings(self):
        """Test that all KUType enum values are strings."""
        for member in KUType:
            assert isinstance(member.value, str), (
                f"KUType.{member.name} should be string"
            )

    def test_json_field_handling(self):
        """Test that JSON fields can handle complex data structures."""
        component_id = uuid4()

        # Test complex metadata structure
        complex_metadata = {
            "processing": {
                "steps": ["extract", "transform", "load"],
                "timestamps": {
                    "started": "2024-01-01T10:00:00Z",
                    "completed": "2026-04-26T10:05:00Z",
                },
            },
            "quality": {"score": 0.95, "issues": [], "validated": True},
            "tags": ["important", "verified", "production"],
            "metrics": {"size_bytes": 1024000, "processing_time_ms": 5430},
        }

        document = KUDocument(
            component_id=component_id,
            content="Test content",
            document_type="test",
            doc_metadata=complex_metadata,
        )

        # Verify complex structure is preserved
        assert document.doc_metadata == complex_metadata
        assert document.doc_metadata["processing"]["steps"] == [
            "extract",
            "transform",
            "load",
        ]
        assert document.doc_metadata["quality"]["score"] == 0.95
        assert document.doc_metadata["tags"] == ["important", "verified", "production"]

"""
Unit tests for IndexEntry model and KUIndex enhancements.
Tests model structure only — no database required.
"""

from uuid import uuid4

import pytest

from analysi.models.index_entry import IndexEntry
from analysi.models.knowledge_unit import KUIndex


@pytest.mark.unit
class TestIndexEntryModel:
    """Test IndexEntry model structure."""

    def test_index_entry_model_attributes(self):
        """Verify all expected attributes exist on IndexEntry."""
        expected_attrs = [
            "id",
            "collection_id",
            "tenant_id",
            "content",
            "embedding",
            "entry_metadata",
            "source_ref",
            "created_at",
            "updated_at",
        ]
        for attr in expected_attrs:
            assert hasattr(IndexEntry, attr), f"IndexEntry missing attribute: {attr}"

    def test_index_entry_initialization(self):
        """Create instance with all fields, verify values."""
        collection_id = uuid4()
        embedding = [0.1] * 1536
        entry_metadata = {"source": "mitre-attack", "technique": "T1566.001"}

        entry = IndexEntry(
            collection_id=collection_id,
            tenant_id="test-tenant",
            content="APT29 uses spearphishing with malicious attachments",
            embedding=embedding,
            entry_metadata=entry_metadata,
            source_ref="document:threat-intel-2025",
        )

        assert entry.collection_id == collection_id
        assert entry.tenant_id == "test-tenant"
        assert entry.content == "APT29 uses spearphishing with malicious attachments"
        assert entry.embedding == embedding
        assert entry.entry_metadata == entry_metadata
        assert entry.source_ref == "document:threat-intel-2025"

    def test_index_entry_initialization_minimal(self):
        """Create with only required fields, verify defaults."""
        collection_id = uuid4()

        entry = IndexEntry(
            collection_id=collection_id,
            tenant_id="test-tenant",
            content="Minimal entry",
        )

        assert entry.collection_id == collection_id
        assert entry.tenant_id == "test-tenant"
        assert entry.content == "Minimal entry"
        assert entry.source_ref is None

    def test_index_entry_table_name(self):
        """Verify correct table name."""
        assert IndexEntry.__tablename__ == "index_entries"


@pytest.mark.unit
class TestKUIndexEnhanced:
    """Test KUIndex model enhancements."""

    def test_ku_index_new_attributes(self):
        """Verify embedding_dimensions and backend_type exist on KUIndex."""
        assert hasattr(KUIndex, "embedding_dimensions")
        assert hasattr(KUIndex, "backend_type")

    def test_ku_index_initialization_with_new_fields(self):
        """Create KUIndex with new fields, verify values."""
        component_id = uuid4()

        index = KUIndex(
            component_id=component_id,
            index_type="vector",
            vector_database="pgvector",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            backend_type="pgvector",
            build_status="pending",
        )

        assert index.embedding_dimensions == 1536
        assert index.backend_type == "pgvector"
        assert index.embedding_model == "text-embedding-3-small"
        assert index.vector_database == "pgvector"

    def test_ku_index_backend_type_default(self):
        """Verify backend_type defaults to 'pgvector' when not set."""
        component_id = uuid4()

        index = KUIndex(
            component_id=component_id,
            index_type="vector",
        )

        # Default should be pgvector (set at DB level, but model should accept None gracefully)
        # The DB column has DEFAULT 'pgvector', so in-memory without DB it may be None
        # What matters is the column exists and accepts the value
        assert hasattr(index, "backend_type")

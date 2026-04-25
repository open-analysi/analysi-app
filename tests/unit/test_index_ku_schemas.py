"""
Unit tests for IndexKU schema enhancements.
Tests Pydantic schema validation — no database required.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from analysi.schemas.knowledge_unit import (
    IndexKUCreate,
    IndexKUResponse,
    IndexKUUpdate,
)


@pytest.mark.unit
class TestIndexKUSchemas:
    """Test IndexKU Pydantic schema enhancements."""

    def test_index_ku_create_with_new_fields(self):
        """IndexKUCreate accepts embedding_dimensions and backend_type."""
        schema = IndexKUCreate(
            name="threat-intel-kb",
            index_type="vector",
            vector_database="pgvector",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            backend_type="pgvector",
        )

        assert schema.embedding_dimensions == 1536
        assert schema.backend_type == "pgvector"
        assert schema.embedding_model == "text-embedding-3-small"

    def test_index_ku_create_defaults(self):
        """backend_type defaults to 'pgvector', embedding_dimensions defaults to None."""
        schema = IndexKUCreate(name="my-index")

        assert schema.backend_type == "pgvector"
        assert schema.embedding_dimensions is None
        assert schema.index_type == "vector"

    def test_index_ku_response_has_new_fields(self):
        """IndexKUResponse includes embedding_dimensions and backend_type."""
        now = datetime.now(UTC)
        response = IndexKUResponse(
            id=uuid4(),
            tenant_id="test-tenant",
            ku_type="index",
            name="threat-intel-kb",
            index_type="vector",
            vector_database="pgvector",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            backend_type="pgvector",
            chunking_config={},
            build_status="completed",
            build_started_at=None,
            build_completed_at=None,
            build_error_message=None,
            index_stats={"entry_count": 42},
            last_sync_at=None,
            created_at=now,
            updated_at=now,
        )

        assert response.embedding_dimensions == 1536
        assert response.backend_type == "pgvector"

    def test_index_ku_response_new_fields_optional(self):
        """IndexKUResponse works with None for new fields."""
        now = datetime.now(UTC)
        response = IndexKUResponse(
            id=uuid4(),
            tenant_id="test-tenant",
            ku_type="index",
            name="bare-index",
            index_type="vector",
            vector_database=None,
            embedding_model=None,
            embedding_dimensions=None,
            backend_type="pgvector",
            chunking_config={},
            build_status="pending",
            build_started_at=None,
            build_completed_at=None,
            build_error_message=None,
            index_stats={},
            last_sync_at=None,
            created_at=now,
            updated_at=now,
        )

        assert response.embedding_dimensions is None
        assert response.backend_type == "pgvector"

    def test_index_ku_update_has_new_fields(self):
        """IndexKUUpdate accepts embedding_dimensions and backend_type."""
        update = IndexKUUpdate(
            embedding_dimensions=768,
            backend_type="chroma",
        )

        assert update.embedding_dimensions == 768
        assert update.backend_type == "chroma"

    def test_index_ku_update_partial(self):
        """IndexKUUpdate works with only some fields set."""
        update = IndexKUUpdate(embedding_model="text-embedding-004")
        dumped = update.model_dump(exclude_unset=True)

        assert "embedding_model" in dumped
        assert "embedding_dimensions" not in dumped
        assert "backend_type" not in dumped

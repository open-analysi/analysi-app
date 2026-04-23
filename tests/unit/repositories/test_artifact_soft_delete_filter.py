"""Regression tests for soft-deleted artifact filtering.

get_by_id() must exclude soft-deleted artifacts (deleted_at IS NOT NULL).
Without this filter, GET /artifacts/{id} and /download return data that
was supposed to be deleted, violating user expectations and potentially
leaking sensitive information.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.repositories.artifact_repository import ArtifactRepository


class TestArtifactGetByIdExcludesSoftDeleted:
    """Verify get_by_id() filters out soft-deleted artifacts."""

    @pytest.mark.asyncio
    async def test_get_by_id_where_clause_includes_is_deleted_filter(self):
        """The WHERE clause in get_by_id must filter deleted_at IS NULL."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        repo = ArtifactRepository(session)
        await repo.get_by_id("test-tenant", uuid4())

        # Inspect the query that was passed to session.execute
        call_args = session.execute.call_args
        stmt = call_args[0][0]

        # Compile and check the WHERE clause specifically
        from sqlalchemy.dialects import postgresql

        compiled = stmt.compile(dialect=postgresql.dialect())
        sql_str = str(compiled)

        # Split at WHERE to only check the filter clause, not SELECT columns
        parts = sql_str.split("WHERE")
        assert len(parts) == 2, f"Expected WHERE clause in query: {sql_str}"
        where_clause = parts[1]

        assert "deleted_at" in where_clause, (
            f"get_by_id WHERE clause must filter deleted_at to exclude "
            f"soft-deleted artifacts. Current WHERE: {where_clause}"
        )

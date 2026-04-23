"""
Unit tests for idempotent index_create Cy function.

TDD: These tests are written BEFORE the implementation.
index_create should create a collection if it doesn't exist,
or return True silently if it already exists.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.services.cy_index_functions import (
    CyIndexFunctions,
    create_cy_index_functions,
)


@pytest.mark.unit
class TestIndexCreateRegistration:
    """index_create should be registered in the Cy function dict."""

    def test_create_cy_index_functions_includes_index_create(self):
        """create_cy_index_functions returns dict containing index_create."""
        session = AsyncMock()
        functions = create_cy_index_functions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=AsyncMock(),
        )

        assert "index_create" in functions
        assert callable(functions["index_create"])


@pytest.mark.unit
class TestIndexCreateWhenNotExists:
    """index_create should create a new collection when it doesn't exist."""

    @pytest.mark.asyncio
    async def test_creates_collection_when_not_found(self):
        """index_create creates a new index collection when name doesn't exist."""
        session = AsyncMock()
        integration_service = AsyncMock()

        cy_funcs = CyIndexFunctions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=integration_service,
        )

        # Mock: collection doesn't exist
        cy_funcs._ku_repo = AsyncMock()
        cy_funcs._ku_repo.get_index_by_name = AsyncMock(return_value=None)
        cy_funcs._ku_repo.create_index_ku = AsyncMock(
            return_value=MagicMock(component_id=uuid4())
        )

        result = await cy_funcs.index_create("my-new-kb")

        assert result is True
        cy_funcs._ku_repo.create_index_ku.assert_awaited_once()

        # Verify the create call used the right tenant and name
        call_args = cy_funcs._ku_repo.create_index_ku.call_args
        assert call_args[0][0] == "test-tenant"  # tenant_id
        create_data = call_args[0][1]  # data dict
        assert create_data["name"] == "my-new-kb"

    @pytest.mark.asyncio
    async def test_creates_with_description(self):
        """index_create passes description through to create_index_ku."""
        session = AsyncMock()
        cy_funcs = CyIndexFunctions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=AsyncMock(),
        )

        cy_funcs._ku_repo = AsyncMock()
        cy_funcs._ku_repo.get_index_by_name = AsyncMock(return_value=None)
        cy_funcs._ku_repo.create_index_ku = AsyncMock(
            return_value=MagicMock(component_id=uuid4())
        )

        result = await cy_funcs.index_create(
            "threat-intel-kb", description="Threat intelligence embeddings"
        )

        assert result is True
        create_data = cy_funcs._ku_repo.create_index_ku.call_args[0][1]
        assert create_data["description"] == "Threat intelligence embeddings"


@pytest.mark.unit
class TestIndexCreateWhenExists:
    """index_create should be a no-op when collection already exists."""

    @pytest.mark.asyncio
    async def test_returns_true_when_already_exists(self):
        """index_create returns True without creating when collection exists."""
        session = AsyncMock()
        cy_funcs = CyIndexFunctions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=AsyncMock(),
        )

        # Mock: collection already exists
        existing_collection = MagicMock()
        existing_collection.component_id = uuid4()
        cy_funcs._ku_repo = AsyncMock()
        cy_funcs._ku_repo.get_index_by_name = AsyncMock(
            return_value=existing_collection
        )

        result = await cy_funcs.index_create("existing-kb")

        assert result is True
        # Should NOT call create
        cy_funcs._ku_repo.create_index_ku.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_caches_collection_id_on_create(self):
        """index_create caches the new collection_id for subsequent index_add calls."""
        session = AsyncMock()
        cy_funcs = CyIndexFunctions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=AsyncMock(),
        )

        new_id = uuid4()
        cy_funcs._ku_repo = AsyncMock()
        cy_funcs._ku_repo.get_index_by_name = AsyncMock(return_value=None)

        mock_new_collection = MagicMock()
        mock_new_collection.component_id = new_id
        cy_funcs._ku_repo.create_index_ku = AsyncMock(return_value=mock_new_collection)

        await cy_funcs.index_create("new-kb")

        # The collection_id should now be cached
        assert "new-kb" in cy_funcs._collection_cache
        assert cy_funcs._collection_cache["new-kb"] == new_id

    @pytest.mark.asyncio
    async def test_caches_collection_id_when_exists(self):
        """index_create caches the existing collection_id for subsequent calls."""
        session = AsyncMock()
        cy_funcs = CyIndexFunctions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=AsyncMock(),
        )

        existing_id = uuid4()
        existing_collection = MagicMock()
        existing_collection.component_id = existing_id
        cy_funcs._ku_repo = AsyncMock()
        cy_funcs._ku_repo.get_index_by_name = AsyncMock(
            return_value=existing_collection
        )

        await cy_funcs.index_create("existing-kb")

        assert "existing-kb" in cy_funcs._collection_cache
        assert cy_funcs._collection_cache["existing-kb"] == existing_id

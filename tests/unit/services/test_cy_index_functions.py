"""
Unit tests for CyIndexFunctions and create_cy_index_functions.

All dependencies mocked — no DB or AI API calls.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.services.cy_index_functions import create_cy_index_functions


@pytest.mark.unit
class TestCreateCyIndexFunctions:
    """Test the wrapper factory function."""

    def test_returns_expected_keys(self):
        """create_cy_index_functions returns dict with expected function names."""
        session = AsyncMock()
        functions = create_cy_index_functions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=AsyncMock(),
        )

        assert "index_add" in functions
        assert "index_add_with_metadata" in functions
        assert "index_search" in functions
        assert "index_delete" in functions

    def test_all_values_are_callable(self):
        """All returned values should be async callables."""
        session = AsyncMock()
        functions = create_cy_index_functions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=AsyncMock(),
        )

        for name, func in functions.items():
            assert callable(func), f"{name} should be callable"


@pytest.mark.unit
class TestCyIndexAdd:
    """Test index_add Cy function."""

    @pytest.mark.asyncio
    async def test_index_add_calls_service(self):
        """index_add resolves collection by name and calls add_entries."""
        session = AsyncMock()
        integration_service = AsyncMock()

        # Mock the underlying service method
        mock_index_service = AsyncMock()
        mock_index_service.add_entries.return_value = [uuid4()]

        # Mock the DB query to resolve collection by name
        mock_index = MagicMock()
        mock_index.component_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_index
        session.execute.return_value = mock_result
        session.refresh = AsyncMock()

        # Patch the service on the CyIndexFunctions instance
        # We need to access the inner function's closure
        # Simpler: test the CyIndexFunctions class directly
        from analysi.services.cy_index_functions import CyIndexFunctions

        cy_funcs = CyIndexFunctions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=integration_service,
        )
        cy_funcs.index_service = mock_index_service

        result = await cy_funcs.index_add("my-kb", "test content")

        assert result is True
        mock_index_service.add_entries.assert_awaited_once()
        call_kwargs = mock_index_service.add_entries.call_args[1]
        assert call_kwargs["texts"] == ["test content"]
        assert call_kwargs["tenant_id"] == "test-tenant"


@pytest.mark.unit
class TestCyIndexSearch:
    """Test index_search Cy function."""

    @pytest.mark.asyncio
    async def test_index_search_returns_list_of_dicts(self):
        """index_search returns list of result dicts with expected keys."""
        from analysi.services.cy_index_functions import CyIndexFunctions
        from analysi.services.index_backends.base import SearchResult

        session = AsyncMock()
        integration_service = AsyncMock()

        cy_funcs = CyIndexFunctions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=integration_service,
        )

        # Mock collection lookup
        mock_index = MagicMock()
        mock_index.component_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_index
        session.execute.return_value = mock_result
        session.refresh = AsyncMock()

        # Mock service search
        entry_id = uuid4()
        cy_funcs.index_service = AsyncMock()
        cy_funcs.index_service.search.return_value = [
            SearchResult(
                entry_id=entry_id,
                content="matched content",
                score=0.85,
                metadata={"source": "test"},
                source_ref="doc:1",
            )
        ]

        results = await cy_funcs.index_search("my-kb", "find this", top_k=5)

        assert len(results) == 1
        assert results[0]["content"] == "matched content"
        assert results[0]["score"] == 0.85
        assert results[0]["entry_id"] == str(entry_id)
        assert results[0]["metadata"] == {"source": "test"}


@pytest.mark.unit
class TestCyIndexDelete:
    """Test index_delete Cy function."""

    @pytest.mark.asyncio
    async def test_index_delete_calls_service(self):
        """index_delete resolves collection and calls delete_entries."""
        from analysi.services.cy_index_functions import CyIndexFunctions

        session = AsyncMock()
        integration_service = AsyncMock()

        cy_funcs = CyIndexFunctions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=integration_service,
        )

        # Mock collection lookup
        mock_index = MagicMock()
        mock_index.component_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_index
        session.execute.return_value = mock_result
        session.refresh = AsyncMock()

        # Mock service delete
        cy_funcs.index_service = AsyncMock()
        cy_funcs.index_service.delete_entries.return_value = 1

        entry_id = str(uuid4())
        result = await cy_funcs.index_delete("my-kb", entry_id)

        assert result is True
        cy_funcs.index_service.delete_entries.assert_awaited_once()


@pytest.mark.unit
class TestCyIndexCollectionNotFound:
    """Test error handling when collection doesn't exist."""

    @pytest.mark.asyncio
    async def test_index_add_collection_not_found(self):
        """index_add raises ValueError when collection not found."""
        from analysi.services.cy_index_functions import CyIndexFunctions

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        cy_funcs = CyIndexFunctions(
            session=session,
            tenant_id="test-tenant",
            execution_context={},
            integration_service=AsyncMock(),
        )

        with pytest.raises(ValueError, match="not found"):
            await cy_funcs.index_add("nonexistent", "content")

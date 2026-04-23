"""Unit tests for KnowledgeUnitRepository name-based lookups."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.knowledge_unit import KUDocument, KUTable
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository


class TestKURepositoryNameLookup:
    """Test KnowledgeUnitRepository name-based lookup operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create a KnowledgeUnitRepository instance with mock session."""
        return KnowledgeUnitRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_table_by_name_success(self, repository, mock_session):
        """Test successful table retrieval by name."""
        tenant_id = "default"
        table_name = "Asset List"

        # Mock table
        mock_table = MagicMock(spec=KUTable)
        mock_component = MagicMock()
        mock_table.component = mock_component

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_table
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        result = await repository.get_table_by_name(tenant_id, table_name)

        # Verify calls
        mock_session.execute.assert_called_once()
        mock_session.refresh.assert_called_once_with(mock_table, ["component"])
        assert result == mock_table

    @pytest.mark.asyncio
    async def test_get_table_by_name_not_found(self, repository, mock_session):
        """Test behavior when requesting a non-existent table name."""
        tenant_id = "default"
        table_name = "Non-Existent Table"

        # Mock query result - no table found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_table_by_name(tenant_id, table_name)

        # Should return None without errors
        assert result is None
        mock_session.refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_document_by_name_success(self, repository, mock_session):
        """Test successful document retrieval by name."""
        tenant_id = "default"
        doc_name = "Security Policy"

        # Mock document
        mock_doc = MagicMock(spec=KUDocument)
        mock_component = MagicMock()
        mock_doc.component = mock_component

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        result = await repository.get_document_by_name(tenant_id, doc_name)

        # Verify calls
        mock_session.execute.assert_called_once()
        mock_session.refresh.assert_called_once_with(mock_doc, ["component"])
        assert result == mock_doc

    @pytest.mark.asyncio
    async def test_get_document_by_name_different_tenant(
        self, repository, mock_session
    ):
        """Test tenant isolation - same name in different tenants should return different KUs."""
        tenant1 = "tenant1"
        tenant2 = "tenant2"
        doc_name = "Shared Doc Name"

        # Mock documents for different tenants
        mock_doc1 = MagicMock(spec=KUDocument)
        mock_doc1.id = uuid.uuid4()
        mock_doc2 = MagicMock(spec=KUDocument)
        mock_doc2.id = uuid.uuid4()

        # Configure mock to return different docs for different tenants
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_doc1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = mock_doc2

        mock_session.execute.side_effect = [mock_result1, mock_result2]
        mock_session.refresh = AsyncMock()

        # Get documents from different tenants
        result1 = await repository.get_document_by_name(tenant1, doc_name)
        result2 = await repository.get_document_by_name(tenant2, doc_name)

        # Should return different documents
        assert result1 == mock_doc1
        assert result2 == mock_doc2
        assert result1.id != result2.id

    @pytest.mark.asyncio
    async def test_get_table_by_name_wrong_ku_type(self, repository, mock_session):
        """Test that searching for a table name that exists as a document returns None."""
        tenant_id = "default"
        name = "Document Not Table"

        # Mock query result - no table with this name
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_table_by_name(tenant_id, name)

        # Should return None (type safety)
        assert result is None


class TestKURepositoryCRUDOperations:
    """Additional tests for KnowledgeUnitRepository CRUD methods."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, mock_session):
        return KnowledgeUnitRepository(mock_session)

    # -----------------------------------------------------------------------
    # get_table_by_id, get_document_by_id, get_index_by_id
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_table_by_id_returns_table_when_found(
        self, repository, mock_session
    ):
        from analysi.models.knowledge_unit import KUTable

        component_id = uuid.uuid4()
        mock_table = MagicMock(spec=KUTable)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_table
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        result = await repository.get_table_by_id(component_id, "test-tenant")
        assert result == mock_table
        mock_session.refresh.assert_called_once_with(mock_table, ["component"])

    @pytest.mark.asyncio
    async def test_get_table_by_id_returns_none_when_not_found(
        self, repository, mock_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_table_by_id(uuid.uuid4(), "test-tenant")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_document_by_id_returns_document_when_found(
        self, repository, mock_session
    ):
        from analysi.models.knowledge_unit import KUDocument

        component_id = uuid.uuid4()
        mock_doc = MagicMock(spec=KUDocument)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        result = await repository.get_document_by_id(component_id, "test-tenant")
        assert result == mock_doc
        mock_session.refresh.assert_called_once_with(mock_doc, ["component"])

    @pytest.mark.asyncio
    async def test_get_document_by_id_returns_none_when_not_found(
        self, repository, mock_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_document_by_id(uuid.uuid4(), "test-tenant")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_index_by_id_returns_index_when_found(
        self, repository, mock_session
    ):
        from analysi.models.knowledge_unit import KUIndex

        component_id = uuid.uuid4()
        mock_index = MagicMock(spec=KUIndex)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_index
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        result = await repository.get_index_by_id(component_id, "test-tenant")
        assert result == mock_index

    @pytest.mark.asyncio
    async def test_get_index_by_id_returns_none_when_not_found(
        self, repository, mock_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_index_by_id(uuid.uuid4(), "test-tenant")
        assert result is None

    # -----------------------------------------------------------------------
    # get_ku_by_id - polymorphic dispatch
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_ku_by_id_returns_table_when_it_exists(
        self, repository, mock_session
    ):
        from analysi.models.knowledge_unit import KUTable

        component_id = uuid.uuid4()
        mock_table = MagicMock(spec=KUTable)

        # First call (get_table_by_id) returns a table
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_table
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        result = await repository.get_ku_by_id(component_id, "test-tenant")
        assert result == mock_table

    @pytest.mark.asyncio
    async def test_get_ku_by_id_returns_none_when_nothing_found(
        self, repository, mock_session
    ):
        # All lookups return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        result = await repository.get_ku_by_id(uuid.uuid4(), "test-tenant")
        assert result is None

    # -----------------------------------------------------------------------
    # update_ku
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_ku_component_fields(self, repository, mock_session):
        from analysi.models.knowledge_unit import KUTable

        mock_component = MagicMock()
        mock_ku = MagicMock(spec=KUTable)
        mock_ku.component = mock_component
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        update_data = {"name": "new_name", "description": "new_desc"}
        await repository.update_ku(mock_ku, update_data)

        assert mock_component.name == "new_name"
        assert mock_component.description == "new_desc"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_ku_ku_specific_fields(self, repository, mock_session):
        from analysi.models.knowledge_unit import KUTable

        mock_ku = MagicMock(spec=KUTable)
        mock_ku.component = MagicMock()
        mock_ku.row_count = 0
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        update_data = {"row_count": 100}
        await repository.update_ku(mock_ku, update_data)

        mock_session.commit.assert_called_once()

    # -----------------------------------------------------------------------
    # delete_ku
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_ku_returns_true_when_found(self, repository, mock_session):
        from analysi.models.component import Component

        component_id = uuid.uuid4()
        mock_component = MagicMock(spec=Component)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_component
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.expunge_all = MagicMock()

        result = await repository.delete_ku(component_id, "test-tenant")
        assert result is True
        mock_session.delete.assert_called_once_with(mock_component)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_ku_returns_false_when_not_found(
        self, repository, mock_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.delete_ku(uuid.uuid4(), "test-tenant")
        assert result is False

    # -----------------------------------------------------------------------
    # list_kus
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_kus_returns_paginated_results(self, repository, mock_session):
        from analysi.models.knowledge_unit import KnowledgeUnit

        mock_ku1 = MagicMock(spec=KnowledgeUnit)
        mock_ku2 = MagicMock(spec=KnowledgeUnit)

        execute_results = []
        # First call: count query
        count_result = MagicMock()
        count_result.scalar.return_value = 2
        execute_results.append(count_result)
        # Second call: data query
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = [mock_ku1, mock_ku2]
        execute_results.append(data_result)
        mock_session.execute.side_effect = execute_results
        mock_session.refresh = AsyncMock()

        kus, pagination = await repository.list_kus("test-tenant")
        assert len(kus) == 2
        assert pagination["total"] == 2

    @pytest.mark.asyncio
    async def test_list_kus_empty_returns_empty(self, repository, mock_session):
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []
        mock_session.execute.side_effect = [count_result, data_result]

        kus, pagination = await repository.list_kus("test-tenant")
        assert len(kus) == 0
        assert pagination["total"] == 0

    # -----------------------------------------------------------------------
    # get_document_by_name
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_document_by_name_returns_document_when_found(
        self, repository, mock_session
    ):
        from analysi.models.knowledge_unit import KUDocument

        mock_doc = MagicMock(spec=KUDocument)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        result = await repository.get_document_by_name("test-tenant", "my_doc")
        assert result == mock_doc

    @pytest.mark.asyncio
    async def test_get_document_by_name_returns_none_when_not_found(
        self, repository, mock_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_document_by_name("test-tenant", "nonexistent")
        assert result is None

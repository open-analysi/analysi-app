"""Unit tests for KnowledgeUnitService."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.models.knowledge_unit import KUDocument, KUIndex, KUTable
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.schemas.knowledge_unit import (
    DocumentKUCreate,
    DocumentKUUpdate,
    IndexKUCreate,
    IndexKUUpdate,
    TableKUCreate,
    TableKUUpdate,
)
from analysi.services.knowledge_unit import KnowledgeUnitService


class TestKnowledgeUnitService:
    """Test KnowledgeUnitService business logic."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_repository(self):
        """Create a mock KnowledgeUnitRepository."""
        return AsyncMock(spec=KnowledgeUnitRepository)

    @pytest.fixture
    def service(self, mock_session, mock_repository):
        """Create a KnowledgeUnitService instance with mocks."""
        service = KnowledgeUnitService(mock_session)
        service.repository = mock_repository
        return service

    # Table KU Tests
    @pytest.mark.asyncio
    async def test_create_table_ku(self, service, mock_repository):
        """Test creating a Table Knowledge Unit."""
        tenant_id = "default"
        table_data = TableKUCreate(
            name="customers",
            description="Customer database table",
            table_data={
                "database": "analytics",
                "schema": "public",
                "columns": ["id", "name", "email"],
            },
        )

        # Mock the repository call
        mock_table = MagicMock(spec=KUTable)
        mock_repository.create_table_ku.return_value = mock_table

        result = await service.create_table(tenant_id, table_data)

        expected_dict = table_data.model_dump()
        expected_dict.pop("namespace", None)
        mock_repository.create_table_ku.assert_called_once_with(
            tenant_id, expected_dict, namespace="/"
        )
        assert result == mock_table

    @pytest.mark.asyncio
    async def test_get_table_ku(self, service, mock_repository):
        """Test retrieving a Table KU by ID."""
        component_id = uuid.uuid4()
        tenant_id = "default"

        # Mock the repository call
        mock_table = MagicMock(spec=KUTable)
        mock_repository.get_table_by_id.return_value = mock_table

        result = await service.get_table(component_id, tenant_id)

        mock_repository.get_table_by_id.assert_called_once_with(component_id, tenant_id)
        assert result == mock_table

    @pytest.mark.asyncio
    async def test_update_table_ku_success(self, service, mock_repository):
        """Test updating an existing Table KU."""
        component_id = uuid.uuid4()
        tenant_id = "default"
        update_data = TableKUUpdate(description="Updated description")

        # Mock getting the table first
        mock_table = MagicMock(spec=KUTable)
        mock_repository.get_table_by_id.return_value = mock_table
        mock_repository.update_ku.return_value = mock_table

        result = await service.update_table(component_id, tenant_id, update_data)

        mock_repository.get_table_by_id.assert_called_once_with(component_id, tenant_id)
        mock_repository.update_ku.assert_called_once_with(
            mock_table, update_data.model_dump(exclude_unset=True)
        )
        assert result == mock_table

    @pytest.mark.asyncio
    async def test_update_table_ku_not_found(self, service, mock_repository):
        """Test updating non-existent Table KU returns None."""
        component_id = uuid.uuid4()
        tenant_id = "default"
        update_data = TableKUUpdate(description="Updated description")

        # Mock repository to return None
        mock_repository.get_table_by_id.return_value = None

        result = await service.update_table(component_id, tenant_id, update_data)

        mock_repository.get_table_by_id.assert_called_once_with(component_id, tenant_id)
        mock_repository.update_ku.assert_not_called()
        assert result is None

    # Document KU Tests
    @pytest.mark.asyncio
    async def test_create_document_ku(self, service, mock_repository):
        """Test creating a Document Knowledge Unit."""
        tenant_id = "default"
        doc_data = DocumentKUCreate(
            name="security_policy",
            description="Security policy document",
            doc_data={
                "content": "Security policy content...",
                "format": "markdown",
                "version": "1.0",
            },
        )

        # Mock the repository call
        mock_doc = MagicMock(spec=KUDocument)
        mock_repository.create_document_ku.return_value = mock_doc

        result = await service.create_document(tenant_id, doc_data)

        expected_dict = doc_data.model_dump()
        expected_dict.pop("namespace", None)
        mock_repository.create_document_ku.assert_called_once_with(
            tenant_id, expected_dict, namespace="/"
        )
        assert result == mock_doc

    @pytest.mark.asyncio
    async def test_get_document_ku(self, service, mock_repository):
        """Test retrieving a Document KU by ID."""
        component_id = uuid.uuid4()
        tenant_id = "default"

        # Mock the repository call
        mock_doc = MagicMock(spec=KUDocument)
        mock_repository.get_document_by_id.return_value = mock_doc

        result = await service.get_document(component_id, tenant_id)

        mock_repository.get_document_by_id.assert_called_once_with(
            component_id, tenant_id
        )
        assert result == mock_doc

    @pytest.mark.asyncio
    async def test_update_document_ku_success(self, service, mock_repository):
        """Test updating an existing Document KU."""
        component_id = uuid.uuid4()
        tenant_id = "default"
        update_data = DocumentKUUpdate(
            doc_data={"content": "Updated content", "version": "2.0"}
        )

        # Mock getting the document first
        mock_doc = MagicMock(spec=KUDocument)
        mock_repository.get_document_by_id.return_value = mock_doc
        mock_repository.update_ku.return_value = mock_doc

        result = await service.update_document(component_id, tenant_id, update_data)

        mock_repository.get_document_by_id.assert_called_once_with(
            component_id, tenant_id
        )
        mock_repository.update_ku.assert_called_once_with(
            mock_doc, update_data.model_dump(exclude_unset=True)
        )
        assert result == mock_doc

    @pytest.mark.asyncio
    async def test_update_document_ku_not_found(self, service, mock_repository):
        """Test updating non-existent Document KU returns None."""
        component_id = uuid.uuid4()
        tenant_id = "default"
        update_data = DocumentKUUpdate(description="Updated description")

        # Mock repository to return None
        mock_repository.get_document_by_id.return_value = None

        result = await service.update_document(component_id, tenant_id, update_data)

        mock_repository.get_document_by_id.assert_called_once_with(
            component_id, tenant_id
        )
        mock_repository.update_ku.assert_not_called()
        assert result is None

    # Index KU Tests
    @pytest.mark.asyncio
    async def test_create_index_ku(self, service, mock_repository):
        """Test creating an Index Knowledge Unit."""
        tenant_id = "default"
        index_data = IndexKUCreate(
            name="vector_index", description="Vector search index", index_type="vector"
        )

        # Mock the repository call
        mock_index = MagicMock(spec=KUIndex)
        mock_repository.create_index_ku.return_value = mock_index

        result = await service.create_index(tenant_id, index_data)

        expected_dict = index_data.model_dump()
        expected_dict.pop("namespace", None)
        mock_repository.create_index_ku.assert_called_once_with(
            tenant_id, expected_dict, namespace="/"
        )
        assert result == mock_index

    @pytest.mark.asyncio
    async def test_get_index_ku(self, service, mock_repository):
        """Test retrieving an Index KU by ID."""
        component_id = uuid.uuid4()
        tenant_id = "default"

        # Mock the repository call
        mock_index = MagicMock(spec=KUIndex)
        mock_repository.get_index_by_id.return_value = mock_index

        result = await service.get_index(component_id, tenant_id)

        mock_repository.get_index_by_id.assert_called_once_with(component_id, tenant_id)
        assert result == mock_index

    @pytest.mark.asyncio
    async def test_update_index_ku_success(self, service, mock_repository):
        """Test updating an existing Index KU."""
        component_id = uuid.uuid4()
        tenant_id = "default"
        update_data = IndexKUUpdate(build_status="ready")

        # Mock getting the index first
        mock_index = MagicMock(spec=KUIndex)
        mock_repository.get_index_by_id.return_value = mock_index
        mock_repository.update_ku.return_value = mock_index

        result = await service.update_index(component_id, tenant_id, update_data)

        mock_repository.get_index_by_id.assert_called_once_with(component_id, tenant_id)
        mock_repository.update_ku.assert_called_once_with(
            mock_index, update_data.model_dump(exclude_unset=True)
        )
        assert result == mock_index

    @pytest.mark.asyncio
    async def test_update_index_ku_not_found(self, service, mock_repository):
        """Test updating non-existent Index KU returns None."""
        component_id = uuid.uuid4()
        tenant_id = "default"
        update_data = IndexKUUpdate(build_status="building")

        # Mock repository to return None
        mock_repository.get_index_by_id.return_value = None

        result = await service.update_index(component_id, tenant_id, update_data)

        mock_repository.get_index_by_id.assert_called_once_with(component_id, tenant_id)
        mock_repository.update_ku.assert_not_called()
        assert result is None

    # Common Operations Tests
    @pytest.mark.asyncio
    async def test_delete_ku_success(self, service, mock_repository):
        """Test successful KU deletion."""
        component_id = uuid.uuid4()
        tenant_id = "default"

        # Mock successful deletion
        mock_repository.delete_ku.return_value = True

        result = await service.delete_ku(component_id, tenant_id)

        mock_repository.delete_ku.assert_called_once_with(component_id, tenant_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_ku_not_found(self, service, mock_repository):
        """Test deletion of non-existent KU."""
        component_id = uuid.uuid4()
        tenant_id = "default"

        # Mock failed deletion
        mock_repository.delete_ku.return_value = False

        result = await service.delete_ku(component_id, tenant_id)

        mock_repository.delete_ku.assert_called_once_with(component_id, tenant_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_list_tables(self, service, mock_repository, mock_session):
        """Test listing Table KUs with pagination."""
        tenant_id = "default"

        # Create mock KUs and tables
        ku1 = MagicMock()
        ku1.component_id = uuid.uuid4()
        ku2 = MagicMock()
        ku2.component_id = uuid.uuid4()

        # Mock the repository response
        mock_repository.list_kus.return_value = ([ku1, ku2], {"total": 2})

        # Mock the session queries for getting actual table objects
        mock_table1 = MagicMock(spec=KUTable)
        mock_table2 = MagicMock(spec=KUTable)

        # Create a mock result that will return tables
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_table1
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = mock_table2

        # Set up execute to return different results based on call count
        mock_session.execute.side_effect = [mock_result1, mock_result2]
        mock_session.refresh = AsyncMock()

        result = await service.list_tables(tenant_id, skip=0, limit=10)

        mock_repository.list_kus.assert_called_once_with(
            tenant_id=tenant_id, ku_type="table", skip=0, limit=10, app=None
        )

        tables, meta = result
        assert len(tables) == 2
        assert meta["total"] == 2

    @pytest.mark.asyncio
    async def test_list_documents(self, service, mock_repository, mock_session):
        """Test listing Document KUs with pagination."""
        tenant_id = "default"

        # Create mock KUs and documents
        ku1 = MagicMock()
        ku1.component_id = uuid.uuid4()

        # Mock the repository response
        mock_repository.list_kus.return_value = ([ku1], {"total": 1})

        # Mock the session query for getting actual document object
        mock_doc = MagicMock(spec=KUDocument)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        result = await service.list_documents(tenant_id, skip=0, limit=10)

        mock_repository.list_kus.assert_called_once_with(
            tenant_id=tenant_id, ku_type="document", skip=0, limit=10, app=None
        )

        docs, meta = result
        assert len(docs) == 1
        assert meta["total"] == 1

    @pytest.mark.asyncio
    async def test_list_indexes(self, service, mock_repository, mock_session):
        """Test listing Index KUs with pagination."""
        tenant_id = "default"

        # Create mock KUs and indexes
        ku1 = MagicMock()
        ku1.component_id = uuid.uuid4()

        # Mock the repository response
        mock_repository.list_kus.return_value = ([ku1], {"total": 1})

        # Mock the session query for getting actual index object
        mock_index = MagicMock(spec=KUIndex)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_index
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        result = await service.list_indexes(tenant_id, skip=0, limit=10)

        mock_repository.list_kus.assert_called_once_with(
            tenant_id=tenant_id, ku_type="index", skip=0, limit=10, app=None
        )

        indexes, meta = result
        assert len(indexes) == 1
        assert meta["total"] == 1

    @pytest.mark.asyncio
    async def test_search_kus(self, service, mock_repository):
        """Test searching across all Knowledge Units."""
        tenant_id = "default"
        query = "customer"

        # Mock the repository response
        mock_kus = [MagicMock(), MagicMock()]
        mock_repository.search_kus.return_value = (mock_kus, {"total": 2})

        result = await service.search_kus(
            tenant_id, query, ku_type="table", status="active", skip=0, limit=50
        )

        mock_repository.search_kus.assert_called_once_with(
            tenant_id=tenant_id,
            query=query,
            ku_type="table",
            status="active",
            skip=0,
            limit=50,
            categories=None,
        )

        kus, meta = result
        assert kus == mock_kus
        assert meta["total"] == 2
        assert meta["skip"] == 0
        assert meta["limit"] == 50

    @pytest.mark.asyncio
    async def test_list_all_kus(self, service, mock_repository):
        """Test listing all Knowledge Units with optional filters."""
        tenant_id = "default"

        # Mock the repository response
        mock_kus = [MagicMock(), MagicMock(), MagicMock()]
        mock_repository.list_kus.return_value = (mock_kus, {"total": 3})

        result = await service.list_all_kus(
            tenant_id, ku_type=None, status="active", skip=10, limit=20
        )

        mock_repository.list_kus.assert_called_once_with(
            tenant_id=tenant_id,
            ku_type=None,
            status="active",
            skip=10,
            limit=20,
            categories=None,
        )

        kus, meta = result
        assert kus == mock_kus
        assert meta["total"] == 3
        assert meta["skip"] == 10
        assert meta["limit"] == 20

    @pytest.mark.asyncio
    async def test_list_tables_with_missing_entries(
        self, service, mock_repository, mock_session
    ):
        """Test listing tables when some KUs don't have corresponding table entries."""
        tenant_id = "default"

        # Create mock KUs
        ku1 = MagicMock()
        ku1.component_id = uuid.uuid4()
        ku2 = MagicMock()
        ku2.component_id = uuid.uuid4()

        # Mock the repository response
        mock_repository.list_kus.return_value = ([ku1, ku2], {"total": 2})

        # Mock one table existing and one not existing
        mock_table = MagicMock(spec=KUTable)
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_table
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = None  # No table for ku2

        mock_session.execute.side_effect = [mock_result1, mock_result2]
        mock_session.refresh = AsyncMock()

        result = await service.list_tables(tenant_id)

        tables, meta = result
        assert len(tables) == 1  # Only one table found
        assert meta["total"] == 2  # But total KUs is 2

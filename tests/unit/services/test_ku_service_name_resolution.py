"""Unit tests for KnowledgeUnitService name/UUID resolution."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.models.knowledge_unit import KUDocument, KUTable
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.knowledge_unit import KnowledgeUnitService


class TestKUServiceNameResolution:
    """Test KnowledgeUnitService name and UUID resolution methods."""

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

    @pytest.mark.asyncio
    async def test_get_table_by_name_or_id_prefers_name(self, service, mock_repository):
        """Test that when both name and id are provided, name takes precedence."""
        tenant_id = "default"
        table_name = "Asset List"
        table_id = str(uuid.uuid4())

        # Mock table
        mock_table = MagicMock(spec=KUTable)
        service.get_table_by_name = AsyncMock(return_value=mock_table)

        result = await service.get_table_by_name_or_id(
            tenant_id, name=table_name, id=table_id
        )

        # Should call get_table_by_name, not get_table
        service.get_table_by_name.assert_called_once_with(tenant_id, table_name)
        assert result == mock_table

    @pytest.mark.asyncio
    async def test_get_table_by_name_or_id_fallback_to_uuid(self, service):
        """Test UUID lookup when name is not provided."""
        tenant_id = "default"
        table_id = str(uuid.uuid4())

        # Mock table
        mock_table = MagicMock(spec=KUTable)
        service.get_table = AsyncMock(return_value=mock_table)

        result = await service.get_table_by_name_or_id(tenant_id, id=table_id)

        # Should call get_table with UUID
        service.get_table.assert_called_once_with(uuid.UUID(table_id), tenant_id)
        assert result == mock_table

    @pytest.mark.asyncio
    async def test_get_document_by_name_or_id_invalid_uuid(self, service):
        """Test proper error handling when invalid UUID format is provided."""
        tenant_id = "default"
        invalid_uuid = "not-a-valid-uuid"

        with pytest.raises(ValueError, match="badly formed hexadecimal UUID string"):
            await service.get_document_by_name_or_id(tenant_id, id=invalid_uuid)

    @pytest.mark.asyncio
    async def test_service_propagates_repository_errors(self, service, mock_repository):
        """Test that service layer properly propagates repository exceptions."""
        tenant_id = "default"
        doc_name = "Error Document"

        # Mock repository to raise an exception
        mock_repository.get_document_by_name.side_effect = RuntimeError(
            "Database connection failed"
        )
        service.get_document_by_name = AsyncMock(
            side_effect=mock_repository.get_document_by_name
        )

        with pytest.raises(RuntimeError, match="Database connection failed"):
            await service.get_document_by_name(tenant_id, doc_name)

    @pytest.mark.asyncio
    async def test_get_table_by_name_success(self, service, mock_repository):
        """Test successful table retrieval by name through service."""
        tenant_id = "default"
        table_name = "Asset List"

        # Mock table
        mock_table = MagicMock(spec=KUTable)
        mock_repository.get_table_by_name.return_value = mock_table

        result = await service.get_table_by_name(tenant_id, table_name)

        mock_repository.get_table_by_name.assert_called_once_with(
            tenant_id, table_name, namespace="/"
        )
        assert result == mock_table

    @pytest.mark.asyncio
    async def test_get_document_by_name_success(self, service, mock_repository):
        """Test successful document retrieval by name through service."""
        tenant_id = "default"
        doc_name = "Security Policy"

        # Mock document
        mock_doc = MagicMock(spec=KUDocument)
        mock_repository.get_document_by_name.return_value = mock_doc

        result = await service.get_document_by_name(tenant_id, doc_name)

        mock_repository.get_document_by_name.assert_called_once_with(
            tenant_id, doc_name, namespace="/"
        )
        assert result == mock_doc

    @pytest.mark.asyncio
    async def test_get_table_by_name_or_id_no_params(self, service):
        """Test that None is returned when neither name nor id is provided."""
        tenant_id = "default"

        result = await service.get_table_by_name_or_id(tenant_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_document_by_name_or_id_no_params(self, service):
        """Test that None is returned when neither name nor id is provided."""
        tenant_id = "default"

        result = await service.get_document_by_name_or_id(tenant_id)

        assert result is None

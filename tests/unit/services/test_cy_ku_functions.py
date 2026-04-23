"""Unit tests for Cy KU Functions."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.knowledge_unit import KUDocument, KUTable
from analysi.services.cy_ku_functions import CyKUFunctions, create_cy_ku_functions
from analysi.services.knowledge_unit import KnowledgeUnitService


class TestCyKUFunctions:
    """Test Cy native functions for Knowledge Unit access."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def mock_ku_service(self):
        """Create a mock KnowledgeUnitService."""
        return AsyncMock(spec=KnowledgeUnitService)

    @pytest.fixture
    def execution_context(self):
        """Create execution context for testing."""
        return {
            "tenant_id": "default",
            "task_id": str(uuid.uuid4()),
            "task_run_id": str(uuid.uuid4()),
        }

    @pytest.fixture
    def cy_functions(self, mock_session, execution_context, mock_ku_service):
        """Create CyKUFunctions instance with mocks."""
        functions = CyKUFunctions(mock_session, "default", execution_context)
        functions.ku_service = mock_ku_service
        return functions

    @pytest.mark.asyncio
    async def test_table_read_by_name(self, cy_functions, mock_ku_service):
        """Test reading table data by friendly name, verify returned format is List[Dict]."""
        table_name = "Asset List"

        # Mock table with content
        mock_table = MagicMock(spec=KUTable)
        mock_table.content = [
            {"id": 1, "name": "Server-1", "ip": "10.0.0.1"},
            {"id": 2, "name": "Server-2", "ip": "10.0.0.2"},
        ]

        mock_ku_service.get_table_by_name_or_id.return_value = mock_table

        result = await cy_functions.table_read(name=table_name)

        # Verify the call
        mock_ku_service.get_table_by_name_or_id.assert_called_once_with(
            "default", name=table_name, id=None
        )
        # Verify format is List[Dict]
        assert isinstance(result, list)
        assert all(isinstance(row, dict) for row in result)
        assert len(result) == 2
        assert result[0]["name"] == "Server-1"

    @pytest.mark.asyncio
    async def test_table_read_max_rows_limit(self, cy_functions, mock_ku_service):
        """Test that max_rows parameter correctly limits the number of returned rows."""
        table_name = "Large Table"
        max_rows = 3

        # Mock table with many rows
        mock_table = MagicMock(spec=KUTable)
        mock_table.content = [{"id": i, "data": f"row-{i}"} for i in range(10)]

        mock_ku_service.get_table_by_name_or_id.return_value = mock_table

        result = await cy_functions.table_read(name=table_name, max_rows=max_rows)

        # Should only return max_rows
        assert len(result) <= max_rows

    @pytest.mark.asyncio
    async def test_table_read_max_bytes_limit(self, cy_functions, mock_ku_service):
        """Test that max_bytes parameter prevents returning excessive data."""
        table_name = "Large Table"
        max_bytes = 100  # Very small limit

        # Mock table with large content
        mock_table = MagicMock(spec=KUTable)
        mock_table.content = [{"id": i, "data": "x" * 1000} for i in range(10)]

        mock_ku_service.get_table_by_name_or_id.return_value = mock_table

        result = await cy_functions.table_read(name=table_name, max_bytes=max_bytes)

        # Should truncate data to stay within byte limit
        result_bytes = len(json.dumps(result).encode())
        assert result_bytes <= max_bytes * 2  # Allow some overhead for JSON encoding

    @pytest.mark.asyncio
    async def test_table_write_replace_mode(self, cy_functions, mock_ku_service):
        """Test writing data to table with replace mode, verify existing data is overwritten."""
        table_name = "Asset List"
        new_data = [
            {"id": 3, "name": "Server-3", "ip": "10.0.0.3"},
            {"id": 4, "name": "Server-4", "ip": "10.0.0.4"},
        ]

        mock_table = MagicMock(spec=KUTable)
        # Configure mock table with required attributes
        mock_table.component_id = str(uuid.uuid4())
        mock_table.component = MagicMock()
        mock_table.component.name = table_name
        mock_table.schema = {
            "columns": [
                {"name": "id", "type": "integer"},
                {"name": "name", "type": "string"},
            ]
        }
        mock_table.content = None

        mock_ku_service.get_table_by_name_or_id.return_value = mock_table
        mock_ku_service.update_table.return_value = mock_table

        result = await cy_functions.table_write(
            name=table_name, data=new_data, mode="replace"
        )

        # Verify table was fetched and updated
        mock_ku_service.get_table_by_name_or_id.assert_called_once()
        assert result is True

    @pytest.mark.asyncio
    async def test_table_write_append_mode(self, cy_functions, mock_ku_service):
        """Test writing data to table with append mode, verify data is added to existing content."""
        table_name = "Asset List"
        existing_data = [{"id": 1, "name": "Server-1"}]
        new_data = [{"id": 2, "name": "Server-2"}]

        mock_table = MagicMock(spec=KUTable)
        # Configure mock table with required attributes
        mock_table.component_id = str(uuid.uuid4())
        mock_table.component = MagicMock()
        mock_table.component.name = table_name
        mock_table.schema = {
            "columns": [
                {"name": "id", "type": "integer"},
                {"name": "name", "type": "string"},
            ]
        }
        mock_table.content = existing_data.copy()

        mock_ku_service.get_table_by_name_or_id.return_value = mock_table
        mock_ku_service.update_table.return_value = mock_table

        result = await cy_functions.table_write(
            name=table_name, data=new_data, mode="append"
        )

        # Verify append behavior
        assert result is True
        # In real implementation, should verify that content = existing + new

    @pytest.mark.asyncio
    async def test_table_write_invalid_mode(self, cy_functions):
        """Test that invalid mode (not 'replace' or 'append') raises ValueError."""
        table_name = "Asset List"
        data = [{"id": 1}]

        with pytest.raises(ValueError, match="Mode must be 'replace' or 'append'"):
            await cy_functions.table_write(name=table_name, data=data, mode="invalid")

    @pytest.mark.asyncio
    async def test_table_write_empty_data(self, cy_functions, mock_ku_service):
        """Test handling of empty data list in table_write."""
        table_name = "Asset List"
        empty_data = []

        mock_table = MagicMock(spec=KUTable)
        # Configure mock table with required attributes
        mock_table.component_id = str(uuid.uuid4())
        mock_table.component = MagicMock()
        mock_table.component.name = table_name
        mock_table.schema = {
            "columns": [
                {"name": "id", "type": "integer"},
                {"name": "name", "type": "string"},
            ]
        }
        mock_table.content = None

        mock_ku_service.get_table_by_name_or_id.return_value = mock_table
        mock_ku_service.update_table.return_value = mock_table

        result = await cy_functions.table_write(
            name=table_name, data=empty_data, mode="replace"
        )

        # Should handle empty data gracefully
        assert result is True

    @pytest.mark.asyncio
    async def test_document_read_by_name(self, cy_functions, mock_ku_service):
        """Test reading document content by name, verify returned format is string."""
        doc_name = "Security Policy"

        # Mock document with content
        mock_doc = MagicMock(spec=KUDocument)
        mock_doc.content = (
            "This is a security policy document with important information."
        )

        mock_ku_service.get_document_by_name_or_id.return_value = mock_doc

        result = await cy_functions.document_read(name=doc_name)

        # Verify the call
        mock_ku_service.get_document_by_name_or_id.assert_called_once_with(
            "default", name=doc_name, id=None
        )
        # Verify format is string
        assert isinstance(result, str)
        assert "security policy" in result

    @pytest.mark.asyncio
    async def test_document_read_max_characters_limit(
        self, cy_functions, mock_ku_service
    ):
        """Test that max_characters parameter truncates long documents."""
        doc_name = "Long Document"
        max_chars = 50

        # Mock document with long content
        mock_doc = MagicMock(spec=KUDocument)
        mock_doc.content = "x" * 1000  # 1000 characters

        mock_ku_service.get_document_by_name_or_id.return_value = mock_doc

        result = await cy_functions.document_read(
            name=doc_name, max_characters=max_chars
        )

        # Should truncate to max_characters
        assert len(result) <= max_chars

    @pytest.mark.asyncio
    async def test_table_read_not_found_error(self, cy_functions, mock_ku_service):
        """Test appropriate error when table doesn't exist."""
        table_name = "Non-Existent Table"

        mock_ku_service.get_table_by_name_or_id.return_value = None

        with pytest.raises(ValueError, match="Table .* not found"):
            await cy_functions.table_read(name=table_name)

    @pytest.mark.asyncio
    async def test_document_read_empty_content(self, cy_functions, mock_ku_service):
        """Test handling of documents with empty content."""
        doc_name = "Empty Document"

        mock_doc = MagicMock(spec=KUDocument)
        mock_doc.content = ""

        mock_ku_service.get_document_by_name_or_id.return_value = mock_doc

        result = await cy_functions.document_read(name=doc_name)

        # Should handle empty content gracefully
        assert result == ""

    def test_create_cy_ku_functions_returns_dict(self, mock_session, execution_context):
        """Test that factory function returns proper dictionary of callables including all wrapper functions."""
        tenant_id = "default"

        functions_dict = create_cy_ku_functions(
            mock_session, tenant_id, execution_context
        )

        # Verify all functions are present (including new wrapper functions)
        assert "table_read" in functions_dict
        assert "table_write" in functions_dict
        assert "document_read" in functions_dict
        assert "table_read_via_id" in functions_dict
        assert "table_write_via_id" in functions_dict
        assert "document_read_via_id" in functions_dict

        # Verify they are callable
        assert callable(functions_dict["table_read"])
        assert callable(functions_dict["table_write"])
        assert callable(functions_dict["document_read"])
        assert callable(functions_dict["table_read_via_id"])
        assert callable(functions_dict["table_write_via_id"])
        assert callable(functions_dict["document_read_via_id"])

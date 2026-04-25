"""
Unit tests for Cy KU error scenarios.

Tests error handling and edge cases in KU access functions.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from analysi.models.knowledge_unit import KUDocument, KUTable
from analysi.services.cy_ku_functions import CyKUFunctions


@pytest.mark.asyncio
class TestCyKUErrorCases:
    """Test error handling in Cy KU functions."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = MagicMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def cy_functions(self, mock_session):
        """Create CyKUFunctions instance with mocked dependencies."""
        tenant_id = "test-tenant"
        execution_context = {"tenant_id": tenant_id}
        return CyKUFunctions(mock_session, tenant_id, execution_context)

    @pytest.mark.asyncio
    async def test_both_name_and_id_missing(self, cy_functions):
        """Test error when neither name nor id provided."""
        with pytest.raises(ValueError, match="Either name or id must be provided"):
            await cy_functions.table_read()

        with pytest.raises(ValueError, match="Either name or id must be provided"):
            await cy_functions.document_read()

    @pytest.mark.asyncio
    async def test_invalid_max_rows_parameter(self, cy_functions):
        """Test handling of negative or zero max_rows."""
        with patch.object(
            cy_functions.ku_service, "get_table_by_name_or_id", new_callable=AsyncMock
        ) as mock_get:
            mock_table = MagicMock(spec=KUTable)
            mock_table.content = {"rows": [{"id": 1}]}
            mock_get.return_value = mock_table

            # Negative max_rows should be treated as no limit
            result = await cy_functions.table_read(name="test", max_rows=-1)
            assert len(result) == 1

            # Zero max_rows should return empty list
            result = await cy_functions.table_read(name="test", max_rows=0)
            assert result == []

    @pytest.mark.asyncio
    async def test_corrupted_table_content(self, cy_functions):
        """Test handling when table content is not valid JSON."""
        with patch.object(
            cy_functions.ku_service, "get_table_by_name_or_id", new_callable=AsyncMock
        ) as mock_get:
            mock_table = MagicMock(spec=KUTable)
            # Simulate corrupted content
            mock_table.content = "not a dict or list"
            mock_get.return_value = mock_table

            result = await cy_functions.table_read(name="test")
            # Should handle gracefully and return empty list
            assert result == []

    @pytest.mark.asyncio
    async def test_document_read_empty_content(self, cy_functions):
        """Test handling of documents with empty content."""
        with patch.object(
            cy_functions.ku_service,
            "get_document_by_name_or_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_doc = MagicMock(spec=KUDocument)
            mock_doc.content = None
            mock_get.return_value = mock_doc

            result = await cy_functions.document_read(name="empty-doc")
            assert result == ""

            # Test with empty string
            mock_doc.content = ""
            result = await cy_functions.document_read(name="empty-doc")
            assert result == ""

    @pytest.mark.asyncio
    async def test_table_write_invalid_mode(self, cy_functions):
        """Test that invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Mode must be 'replace' or 'append'"):
            await cy_functions.table_write(
                name="test", data=[{"id": 1}], mode="invalid"
            )

    @pytest.mark.asyncio
    async def test_table_write_empty_data(self, cy_functions):
        """Test handling of empty data list in table_write."""
        with patch.object(
            cy_functions.ku_service, "get_table_by_name_or_id", new_callable=AsyncMock
        ) as mock_get:
            with patch.object(
                cy_functions.ku_service, "update_table", new_callable=AsyncMock
            ) as mock_update:
                mock_table = MagicMock(spec=KUTable)
                mock_table.content = {"rows": [{"id": 1}]}
                mock_table.component_id = UUID("12345678-1234-5678-1234-567812345678")
                # Configure required attributes for TableKUUpdate
                mock_table.component = MagicMock()
                mock_table.component.name = "test"
                mock_table.schema = {"columns": [{"name": "id", "type": "integer"}]}
                mock_get.return_value = mock_table
                mock_update.return_value = mock_table

                # Write empty data in replace mode - should clear table
                result = await cy_functions.table_write(
                    name="test", data=[], mode="replace"
                )
                assert result is True
                mock_update.assert_called_once()
                call_args = mock_update.call_args[0]
                assert call_args[2].content == {"rows": []}

    @pytest.mark.asyncio
    async def test_table_write_non_existent_table(self, cy_functions):
        """Test error when trying to write to non-existent table."""
        with patch.object(
            cy_functions.ku_service, "get_table_by_name_or_id", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            with pytest.raises(ValueError, match="Table 'Missing' not found"):
                await cy_functions.table_write(
                    name="Missing", data=[{"id": 1}], mode="replace"
                )

    @pytest.mark.asyncio
    async def test_document_read_max_characters_truncation(self, cy_functions):
        """Test that max_characters properly truncates long documents."""
        with patch.object(
            cy_functions.ku_service,
            "get_document_by_name_or_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_doc = MagicMock(spec=KUDocument)
            mock_doc.content = "a" * 1000  # 1000 character document
            mock_get.return_value = mock_doc

            # Should truncate to 100 characters
            result = await cy_functions.document_read(
                name="long-doc", max_characters=100
            )
            assert len(result) == 100
            assert result == "a" * 100

    @pytest.mark.asyncio
    async def test_table_read_max_bytes_limit(self, cy_functions):
        """Test that max_bytes parameter prevents returning excessive data."""
        with patch.object(
            cy_functions.ku_service, "get_table_by_name_or_id", new_callable=AsyncMock
        ) as mock_get:
            mock_table = MagicMock(spec=KUTable)
            # Create large rows
            large_rows = [{"id": i, "data": "x" * 1000} for i in range(10)]
            mock_table.content = {"rows": large_rows}
            mock_get.return_value = mock_table

            # With max_bytes limit, should return fewer rows
            result = await cy_functions.table_read(name="large-table", max_bytes=2000)
            # Should return only as many rows as fit in byte limit
            assert len(result) < 10
            # Verify we got at least one row
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_invalid_uuid_format(self, cy_functions):
        """Test handling of invalid UUID format in id parameter."""
        with pytest.raises(ValueError, match="badly formed hexadecimal UUID string"):
            await cy_functions.table_read(id="not-a-uuid")

        with pytest.raises(ValueError, match="badly formed hexadecimal UUID string"):
            await cy_functions.document_read(id="invalid-uuid-123")

    @pytest.mark.asyncio
    async def test_none_content_handling(self, cy_functions):
        """Test graceful handling when KU content is None."""
        with patch.object(
            cy_functions.ku_service, "get_table_by_name_or_id", new_callable=AsyncMock
        ) as mock_get:
            mock_table = MagicMock(spec=KUTable)
            mock_table.content = None
            mock_get.return_value = mock_table

            result = await cy_functions.table_read(name="null-table")
            assert result == []

    @pytest.mark.asyncio
    async def test_legacy_list_format_handling(self, cy_functions):
        """Test handling of legacy list format for table content."""
        with patch.object(
            cy_functions.ku_service, "get_table_by_name_or_id", new_callable=AsyncMock
        ) as mock_get:
            mock_table = MagicMock(spec=KUTable)
            # Legacy format: content as list instead of dict
            mock_table.content = [{"id": 1, "name": "legacy"}]
            mock_get.return_value = mock_table

            result = await cy_functions.table_read(name="legacy-table")
            assert len(result) == 1
            assert result[0]["name"] == "legacy"

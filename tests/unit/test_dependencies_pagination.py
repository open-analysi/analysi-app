"""Unit tests for pagination and sorting dependencies."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Query

from analysi.dependencies.pagination import (
    PaginationParams,
    SortingParams,
    apply_pagination_to_query,
    apply_sorting_to_query,
    get_pagination,
    get_sorting,
)


class TestPaginationParams:
    """Test PaginationParams model."""

    def test_pagination_params_valid(self):
        """Test PaginationParams with valid values."""
        params = PaginationParams(limit=20, offset=0)
        assert params.limit == 20
        assert params.offset == 0

    def test_pagination_params_boundary_values(self):
        """Test PaginationParams with boundary values."""
        # Minimum values
        params = PaginationParams(limit=1, offset=0)
        assert params.limit == 1
        assert params.offset == 0

        # Maximum limit
        params = PaginationParams(limit=100, offset=999999)
        assert params.limit == 100
        assert params.offset == 999999

    def test_pagination_params_invalid_limit_low(self):
        """Test PaginationParams with limit too low."""
        with pytest.raises(ValueError):
            PaginationParams(limit=0, offset=0)

    def test_pagination_params_invalid_limit_high(self):
        """Test PaginationParams with limit too high."""
        with pytest.raises(ValueError):
            PaginationParams(limit=101, offset=0)

    def test_pagination_params_invalid_offset(self):
        """Test PaginationParams with negative offset."""
        with pytest.raises(ValueError):
            PaginationParams(limit=20, offset=-1)


class TestSortingParams:
    """Test SortingParams model."""

    def test_sorting_params_valid_asc(self):
        """Test SortingParams with ascending order."""
        params = SortingParams(sort_by="name", sort_order="asc")
        assert params.sort_by == "name"
        assert params.sort_order == "asc"

    def test_sorting_params_valid_desc(self):
        """Test SortingParams with descending order."""
        params = SortingParams(sort_by="created_at", sort_order="desc")
        assert params.sort_by == "created_at"
        assert params.sort_order == "desc"

    def test_sorting_params_invalid_order(self):
        """Test SortingParams with invalid sort order."""
        # This should be validated in the actual implementation
        params = SortingParams(sort_by="name", sort_order="invalid")
        # For now this passes, but should be validated
        assert params.sort_order == "invalid"

    def test_sorting_params_common_fields(self):
        """Test SortingParams with common sortable fields."""
        common_fields = ["id", "name", "created_at", "updated_at", "status"]

        for field in common_fields:
            params = SortingParams(sort_by=field, sort_order="asc")
            assert params.sort_by == field


class TestGetPagination:
    """Test get_pagination dependency."""

    @pytest.mark.asyncio
    async def test_get_pagination_default_values(self):
        """Test get_pagination with default values."""
        pagination = await get_pagination(limit=20, offset=0)
        assert pagination.limit == 20
        assert pagination.offset == 0

    @pytest.mark.asyncio
    async def test_get_pagination_custom_values(self):
        """Test get_pagination with custom values."""
        pagination = await get_pagination(limit=50, offset=100)
        assert pagination.limit == 50
        assert pagination.offset == 100

    @pytest.mark.asyncio
    async def test_get_pagination_validation(self):
        """Test get_pagination validates input."""
        # Should validate limit bounds
        with pytest.raises(ValueError):
            await get_pagination(limit=0, offset=0)

        with pytest.raises(ValueError):
            await get_pagination(limit=101, offset=0)

        # Should validate offset bounds
        with pytest.raises(ValueError):
            await get_pagination(limit=20, offset=-1)

    @pytest.mark.asyncio
    async def test_get_pagination_boundary_values(self):
        """Test get_pagination with boundary values."""
        # Minimum valid values
        pagination = await get_pagination(limit=1, offset=0)
        assert pagination.limit == 1
        assert pagination.offset == 0

        # Maximum valid values
        pagination = await get_pagination(limit=100, offset=999999)
        assert pagination.limit == 100
        assert pagination.offset == 999999


class TestGetSorting:
    """Test get_sorting dependency."""

    @pytest.mark.asyncio
    async def test_get_sorting_default_values(self):
        """Test get_sorting with default values."""
        sorting = await get_sorting(sort_by="created_at", sort_order="desc")
        assert sorting.sort_by == "created_at"
        assert sorting.sort_order == "desc"

    @pytest.mark.asyncio
    async def test_get_sorting_custom_values(self):
        """Test get_sorting with custom values."""
        sorting = await get_sorting(sort_by="name", sort_order="asc")
        assert sorting.sort_by == "name"
        assert sorting.sort_order == "asc"

    @pytest.mark.asyncio
    async def test_get_sorting_validation(self):
        """Test get_sorting validates sort order."""
        # Valid sort orders
        valid_orders = ["asc", "desc"]
        for order in valid_orders:
            sorting = await get_sorting(sort_by="name", sort_order=order)
            assert sorting.sort_order == order

    @pytest.mark.asyncio
    async def test_get_sorting_invalid_order(self):
        """Test get_sorting with invalid sort order."""
        # Should validate sort order in actual implementation
        # For now, this will pass but should eventually raise ValueError
        sorting = await get_sorting(sort_by="name", sort_order="invalid")
        assert sorting.sort_order == "invalid"

    @pytest.mark.asyncio
    async def test_get_sorting_common_fields(self):
        """Test get_sorting with common sortable fields."""
        common_fields = ["id", "name", "created_at", "updated_at", "status"]

        for field in common_fields:
            sorting = await get_sorting(sort_by=field, sort_order="asc")
            assert sorting.sort_by == field


class TestApplyPaginationToQuery:
    """Test apply_pagination_to_query function."""

    def test_apply_pagination_basic(self):
        """Test applying pagination to query."""
        mock_query = MagicMock()
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        pagination = PaginationParams(limit=20, offset=10)

        apply_pagination_to_query(mock_query, pagination)

        # Should call offset and limit on query
        mock_query.offset.assert_called_once_with(10)
        mock_query.limit.assert_called_once_with(20)

    def test_apply_pagination_chaining(self):
        """Test pagination query chaining."""
        mock_query = MagicMock(spec=Query)
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query

        pagination = PaginationParams(limit=50, offset=25)

        result_query = apply_pagination_to_query(mock_query, pagination)

        # Should return the modified query
        assert result_query is not None

    def test_apply_pagination_zero_offset(self):
        """Test applying pagination with zero offset."""
        mock_query = MagicMock()
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        pagination = PaginationParams(limit=10, offset=0)

        apply_pagination_to_query(mock_query, pagination)

        # Should still call offset with 0
        mock_query.offset.assert_called_once_with(0)
        mock_query.limit.assert_called_once_with(10)

    def test_apply_pagination_boundary_values(self):
        """Test applying pagination with boundary values."""
        mock_query = MagicMock(spec=Query)

        # Minimum values
        pagination = PaginationParams(limit=1, offset=0)
        apply_pagination_to_query(mock_query, pagination)

        # Maximum limit
        pagination = PaginationParams(limit=100, offset=999)
        apply_pagination_to_query(mock_query, pagination)


class TestApplySortingToQuery:
    """Test apply_sorting_to_query function."""

    def test_apply_sorting_ascending(self):
        """Test applying ascending sort to query."""
        mock_query = MagicMock(spec=Query)
        mock_model = MagicMock()
        mock_field = MagicMock()
        mock_model.name = mock_field
        sorting = SortingParams(sort_by="name", sort_order="asc")

        result_query = apply_sorting_to_query(mock_query, sorting, mock_model)

        # Should apply ascending order
        assert result_query is not None

    def test_apply_sorting_descending(self):
        """Test applying descending sort to query."""
        mock_query = MagicMock(spec=Query)
        mock_model = MagicMock()
        mock_field = MagicMock()
        mock_model.created_at = mock_field
        sorting = SortingParams(sort_by="created_at", sort_order="desc")

        result_query = apply_sorting_to_query(mock_query, sorting, mock_model)

        # Should apply descending order
        assert result_query is not None

    def test_apply_sorting_field_validation(self):
        """Test sorting validates field exists on model."""
        mock_query = MagicMock(spec=Query)

        # Create a more realistic mock that actually lacks the field
        class MockModel:
            pass

        mock_model = MockModel
        sorting = SortingParams(sort_by="nonexistent_field", sort_order="asc")

        with pytest.raises(
            ValueError, match="Field 'nonexistent_field' does not exist"
        ):
            # Should validate field exists on model
            apply_sorting_to_query(mock_query, sorting, mock_model)

    def test_apply_sorting_sql_injection_protection(self):
        """Test sorting protects against SQL injection."""
        mock_query = MagicMock(spec=Query)

        # Create a more realistic mock that actually lacks these malicious fields
        class MockModel:
            pass

        mock_model = MockModel

        # Potential SQL injection attempts
        malicious_fields = [
            "name; DROP TABLE users; --",
            "name' OR '1'='1",
            "name UNION SELECT * FROM passwords",
        ]

        for field in malicious_fields:
            sorting = SortingParams(sort_by=field, sort_order="asc")
            with pytest.raises(ValueError):
                # Should sanitize or reject malicious field names
                apply_sorting_to_query(mock_query, sorting, mock_model)

    def test_apply_sorting_common_fields(self):
        """Test sorting with common database fields."""
        mock_query = MagicMock(spec=Query)
        mock_model = MagicMock()

        common_fields = ["id", "name", "created_at", "updated_at"]

        for field in common_fields:
            sorting = SortingParams(sort_by=field, sort_order="asc")
            # Mock the model to have these fields
            setattr(mock_model, field, MagicMock())
            result = apply_sorting_to_query(mock_query, sorting, mock_model)
            assert result is not None

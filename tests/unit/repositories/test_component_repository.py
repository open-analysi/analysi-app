"""Unit tests for ComponentRepository cy_name functionality."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.component import ComponentKind
from analysi.repositories.component import ComponentRepository


class TestComponentRepository:
    """Test ComponentRepository cy_name operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create a ComponentRepository instance with mock session."""
        return ComponentRepository(mock_session)

    def test_generate_cy_name_basic(self, repository):
        """Test basic cy_name generation from display name."""
        result = repository.generate_cy_name(
            "Incident Response Playbook", ComponentKind.TASK
        )
        assert result == "incident_response_playbook"

    def test_generate_cy_name_special_chars(self, repository):
        """Test cy_name generation with special characters."""
        result = repository.generate_cy_name("My-Special Task!", ComponentKind.TASK)
        assert result == "my_special_task"

    def test_generate_cy_name_numeric_prefix(self, repository):
        """Test cy_name generation when name starts with number.

        cy_name must match pattern ^[a-z][a-z0-9_]*$ (start with lowercase letter).
        Names starting with digits get 'n' prefix.
        """
        result = repository.generate_cy_name("123 Numbers First", ComponentKind.TASK)
        # Must start with letter to match validation pattern ^[a-z][a-z0-9_]*$
        assert result == "n123_numbers_first"
        assert result[0].isalpha(), "cy_name must start with a letter"

    def test_generate_cy_name_year_filename(self, repository):
        """Test cy_name generation for year-based filenames like 2024.md.

        This reproduces the bug where GET /knowledge-units/documents returned 500
        because cy_name '_2024_md' violated pattern ^[a-z][a-z0-9_]*$.
        """
        result = repository.generate_cy_name("2024.md", ComponentKind.KU)
        # Must start with letter, not underscore
        assert result[0].isalpha(), f"cy_name '{result}' must start with a letter"
        assert result == "n2024_md"

        # Validate against the actual schema pattern
        import re

        pattern = r"^[a-z][a-z0-9_]*$"
        assert re.match(pattern, result), f"cy_name '{result}' must match {pattern}"

    def test_generate_cy_name_reserved_word(self, repository):
        """Test cy_name generation with reserved words."""
        result = repository.generate_cy_name("table", ComponentKind.TASK)
        assert result == "task_table"

    def test_generate_cy_name_empty(self, repository):
        """Test cy_name generation with empty string."""
        result = repository.generate_cy_name("", ComponentKind.TASK)
        assert result == "task_component"

    def test_generate_cy_name_multiple_spaces(self, repository):
        """Test cy_name generation with multiple spaces."""
        result = repository.generate_cy_name(
            "Name   With    Many     Spaces", ComponentKind.TASK
        )
        assert result == "name_with_many_spaces"

    def test_generate_cy_name_underscore_preservation(self, repository):
        """Test that existing underscores are preserved."""
        result = repository.generate_cy_name(
            "already_has_underscores", ComponentKind.TASK
        )
        assert result == "already_has_underscores"

    def test_generate_cy_name_max_length(self, repository):
        """Test that cy_name is truncated to max length."""
        long_name = "a" * 300
        result = repository.generate_cy_name(long_name, ComponentKind.TASK)
        assert len(result) == 255
        assert result == "a" * 255

    @pytest.mark.asyncio
    async def test_ensure_unique_cy_name(self, repository, mock_session):
        """Test that ensure_unique_cy_name generates unique names."""
        # Mock get_by_cy_name to return None (name doesn't exist)
        repository.get_by_cy_name = AsyncMock(return_value=None)

        result = await repository.ensure_unique_cy_name(
            "test_name", "tenant-id", "default"
        )
        assert result == "test_name"

        # Mock get_by_cy_name to return existing component on first call, then None
        repository.get_by_cy_name = AsyncMock(side_effect=[MagicMock(), None])

        result = await repository.ensure_unique_cy_name(
            "test_name", "tenant-id", "default"
        )
        assert result == "test_name_2"

    @pytest.mark.asyncio
    async def test_get_by_cy_name(self, repository, mock_session):
        """Test that get_by_cy_name queries correctly."""
        # Mock execute to return a result with scalar_one_or_none
        mock_result = MagicMock()
        mock_component = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_component
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_cy_name("tenant-id", "default", "test_cy_name")

        assert result == mock_component
        mock_session.execute.assert_called_once()

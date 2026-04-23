"""Unit tests for skill-ownership guard."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.auth.skill_guard import check_ku_belongs_to_skill


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


def _make_result(has_row: bool):
    """Create a mock result that mimics scalar_one_or_none."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid4() if has_row else None
    return result


class TestCheckKuBelongsToSkill:
    @pytest.mark.asyncio
    async def test_ku_with_contains_edge_belongs_to_skill(self, mock_session):
        """KU with a CONTAINS edge from a skill returns True."""
        mock_session.execute.return_value = _make_result(has_row=True)

        result = await check_ku_belongs_to_skill(uuid4(), "tenant-1", mock_session)

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_ku_without_contains_edge_does_not_belong(self, mock_session):
        """KU with no CONTAINS edge returns False."""
        mock_session.execute.return_value = _make_result(has_row=False)

        result = await check_ku_belongs_to_skill(uuid4(), "tenant-1", mock_session)

        assert result is False

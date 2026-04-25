"""Unit tests for UserRepository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.repositories.user_repository import UserRepository


class TestUserRepository:
    """Tests for UserRepository."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.get = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        return UserRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_returns_row_from_insert(self, repo, mock_session):
        """create() issues an INSERT…ON CONFLICT and returns the inserted row.

        Implementation uses ``session.execute(pg_insert(...).on_conflict_do_nothing()
        .returning(User))``. When there's no conflict the INSERT returns the new
        row via RETURNING, and create() returns that row after a flush.
        """
        mock_user = MagicMock()
        mock_user.keycloak_id = "kc-123"
        mock_user.email = "alice@example.com"
        mock_user.display_name = "Alice"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_session.execute.return_value = mock_result

        user = await repo.create(
            keycloak_id="kc-123",
            email="alice@example.com",
            display_name="Alice",
        )

        assert user is mock_user
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_falls_back_to_select_on_conflict(self, repo, mock_session):
        """When INSERT conflicts (row already exists), create() fetches the
        existing row via get_by_keycloak_id instead of raising IntegrityError.
        """
        mock_existing = MagicMock()
        mock_existing.keycloak_id = "kc-race"
        mock_existing.email = "race@example.com"

        # First execute call: INSERT returns no row (conflict — ON CONFLICT DO NOTHING)
        insert_result = MagicMock()
        insert_result.scalar_one_or_none = MagicMock(return_value=None)

        # Second execute call: SELECT by keycloak_id returns the existing row
        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=mock_existing)

        mock_session.execute.side_effect = [insert_result, select_result]

        user = await repo.create(keycloak_id="kc-race", email="race@example.com")

        assert user is mock_existing
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, repo, mock_session):
        """get_by_id() returns user when present."""
        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(user_id)

        assert result is mock_user
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo, mock_session):
        """get_by_id() returns None when user absent."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_keycloak_id_found(self, repo, mock_session):
        """get_by_keycloak_id() returns user for matching sub claim."""
        mock_user = MagicMock()
        mock_user.keycloak_id = "kc-789"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_keycloak_id("kc-789")

        assert result is mock_user

    @pytest.mark.asyncio
    async def test_get_by_email_found(self, repo, mock_session):
        """get_by_email() returns user for matching email."""
        mock_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_email("carol@example.com")

        assert result is mock_user

    @pytest.mark.asyncio
    async def test_get_by_keycloak_id_empty_string_returns_none(
        self, repo, mock_session
    ):
        """Security: empty keycloak_id must never query the DB."""
        result = await repo.get_by_keycloak_id("")
        assert result is None
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_keycloak_id_whitespace_returns_none(self, repo, mock_session):
        """Security: whitespace-only keycloak_id must never query the DB."""
        result = await repo.get_by_keycloak_id("   ")
        assert result is None
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_keycloak_id_none_returns_none(self, repo, mock_session):
        """Security: None keycloak_id must never query the DB."""
        result = await repo.get_by_keycloak_id(None)
        assert result is None
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_last_seen_executes_update(self, repo, mock_session):
        """update_last_seen() fires an UPDATE statement."""
        user_id = uuid4()
        now = datetime.now(UTC)

        await repo.update_last_seen(user_id, now)

        mock_session.execute.assert_called_once()

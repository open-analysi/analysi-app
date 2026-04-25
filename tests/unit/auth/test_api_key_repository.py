"""Unit tests for ApiKeyRepository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.repositories.api_key_repository import ApiKeyRepository


class TestApiKeyRepository:
    """Tests for ApiKeyRepository."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.get = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        return ApiKeyRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_sets_fields_and_flushes(self, repo, mock_session):
        """create() sets all fields, adds to session, and flushes."""
        user_id = uuid4()

        api_key = await repo.create(
            tenant_id="acme",
            name="CI token",
            key_hash="abc123hash",
            key_prefix="ak_abc1",
            user_id=user_id,
            scopes=["tasks:read"],
        )

        assert api_key.tenant_id == "acme"
        assert api_key.name == "CI token"
        assert api_key.key_hash == "abc123hash"
        assert api_key.key_prefix == "ak_abc1"
        assert api_key.user_id == user_id
        assert api_key.scopes == ["tasks:read"]
        assert api_key.id is not None
        mock_session.add.assert_called_once_with(api_key)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_system_key_no_user(self, repo, mock_session):
        """create() supports system keys (user_id=None)."""
        api_key = await repo.create(
            tenant_id="acme",
            name="system",
            key_hash="syskey_hash",
            key_prefix="ak_sys",
        )

        assert api_key.user_id is None
        assert api_key.scopes == []

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, repo, mock_session):
        """get_by_id() returns key when present."""
        key_id = uuid4()
        mock_key = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_key)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(key_id)

        assert result is mock_key

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo, mock_session):
        """get_by_id() returns None when key absent."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_hash_found(self, repo, mock_session):
        """get_by_hash() returns key for matching hash (auth path)."""
        mock_key = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_key)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_hash("abc123hash")

        assert result is mock_key

    @pytest.mark.asyncio
    async def test_list_by_tenant_returns_list(self, repo, mock_session):
        """list_by_tenant() returns all keys for a tenant."""
        mock_k1 = MagicMock()
        mock_k2 = MagicMock()

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_k1, mock_k2])
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        result = await repo.list_by_tenant("acme")

        assert result == [mock_k1, mock_k2]

    @pytest.mark.asyncio
    async def test_delete_returns_true_when_found(self, repo, mock_session):
        """delete() removes the key and returns True."""
        key_id = uuid4()
        mock_key = MagicMock()
        mock_session.get.return_value = mock_key

        result = await repo.delete(key_id)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_key)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self, repo, mock_session):
        """delete() returns False if the key does not exist."""
        mock_session.get.return_value = None

        result = await repo.delete(uuid4())

        assert result is False
        mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_by_user_and_tenant_returns_count(self, repo, mock_session):
        """delete_by_user_and_tenant() returns the number of deleted rows."""
        user_id = uuid4()

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[("id1",), ("id2",)])
        mock_session.execute.return_value = mock_result

        count = await repo.delete_by_user_and_tenant(user_id, "acme")

        assert count == 2
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_last_used_executes_update(self, repo, mock_session):
        """update_last_used() fires an UPDATE statement."""
        key_id = uuid4()
        now = datetime.now(UTC)

        await repo.update_last_used(key_id, now)

        mock_session.execute.assert_called_once()

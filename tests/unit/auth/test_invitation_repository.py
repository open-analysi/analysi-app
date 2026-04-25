"""Unit tests for InvitationRepository."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.repositories.invitation_repository import InvitationRepository


class TestInvitationRepository:
    """Tests for InvitationRepository."""

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
        return InvitationRepository(mock_session)

    @pytest.fixture
    def expires_at(self):
        return datetime.now(UTC) + timedelta(days=7)

    @pytest.mark.asyncio
    async def test_create_sets_fields_and_flushes(self, repo, mock_session, expires_at):
        """create() sets all fields, adds to session, and flushes."""
        inviter_id = uuid4()

        invitation = await repo.create(
            tenant_id="acme",
            email="alice@example.com",
            role="analyst",
            token_hash="abc123hash",
            expires_at=expires_at,
            invited_by=inviter_id,
        )

        assert invitation.tenant_id == "acme"
        assert invitation.email == "alice@example.com"
        assert invitation.role == "analyst"
        assert invitation.token_hash == "abc123hash"
        assert invitation.expires_at == expires_at
        assert invitation.invited_by == inviter_id
        assert invitation.accepted_at is None
        assert invitation.id is not None
        mock_session.add.assert_called_once_with(invitation)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_without_invited_by(self, repo, mock_session, expires_at):
        """create() works without invited_by."""
        invitation = await repo.create(
            tenant_id="acme",
            email="bob@example.com",
            role="viewer",
            token_hash="def456hash",
            expires_at=expires_at,
        )

        assert invitation.invited_by is None
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, repo, mock_session):
        """get_by_id() returns invitation when present."""
        invitation_id = uuid4()
        mock_invitation = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_invitation)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(invitation_id)

        assert result is mock_invitation

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo, mock_session):
        """get_by_id() returns None when invitation absent."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_token_hash_found(self, repo, mock_session):
        """get_by_token_hash() returns invitation for matching hash (accept path)."""
        mock_invitation = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_invitation)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_token_hash("abc123hash")

        assert result is mock_invitation

    @pytest.mark.asyncio
    async def test_get_by_token_hash_not_found(self, repo, mock_session):
        """get_by_token_hash() returns None for unknown hash."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_token_hash("unknown")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_tenant_returns_list(self, repo, mock_session):
        """list_by_tenant() returns all invitations for a tenant."""
        mock_i1 = MagicMock()
        mock_i2 = MagicMock()

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_i1, mock_i2])
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        result = await repo.list_by_tenant("acme")

        assert result == [mock_i1, mock_i2]

    @pytest.mark.asyncio
    async def test_mark_accepted_stamps_timestamp(self, repo, mock_session):
        """mark_accepted() sets accepted_at on the invitation."""
        invitation_id = uuid4()
        now = datetime.now(UTC)
        mock_invitation = MagicMock()
        mock_session.get.return_value = mock_invitation

        result = await repo.mark_accepted(invitation_id, now)

        assert result is mock_invitation
        assert mock_invitation.accepted_at == now
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_accepted_not_found_returns_none(self, repo, mock_session):
        """mark_accepted() returns None if invitation does not exist."""
        mock_session.get.return_value = None

        result = await repo.mark_accepted(uuid4(), datetime.now(UTC))

        assert result is None
        mock_session.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_returns_true_when_found(self, repo, mock_session):
        """delete() removes the invitation and returns True."""
        invitation_id = uuid4()
        mock_invitation = MagicMock()
        mock_session.get.return_value = mock_invitation

        result = await repo.delete(invitation_id)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_invitation)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self, repo, mock_session):
        """delete() returns False if the invitation does not exist."""
        mock_session.get.return_value = None

        result = await repo.delete(uuid4())

        assert result is False
        mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_pending_by_tenant_filters_accepted_and_expired(
        self, repo, mock_session
    ):
        """list_pending_by_tenant() returns only non-accepted, non-expired invitations."""
        mock_pending = MagicMock()

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_pending])
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        now = datetime.now(UTC)
        result = await repo.list_pending_by_tenant("acme", now)

        assert result == [mock_pending]
        mock_session.execute.assert_called_once()

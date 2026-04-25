"""Unit tests for MembershipRepository."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.repositories.membership_repository import MembershipRepository


class TestMembershipRepository:
    """Tests for MembershipRepository."""

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
        return MembershipRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_sets_fields_and_flushes(self, repo, mock_session):
        """create() sets all fields, adds to session, and flushes."""
        user_id = uuid4()
        inviter_id = uuid4()

        membership = await repo.create(
            user_id=user_id,
            tenant_id="acme",
            role="analyst",
            invited_by=inviter_id,
        )

        assert membership.user_id == user_id
        assert membership.tenant_id == "acme"
        assert membership.role == "analyst"
        assert membership.invited_by == inviter_id
        assert membership.id is not None
        mock_session.add.assert_called_once_with(membership)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_without_invited_by(self, repo, mock_session):
        """create() works without invited_by (JIT provisioning)."""
        membership = await repo.create(user_id=uuid4(), tenant_id="acme", role="owner")

        assert membership.invited_by is None
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_and_tenant_found(self, repo, mock_session):
        """get_by_user_and_tenant() returns membership when present."""
        user_id = uuid4()
        mock_membership = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_membership)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_user_and_tenant(user_id, "acme")

        assert result is mock_membership

    @pytest.mark.asyncio
    async def test_get_by_user_and_tenant_not_found(self, repo, mock_session):
        """get_by_user_and_tenant() returns None when not a member."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_user_and_tenant(uuid4(), "acme")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_tenant_returns_list(self, repo, mock_session):
        """list_by_tenant() returns all memberships for a tenant."""
        mock_m1 = MagicMock()
        mock_m2 = MagicMock()

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_m1, mock_m2])
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        result = await repo.list_by_tenant("acme")

        assert result == [mock_m1, mock_m2]

    @pytest.mark.asyncio
    async def test_update_role_returns_updated(self, repo, mock_session):
        """update_role() fires an UPDATE RETURNING and returns updated membership."""
        membership_id = uuid4()
        mock_membership = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_membership)
        mock_session.execute.return_value = mock_result

        result = await repo.update_role(membership_id, "admin")

        assert result is mock_membership
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_returns_true_when_found(self, repo, mock_session):
        """delete() removes the membership and returns True."""
        membership_id = uuid4()
        mock_membership = MagicMock()
        mock_session.get.return_value = mock_membership

        result = await repo.delete(membership_id)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_membership)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self, repo, mock_session):
        """delete() returns False if the membership does not exist."""
        mock_session.get.return_value = None

        result = await repo.delete(uuid4())

        assert result is False
        mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_count_owners_returns_count(self, repo, mock_session):
        """count_owners() returns the count of owner-role memberships."""
        mock_result = MagicMock()
        mock_result.scalar = MagicMock(return_value=2)
        mock_session.execute.return_value = mock_result

        result = await repo.count_owners("acme")

        assert result == 2

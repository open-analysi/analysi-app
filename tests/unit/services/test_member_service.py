"""Unit tests for MemberService.

Uses AsyncMock / MagicMock to avoid hitting the database.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.auth.models import CurrentUser
from analysi.models.auth import Invitation, Membership, User
from analysi.schemas.auth import InvitationResponse, MemberResponse
from analysi.services.member_service import MemberService


def _make_current_user(
    user_id: str = "kc-user-1",
    tenant_id: str | None = "acme",
    roles: list[str] | None = None,
    actor_type: str = "user",
    is_platform_admin: bool = False,
) -> CurrentUser:
    r = roles or (["platform_admin"] if is_platform_admin else ["owner"])
    return CurrentUser(
        user_id=user_id,
        email="user@acme.com",
        tenant_id=tenant_id,
        roles=r,
        actor_type=actor_type,
    )


def _make_user(email: str = "user@acme.com") -> User:
    u = MagicMock(spec=User)
    u.id = uuid4()
    u.keycloak_id = "kc-user-1"
    u.email = email
    return u


def _make_membership(
    user_id=None,
    tenant_id: str = "acme",
    role: str = "owner",
    user: User | None = None,
) -> Membership:
    m = MagicMock(spec=Membership)
    m.id = uuid4()
    m.user_id = user_id or uuid4()
    m.tenant_id = tenant_id
    m.role = role
    m.invited_by = None
    m.created_at = datetime.now(UTC)
    m.user = user or _make_user()
    return m


def _make_invitation(
    tenant_id: str = "acme",
    role: str = "viewer",
    accepted_at=None,
    expires_at=None,
    invited_by=None,
) -> Invitation:
    inv = MagicMock(spec=Invitation)
    inv.id = uuid4()
    inv.tenant_id = tenant_id
    inv.email = "invited@acme.com"
    inv.role = role
    inv.token_hash = "abc123"
    inv.accepted_at = accepted_at
    inv.expires_at = expires_at or datetime.now(UTC) + timedelta(days=7)
    inv.invited_by = invited_by
    inv.created_at = datetime.now(UTC)
    return inv


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    svc = MemberService(mock_session)
    svc._users = AsyncMock()
    svc._memberships = AsyncMock()
    svc._invitations = AsyncMock()
    svc._api_keys = AsyncMock()
    return svc


class TestProvisionUserJit:
    @pytest.mark.asyncio
    async def test_provision_skips_platform_admin(self, service):
        user = _make_current_user(
            is_platform_admin=True, tenant_id=None, roles=["platform_admin"]
        )
        result = await service.provision_user_jit(user)
        assert result is None
        service._users.get_by_keycloak_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_provision_skips_api_key_actor(self, service):
        user = _make_current_user(actor_type="api_key")
        result = await service.provision_user_jit(user)
        assert result is None

    @pytest.mark.asyncio
    async def test_provision_skips_no_tenant(self, service):
        user = _make_current_user(tenant_id=None, roles=[])
        result = await service.provision_user_jit(user)
        assert result is None

    @pytest.mark.asyncio
    async def test_provision_creates_new_user(self, service):
        user = _make_current_user()
        service._users.get_by_keycloak_id.return_value = None
        service._users.get_by_email.return_value = None  # no email match either
        db_user = _make_user()
        service._users.create.return_value = db_user
        service._memberships.list_by_tenant.return_value = []
        service._memberships.get_by_user_and_tenant.return_value = None
        service._memberships.create.return_value = _make_membership()

        result = await service.provision_user_jit(user)

        service._users.create.assert_called_once()
        assert result is db_user

    @pytest.mark.asyncio
    async def test_provision_backfills_keycloak_id(self, service):
        """User exists by email but with empty keycloak_id — backfill it."""
        user = _make_current_user(user_id="kc-new-sub")
        service._users.get_by_keycloak_id.return_value = None
        db_user = _make_user()
        db_user.keycloak_id = ""  # old empty keycloak_id
        service._users.get_by_email.return_value = db_user
        service._memberships.get_by_user_and_tenant.return_value = _make_membership()

        result = await service.provision_user_jit(user)

        # Should NOT create a new user
        service._users.create.assert_not_called()
        # Should backfill keycloak_id
        assert db_user.keycloak_id == "kc-new-sub"
        assert result is db_user

    @pytest.mark.asyncio
    async def test_provision_skips_existing_user(self, service):
        user = _make_current_user()
        db_user = _make_user()
        service._users.get_by_keycloak_id.return_value = db_user
        service._memberships.get_by_user_and_tenant.return_value = _make_membership()

        result = await service.provision_user_jit(user)

        service._users.create.assert_not_called()
        assert result is db_user

    @pytest.mark.asyncio
    async def test_provision_first_user_gets_owner_role(self, service):
        user = _make_current_user()
        service._users.get_by_keycloak_id.return_value = None
        service._users.get_by_email.return_value = None
        service._users.create.return_value = _make_user()
        service._memberships.list_by_tenant.return_value = []  # no members yet
        service._memberships.get_by_user_and_tenant.return_value = None
        service._memberships.create.return_value = MagicMock()

        await service.provision_user_jit(user)

        service._memberships.create.assert_called_once()
        call_kwargs = service._memberships.create.call_args.kwargs
        assert call_kwargs["role"] == "owner"

    @pytest.mark.asyncio
    async def test_provision_second_user_no_jwt_role_gets_viewer(self, service):
        """Second user with no valid tenant role in JWT gets viewer."""
        user = _make_current_user(roles=["offline_access"])
        service._users.get_by_keycloak_id.return_value = None
        service._users.get_by_email.return_value = None
        service._users.create.return_value = _make_user()
        service._memberships.list_by_tenant.return_value = [_make_membership()]
        service._memberships.get_by_user_and_tenant.return_value = None
        service._memberships.create.return_value = MagicMock()

        await service.provision_user_jit(user)

        call_kwargs = service._memberships.create.call_args.kwargs
        assert call_kwargs["role"] == "viewer"

    @pytest.mark.asyncio
    async def test_provision_second_user_jwt_admin_gets_admin(self, service):
        """Second user with admin JWT role gets admin membership."""
        user = _make_current_user(roles=["admin", "offline_access"])
        service._users.get_by_keycloak_id.return_value = None
        service._users.get_by_email.return_value = None
        service._users.create.return_value = _make_user()
        service._memberships.list_by_tenant.return_value = [_make_membership()]
        service._memberships.get_by_user_and_tenant.return_value = None
        service._memberships.create.return_value = MagicMock()

        await service.provision_user_jit(user)

        call_kwargs = service._memberships.create.call_args.kwargs
        assert call_kwargs["role"] == "admin"

    @pytest.mark.asyncio
    async def test_provision_skips_empty_user_id(self, service):
        """Security: empty user_id (missing JWT sub) must not query DB."""
        user = _make_current_user(user_id="")
        result = await service.provision_user_jit(user)
        assert result is None
        service._users.get_by_keycloak_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_provision_second_user_highest_jwt_role_wins(self, service):
        """When JWT has multiple valid roles, highest privilege wins."""
        user = _make_current_user(roles=["viewer", "analyst", "admin"])
        service._users.get_by_keycloak_id.return_value = None
        service._users.get_by_email.return_value = None
        service._users.create.return_value = _make_user()
        service._memberships.list_by_tenant.return_value = [_make_membership()]
        service._memberships.get_by_user_and_tenant.return_value = None
        service._memberships.create.return_value = MagicMock()

        await service.provision_user_jit(user)

        call_kwargs = service._memberships.create.call_args.kwargs
        assert call_kwargs["role"] == "admin"

    @pytest.mark.asyncio
    async def test_provision_handles_concurrent_create_race(
        self, service, mock_session
    ):
        """Concurrent first-login race is now resolved inside
        ``UserRepository.create`` via ``INSERT … ON CONFLICT DO NOTHING``: the
        loser gets the winner's row back rather than an ``IntegrityError``.
        ``provision_user_jit`` trusts whatever ``create`` returns — no
        rollback, no re-fetch at the service layer.
        """
        user = _make_current_user()
        db_user = _make_user()

        # User doesn't exist when service checks by keycloak_id or email.
        service._users.get_by_keycloak_id.return_value = None
        service._users.get_by_email.return_value = None

        # Repository returns the existing row (winner's) — race handled internally.
        service._users.create.return_value = db_user
        service._memberships.get_by_user_and_tenant.return_value = _make_membership()

        result = await service.provision_user_jit(user)

        assert result is db_user
        # Service no longer rolls back — race handling lives in the repository.
        mock_session.rollback.assert_not_called()


class TestListMembers:
    @pytest.mark.asyncio
    async def test_list_members_returns_email(self, service):
        db_user = _make_user(email="alice@acme.com")
        m = _make_membership(user=db_user, tenant_id="acme", role="owner")
        service._memberships.list_by_tenant_with_user.return_value = [m]

        result = await service.list_members("acme")

        assert len(result) == 1
        assert result[0].email == "alice@acme.com"
        assert result[0].role == "owner"


class TestInviteMember:
    @pytest.mark.asyncio
    async def test_invite_returns_token(self, service):
        inv = _make_invitation()
        service._invitations.create.return_value = inv

        response, token = await service.invite_member(
            tenant_id="acme",
            email="new@acme.com",
            role="viewer",
            inviter_user_id=uuid4(),
        )

        assert token  # non-empty
        assert isinstance(response, InvitationResponse)

    @pytest.mark.asyncio
    async def test_invite_stores_hash_not_plaintext(self, service):
        inv = _make_invitation()
        service._invitations.create.return_value = inv

        _response, token = await service.invite_member(
            tenant_id="acme",
            email="new@acme.com",
            role="viewer",
            inviter_user_id=uuid4(),
        )

        call_kwargs = service._invitations.create.call_args.kwargs
        import hashlib

        assert call_kwargs["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
        assert token not in str(call_kwargs)  # plaintext not stored

    @pytest.mark.asyncio
    async def test_invite_invalid_role_raises_422(self, service):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.invite_member(
                tenant_id="acme",
                email="new@acme.com",
                role="superuser",
                inviter_user_id=uuid4(),
            )
        assert exc_info.value.status_code == 422


class TestAcceptInvite:
    @pytest.mark.asyncio
    async def test_accept_creates_membership(self, service):
        inv = _make_invitation()  # email="invited@acme.com"
        service._invitations.get_by_token_hash.return_value = inv
        db_user = _make_user(email="invited@acme.com")
        service._users.get_by_keycloak_id.return_value = db_user
        service._memberships.get_by_user_and_tenant.return_value = None
        inv.invited_by = None  # no inviter check needed
        m = _make_membership(user_id=db_user.id)
        service._memberships.create.return_value = m

        # current_user email must match invitation email
        matching_user = _make_current_user()
        matching_user.email = "invited@acme.com"

        with patch("analysi.services.member_service.invite_rate_limiter") as mock_rl:
            mock_rl.check_and_record.return_value = True
            result = await service.accept_invite(
                tenant_id="acme",
                token="valid-token",
                current_user=matching_user,
            )

        service._invitations.mark_accepted.assert_called_once()
        assert isinstance(result, MemberResponse)

    @pytest.mark.asyncio
    async def test_accept_rejects_expired(self, service):
        from fastapi import HTTPException

        inv = _make_invitation(
            expires_at=datetime.now(UTC) - timedelta(days=1)  # expired
        )
        service._invitations.get_by_token_hash.return_value = inv

        # Use matching email so the email check passes and we test expiry
        matching_user = _make_current_user()
        matching_user.email = "invited@acme.com"

        with patch("analysi.services.member_service.invite_rate_limiter") as mock_rl:
            mock_rl.check_and_record.return_value = True
            with pytest.raises(HTTPException) as exc_info:
                await service.accept_invite(
                    tenant_id="acme",
                    token="tok",
                    current_user=matching_user,
                )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_rejects_used(self, service):
        from fastapi import HTTPException

        inv = _make_invitation(accepted_at=datetime.now(UTC))
        service._invitations.get_by_token_hash.return_value = inv

        # Use matching email so the email check passes and we test single-use
        matching_user = _make_current_user()
        matching_user.email = "invited@acme.com"

        with patch("analysi.services.member_service.invite_rate_limiter") as mock_rl:
            mock_rl.check_and_record.return_value = True
            with pytest.raises(HTTPException) as exc_info:
                await service.accept_invite(
                    tenant_id="acme",
                    token="tok",
                    current_user=matching_user,
                )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_rate_limited(self, service):
        from fastapi import HTTPException

        with patch("analysi.services.member_service.invite_rate_limiter") as mock_rl:
            mock_rl.check_and_record.return_value = False  # rate limited
            with pytest.raises(HTTPException) as exc_info:
                await service.accept_invite(
                    tenant_id="acme",
                    token="tok",
                    current_user=_make_current_user(),
                )
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_accept_rejects_wrong_email(self, service):
        """Invitation can only be accepted by the invited email address."""
        from fastapi import HTTPException

        inv = _make_invitation()  # email="invited@acme.com"
        service._invitations.get_by_token_hash.return_value = inv

        # current_user has a different email ("user@acme.com")
        wrong_user = _make_current_user(user_id="kc-attacker")

        with patch("analysi.services.member_service.invite_rate_limiter") as mock_rl:
            mock_rl.check_and_record.return_value = True
            with pytest.raises(HTTPException) as exc_info:
                await service.accept_invite(
                    tenant_id="acme",
                    token="valid-token",
                    current_user=wrong_user,
                )
        assert exc_info.value.status_code == 403
        assert "email" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_accept_matches_email_with_whitespace_and_case(self, service):
        """Email matching normalizes whitespace and case."""
        inv = _make_invitation()
        inv.email = "  Invited@Acme.COM "  # messy stored email
        service._invitations.get_by_token_hash.return_value = inv
        inv.invited_by = None

        db_user = _make_user(email="invited@acme.com")
        service._users.get_by_keycloak_id.return_value = db_user
        service._memberships.get_by_user_and_tenant.return_value = None
        m = _make_membership(user_id=db_user.id)
        service._memberships.create.return_value = m

        matching_user = _make_current_user()
        matching_user.email = "invited@acme.com"

        with patch("analysi.services.member_service.invite_rate_limiter") as mock_rl:
            mock_rl.check_and_record.return_value = True
            result = await service.accept_invite(
                tenant_id="acme",
                token="valid-token",
                current_user=matching_user,
            )

        assert isinstance(result, MemberResponse)


class TestChangeRole:
    @pytest.mark.asyncio
    async def test_change_role_updates_membership(self, service):
        user_id = uuid4()
        db_user = _make_user()
        m = _make_membership(user_id=user_id, role="viewer", user=db_user)
        service._memberships.get_by_user_and_tenant.return_value = m
        updated = _make_membership(user_id=user_id, role="analyst", user=db_user)
        service._memberships.update_role.return_value = updated
        service._memberships.get_by_id_with_user.return_value = updated

        result = await service.change_role("acme", user_id, "analyst")

        service._memberships.update_role.assert_called_once_with(m.id, "analyst")
        assert result.role == "analyst"

    @pytest.mark.asyncio
    async def test_change_role_prevents_ownerless_tenant(self, service):
        from fastapi import HTTPException

        user_id = uuid4()
        m = _make_membership(user_id=user_id, role="owner")
        service._memberships.get_by_user_and_tenant.return_value = m
        service._memberships.count_owners.return_value = 1  # only one owner

        with pytest.raises(HTTPException) as exc_info:
            await service.change_role("acme", user_id, "admin")
        assert exc_info.value.status_code == 400


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_remove_member_deletes_api_keys(self, service):
        user_id = uuid4()
        m = _make_membership(user_id=user_id, role="analyst")
        service._memberships.get_by_user_and_tenant.return_value = m
        service._api_keys.delete_by_user_and_tenant.return_value = 2
        service._memberships.delete.return_value = True

        await service.remove_member("acme", user_id)

        service._api_keys.delete_by_user_and_tenant.assert_called_once_with(
            user_id, "acme"
        )
        service._memberships.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_last_owner_raises(self, service):
        from fastapi import HTTPException

        user_id = uuid4()
        m = _make_membership(user_id=user_id, role="owner")
        service._memberships.get_by_user_and_tenant.return_value = m
        service._memberships.count_owners.return_value = 1

        with pytest.raises(HTTPException) as exc_info:
            await service.remove_member("acme", user_id)
        assert exc_info.value.status_code == 400

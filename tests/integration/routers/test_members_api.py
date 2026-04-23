"""Integration tests for member and API key management endpoints."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.dependencies import get_current_user
from analysi.auth.models import CurrentUser
from analysi.main import app
from analysi.models.auth import Membership, User
from analysi.repositories.api_key_repository import ApiKeyRepository
from analysi.repositories.invitation_repository import InvitationRepository
from analysi.repositories.membership_repository import MembershipRepository
from analysi.repositories.user_repository import UserRepository
from analysi.services.api_key_service import ApiKeyService
from analysi.services.member_service import MemberService, _hash_token

_TEST_DB_USER_ID = UUID("00000000-0000-0000-0000-aaaaaaaaaaaa")


def _make_user_obj(
    roles: list[str],
    tenant_id: str | None,
    user_id: str = "test-user",
) -> CurrentUser:
    return CurrentUser(
        user_id=user_id,
        email="owner@acme.com",
        tenant_id=tenant_id,
        roles=roles,
        actor_type="user",
        db_user_id=_TEST_DB_USER_ID,
    )


@pytest.fixture
def tenant() -> str:
    return f"test-{uuid4().hex[:8]}"


@pytest.fixture
async def owner_client(tenant: str) -> AsyncGenerator[AsyncClient]:
    user = _make_user_obj(["owner"], tenant_id=tenant)
    app.dependency_overrides[get_current_user] = lambda: user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def viewer_client(tenant: str) -> AsyncGenerator[AsyncClient]:
    user = _make_user_obj(["viewer"], tenant_id=tenant)
    app.dependency_overrides[get_current_user] = lambda: user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Helper: seed a User + Membership directly via repository
# ---------------------------------------------------------------------------


async def _seed_member(
    session: AsyncSession,
    tenant_id: str,
    role: str = "owner",
    email: str | None = None,
    keycloak_id: str | None = None,
) -> tuple[User, Membership]:
    user_repo = UserRepository(session)
    membership_repo = MembershipRepository(session)
    kc_id = keycloak_id or f"kc-{uuid4().hex}"
    email = email or f"user-{uuid4().hex[:6]}@acme.com"
    user = await user_repo.create(keycloak_id=kc_id, email=email)
    membership = await membership_repo.create(
        user_id=user.id, tenant_id=tenant_id, role=role
    )
    await session.commit()
    return user, membership


@pytest.mark.integration
class TestListMembers:
    async def test_list_members_empty(self, owner_client: AsyncClient, tenant: str):
        response = await owner_client.get(f"/v1/{tenant}/members")
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_list_members_returns_seeded_member(
        self,
        owner_client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        user, membership = await _seed_member(
            integration_test_session, tenant, role="owner"
        )
        response = await owner_client.get(f"/v1/{tenant}/members")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["role"] == "owner"
        assert data[0]["email"] == user.email

    async def test_viewer_cannot_read_members(
        self, viewer_client: AsyncClient, tenant: str
    ):
        # members:read requires admin role or above — viewer is denied
        response = await viewer_client.get(f"/v1/{tenant}/members")
        assert response.status_code == 403


@pytest.mark.integration
class TestInviteAndAccept:
    async def test_invite_returns_invitation(
        self,
        owner_client: AsyncClient,
        tenant: str,
    ):
        response = await owner_client.post(
            f"/v1/{tenant}/members/invite",
            json={"email": "new@acme.com", "role": "viewer"},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["email"] == "new@acme.com"
        assert data["role"] == "viewer"
        assert "token_hash" not in data  # secret never returned

    async def test_invite_invalid_role_returns_422(
        self,
        owner_client: AsyncClient,
        tenant: str,
    ):
        response = await owner_client.post(
            f"/v1/{tenant}/members/invite",
            json={"email": "bad@acme.com", "role": "superadmin"},
        )
        assert response.status_code == 422

    async def test_full_invite_accept_flow(
        self,
        owner_client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """Invite → accept → member appears in list."""
        # Invite via dev endpoint that returns token
        response = await owner_client.post(
            f"/v1/{tenant}/members/invite-with-token",
            json={"email": "joiner@acme.com", "role": "analyst"},
        )
        assert response.status_code == 201
        token = response.json()["data"]["token"]

        # Accept the invitation as a new user (not yet a member)
        joiner = CurrentUser(
            user_id=f"kc-joiner-{uuid4().hex[:6]}",
            email="joiner@acme.com",
            tenant_id=None,  # not a member yet
            roles=[],
            actor_type="user",
        )
        app.dependency_overrides[get_current_user] = lambda: joiner
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as joiner_client:
            accept_resp = await joiner_client.post(
                f"/v1/{tenant}/members/accept-invite",
                json={"token": token},
            )
        app.dependency_overrides.pop(get_current_user, None)

        assert accept_resp.status_code == 201
        member_data = accept_resp.json()["data"]
        assert member_data["role"] == "analyst"
        assert member_data["email"] == "joiner@acme.com"

    async def test_accept_expired_invitation_returns_400(
        self,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        # Seed an expired invitation directly
        inv_repo = InvitationRepository(integration_test_session)
        token = "expired-token-test"
        token_hash = _hash_token(token)
        expired_at = datetime.now(UTC) - timedelta(days=1)
        await inv_repo.create(
            tenant_id=tenant,
            email="expired@acme.com",
            role="viewer",
            token_hash=token_hash,
            expires_at=expired_at,
        )
        await integration_test_session.commit()

        some_user = CurrentUser(
            user_id="kc-expired-user",
            email="expired@acme.com",
            tenant_id=None,
            roles=[],
            actor_type="user",
        )
        app.dependency_overrides[get_current_user] = lambda: some_user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post(
                f"/v1/{tenant}/members/accept-invite",
                json={"token": token},
            )
        app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 400

    async def test_accept_wrong_email_returns_403(
        self,
        owner_client: AsyncClient,
        tenant: str,
    ):
        """Invitation can only be accepted by the invited email, not a stranger."""
        # Invite alice@acme.com
        response = await owner_client.post(
            f"/v1/{tenant}/members/invite-with-token",
            json={"email": "alice@acme.com", "role": "viewer"},
        )
        assert response.status_code == 201
        token = response.json()["data"]["token"]

        # Try to accept as bob@evil.com
        attacker = CurrentUser(
            user_id=f"kc-attacker-{uuid4().hex[:6]}",
            email="bob@evil.com",
            tenant_id=None,
            roles=[],
            actor_type="user",
        )
        app.dependency_overrides[get_current_user] = lambda: attacker
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as attacker_client:
            resp = await attacker_client.post(
                f"/v1/{tenant}/members/accept-invite",
                json={"token": token},
            )
        app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 403
        assert "email" in resp.json()["detail"].lower()

    async def test_accept_used_invitation_returns_400(
        self,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        inv_repo = InvitationRepository(integration_test_session)
        token = "used-token-test"
        token_hash = _hash_token(token)
        await inv_repo.create(
            tenant_id=tenant,
            email="used@acme.com",
            role="viewer",
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        # Mark it accepted immediately

        inv = await inv_repo.get_by_token_hash(token_hash)
        await inv_repo.mark_accepted(inv.id, datetime.now(UTC))
        await integration_test_session.commit()

        some_user = CurrentUser(
            user_id="kc-used-user",
            email="used@acme.com",
            tenant_id=None,
            roles=[],
            actor_type="user",
        )
        app.dependency_overrides[get_current_user] = lambda: some_user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post(
                f"/v1/{tenant}/members/accept-invite",
                json={"token": token},
            )
        app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 400


@pytest.mark.integration
class TestChangeRole:
    async def test_change_role_updates_member(
        self,
        owner_client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        user, _membership = await _seed_member(
            integration_test_session, tenant, role="viewer"
        )
        # Seed a second owner so we can change this user's role freely
        await _seed_member(integration_test_session, tenant, role="owner")
        await integration_test_session.commit()

        response = await owner_client.patch(
            f"/v1/{tenant}/members/{user.id}",
            json={"role": "analyst"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["role"] == "analyst"

    async def test_cannot_demote_last_owner(
        self,
        owner_client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        user, _membership = await _seed_member(
            integration_test_session, tenant, role="owner"
        )

        response = await owner_client.patch(
            f"/v1/{tenant}/members/{user.id}",
            json={"role": "analyst"},
        )
        assert response.status_code == 400


@pytest.mark.integration
class TestRemoveMember:
    async def test_remove_member_revokes_api_keys(
        self,
        owner_client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        user, _membership = await _seed_member(
            integration_test_session, tenant, role="analyst"
        )
        # Seed a second owner so removal is allowed
        await _seed_member(integration_test_session, tenant, role="owner")

        # Seed an API key for the user
        key_svc = ApiKeyService(integration_test_session)
        await key_svc.create_api_key(
            tenant_id=tenant,
            name="User Key",
            user_id=user.id,
        )
        await integration_test_session.commit()

        response = await owner_client.delete(f"/v1/{tenant}/members/{user.id}")
        assert response.status_code == 204

        # Verify API keys were removed
        key_repo = ApiKeyRepository(integration_test_session)
        keys = await key_repo.list_by_tenant(tenant)
        assert all(k.user_id != user.id for k in keys)

    async def test_remove_member_not_found_returns_404(
        self,
        owner_client: AsyncClient,
        tenant: str,
    ):
        response = await owner_client.delete(f"/v1/{tenant}/members/{uuid4()}")
        assert response.status_code == 404


@pytest.mark.integration
class TestApiKeyEndpoints:
    @pytest.fixture(autouse=True)
    async def _ensure_db_user(
        self, integration_test_session: AsyncSession, tenant: str
    ):
        """Create the test user in the DB so the API key FK constraint is satisfied."""
        user_repo = UserRepository(integration_test_session)
        existing = await user_repo.get_by_id(_TEST_DB_USER_ID)
        if existing is None:
            user = User(
                id=_TEST_DB_USER_ID,
                keycloak_id="test-user",
                email="owner@acme.com",
            )
            integration_test_session.add(user)
            # Also create membership for this tenant
            membership = Membership(
                user_id=_TEST_DB_USER_ID,
                tenant_id=tenant,
                role="owner",
            )
            integration_test_session.add(membership)
            await integration_test_session.commit()

    async def test_create_api_key_returns_secret(
        self,
        owner_client: AsyncClient,
        tenant: str,
    ):
        response = await owner_client.post(
            f"/v1/{tenant}/api-keys",
            json={"name": "My Key"},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert "secret" in data
        assert data["secret"]  # non-empty
        assert data["name"] == "My Key"

    async def test_list_api_keys_no_secret(
        self,
        owner_client: AsyncClient,
        tenant: str,
    ):
        # Create one first
        await owner_client.post(
            f"/v1/{tenant}/api-keys",
            json={"name": "Listed Key"},
        )
        response = await owner_client.get(f"/v1/{tenant}/api-keys")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) >= 1
        for key in data:
            assert "secret" not in key

    async def test_revoke_api_key(
        self,
        owner_client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        # Create via service so we have the DB ID
        key_svc = ApiKeyService(integration_test_session)
        created = await key_svc.create_api_key(tenant_id=tenant, name="To Revoke")
        await integration_test_session.commit()

        response = await owner_client.delete(f"/v1/{tenant}/api-keys/{created.id}")
        assert response.status_code == 204

    async def test_revoke_nonexistent_key_returns_404(
        self,
        owner_client: AsyncClient,
        tenant: str,
    ):
        response = await owner_client.delete(f"/v1/{tenant}/api-keys/{uuid4()}")
        assert response.status_code == 404


@pytest.mark.integration
class TestJitProvisioning:
    async def test_first_jwt_user_gets_owner_role(
        self,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """JIT provisioning: first user for a tenant becomes owner."""
        svc = MemberService(integration_test_session)
        first_user = CurrentUser(
            user_id="kc-first-jit",
            email="first@acme.com",
            tenant_id=tenant,
            roles=[],
            actor_type="user",
        )
        await svc.provision_user_jit(first_user)
        await integration_test_session.flush()

        membership_repo = MembershipRepository(integration_test_session)
        user_repo = UserRepository(integration_test_session)
        db_user = await user_repo.get_by_keycloak_id("kc-first-jit")
        assert db_user is not None
        membership = await membership_repo.get_by_user_and_tenant(db_user.id, tenant)
        assert membership is not None
        assert membership.role == "owner"

    async def test_second_jwt_user_gets_viewer_role(
        self,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """JIT provisioning: second user gets viewer role."""
        svc = MemberService(integration_test_session)

        first = CurrentUser(
            user_id="kc-jit-a",
            email="first@jit.com",
            tenant_id=tenant,
            roles=[],
            actor_type="user",
        )
        await svc.provision_user_jit(first)
        await integration_test_session.flush()

        second = CurrentUser(
            user_id="kc-jit-b",
            email="second@jit.com",
            tenant_id=tenant,
            roles=[],
            actor_type="user",
        )
        await svc.provision_user_jit(second)
        await integration_test_session.flush()

        user_repo = UserRepository(integration_test_session)
        membership_repo = MembershipRepository(integration_test_session)
        db_user2 = await user_repo.get_by_keycloak_id("kc-jit-b")
        membership2 = await membership_repo.get_by_user_and_tenant(db_user2.id, tenant)
        assert membership2.role == "viewer"


@pytest.mark.integration
class TestApiKeyAuthentication:
    async def test_api_key_validates_successfully(
        self,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """A valid API key is accepted by validate_api_key."""
        # Seed a user + membership first
        user, _ = await _seed_member(integration_test_session, tenant, role="analyst")

        # Create the API key
        key_svc = ApiKeyService(integration_test_session)
        created = await key_svc.create_api_key(
            tenant_id=tenant,
            name="Auth Test Key",
            user_id=user.id,
        )
        await integration_test_session.commit()

        # Validate it
        from analysi.auth.api_key import validate_api_key

        result = await validate_api_key(created.secret, integration_test_session)

        assert result is not None
        assert result.tenant_id == tenant
        assert result.actor_type == "api_key"
        assert "analyst" in result.roles

    async def test_invalid_api_key_returns_none(
        self,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        from analysi.auth.api_key import validate_api_key

        result = await validate_api_key("totally-invalid-key", integration_test_session)
        assert result is None

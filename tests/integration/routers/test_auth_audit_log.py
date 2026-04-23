"""Integration tests for audit logging of auth events.

Verifies that:
- Creating an API key logs an audit event (action = api_key.created)
- Revoking an API key logs an audit event (action = api_key.revoked)
- Changing a member's role logs an audit event (action = member.role_changed)
"""

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.dependencies import get_current_user
from analysi.auth.models import CurrentUser
from analysi.main import app
from analysi.models.activity_audit import ActivityAuditTrail
from tests.integration.routers.test_members_api import _seed_member

_TEST_DB_USER_ID = UUID("00000000-0000-0000-0000-bbbbbbbbbbbb")


def _make_owner(tenant_id: str) -> CurrentUser:
    return CurrentUser(
        user_id=f"kc-owner-{uuid4().hex[:8]}",
        email="owner@test.com",
        tenant_id=tenant_id,
        roles=["owner"],
        actor_type="user",
        db_user_id=_TEST_DB_USER_ID,
    )


@pytest.fixture
def tenant() -> str:
    return f"test-{uuid4().hex[:8]}"


@pytest.fixture
async def owner_client(tenant: str) -> AsyncGenerator[AsyncClient]:
    user = _make_owner(tenant)
    app.dependency_overrides[get_current_user] = lambda: user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


async def _get_audit_events(
    session: AsyncSession,
    tenant_id: str,
    action: str,
) -> list:
    """Helper to query audit events by tenant + action."""
    stmt = select(ActivityAuditTrail).where(
        ActivityAuditTrail.tenant_id == tenant_id,
        ActivityAuditTrail.action == action,
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@pytest.mark.integration
@pytest.mark.kind_ci
class TestApiKeyAuditLog:
    @pytest.fixture(autouse=True)
    async def _ensure_db_user(
        self, integration_test_session: AsyncSession, tenant: str
    ):
        """Create User + Membership so API key endpoints can resolve db_user_id."""
        from analysi.repositories.membership_repository import MembershipRepository
        from analysi.repositories.user_repository import UserRepository

        user_repo = UserRepository(integration_test_session)
        existing = await user_repo.get_by_id(_TEST_DB_USER_ID)
        if not existing:
            from analysi.models.auth import User

            user = User(
                id=_TEST_DB_USER_ID,
                keycloak_id=f"kc-owner-audit-{uuid4().hex[:8]}",
                email="owner@test.com",
            )
            integration_test_session.add(user)
            membership_repo = MembershipRepository(integration_test_session)
            await membership_repo.create(
                user_id=_TEST_DB_USER_ID,
                tenant_id=tenant,
                role="owner",
            )
            await integration_test_session.commit()

    async def test_create_api_key_logs_audit_event(
        self,
        owner_client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """Creating an API key records an audit event."""
        response = await owner_client.post(
            f"/v1/{tenant}/api-keys",
            json={"name": "Audit Test Key"},
        )
        assert response.status_code == 201

        # Flush any pending writes
        await integration_test_session.commit()
        integration_test_session.expire_all()

        events = await _get_audit_events(
            integration_test_session, tenant, "api_key.created"
        )
        assert len(events) >= 1
        assert events[0].resource_type == "api_key"

    async def test_revoke_api_key_logs_audit_event(
        self,
        owner_client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """Revoking an API key records an audit event."""
        from analysi.services.api_key_service import ApiKeyService

        svc = ApiKeyService(integration_test_session)
        created = await svc.create_api_key(
            tenant_id=tenant, name="To Revoke Audit", user_id=_TEST_DB_USER_ID
        )
        await integration_test_session.commit()

        response = await owner_client.delete(f"/v1/{tenant}/api-keys/{created.id}")
        assert response.status_code == 204

        await integration_test_session.commit()
        integration_test_session.expire_all()

        events = await _get_audit_events(
            integration_test_session, tenant, "api_key.revoked"
        )
        assert len(events) >= 1
        assert events[0].resource_type == "api_key"
        assert str(created.id) in str(events[0].resource_id)


@pytest.mark.integration
@pytest.mark.kind_ci
class TestMemberAuditLog:
    async def test_change_role_logs_audit_event(
        self,
        owner_client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """Changing a member's role records an audit event."""
        # Seed a viewer member to change role on
        user, _ = await _seed_member(integration_test_session, tenant, role="viewer")
        # Seed a second owner so we're not demoting the last owner
        await _seed_member(integration_test_session, tenant, role="owner")
        await integration_test_session.commit()

        response = await owner_client.patch(
            f"/v1/{tenant}/members/{user.id}",
            json={"role": "analyst"},
        )
        assert response.status_code == 200

        await integration_test_session.commit()
        integration_test_session.expire_all()

        events = await _get_audit_events(
            integration_test_session, tenant, "member.role_changed"
        )
        assert len(events) >= 1
        assert events[0].resource_type == "member"

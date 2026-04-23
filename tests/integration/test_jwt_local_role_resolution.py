"""Tests for JWT local role resolution — Mikonos P1.

Verifies that JWT-authenticated users have their roles resolved from the
local memberships table (source of truth) rather than the JWT claims,
which may be stale after admin role changes.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.dependencies import get_current_user
from analysi.auth.models import CurrentUser
from analysi.models.auth import Membership, User


def _make_jwt_user(
    keycloak_id: str,
    tenant_id: str,
    roles: list[str],
    email: str = "user@test.com",
) -> CurrentUser:
    """Simulate a CurrentUser as returned by validate_jwt_token."""
    return CurrentUser(
        user_id=keycloak_id,
        email=email,
        tenant_id=tenant_id,
        roles=roles,
        actor_type="user",
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestJWTLocalRoleResolution:
    """JWT roles must be overridden by local membership roles."""

    @pytest_asyncio.fixture
    async def tenant_id(self):
        return f"test-role-res-{uuid4().hex[:8]}"

    @pytest_asyncio.fixture
    async def keycloak_id(self):
        return f"kc-{uuid4().hex[:8]}"

    @pytest_asyncio.fixture
    async def db_user_with_viewer_membership(
        self, db_session: AsyncSession, tenant_id: str, keycloak_id: str
    ):
        """Create a local user with 'viewer' role in the memberships table."""
        user = User(
            keycloak_id=keycloak_id,
            email=f"{keycloak_id}@test.com",
        )
        db_session.add(user)
        await db_session.flush()

        membership = Membership(
            user_id=user.id,
            tenant_id=tenant_id,
            role="viewer",
        )
        db_session.add(membership)
        await db_session.commit()
        return user

    async def test_jwt_admin_demoted_to_local_viewer(
        self,
        db_session: AsyncSession,
        db_user_with_viewer_membership: User,
        tenant_id: str,
        keycloak_id: str,
    ):
        """User with admin in JWT but viewer in local DB should resolve as viewer."""
        stale_jwt_user = _make_jwt_user(
            keycloak_id=keycloak_id,
            tenant_id=tenant_id,
            roles=["admin"],  # stale JWT claim
        )

        with (
            patch(
                "analysi.auth.dependencies.is_jwks_configured",
                return_value=True,
            ),
            patch(
                "analysi.auth.dependencies.validate_jwt_token",
                return_value=stale_jwt_user,
            ),
        ):
            # Call get_current_user with a fake token and real DB session
            resolved = await get_current_user(
                token="fake.jwt.token",
                request=None,
                db=db_session,
            )

        assert resolved is not None
        assert resolved.roles == ["viewer"], (
            f"Expected local role ['viewer'] but got {resolved.roles} — "
            "JWT claims were not overridden by local membership"
        )
        assert resolved.db_user_id == db_user_with_viewer_membership.id

    async def test_jwt_viewer_promoted_to_local_admin(
        self,
        db_session: AsyncSession,
        tenant_id: str,
        keycloak_id: str,
    ):
        """User with viewer in JWT but admin in local DB should resolve as admin."""
        # Create user with admin role locally
        user = User(
            keycloak_id=keycloak_id,
            email=f"{keycloak_id}@test.com",
        )
        db_session.add(user)
        await db_session.flush()
        db_session.add(Membership(user_id=user.id, tenant_id=tenant_id, role="admin"))
        await db_session.commit()

        stale_jwt_user = _make_jwt_user(
            keycloak_id=keycloak_id,
            tenant_id=tenant_id,
            roles=["viewer"],  # stale JWT claim
        )

        with (
            patch(
                "analysi.auth.dependencies.is_jwks_configured",
                return_value=True,
            ),
            patch(
                "analysi.auth.dependencies.validate_jwt_token",
                return_value=stale_jwt_user,
            ),
        ):
            resolved = await get_current_user(
                token="fake.jwt.token",
                request=None,
                db=db_session,
            )

        assert resolved is not None
        assert resolved.roles == ["admin"], (
            f"Expected local role ['admin'] but got {resolved.roles} — "
            "JWT claims were not overridden by local membership"
        )

    async def test_removed_user_does_not_keep_stale_jwt_roles(
        self,
        db_session: AsyncSession,
        tenant_id: str,
        keycloak_id: str,
    ):
        """Removed user with stale admin JWT must NOT retain admin role.

        JIT provisioning may re-create a viewer membership, which is acceptable.
        The key invariant: the stale JWT "admin" claim must never survive.
        """
        # Create user WITHOUT a membership (simulates a removed member)
        user = User(
            keycloak_id=keycloak_id,
            email=f"{keycloak_id}@test.com",
        )
        db_session.add(user)
        await db_session.commit()

        stale_jwt_user = _make_jwt_user(
            keycloak_id=keycloak_id,
            tenant_id=tenant_id,
            roles=["admin"],  # stale JWT claim from before removal
        )

        with (
            patch(
                "analysi.auth.dependencies.is_jwks_configured",
                return_value=True,
            ),
            patch(
                "analysi.auth.dependencies.validate_jwt_token",
                return_value=stale_jwt_user,
            ),
        ):
            resolved = await get_current_user(
                token="fake.jwt.token",
                request=None,
                db=db_session,
            )

        assert resolved is not None
        assert "admin" not in resolved.roles, (
            f"Stale JWT 'admin' role survived role resolution: {resolved.roles}"
        )

    async def test_fail_closed_when_jit_fails(
        self,
        db_session: AsyncSession,
        tenant_id: str,
        keycloak_id: str,
    ):
        """When JIT provisioning fails, stale JWT roles must not survive.

        If _resolve_local_roles runs independently of JIT, a user with no
        membership should get empty roles rather than keeping JWT claims.
        """
        # Create user WITHOUT membership
        user = User(
            keycloak_id=keycloak_id,
            email=f"{keycloak_id}@test.com",
        )
        db_session.add(user)
        await db_session.commit()

        stale_jwt_user = _make_jwt_user(
            keycloak_id=keycloak_id,
            tenant_id=tenant_id,
            roles=["admin"],  # stale JWT claim
        )

        with (
            patch(
                "analysi.auth.dependencies.is_jwks_configured",
                return_value=True,
            ),
            patch(
                "analysi.auth.dependencies.validate_jwt_token",
                return_value=stale_jwt_user,
            ),
            patch(
                "analysi.services.member_service.MemberService.provision_user_jit",
                side_effect=RuntimeError("Simulated JIT failure"),
            ),
        ):
            resolved = await get_current_user(
                token="fake.jwt.token",
                request=None,
                db=db_session,
            )

        assert resolved is not None
        assert resolved.roles == [], (
            f"Expected empty roles after JIT failure for user without membership, "
            f"got {resolved.roles}"
        )

    async def test_platform_admin_roles_not_overridden(
        self,
        db_session: AsyncSession,
    ):
        """Platform admin roles from JWT should not be overridden."""
        jwt_user = CurrentUser(
            user_id="admin-kc-id",
            email="admin@test.com",
            tenant_id=None,
            roles=["platform_admin"],
            actor_type="user",
        )

        with (
            patch(
                "analysi.auth.dependencies.is_jwks_configured",
                return_value=True,
            ),
            patch(
                "analysi.auth.dependencies.validate_jwt_token",
                return_value=jwt_user,
            ),
        ):
            resolved = await get_current_user(
                token="fake.jwt.token",
                request=None,
                db=db_session,
            )

        assert resolved is not None
        assert "platform_admin" in resolved.roles

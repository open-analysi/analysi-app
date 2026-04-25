"""Unit tests for MCPTenantMiddleware Bearer token and API key authentication."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

from analysi.auth.models import CurrentUser
from analysi.mcp.middleware import MCPTenantMiddleware, _resolve_actor


def _make_test_app() -> Starlette:
    """Create a minimal Starlette app for middleware testing."""

    async def homepage(request: Request) -> Response:
        return Response("ok", status_code=200)

    app = Starlette(routes=[Route("/v1/demo/mcp/test", homepage)])
    app.add_middleware(MCPTenantMiddleware)
    return app


def _make_current_user(tenant_id: str = "demo") -> CurrentUser:
    return CurrentUser(
        user_id="kc-test-user",
        email="user@test.com",
        tenant_id=tenant_id,
        roles=["owner"],
        actor_type="user",
    )


class TestMCPTenantMiddlewareBearer:
    """Tests for Bearer token validation in MCPTenantMiddleware."""

    def test_no_auth_header_returns_401(self):
        """Request with no auth header must be rejected."""
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/v1/demo/mcp/test")
        assert response.status_code == 401

    def test_jwks_not_configured_rejects_bearer(self):
        """When JWKS is not configured, Bearer tokens cannot be validated → 401."""
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch("analysi.mcp.middleware.is_jwks_configured", return_value=False):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={"Authorization": "Bearer any-token"},
            )
        assert response.status_code == 401

    def test_valid_bearer_token_sets_current_user(self):
        """Valid JWT with JWKS configured → CurrentUser ContextVar is set."""
        expected_user = _make_current_user()
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("analysi.mcp.middleware.is_jwks_configured", return_value=True),
            patch(
                "analysi.mcp.middleware.validate_jwt_token",
                return_value=expected_user,
            ),
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
        assert response.status_code == 200

    def test_invalid_bearer_token_returns_401(self):
        """Invalid JWT with JWKS configured → 401 Unauthorized."""
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("analysi.mcp.middleware.is_jwks_configured", return_value=True),
            patch(
                "analysi.mcp.middleware.validate_jwt_token",
                side_effect=HTTPException(status_code=401, detail="Invalid token"),
            ),
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={"Authorization": "Bearer tampered.jwt.token"},
            )
        assert response.status_code == 401

    def test_invalid_api_key_returns_401(self):
        """X-API-Key that fails validation must be rejected."""
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        # validate_api_key returns None for invalid keys
        with patch(
            "analysi.mcp.middleware.validate_api_key",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={"X-API-Key": "invalid-key"},
            )
        assert response.status_code == 401

    def test_valid_api_key_sets_current_user(self):
        """Valid X-API-Key → CurrentUser ContextVar is set, 200."""
        expected_user = _make_current_user()
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "analysi.mcp.middleware.validate_api_key",
            new_callable=AsyncMock,
            return_value=expected_user,
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={"X-API-Key": "valid-api-key-123"},
            )
        assert response.status_code == 200


class TestMCPTenantIsolation:
    """Tenant isolation: credentials must belong to the tenant in the URL."""

    def test_bearer_wrong_tenant_returns_403(self):
        """JWT user for tenant-a cannot access /v1/demo/mcp (tenant=demo)."""
        wrong_tenant_user = _make_current_user(tenant_id="other-tenant")
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("analysi.mcp.middleware.is_jwks_configured", return_value=True),
            patch(
                "analysi.mcp.middleware.validate_jwt_token",
                return_value=wrong_tenant_user,
            ),
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
        assert response.status_code == 403

    def test_api_key_wrong_tenant_returns_403(self):
        """API key for tenant-a cannot access /v1/demo/mcp (tenant=demo)."""
        wrong_tenant_user = _make_current_user(tenant_id="other-tenant")
        wrong_tenant_user.actor_type = "api_key"
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "analysi.mcp.middleware.validate_api_key",
            new_callable=AsyncMock,
            return_value=wrong_tenant_user,
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={"X-API-Key": "valid-key-wrong-tenant"},
            )
        assert response.status_code == 403

    def test_platform_admin_bypasses_tenant_check(self):
        """Platform admin can access any tenant's MCP endpoints."""
        admin_user = CurrentUser(
            user_id="kc-admin",
            email="admin@test.com",
            tenant_id=None,
            roles=["platform_admin"],
            actor_type="user",
        )
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("analysi.mcp.middleware.is_jwks_configured", return_value=True),
            patch(
                "analysi.mcp.middleware.validate_jwt_token",
                return_value=admin_user,
            ),
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={"Authorization": "Bearer admin.jwt.token"},
            )
        assert response.status_code == 200

    def test_system_actor_bypasses_tenant_check(self):
        """System API keys (workers) can access any tenant's MCP endpoints."""
        system_user = CurrentUser(
            user_id="system:test-key",
            email="system@analysi.internal",
            tenant_id="default",  # system key tenant != URL tenant
            roles=["system", "platform_admin"],
            actor_type="system",
        )
        app = _make_test_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "analysi.mcp.middleware.validate_api_key",
            new_callable=AsyncMock,
            return_value=system_user,
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={"X-API-Key": "system-api-key"},
            )
        assert response.status_code == 200


class TestResolveActorRoles:
    """Verify _resolve_actor resolves actor's roles from membership, not system roles."""

    async def test_actor_gets_membership_role(self):
        """Actor override should resolve the actor's actual role from membership."""
        actor_uuid = uuid4()
        system_user = CurrentUser(
            user_id="system:key",
            email="system@analysi.internal",
            tenant_id="default",
            roles=["system", "platform_admin"],
            actor_type="system",
        )

        # Mock session that returns "analyst" role for the actor
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "analyst"
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        resolved = await _resolve_actor(
            mock_session, str(actor_uuid), "demo-tenant", system_user
        )

        assert resolved.db_user_id == actor_uuid
        assert resolved.roles == ["analyst"]
        assert resolved.actor_type == "user"
        assert resolved.tenant_id == "demo-tenant"
        assert not resolved.is_platform_admin

    async def test_actor_no_membership_clears_roles(self):
        """If actor has no membership, roles are cleared (fail closed)."""
        actor_uuid = uuid4()
        system_user = CurrentUser(
            user_id="system:key",
            email="system@analysi.internal",
            tenant_id="default",
            roles=["system", "platform_admin"],
            actor_type="system",
        )

        # Mock session that returns None (no membership)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        resolved = await _resolve_actor(
            mock_session, str(actor_uuid), "demo-tenant", system_user
        )

        # Fail closed: roles cleared, not kept from system key
        assert resolved.roles == []
        assert resolved.actor_type == "user"
        assert resolved.tenant_id == "demo-tenant"

    async def test_actor_invalid_uuid_keeps_system_user(self):
        """Invalid UUID in actor header returns original system user."""
        system_user = CurrentUser(
            user_id="system:key",
            email="system@analysi.internal",
            tenant_id="default",
            roles=["system", "platform_admin"],
            actor_type="system",
        )

        mock_session = AsyncMock()

        resolved = await _resolve_actor(
            mock_session, "not-a-uuid", "demo-tenant", system_user
        )

        assert resolved is system_user
        assert resolved.roles == ["system", "platform_admin"]

    async def test_actor_viewer_role_limits_permissions(self):
        """Actor with viewer role should not have write permissions."""
        actor_uuid = uuid4()
        system_user = CurrentUser(
            user_id="system:key",
            email="system@analysi.internal",
            tenant_id="default",
            roles=["system", "platform_admin"],
            actor_type="system",
        )

        # Actor has viewer role only
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "viewer"
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        resolved = await _resolve_actor(
            mock_session, str(actor_uuid), "demo-tenant", system_user
        )

        assert resolved.roles == ["viewer"]
        assert resolved.actor_type == "user"
        assert resolved.tenant_id == "demo-tenant"
        assert not resolved.is_platform_admin


class TestMCPJwtLocalRolesFailClosed:
    """Verify _resolve_jwt_local_roles fails closed when local user is missing."""

    async def test_missing_local_user_clears_roles(self):
        """JWT user with no local user row should have roles cleared to []."""
        from analysi.mcp.middleware import _resolve_jwt_local_roles

        user = CurrentUser(
            user_id="kc-unknown",
            email="unknown@test.com",
            tenant_id="demo",
            roles=["admin"],  # stale JWT claim
            actor_type="user",
        )

        # Mock session where keycloak_id lookup returns None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        # AsyncSessionLocal() returns an async context manager
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "analysi.db.session.AsyncSessionLocal",
            return_value=mock_session,
        ):
            await _resolve_jwt_local_roles(user, "demo")

        assert user.roles == [], (
            f"Expected empty roles for missing local user, got {user.roles}"
        )

    async def test_empty_user_id_clears_roles(self):
        """Security: empty user_id (missing JWT sub) must fail closed without DB query."""
        from analysi.mcp.middleware import _resolve_jwt_local_roles

        user = CurrentUser(
            user_id="",
            email="attacker@attacker.example",
            tenant_id="demo",
            roles=["owner"],  # should not survive
            actor_type="user",
        )

        # Should not even open a session
        with patch(
            "analysi.db.session.AsyncSessionLocal",
            side_effect=AssertionError("Should not open session for empty user_id"),
        ):
            await _resolve_jwt_local_roles(user, "demo")

        assert user.roles == []

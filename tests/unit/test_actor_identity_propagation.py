"""Unit tests for user identity propagation: REST API → Agent Orchestration → MCP.

Tests three layers:
1. internal_auth_headers() — X-Actor-User-Id header generation
2. get_mcp_servers() — auth headers in MCP server configs
3. MCPTenantMiddleware — X-Actor-User-Id trusted only from system API keys,
   and only when the actor has a membership in the MCP tenant
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

from analysi.auth.models import CurrentUser
from analysi.common.internal_auth import internal_auth_headers
from analysi.mcp.context import get_mcp_current_user
from analysi.mcp.middleware import MCPTenantMiddleware

# ---------------------------------------------------------------------------
# 1. internal_auth_headers()
# ---------------------------------------------------------------------------


class TestInternalAuthHeadersActor:
    """Tests for actor_user_id support in internal_auth_headers."""

    def test_no_actor_returns_only_api_key(self):
        with patch.dict(os.environ, {"ANALYSI_SYSTEM_API_KEY": "sys-key"}):
            headers = internal_auth_headers()
        assert headers == {"X-API-Key": "sys-key"}
        assert "X-Actor-User-Id" not in headers

    def test_actor_uuid_adds_header(self):
        actor = uuid4()
        with patch.dict(os.environ, {"ANALYSI_SYSTEM_API_KEY": "sys-key"}):
            headers = internal_auth_headers(actor_user_id=actor)
        assert headers["X-API-Key"] == "sys-key"
        assert headers["X-Actor-User-Id"] == str(actor)

    def test_actor_string_adds_header(self):
        actor_str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch.dict(os.environ, {"ANALYSI_SYSTEM_API_KEY": "sys-key"}):
            headers = internal_auth_headers(actor_user_id=actor_str)
        assert headers["X-Actor-User-Id"] == actor_str

    def test_no_api_key_still_adds_actor(self):
        actor = uuid4()
        with patch.dict(os.environ, {}, clear=True):
            headers = internal_auth_headers(actor_user_id=actor)
        assert "X-API-Key" not in headers
        assert headers["X-Actor-User-Id"] == str(actor)

    def test_no_api_key_no_actor_returns_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            headers = internal_auth_headers()
        assert headers == {}


# ---------------------------------------------------------------------------
# 2. get_mcp_servers()
# ---------------------------------------------------------------------------


class TestGetMCPServersHeaders:
    """Tests for auth headers in get_mcp_servers."""

    def test_no_actor_no_api_key_no_headers(self):
        """Without API key or actor, server configs have no headers key."""
        from analysi.agentic_orchestration.config import get_mcp_servers

        with patch.dict(os.environ, {}, clear=True):
            servers = get_mcp_servers("tenant1")
        for cfg in servers.values():
            assert "headers" not in cfg

    def test_api_key_only_adds_headers(self):
        """System API key alone adds headers with X-API-Key."""
        from analysi.agentic_orchestration.config import get_mcp_servers

        with patch.dict(os.environ, {"ANALYSI_SYSTEM_API_KEY": "sys-key"}, clear=True):
            servers = get_mcp_servers("tenant1")
        for cfg in servers.values():
            assert cfg["headers"] == {"X-API-Key": "sys-key"}

    def test_actor_user_id_adds_both_headers(self):
        """actor_user_id adds both X-API-Key and X-Actor-User-Id."""
        from analysi.agentic_orchestration.config import get_mcp_servers

        actor = uuid4()
        with patch.dict(os.environ, {"ANALYSI_SYSTEM_API_KEY": "sys-key"}, clear=True):
            servers = get_mcp_servers("tenant1", actor_user_id=actor)
        for cfg in servers.values():
            assert cfg["headers"]["X-API-Key"] == "sys-key"
            assert cfg["headers"]["X-Actor-User-Id"] == str(actor)

    def test_actor_user_id_without_api_key(self):
        """actor_user_id without API key still adds the actor header."""
        from analysi.agentic_orchestration.config import get_mcp_servers

        actor = uuid4()
        with patch.dict(os.environ, {}, clear=True):
            servers = get_mcp_servers("tenant1", actor_user_id=actor)
        for cfg in servers.values():
            assert cfg["headers"]["X-Actor-User-Id"] == str(actor)
            assert "X-API-Key" not in cfg["headers"]

    def test_server_urls_unchanged_with_headers(self):
        """Adding headers doesn't affect URL construction."""
        from analysi.agentic_orchestration.config import get_mcp_servers

        actor = uuid4()
        with patch.dict(os.environ, {"ANALYSI_SYSTEM_API_KEY": "sys-key"}, clear=True):
            servers = get_mcp_servers(
                "tenant1", api_host="localhost", api_port=8001, actor_user_id=actor
            )
        assert servers["analysi"]["url"] == "http://localhost:8001/v1/tenant1/mcp/"


# ---------------------------------------------------------------------------
# 3. MCPTenantMiddleware — X-Actor-User-Id handling
# ---------------------------------------------------------------------------

_SYSTEM_DB_ID = UUID("00000000-0000-0000-0000-000000000001")


def _make_system_user() -> CurrentUser:
    return CurrentUser(
        user_id="system",
        email="system@internal",
        tenant_id=None,
        roles=[],
        actor_type="system",
        db_user_id=_SYSTEM_DB_ID,
    )


def _make_test_app_with_user_capture() -> tuple[Starlette, list]:
    """Create app that captures the resolved CurrentUser from ContextVar."""
    captured: list = []

    async def handler(request: Request) -> Response:
        user = get_mcp_current_user()
        captured.append(user)
        return Response("ok", status_code=200)

    app = Starlette(routes=[Route("/v1/demo/mcp/test", handler)])
    app.add_middleware(MCPTenantMiddleware)
    return app, captured


def _mock_membership_found():
    """Mock _resolve_actor to simulate a valid membership lookup."""

    async def _resolve(session, actor_header, tenant, user):
        import dataclasses

        return dataclasses.replace(
            user,
            db_user_id=UUID(actor_header),
            roles=["analyst"],
            actor_type="user",
            tenant_id=tenant,
        )

    return patch("analysi.mcp.middleware._resolve_actor", side_effect=_resolve)


def _mock_membership_not_found():
    """Mock _resolve_actor to simulate no membership (fail closed)."""
    import dataclasses

    async def _resolve(session, actor_header, tenant, user):
        # Fail closed: clear roles instead of keeping system admin
        return dataclasses.replace(user, roles=[], actor_type="user", tenant_id=tenant)

    return patch("analysi.mcp.middleware._resolve_actor", side_effect=_resolve)


class TestMCPMiddlewareActorHeader:
    """Tests for X-Actor-User-Id trust logic in MCPTenantMiddleware."""

    def test_system_key_with_valid_actor_overrides_db_user_id(self):
        """System API key + X-Actor-User-Id with valid membership → db_user_id overridden."""
        actor_uuid = uuid4()
        system_user = _make_system_user()

        app, captured = _make_test_app_with_user_capture()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch(
                "analysi.mcp.middleware.validate_api_key",
                new_callable=AsyncMock,
                return_value=system_user,
            ),
            _mock_membership_found(),
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={
                    "X-API-Key": "system-key",
                    "X-Actor-User-Id": str(actor_uuid),
                },
            )

        assert response.status_code == 200
        assert len(captured) == 1
        assert captured[0].db_user_id == actor_uuid
        assert captured[0].roles == ["analyst"]
        assert captured[0].actor_type == "user"

    def test_system_key_actor_not_in_tenant_clears_roles(self):
        """System API key + X-Actor-User-Id not in tenant → fail closed."""
        actor_uuid = uuid4()
        system_user = _make_system_user()

        app, captured = _make_test_app_with_user_capture()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch(
                "analysi.mcp.middleware.validate_api_key",
                new_callable=AsyncMock,
                return_value=system_user,
            ),
            _mock_membership_not_found(),
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={
                    "X-API-Key": "system-key",
                    "X-Actor-User-Id": str(actor_uuid),
                },
            )

        # Request reaches endpoint (tenant matches) but roles are empty
        assert response.status_code == 200
        assert len(captured) == 1
        assert captured[0].roles == []
        assert captured[0].actor_type == "user"

    def test_user_api_key_with_actor_header_ignored(self):
        """User API key + X-Actor-User-Id → header is IGNORED (no impersonation)."""
        actor_uuid = uuid4()
        original_db_user_id = uuid4()
        user_key_user = CurrentUser(
            user_id="user-123",
            email="user@example.com",
            tenant_id="demo",
            roles=["analyst"],
            actor_type="api_key",
            db_user_id=original_db_user_id,
        )

        app, captured = _make_test_app_with_user_capture()
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "analysi.mcp.middleware.validate_api_key",
            new_callable=AsyncMock,
            return_value=user_key_user,
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={
                    "X-API-Key": "user-key",
                    "X-Actor-User-Id": str(actor_uuid),
                },
            )

        assert response.status_code == 200
        assert len(captured) == 1
        assert captured[0].db_user_id == original_db_user_id

    def test_jwt_user_with_actor_header_ignored(self):
        """JWT-authenticated user + X-Actor-User-Id → header is IGNORED."""
        actor_uuid = uuid4()
        original_db_user_id = uuid4()
        jwt_user = CurrentUser(
            user_id="kc-user",
            email="user@example.com",
            tenant_id="demo",
            roles=["owner"],
            actor_type="user",
            db_user_id=original_db_user_id,
        )

        app, captured = _make_test_app_with_user_capture()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("analysi.mcp.middleware.is_jwks_configured", return_value=True),
            patch(
                "analysi.mcp.middleware.validate_jwt_token",
                return_value=jwt_user,
            ),
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={
                    "Authorization": "Bearer valid.jwt.token",
                    "X-Actor-User-Id": str(actor_uuid),
                },
            )

        assert response.status_code == 200
        assert len(captured) == 1
        assert captured[0].db_user_id == original_db_user_id

    def test_system_key_without_actor_header_keeps_default(self):
        """System API key without X-Actor-User-Id → db_user_id unchanged."""
        system_user = _make_system_user()

        app, captured = _make_test_app_with_user_capture()
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "analysi.mcp.middleware.validate_api_key",
            new_callable=AsyncMock,
            return_value=system_user,
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={"X-API-Key": "system-key"},
            )

        assert response.status_code == 200
        assert len(captured) == 1
        assert captured[0].db_user_id == _SYSTEM_DB_ID

    def test_system_key_with_invalid_uuid_keeps_default(self):
        """System API key + invalid UUID in X-Actor-User-Id → header ignored."""
        system_user = _make_system_user()

        app, captured = _make_test_app_with_user_capture()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch(
                "analysi.mcp.middleware.validate_api_key",
                new_callable=AsyncMock,
                return_value=system_user,
            ),
            # _resolve_actor handles invalid UUID internally
            patch(
                "analysi.mcp.middleware._resolve_actor",
                new_callable=AsyncMock,
                return_value=system_user,  # Returns unchanged
            ),
        ):
            response = client.get(
                "/v1/demo/mcp/test",
                headers={
                    "X-API-Key": "system-key",
                    "X-Actor-User-Id": "not-a-valid-uuid",
                },
            )

        assert response.status_code == 200
        assert len(captured) == 1
        assert captured[0].db_user_id == _SYSTEM_DB_ID


class TestResolveActor:
    """Tests for _resolve_actor — the membership validation function."""

    @staticmethod
    def _mock_session(membership_role: str | None) -> AsyncMock:
        """Create a mock DB session that returns a membership role or None."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = membership_role
        session.execute.return_value = mock_result
        return session

    @staticmethod
    async def _call_resolve(session, actor_str, tenant, user):
        from analysi.mcp.middleware import _resolve_actor

        return await _resolve_actor(session, actor_str, tenant, user)

    async def test_valid_actor_with_membership_overrides(self):
        """Actor UUID with membership in tenant → db_user_id, roles, actor_type, and tenant_id overridden."""
        actor_uuid = uuid4()
        user = _make_system_user()
        session = self._mock_session(membership_role="analyst")

        result = await self._call_resolve(session, str(actor_uuid), "demo", user)

        assert result.db_user_id == actor_uuid
        assert result.roles == ["analyst"]
        assert result.actor_type == "user"
        assert result.tenant_id == "demo"
        session.execute.assert_called_once()

    async def test_valid_actor_no_membership_clears_roles(self):
        """Actor UUID without membership → fail closed (roles cleared)."""
        actor_uuid = uuid4()
        user = _make_system_user()
        session = self._mock_session(membership_role=None)

        result = await self._call_resolve(session, str(actor_uuid), "demo", user)

        assert result.roles == []
        assert result.actor_type == "user"
        assert result.tenant_id == "demo"
        session.execute.assert_called_once()

    async def test_invalid_uuid_keeps_default(self):
        """Non-UUID string → db_user_id unchanged, no DB query."""
        user = _make_system_user()
        session = self._mock_session(membership_role=None)

        result = await self._call_resolve(session, "not-a-uuid", "demo", user)

        assert result.db_user_id == _SYSTEM_DB_ID
        session.execute.assert_not_called()

    async def test_cross_tenant_actor_rejected(self):
        """Actor UUID from a different tenant → fail closed (roles cleared).

        This is the key security test: even if the UUID is valid,
        if the actor has no membership in the target tenant, we deny.
        """
        actor_uuid = uuid4()
        user = _make_system_user()
        # Simulate: actor exists but NOT in this tenant
        session = self._mock_session(membership_role=None)

        result = await self._call_resolve(
            session, str(actor_uuid), "different-tenant", user
        )

        assert result.roles == []
        assert result.actor_type == "user"

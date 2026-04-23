"""Integration tests for MCP authentication enforcement.

Tests go through the full HTTP stack using fresh MCP server instances,
mirroring the approach in test_mcp_http_transport.py.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.routing import Router as StarletteRouter

from analysi.auth.models import CurrentUser
from analysi.mcp.context import get_mcp_actor_user_id, mcp_current_user_context
from analysi.models.auth import SYSTEM_USER_ID

TENANT = "test-bearer-auth"
MCP_URL = f"/v1/{TENANT}/mcp/"

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

MCP_INIT_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    },
}


def _make_current_user(tenant_id: str = TENANT, **kwargs) -> CurrentUser:
    defaults = {
        "user_id": f"kc-{uuid4().hex[:8]}",
        "email": "user@test.com",
        "tenant_id": tenant_id,
        "roles": ["owner"],
        "actor_type": "user",
    }
    defaults.update(kwargs)
    return CurrentUser(**defaults)


def _build_test_mcp_app():
    """Build a minimal MCP Starlette app with fresh server instances."""
    from analysi.mcp.analysi_server import create_analysi_mcp_server
    from analysi.mcp.middleware import wrap_mcp_app_with_tenant

    cy_server = create_analysi_mcp_server()
    cy_asgi = wrap_mcp_app_with_tenant(cy_server.streamable_http_app())

    inner = StarletteRouter(routes=[Mount(f"/{TENANT}/mcp", app=cy_asgi)])
    outer = Starlette(routes=[Mount("/v1", app=inner)])
    return outer, cy_server


@pytest_asyncio.fixture
async def mcp_auth_client() -> AsyncGenerator[AsyncClient]:
    """HTTP client with a fresh MCP server for auth tests."""
    test_app, cy_server = _build_test_mcp_app()

    cy_cm = cy_server.session_manager.run()
    await cy_cm.__aenter__()

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test-host") as client:
        yield client

    try:
        await cy_cm.__aexit__(None, None, None)
    except RuntimeError as e:
        if "cancel scope" not in str(e).lower():
            raise


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPBearerTokenAuth:
    """Integration tests for MCP middleware Bearer token validation."""

    async def test_mcp_invalid_jwt_returns_401_when_jwks_configured(
        self,
        mcp_auth_client: AsyncClient,
    ):
        """When JWKS configured, invalid JWT returns 401."""
        with (
            patch("analysi.mcp.middleware.is_jwks_configured", return_value=True),
            patch(
                "analysi.mcp.middleware.validate_jwt_token",
                side_effect=HTTPException(status_code=401, detail="Invalid token"),
            ),
        ):
            response = await mcp_auth_client.post(
                MCP_URL,
                headers={**MCP_HEADERS, "Authorization": "Bearer bad.token.here"},
                json=MCP_INIT_PAYLOAD,
            )
        assert response.status_code == 401

    async def test_mcp_valid_jwt_passes_through(
        self,
        mcp_auth_client: AsyncClient,
    ):
        """When JWKS configured, valid JWT allows request to proceed."""
        expected_user = _make_current_user()

        with (
            patch("analysi.mcp.middleware.is_jwks_configured", return_value=True),
            patch(
                "analysi.mcp.middleware.validate_jwt_token",
                return_value=expected_user,
            ),
        ):
            response = await mcp_auth_client.post(
                MCP_URL,
                headers={**MCP_HEADERS, "Authorization": "Bearer valid.jwt.token"},
                json=MCP_INIT_PAYLOAD,
            )
        # Not a 401 — auth passed, request was processed
        assert response.status_code != 401


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPAuthEnforcement:
    """Tests for P0: MCP endpoints must reject unauthenticated requests."""

    async def test_mcp_no_auth_returns_401(
        self,
        mcp_auth_client: AsyncClient,
    ):
        """Unauthenticated MCP requests must be rejected with 401."""
        with patch("analysi.mcp.middleware.is_jwks_configured", return_value=False):
            response = await mcp_auth_client.post(
                MCP_URL, headers=MCP_HEADERS, json=MCP_INIT_PAYLOAD
            )
        assert response.status_code == 401

    async def test_mcp_no_auth_returns_401_when_jwks_configured(
        self,
        mcp_auth_client: AsyncClient,
    ):
        """Unauthenticated MCP requests rejected even when JWKS is configured."""
        with patch("analysi.mcp.middleware.is_jwks_configured", return_value=True):
            response = await mcp_auth_client.post(
                MCP_URL, headers=MCP_HEADERS, json=MCP_INIT_PAYLOAD
            )
        assert response.status_code == 401

    async def test_mcp_invalid_api_key_returns_401(
        self,
        mcp_auth_client: AsyncClient,
    ):
        """Invalid API key must be rejected with 401, not passed through."""
        with patch(
            "analysi.mcp.middleware.validate_api_key",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await mcp_auth_client.post(
                MCP_URL,
                headers={**MCP_HEADERS, "X-API-Key": "invalid-key-here"},
                json=MCP_INIT_PAYLOAD,
            )
        assert response.status_code == 401

    async def test_mcp_valid_api_key_passes_through(
        self,
        mcp_auth_client: AsyncClient,
    ):
        """Valid API key allows request to proceed."""
        expected_user = _make_current_user(actor_type="api_key")

        with patch(
            "analysi.mcp.middleware.validate_api_key",
            new_callable=AsyncMock,
            return_value=expected_user,
        ):
            response = await mcp_auth_client.post(
                MCP_URL,
                headers={**MCP_HEADERS, "X-API-Key": "valid-key"},
                json=MCP_INIT_PAYLOAD,
            )
        assert response.status_code != 401

    async def test_mcp_bearer_without_jwks_returns_401(
        self,
        mcp_auth_client: AsyncClient,
    ):
        """Bearer token when JWKS not configured must be rejected (cannot validate)."""
        with patch("analysi.mcp.middleware.is_jwks_configured", return_value=False):
            response = await mcp_auth_client.post(
                MCP_URL,
                headers={**MCP_HEADERS, "Authorization": "Bearer some.jwt.token"},
                json=MCP_INIT_PAYLOAD,
            )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestMCPActorUserIdSafety:
    """Tests for P0: get_mcp_actor_user_id must not silently fall back to SYSTEM_USER_ID."""

    async def test_get_mcp_actor_user_id_raises_when_no_user(self):
        """Must raise RuntimeError when no authenticated user is in context."""
        # Ensure no user is set
        token = mcp_current_user_context.set(None)
        try:
            with pytest.raises(RuntimeError, match="No authenticated user"):
                get_mcp_actor_user_id()
        finally:
            mcp_current_user_context.reset(token)

    async def test_get_mcp_actor_user_id_returns_db_user_id(self):
        """Returns db_user_id when an authenticated user with db_user_id is present."""
        user_uuid = uuid4()
        user = _make_current_user(db_user_id=user_uuid)
        token = mcp_current_user_context.set(user)
        try:
            assert get_mcp_actor_user_id() == user_uuid
        finally:
            mcp_current_user_context.reset(token)

    async def test_get_mcp_actor_user_id_falls_back_to_system_for_authenticated_user(
        self,
    ):
        """Authenticated user without db_user_id (e.g., system API key) gets SYSTEM_USER_ID."""
        user = _make_current_user(actor_type="system")
        # db_user_id is None by default
        token = mcp_current_user_context.set(user)
        try:
            assert get_mcp_actor_user_id() == SYSTEM_USER_ID
        finally:
            mcp_current_user_context.reset(token)

"""Regression tests for API key creation privilege escalation (P0).

An API-key-authenticated user (actor_type="api_key") must always bind the
new key to their db_user_id.  If user_id is None, validate_api_key treats
the key as a system key with ["system", "platform_admin"] roles.

This file tests the router-level user_id resolution logic to ensure
non-system callers can never create a system key.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.auth.models import CurrentUser


def _make_current_user(
    *,
    actor_type: str = "api_key",
    db_user_id=None,
    user_id: str = "kc-alice",
    roles: list[str] | None = None,
    tenant_id: str = "acme",
) -> CurrentUser:
    return CurrentUser(
        user_id=user_id,
        email="alice@acme.com",
        tenant_id=tenant_id,
        roles=roles or ["analyst"],
        actor_type=actor_type,
        db_user_id=db_user_id,
    )


class TestApiKeyCreationUserBinding:
    """Verify that create_api_key always binds user_id for non-system callers."""

    @pytest.mark.asyncio
    async def test_api_key_caller_binds_db_user_id(self):
        """API-key-authenticated caller must have their db_user_id bound to the new key."""
        db_user_uuid = uuid4()
        current_user = _make_current_user(
            actor_type="api_key",
            db_user_id=db_user_uuid,
        )

        mock_service = AsyncMock()
        mock_service.create_api_key.return_value = MagicMock(id=uuid4())

        from analysi.routers.api_keys import create_api_key
        from analysi.schemas.auth import CreateApiKeyRequest

        body = CreateApiKeyRequest(name="my-key")
        mock_session = AsyncMock()
        mock_request = MagicMock()
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.headers = {}
        mock_request.state.request_id = "test-request-id"

        with patch(
            "analysi.routers.api_keys._log_api_key_audit", new_callable=AsyncMock
        ):
            await create_api_key(
                tenant="acme",
                body=body,
                service=mock_service,
                current_user=current_user,
                session=mock_session,
                request=mock_request,
            )

        # The key must be created with user_id=db_user_uuid, NOT None
        call_kwargs = mock_service.create_api_key.call_args.kwargs
        assert call_kwargs["user_id"] == db_user_uuid, (
            "API-key caller must bind their db_user_id to the new key. "
            "user_id=None would create a system key (privilege escalation)."
        )

    @pytest.mark.asyncio
    async def test_api_key_caller_without_db_user_id_rejected(self):
        """API-key caller with no db_user_id must be rejected (cannot create orphan key)."""
        current_user = _make_current_user(
            actor_type="api_key",
            db_user_id=None,
        )

        mock_service = AsyncMock()

        from analysi.routers.api_keys import create_api_key
        from analysi.schemas.auth import CreateApiKeyRequest

        body = CreateApiKeyRequest(name="my-key")
        mock_session = AsyncMock()
        mock_request = MagicMock()
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.headers = {}

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await create_api_key(
                tenant="acme",
                body=body,
                service=mock_service,
                current_user=current_user,
                session=mock_session,
                request=mock_request,
            )

        assert exc_info.value.status_code == 403
        # Service should never be called
        mock_service.create_api_key.assert_not_called()

    @pytest.mark.asyncio
    async def test_jwt_user_binds_db_user_id(self):
        """JWT-authenticated user with db_user_id must bind it."""
        db_user_uuid = uuid4()
        current_user = _make_current_user(
            actor_type="user",
            db_user_id=db_user_uuid,
            user_id="kc-bob",
        )

        mock_service = AsyncMock()
        mock_service.create_api_key.return_value = MagicMock(id=uuid4())

        from analysi.routers.api_keys import create_api_key
        from analysi.schemas.auth import CreateApiKeyRequest

        body = CreateApiKeyRequest(name="jwt-key")
        mock_session = AsyncMock()
        mock_request = MagicMock()
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.headers = {}
        mock_request.state.request_id = "test-request-id"

        # Mock the UserRepository lookup for JWT users
        mock_db_user = MagicMock()
        mock_db_user.id = db_user_uuid
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_keycloak_id = AsyncMock(return_value=mock_db_user)

        with (
            patch(
                "analysi.routers.api_keys.UserRepository", return_value=mock_user_repo
            ),
            patch(
                "analysi.routers.api_keys._log_api_key_audit", new_callable=AsyncMock
            ),
        ):
            await create_api_key(
                tenant="acme",
                body=body,
                service=mock_service,
                current_user=current_user,
                session=mock_session,
                request=mock_request,
            )

        call_kwargs = mock_service.create_api_key.call_args.kwargs
        assert call_kwargs["user_id"] == db_user_uuid

    @pytest.mark.asyncio
    async def test_jwt_user_without_db_record_rejected(self):
        """JWT user whose keycloak_id doesn't resolve in DB must be rejected."""
        current_user = _make_current_user(
            actor_type="user",
            db_user_id=None,
            user_id="kc-ghost",
        )

        mock_service = AsyncMock()

        from analysi.routers.api_keys import create_api_key
        from analysi.schemas.auth import CreateApiKeyRequest

        body = CreateApiKeyRequest(name="ghost-key")
        mock_session = AsyncMock()
        mock_request = MagicMock()
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.headers = {}

        # UserRepository returns None (user not in DB)
        mock_user_repo = MagicMock()
        mock_user_repo.get_by_keycloak_id = AsyncMock(return_value=None)

        from fastapi import HTTPException

        with (
            patch(
                "analysi.routers.api_keys.UserRepository", return_value=mock_user_repo
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await create_api_key(
                tenant="acme",
                body=body,
                service=mock_service,
                current_user=current_user,
                session=mock_session,
                request=mock_request,
            )

        assert exc_info.value.status_code == 403
        mock_service.create_api_key.assert_not_called()

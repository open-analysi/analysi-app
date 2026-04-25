"""Unit tests for validate_api_key identity resolution.

Verifies that user-owned API keys produce a CurrentUser with db_user_id
set to the user's UUID (not None), so downstream identity propagation
(e.g., task generation → ARQ → MCP) attributes actions to the real user.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.auth.api_key import validate_api_key


def _make_api_key_row(*, user_id=None, tenant_id="acme", expired=False):
    """Create a mock ApiKey row."""
    row = MagicMock()
    row.id = uuid4()
    row.user_id = user_id
    row.tenant_id = tenant_id
    row.key_prefix = "ak_test1"
    if expired:
        row.expires_at = datetime.now(UTC) - timedelta(hours=1)
    else:
        row.expires_at = None
    return row


def _make_user_row(user_id=None, keycloak_id="kc-user-123", email="alice@acme.com"):
    """Create a mock User row."""
    row = MagicMock()
    row.id = user_id or uuid4()
    row.keycloak_id = keycloak_id
    row.email = email
    return row


def _make_membership_row(role="analyst"):
    """Create a mock Membership row."""
    row = MagicMock()
    row.role = role
    return row


def _mock_session_for_validate(api_key_row, user_row=None, membership_row=None):
    """Build a mock AsyncSession that returns the right rows for validate_api_key.

    validate_api_key does up to 3 queries in sequence:
    1. select(ApiKey) by key_hash
    2. select(User) by user_id (only for user-owned keys)
    3. select(Membership) by user_id + tenant_id (only for user-owned keys)
    """
    session = AsyncMock()
    results = []

    # Query 1: ApiKey lookup
    r1 = MagicMock()
    r1.scalar_one_or_none.return_value = api_key_row
    results.append(r1)

    if user_row is not None:
        # Query 2: User lookup
        r2 = MagicMock()
        r2.scalar_one_or_none.return_value = user_row
        results.append(r2)

        # Query 3: Membership lookup
        r3 = MagicMock()
        r3.scalar_one_or_none.return_value = membership_row
        results.append(r3)

    session.execute = AsyncMock(side_effect=results)
    return session


class TestValidateApiKeyIdentity:
    """Tests for db_user_id in validate_api_key results."""

    @pytest.mark.asyncio
    async def test_user_owned_key_sets_db_user_id(self):
        """User-owned API key must populate db_user_id with the user's UUID."""
        user_uuid = uuid4()
        user_row = _make_user_row(user_id=user_uuid)
        api_key_row = _make_api_key_row(user_id=user_uuid)
        membership_row = _make_membership_row(role="analyst")
        session = _mock_session_for_validate(api_key_row, user_row, membership_row)

        with patch("analysi.repositories.api_key_repository.ApiKeyRepository"):
            result = await validate_api_key("test-key-value", session)

        assert result is not None
        assert result.db_user_id == user_uuid, (
            "User-owned API key must set db_user_id to the user's UUID, "
            "not None (which causes fallback to SYSTEM_USER_ID downstream)"
        )

    @pytest.mark.asyncio
    async def test_system_key_has_no_db_user_id(self):
        """System API key should NOT have a db_user_id (no real user)."""
        api_key_row = _make_api_key_row(user_id=None)
        session = _mock_session_for_validate(api_key_row)

        with patch("analysi.repositories.api_key_repository.ApiKeyRepository"):
            result = await validate_api_key("sys-key-value", session)

        assert result is not None
        assert result.db_user_id is None

    @pytest.mark.asyncio
    async def test_user_owned_key_preserves_other_fields(self):
        """Verify actor_type, email, tenant, roles are correctly set."""
        user_uuid = uuid4()
        user_row = _make_user_row(
            user_id=user_uuid, keycloak_id="kc-bob", email="bob@acme.com"
        )
        api_key_row = _make_api_key_row(user_id=user_uuid, tenant_id="acme")
        membership_row = _make_membership_row(role="owner")
        session = _mock_session_for_validate(api_key_row, user_row, membership_row)

        with patch("analysi.repositories.api_key_repository.ApiKeyRepository"):
            result = await validate_api_key("test-key-value", session)

        assert result.actor_type == "api_key"
        assert result.email == "bob@acme.com"
        assert result.tenant_id == "acme"
        assert result.roles == ["owner", "platform_admin"]
        assert result.user_id == "kc-bob"

    @pytest.mark.asyncio
    async def test_owner_role_gets_platform_admin(self):
        """Owner API key must include platform_admin for /admin/v1/ access."""
        user_uuid = uuid4()
        user_row = _make_user_row(user_id=user_uuid)
        api_key_row = _make_api_key_row(user_id=user_uuid)
        membership_row = _make_membership_row(role="owner")
        session = _mock_session_for_validate(api_key_row, user_row, membership_row)

        with patch("analysi.repositories.api_key_repository.ApiKeyRepository"):
            result = await validate_api_key("owner-key-value", session)

        assert "owner" in result.roles
        assert "platform_admin" in result.roles

    @pytest.mark.asyncio
    async def test_analyst_role_does_not_get_platform_admin(self):
        """Non-owner roles must NOT receive platform_admin."""
        user_uuid = uuid4()
        user_row = _make_user_row(user_id=user_uuid)
        api_key_row = _make_api_key_row(user_id=user_uuid)
        membership_row = _make_membership_row(role="analyst")
        session = _mock_session_for_validate(api_key_row, user_row, membership_row)

        with patch("analysi.repositories.api_key_repository.ApiKeyRepository"):
            result = await validate_api_key("analyst-key-value", session)

        assert result.roles == ["analyst"]
        assert "platform_admin" not in result.roles

    @pytest.mark.asyncio
    async def test_system_key_does_not_get_platform_admin(self):
        """System keys must NOT receive platform_admin."""
        api_key_row = _make_api_key_row(user_id=None)
        session = _mock_session_for_validate(api_key_row)

        with patch("analysi.repositories.api_key_repository.ApiKeyRepository"):
            result = await validate_api_key("sys-key-value", session)

        assert result.roles == ["system"]
        assert "platform_admin" not in result.roles

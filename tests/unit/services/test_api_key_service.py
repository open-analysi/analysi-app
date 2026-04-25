"""Unit tests for ApiKeyService."""

import hashlib
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.models.auth import ApiKey
from analysi.schemas.auth import ApiKeyCreatedResponse, ApiKeyResponse
from analysi.services.api_key_service import _KEY_PREFIX_LENGTH, ApiKeyService


def _make_api_key(tenant_id: str = "acme", secret: str = "test-secret-abc") -> ApiKey:
    key = MagicMock(spec=ApiKey)
    key.id = uuid4()
    key.tenant_id = tenant_id
    key.user_id = uuid4()
    key.name = "My Key"
    key.key_hash = hashlib.sha256(secret.encode()).hexdigest()
    key.key_prefix = secret[:_KEY_PREFIX_LENGTH]
    key.scopes = []
    key.last_used_at = None
    key.expires_at = None
    from datetime import UTC, datetime

    key.created_at = datetime.now(UTC)
    return key


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    svc = ApiKeyService(mock_session)
    svc._api_keys = AsyncMock()
    return svc


class TestListApiKeys:
    @pytest.mark.asyncio
    async def test_list_api_keys_no_secret(self, service):
        key = _make_api_key()
        service._api_keys.list_by_tenant.return_value = [key]

        result = await service.list_api_keys("acme")

        assert len(result) == 1
        assert isinstance(result[0], ApiKeyResponse)
        assert not hasattr(result[0], "secret") or not isinstance(
            result[0], ApiKeyCreatedResponse
        )


class TestCreateApiKey:
    @pytest.mark.asyncio
    async def test_create_returns_secret_once(self, service):
        db_key = _make_api_key()
        service._api_keys.create.return_value = db_key

        result = await service.create_api_key(
            tenant_id="acme",
            name="My Key",
        )

        assert isinstance(result, ApiKeyCreatedResponse)
        assert result.secret  # non-empty

    @pytest.mark.asyncio
    async def test_create_stores_hash_not_plaintext(self, service):
        db_key = _make_api_key()
        service._api_keys.create.return_value = db_key

        result = await service.create_api_key(tenant_id="acme", name="My Key")

        create_kwargs = service._api_keys.create.call_args.kwargs
        expected_hash = hashlib.sha256(result.secret.encode()).hexdigest()
        assert create_kwargs["key_hash"] == expected_hash
        # plaintext secret not passed to repository
        assert "secret" not in create_kwargs

    @pytest.mark.asyncio
    async def test_create_prefix_matches_secret(self, service):
        db_key = _make_api_key()
        service._api_keys.create.return_value = db_key

        result = await service.create_api_key(tenant_id="acme", name="My Key")

        create_kwargs = service._api_keys.create.call_args.kwargs
        assert create_kwargs["key_prefix"] == result.secret[:_KEY_PREFIX_LENGTH]


class TestRevokeApiKey:
    @pytest.mark.asyncio
    async def test_revoke_returns_true_on_success(self, service):
        key = _make_api_key()
        service._api_keys.get_by_id.return_value = key
        service._api_keys.delete.return_value = True

        result = await service.revoke_api_key("acme", key.id)

        assert result is True
        service._api_keys.delete.assert_called_once_with(key.id)

    @pytest.mark.asyncio
    async def test_revoke_returns_false_when_not_found(self, service):
        service._api_keys.get_by_id.return_value = None

        result = await service.revoke_api_key("acme", uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_tenant_isolation(self, service):
        from fastapi import HTTPException

        key = _make_api_key(tenant_id="other-tenant")
        service._api_keys.get_by_id.return_value = key

        with pytest.raises(HTTPException) as exc_info:
            await service.revoke_api_key("acme", key.id)
        assert exc_info.value.status_code == 403

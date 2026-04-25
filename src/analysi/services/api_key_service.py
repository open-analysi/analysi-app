"""API key management service — creation, listing, and revocation.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)

Secrets are generated once via secrets.token_urlsafe(32) and stored only
as their SHA-256 hash. The plaintext is returned once on creation and
never retrievable again.
"""

import hashlib
import secrets
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.repositories.api_key_repository import ApiKeyRepository
from analysi.schemas.auth import ApiKeyCreatedResponse, ApiKeyResponse

logger = get_logger(__name__)

# How many characters of the key to store as a human-readable prefix.
_KEY_PREFIX_LENGTH = 8


def _generate_secret() -> str:
    """Generate a URL-safe API key secret with enough entropy."""
    return secrets.token_urlsafe(32)


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class ApiKeyService:
    """Business logic for API key management."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._api_keys = ApiKeyRepository(session)

    async def list_api_keys(self, tenant_id: str) -> list[ApiKeyResponse]:
        """Return all API keys for a tenant (secrets never included)."""
        keys = await self._api_keys.list_by_tenant(tenant_id)
        return [ApiKeyResponse.model_validate(k) for k in keys]

    async def create_api_key(
        self,
        tenant_id: str,
        name: str,
        user_id: UUID | None = None,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> ApiKeyCreatedResponse:
        """Create a new API key.

        Returns ApiKeyCreatedResponse which includes the plaintext secret.
        The secret is shown ONCE and cannot be retrieved again.
        """
        secret = _generate_secret()
        key_hash = _hash_secret(secret)
        key_prefix = secret[:_KEY_PREFIX_LENGTH]

        api_key = await self._api_keys.create(
            tenant_id=tenant_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            user_id=user_id,
            scopes=scopes or [],
            expires_at=expires_at,
        )

        logger.info(
            "api_key_created",
            key_id=str(api_key.id),
            tenant_id=tenant_id,
            name=name,
        )

        response_data = ApiKeyResponse.model_validate(api_key).model_dump()
        response_data["secret"] = secret
        return ApiKeyCreatedResponse(**response_data)

    async def revoke_api_key(
        self,
        tenant_id: str,
        key_id: UUID,
    ) -> bool:
        """Revoke an API key. Returns True if deleted, False if not found.

        Validates tenant ownership before deletion.
        """
        api_key = await self._api_keys.get_by_id(key_id)
        if api_key is None:
            return False

        if api_key.tenant_id != tenant_id:
            raise HTTPException(
                status_code=403,
                detail="API key does not belong to this tenant.",
            )

        deleted = await self._api_keys.delete(key_id)

        if deleted:
            logger.info(
                "api_key_revoked",
                key_id=str(key_id),
                tenant_id=tenant_id,
            )

        return deleted

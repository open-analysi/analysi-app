"""
Agent Credential Factory for retrieving agent OAuth tokens from integrations.

Similar to LangChainFactory but for agentic execution frameworks.
"""

import time
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.services.integration_service import IntegrationService
from analysi.services.vault_client import VaultClient

logger = get_logger(__name__)


class AgentCredentialFactory:
    """Factory for retrieving agent credentials from integrations."""

    # Class-level cache for credentials
    _credential_cache: ClassVar[dict[str, dict[str, Any]]] = {}
    _cache_timestamps: ClassVar[dict[str, float]] = {}
    MAX_CACHE_SIZE = 50
    CACHE_TTL_SECONDS = 30  # Same TTL as LangChainFactory

    def __init__(
        self,
        integration_service: IntegrationService,
        vault_client: VaultClient | None = None,
    ):
        """
        Initialize factory with integration service.

        Args:
            integration_service: Service for accessing integrations
            vault_client: Optional vault client for credential decryption
        """
        self.integration_service = integration_service
        self.vault_client = vault_client or VaultClient()

    async def get_agent_credentials(
        self,
        tenant_id: str,
        integration_type: str = "anthropic_agent",
        session: AsyncSession | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """
        Get agent credentials from integration.

        Looks for an integration of the specified type (default: anthropic_agent)
        and retrieves the OAuth token from Vault.

        Args:
            tenant_id: Tenant identifier
            integration_type: Integration type to look for
            session: Optional database session to reuse
            force_refresh: If True, bypass cache and fetch fresh credentials

        Returns:
            Dict with credentials and settings:
            {
                "oauth_token": "sk-ant-...",
                "settings": {"max_turns": 100, "permission_mode": "bypassPermissions"}
            }

        Raises:
            ValueError: If no integration of the specified type is configured
        """
        cache_key = f"{tenant_id}:{integration_type}"

        # Check cache unless force_refresh is set
        if not force_refresh:
            cached = self._get_cached_credentials(cache_key)
            if cached is not None:
                logger.debug("returning_cached_credentials_for", cache_key=cache_key)
                return cached

        # Get integrations of the specified type
        integrations = await self.integration_service.list_integrations(
            tenant_id=tenant_id,
            integration_type=integration_type,
        )

        if not integrations:
            raise ValueError(
                f"No {integration_type} integration configured for tenant {tenant_id}"
            )

        # Use first integration found
        integration = integrations[0]

        # Handle both IntegrationResponse objects and dicts
        if hasattr(integration, "integration_id"):
            integration_id = integration.integration_id
            settings = integration.settings or {}
        else:
            integration_id = integration.get("integration_id", "unknown")
            settings = integration.get("settings", {})

        # Get credentials from Vault
        credentials = await self._get_credentials(tenant_id, integration_id, session)

        # Validate oauth_token
        oauth_token = credentials.get("oauth_token", "")
        if not oauth_token:
            raise ValueError(
                f"oauth_token cannot be empty for integration {integration_id}"
            )

        result = {
            "oauth_token": oauth_token,
            "settings": {
                "max_turns": settings.get("max_turns", 100),
                "permission_mode": settings.get("permission_mode", "bypassPermissions"),
            },
        }

        # Cache the result
        self._cache_credentials(cache_key, result)

        return result

    async def get_credentials_by_id(
        self,
        tenant_id: str,
        integration_id: str,
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """
        Get credentials for a specific integration by ID.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier
            session: Optional database session

        Returns:
            Dict with credentials and settings

        Raises:
            ValueError: If integration not found
        """
        cache_key = f"{tenant_id}:{integration_id}"

        # Check cache
        cached = self._get_cached_credentials(cache_key)
        if cached is not None:
            logger.debug("returning_cached_credentials_for", cache_key=cache_key)
            return cached

        # Get specific integration
        integration = await self.integration_service.get_integration(
            tenant_id, integration_id
        )

        if not integration:
            raise ValueError(
                f"Integration {integration_id} not found for tenant {tenant_id}"
            )

        # Handle both IntegrationResponse objects and dicts
        if hasattr(integration, "settings"):
            settings = integration.settings or {}
        else:
            settings = integration.get("settings", {})

        # Get credentials from Vault
        credentials = await self._get_credentials(tenant_id, integration_id, session)

        # Validate oauth_token
        oauth_token = credentials.get("oauth_token", "")
        if not oauth_token:
            raise ValueError(
                f"oauth_token cannot be empty for integration {integration_id}"
            )

        result = {
            "oauth_token": oauth_token,
            "settings": {
                "max_turns": settings.get("max_turns", 100),
                "permission_mode": settings.get("permission_mode", "bypassPermissions"),
            },
        }

        # Cache the result
        self._cache_credentials(cache_key, result)

        return result

    async def _get_credentials(
        self,
        tenant_id: str,
        integration_id: str,
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """
        Get decrypted credentials for integration from Vault.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier
            session: Optional database session

        Returns:
            Decrypted credentials dictionary
        """
        from uuid import UUID

        from analysi.db.session import AsyncSessionLocal
        from analysi.services.credential_service import CredentialService

        # Use provided session or create a new one
        if session:
            credential_service = CredentialService(session)

            # Get credential metadata for this integration
            credential_metadata_list = (
                await credential_service.get_integration_credentials(
                    tenant_id, integration_id
                )
            )

            if not credential_metadata_list:
                raise ValueError(
                    f"No credentials found for integration {integration_id}"
                )

            # Get first credential
            credential_metadata = credential_metadata_list[0]
            credential_id = credential_metadata.get("id")

            if isinstance(credential_id, str):
                credential_id = UUID(credential_id)

            # Get actual credential data (requires tenant_id and credential_id)
            credential_data = await credential_service.get_credential(
                tenant_id, credential_id
            )
            return credential_data or {}
        # Create new session
        async with AsyncSessionLocal() as new_session:
            credential_service = CredentialService(new_session)

            # Get credential metadata for this integration
            credential_metadata_list = (
                await credential_service.get_integration_credentials(
                    tenant_id, integration_id
                )
            )

            if not credential_metadata_list:
                raise ValueError(
                    f"No credentials found for integration {integration_id}"
                )

            # Get first credential
            credential_metadata = credential_metadata_list[0]
            credential_id = credential_metadata.get("id")

            if isinstance(credential_id, str):
                credential_id = UUID(credential_id)

            # Get actual credential data (requires tenant_id and credential_id)
            credential_data = await credential_service.get_credential(
                tenant_id, credential_id
            )
            return credential_data or {}

    def _cache_credentials(self, cache_key: str, credentials: dict[str, Any]) -> None:
        """Cache credentials with TTL.

        Evicts oldest entry if cache is at max size.
        """
        # Evict oldest if at max size
        if len(self._credential_cache) >= self.MAX_CACHE_SIZE:
            oldest_key = min(
                self._cache_timestamps.keys(), key=lambda k: self._cache_timestamps[k]
            )
            del self._credential_cache[oldest_key]
            del self._cache_timestamps[oldest_key]

        self._credential_cache[cache_key] = credentials
        self._cache_timestamps[cache_key] = time.time()

    def _get_cached_credentials(self, cache_key: str) -> dict[str, Any] | None:
        """Get cached credentials if not expired."""
        if cache_key not in self._credential_cache:
            return None

        cached_time = self._cache_timestamps.get(cache_key, 0)
        if time.time() - cached_time > self.CACHE_TTL_SECONDS:
            # Cache expired - remove and return None
            del self._credential_cache[cache_key]
            del self._cache_timestamps[cache_key]
            return None

        return self._credential_cache[cache_key]

    @classmethod
    def clear_cache(cls, tenant_id: str | None = None) -> None:
        """Clear credential cache.

        Args:
            tenant_id: If provided, only clear entries for this tenant.
                      If None, clear entire cache.
        """
        if tenant_id is None:
            cls._credential_cache.clear()
            cls._cache_timestamps.clear()
        else:
            # Clear all entries for this tenant
            keys_to_remove = [
                k for k in cls._credential_cache if k.startswith(f"{tenant_id}:")
            ]
            for key in keys_to_remove:
                del cls._credential_cache[key]
                if key in cls._cache_timestamps:
                    del cls._cache_timestamps[key]

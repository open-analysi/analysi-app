"""
Splunk Factory for creating Splunk service instances from integration configurations.

This follows the same pattern as LangChainFactory for consistency.
"""

import time
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.schemas.integration import IntegrationResponse
from analysi.services.integration_service import IntegrationService
from analysi.services.vault_client import VaultClient

logger = get_logger(__name__)


class SplunkFactory:
    """Factory for creating Splunk service instances from integrations."""

    # Class-level cache for Splunk service instances
    _service_cache: ClassVar[dict[str, Any]] = {}
    _cache_settings: ClassVar[dict[str, dict]] = {}  # Track settings to detect changes
    _cache_timestamps: ClassVar[
        dict[str, float]
    ] = {}  # Track cache entry creation time
    MAX_CACHE_SIZE = 50  # Prevent memory leaks
    CACHE_TTL_SECONDS = 300  # 5 minutes TTL for Splunk connections

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

    async def get_primary_splunk_service(
        self, tenant_id: str, session: AsyncSession | None = None
    ) -> Any:
        """
        Get the primary Splunk service for a tenant with caching.

        Args:
            tenant_id: Tenant identifier
            session: Optional database session to reuse

        Returns:
            Configured Splunk service instance

        Raises:
            ValueError: If no Splunk integration found or configuration invalid
        """
        cache_key = f"splunk_{tenant_id}"

        # Check cache first
        if cache_key in self._service_cache:
            cache_time = self._cache_timestamps.get(cache_key, 0)
            if time.time() - cache_time < self.CACHE_TTL_SECONDS:
                logger.debug(
                    "using_cached_splunk_service_for_tenant", tenant_id=tenant_id
                )
                return self._service_cache[cache_key]

        # Get Splunk integration
        integrations = await self.integration_service.list_integrations(
            tenant_id, integration_type="splunk"
        )

        enabled_integrations = [
            integration
            for integration in integrations
            if integration.enabled and integration.integration_type == "splunk"
        ]

        if not enabled_integrations:
            raise ValueError(
                f"No enabled Splunk integration found for tenant {tenant_id}"
            )

        # Use the first enabled integration (can be enhanced to support multiple later)
        integration = enabled_integrations[0]

        # Create Splunk service
        service = await self.create_splunk_service(tenant_id, integration, session)

        # Cache the service
        self._cleanup_cache()
        self._service_cache[cache_key] = service
        self._cache_settings[cache_key] = integration.settings or {}
        self._cache_timestamps[cache_key] = time.time()

        return service

    async def create_splunk_service(
        self,
        tenant_id: str,
        integration: IntegrationResponse | dict,
        session: AsyncSession | None = None,
    ) -> Any:
        """
        Create Splunk service instance from integration configuration.

        Args:
            tenant_id: Tenant identifier
            integration: Integration configuration
            session: Optional database session to reuse

        Returns:
            Configured Splunk service instance

        Raises:
            ValueError: If integration configuration is invalid
            ImportError: If splunklib is not available
        """
        # Handle both IntegrationResponse and dict formats
        if isinstance(integration, IntegrationResponse):
            settings = integration.settings or {}
            integration_id = integration.integration_id
        elif isinstance(integration, dict):
            settings = integration.get("settings", {})
            integration_id = integration["integration_id"]
        else:
            raise ValueError(f"Unsupported integration type: {type(integration)}")

        # Get credentials (pass session if available)
        credentials = await self._get_credentials(tenant_id, integration_id, session)

        # Create Splunk service
        return self._create_splunk_service(settings, credentials)

    def _create_splunk_service(
        self, settings: dict[str, Any], credentials: dict[str, Any]
    ) -> Any:
        """
        Create Splunk service instance.

        Args:
            settings: Integration settings
            credentials: Decrypted credentials

        Returns:
            Splunk service instance

        Raises:
            ImportError: If splunklib is not available
            ValueError: If required configuration is missing
        """
        try:
            import splunklib.client as client
        except ImportError:
            raise ImportError(
                "Splunk Python SDK not available. Install with 'pip install splunk-sdk'"
            )

        # Get connection parameters with proper hierarchy
        # Priority: credentials > settings > environment variables
        host = settings.get("host")
        port = settings.get("port", 8089)
        app = settings.get("app", "search")
        scheme = settings.get("scheme", "https")

        # Get credentials with fallback to settings
        username = credentials.get("username") or settings.get("username")
        password = credentials.get("password") or settings.get("password")

        # Validate required parameters
        if not username:
            raise ValueError(
                "Splunk username not configured in credentials or settings"
            )
        if not password:
            raise ValueError(
                "Splunk password not configured in credentials or settings"
            )
        if not host:
            raise ValueError("Splunk host not configured in settings")

        logger.info(
            "creating_splunk_service_connection_to_for_user",
            host=host,
            port=port,
            username=username,
        )

        try:
            # Create Splunk service connection
            # For HTTPS connections, disable SSL verification for self-signed certs (like development)
            connection_kwargs = {
                "host": host,
                "port": port,
                "username": username,
                "password": password,
                "app": app,
                "autologin": True,
                "scheme": scheme,
            }

            # Disable SSL verification for development/test environments
            if scheme.lower() == "https":
                connection_kwargs["verify"] = False

            service = client.connect(**connection_kwargs)

            logger.info("successfully_connected_to_splunk_at", host=host, port=port)
            return service

        except Exception as e:
            error_msg = str(e).lower()

            # Provide specific error messages
            if "login failed" in error_msg or "authentication failed" in error_msg:
                raise ValueError(
                    f"Splunk authentication failed. "
                    f"Please verify username '{username}' and password are correct. "
                    f"Original error: {e!s}"
                )
            if (
                "connection refused" in error_msg
                or "network is unreachable" in error_msg
            ):
                raise ValueError(
                    f"Cannot reach Splunk server at {host}:{port}. "
                    f"Please verify host and port are correct and accessible. "
                    f"Original error: {e!s}"
                )
            if "ssl" in error_msg or "certificate" in error_msg:
                raise ValueError(
                    f"SSL/TLS connection error to {host}:{port}. "
                    f"Try setting scheme to 'http' or verify SSL certificates. "
                    f"Original error: {e!s}"
                )
            if "timeout" in error_msg:
                raise ValueError(
                    f"Connection timeout to Splunk server at {host}:{port}. "
                    f"Please check network connectivity. "
                    f"Original error: {e!s}"
                )
            raise ValueError(
                f"Failed to connect to Splunk at {host}:{port}. "
                f"Username: {username}, Scheme: {scheme}. "
                f"Original error: {e!s}"
            )

    async def _get_credentials(
        self, tenant_id: str, integration_id: str, session: AsyncSession | None = None
    ) -> dict[str, Any]:
        """
        Get decrypted credentials for integration with environment variable fallback.

        Working connectors likely fall back to environment variables when vault isn't available.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier (can be string or UUID)
            session: Optional database session to reuse

        Returns:
            Decrypted credentials dictionary
        """
        try:
            # First try the database/vault approach (if API server is available)
            from analysi.integrations.api_client import IntegrationAPIClient

            api_client = IntegrationAPIClient()
            integration_creds = await api_client.list_integration_credentials(
                tenant_id, integration_id
            )

            if integration_creds:
                # Find primary credential or first available
                primary_cred = None
                for cred_meta in integration_creds:
                    if cred_meta.get("is_primary", False):
                        primary_cred = cred_meta
                        break

                if not primary_cred and integration_creds:
                    primary_cred = integration_creds[0]

                if primary_cred:
                    from uuid import UUID

                    credential_id = UUID(primary_cred["id"])
                    credential_data = await api_client.get_credential(
                        tenant_id, credential_id
                    )
                    credentials = credential_data.get("secret", {})

                    if credentials:
                        logger.debug(
                            "successfully_retrieved_vault_credentials_for_integ",
                            integration_id=integration_id,
                        )
                        return credentials

        except Exception as e:
            # API client failed (expected if API server not running)
            logger.debug(
                "api_client_failed_for_integration",
                integration_id=integration_id,
                error=str(e),
            )

        # Fall back to environment variables like working connectors probably do
        from analysi.integrations.config import IntegrationConfig

        fallback_credentials = {}

        # Use environment variable defaults from IntegrationConfig
        if IntegrationConfig.SPLUNK_USERNAME:
            fallback_credentials["username"] = IntegrationConfig.SPLUNK_USERNAME
        if IntegrationConfig.SPLUNK_PASSWORD:
            fallback_credentials["password"] = IntegrationConfig.SPLUNK_PASSWORD

        if fallback_credentials:
            logger.info(
                "using_environment_variable_credentials_for_integra",
                integration_id=integration_id,
            )
            return fallback_credentials
        logger.warning(
            "no_vault_credentials_or_environment_variables_avai",
            integration_id=integration_id,
        )
        return {}

    def _cleanup_cache(self):
        """Clean up old cache entries to prevent memory leaks."""
        if len(self._service_cache) >= self.MAX_CACHE_SIZE:
            # Remove oldest entries
            current_time = time.time()
            old_keys = []
            for key, timestamp in self._cache_timestamps.items():
                if current_time - timestamp > self.CACHE_TTL_SECONDS:
                    old_keys.append(key)

            # Remove expired entries
            for key in old_keys[:10]:  # Remove up to 10 old entries
                self._service_cache.pop(key, None)
                self._cache_settings.pop(key, None)
                self._cache_timestamps.pop(key, None)

    def clear_cache(self):
        """Clear all cached Splunk services."""
        self._service_cache.clear()
        self._cache_settings.clear()
        self._cache_timestamps.clear()
        logger.info("Cleared Splunk service cache")

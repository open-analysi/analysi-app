"""
LangChain Factory for creating LLM instances from integration configurations.
"""

import time
from typing import Any, ClassVar

from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.schemas.integration import IntegrationResponse
from analysi.services.integration_service import IntegrationService
from analysi.services.vault_client import VaultClient

logger = get_logger(__name__)


class LangChainFactory:
    """Factory for creating LangChain LLM instances from integrations."""

    # Class-level cache for LLM instances
    _llm_cache: ClassVar[dict[str, Any]] = {}
    _cache_settings: ClassVar[dict[str, dict]] = {}  # Track settings to detect changes
    _cache_timestamps: ClassVar[
        dict[str, float]
    ] = {}  # Track cache entry creation time
    MAX_CACHE_SIZE = 100  # Prevent memory leaks
    CACHE_TTL_SECONDS = 30  # 30 seconds TTL - prevent back-to-back calls

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

    async def get_primary_llm(
        self, tenant_id: str, session: AsyncSession | None = None
    ) -> Any:
        """
        Get the primary LLM for a tenant with caching.

        Looks for an LLM integration marked as primary.

        Args:
            tenant_id: Tenant identifier
            session: Optional database session to reuse for credential retrieval

        Returns:
            LangChain LLM instance (cached)

        Raises:
            ValueError: If no primary LLM is configured
        """
        # Discover all AI-archetype integration types from the framework registry
        # (e.g. openai, gemini, anthropic_agent) — no hardcoded list.
        from analysi.integrations.framework.models import Archetype
        from analysi.integrations.framework.registry import get_registry

        ai_types = [m.id for m in get_registry().list_by_archetype(Archetype.AI)]

        integrations: list[Any] = []
        for ai_type in ai_types:
            integrations.extend(
                await self.integration_service.list_integrations(
                    tenant_id=tenant_id,
                    integration_type=ai_type,
                )
            )

        # Find primary integration
        primary_integration = None
        for integration in integrations:
            # Handle both IntegrationResponse objects and dicts (for testing compatibility)
            if hasattr(integration, "integration_type") and hasattr(
                integration, "settings"
            ):
                # IntegrationResponse object
                settings = integration.settings or {}
            else:
                # Dict (from mocks/tests)
                settings = (
                    integration.get("settings", {})
                    if isinstance(integration, dict)
                    else {}
                )

            if settings.get("is_primary", False):
                primary_integration = integration
                break

        # If no primary marked, use first available
        if not primary_integration and integrations:
            primary_integration = integrations[0]
            if hasattr(primary_integration, "integration_id"):
                integration_id = primary_integration.integration_id
            else:
                integration_id = (
                    primary_integration.get("integration_id", "unknown")
                    if isinstance(primary_integration, dict)
                    else "unknown"
                )
            logger.warning(
                "no_primary_llm_integration_marked",
                tenant_id=tenant_id,
                fallback_integration_id=integration_id,
            )

        if not primary_integration:
            raise ValueError(
                f"No LLM integrations configured for tenant {tenant_id}. "
                f"Please configure an AI integration ({', '.join(sorted(ai_types))}) "
                "via the integrations API."
            )

        # Create cache key - handle both object types
        if hasattr(primary_integration, "integration_id"):
            integration_id = primary_integration.integration_id
        else:
            integration_id = (
                primary_integration.get("integration_id", "unknown")
                if isinstance(primary_integration, dict)
                else "unknown"
            )
        cache_key = f"{tenant_id}:{integration_id}"

        # Check cache with TTL validation (lazy expiration)
        if cache_key in self._llm_cache:
            cache_age = time.time() - self._cache_timestamps.get(cache_key, 0)

            if cache_age < self.CACHE_TTL_SECONDS:
                # Cache is fresh, return immediately without DB calls
                logger.debug(
                    "returning_cached_llm",
                    cache_key=cache_key,
                    cache_age_seconds=round(cache_age, 1),
                )
                return self._llm_cache[cache_key]
            # Cache expired, invalidate and recreate
            logger.info(
                "llm_cache_expired",
                cache_key=cache_key,
                cache_age_seconds=round(cache_age, 1),
            )
            self._invalidate_cache_entry(cache_key)

        # Create LLM from integration (pass session if available)
        llm = await self._create_llm_from_integration(
            tenant_id, primary_integration, session
        )

        # Cache the instance - handle both object types
        if hasattr(primary_integration, "settings"):
            settings = primary_integration.settings or {}
        else:
            settings = (
                primary_integration.get("settings", {})
                if isinstance(primary_integration, dict)
                else {}
            )
        self._cache_llm(cache_key, llm, settings)

        return llm

    async def get_llm_by_id(
        self, tenant_id: str, integration_id: str, session: AsyncSession | None = None
    ) -> Any:
        """
        Get a specific LLM by integration ID with caching.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier
            session: Optional database session to reuse for credential retrieval

        Returns:
            LangChain LLM instance (cached)

        Raises:
            ValueError: If integration not found
        """
        # Create cache key
        cache_key = f"{tenant_id}:{integration_id}"

        # Check cache with TTL validation (lazy expiration)
        if cache_key in self._llm_cache:
            cache_age = time.time() - self._cache_timestamps.get(cache_key, 0)

            if cache_age < self.CACHE_TTL_SECONDS:
                # Cache is fresh, return immediately without DB calls
                logger.debug(
                    "returning_cached_llm",
                    cache_key=cache_key,
                    cache_age_seconds=round(cache_age, 1),
                )
                return self._llm_cache[cache_key]
            # Cache expired, invalidate and recreate
            logger.info(
                "llm_cache_expired",
                cache_key=cache_key,
                cache_age_seconds=round(cache_age, 1),
            )
            self._invalidate_cache_entry(cache_key)

        # Get fresh integration
        integration = await self.integration_service.get_integration(
            tenant_id, integration_id
        )

        if not integration:
            raise ValueError(
                f"Integration {integration_id} not found for tenant {tenant_id}"
            )

        # Create new LLM instance (pass session if available)
        llm = await self._create_llm_from_integration(tenant_id, integration, session)

        # Cache it - handle both object types
        if hasattr(integration, "settings"):
            settings = integration.settings or {}
        else:
            settings = (
                integration.get("settings", {}) if isinstance(integration, dict) else {}
            )
        self._cache_llm(cache_key, llm, settings)

        return llm

    async def _create_llm_from_integration(
        self,
        tenant_id: str,
        integration: IntegrationResponse | dict[str, Any],
        session: AsyncSession | None = None,
    ) -> Any:
        """
        Create LLM instance from integration configuration.

        Args:
            tenant_id: Tenant identifier
            integration: Integration data
            session: Optional database session to reuse

        Returns:
            LangChain LLM instance
        """
        # Handle both IntegrationResponse objects and dicts (for testing compatibility)
        if hasattr(integration, "integration_type") and hasattr(
            integration, "integration_id"
        ):
            # IntegrationResponse object - mypy type guard
            assert isinstance(integration, IntegrationResponse), (
                "Expected IntegrationResponse object"
            )
            integration_type = integration.integration_type
            settings = integration.settings or {}
            integration_id = integration.integration_id
        elif isinstance(integration, dict):
            # Dict (from mocks/tests) - mypy type guard
            integration_type = integration["integration_type"]
            settings = integration.get("settings", {})
            integration_id = integration["integration_id"]
        else:
            raise ValueError(f"Unsupported integration type: {type(integration)}")

        # Get credentials (pass session if available)
        credentials = await self._get_credentials(tenant_id, integration_id, session)

        # Dispatch to provider-specific factory method.
        # To add a new AI provider: register its manifest with the AI archetype
        # and add a _create_<type>_llm method + entry here.
        provider_factories = {
            "openai": self._create_openai_llm,
            "gemini": self._create_gemini_llm,
            "anthropic_agent": self._create_anthropic_llm,
        }
        factory_fn = provider_factories.get(integration_type)
        if not factory_fn:
            raise ValueError(f"Unsupported LLM integration type: {integration_type}")
        return factory_fn(settings, credentials)

    def _create_openai_llm(
        self, settings: dict[str, Any], credentials: dict[str, Any]
    ) -> ChatOpenAI | AzureChatOpenAI:
        """
        Create OpenAI LLM instance.

        Args:
            settings: Integration settings
            credentials: Decrypted credentials

        Returns:
            ChatOpenAI instance
        """
        api_key = credentials.get("api_key")
        if not api_key:
            raise ValueError("Missing API key in OpenAI credentials")

        # Get settings with defaults
        model = settings.get("model", "gpt-4o-mini")
        temperature = settings.get("temperature", 0.7)
        max_tokens = settings.get("max_tokens", 4096)
        api_url = settings.get("api_url", "https://api.openai.com/v1")

        # Check if this is Azure OpenAI (by URL pattern)
        if "azure" in api_url.lower():
            # Azure OpenAI uses different initialization
            # Extract deployment name from model or settings
            deployment = settings.get("deployment_name", model)
            azure_endpoint = api_url.rstrip("/v1")  # Remove /v1 suffix

            logger.info(
                "creating_azure_openai_llm",
                deployment=deployment,
                endpoint=azure_endpoint,
            )

            return AzureChatOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=SecretStr(api_key) if api_key else None,
                api_version=settings.get("api_version", "2024-02-01"),
                azure_deployment=deployment,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        # Standard OpenAI
        logger.info(
            "creating_openai_llm",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Handle custom base URL
        if api_url != "https://api.openai.com/v1":
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,  # type: ignore
                api_key=SecretStr(api_key) if api_key else None,
                base_url=api_url,
            )
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,  # type: ignore
            api_key=SecretStr(api_key) if api_key else None,
        )

    def _create_gemini_llm(
        self, settings: dict[str, Any], credentials: dict[str, Any]
    ) -> ChatGoogleGenerativeAI:
        """
        Create Google Gemini LLM instance.

        Args:
            settings: Integration settings
            credentials: Decrypted credentials

        Returns:
            ChatGoogleGenerativeAI instance
        """
        api_key = credentials.get("api_key")
        if not api_key:
            raise ValueError("Missing API key in Gemini credentials")

        model = settings.get("model", "gemini-2.0-flash")
        temperature = settings.get("temperature", 0.7)
        max_tokens = settings.get("max_tokens", 4096)

        logger.info(
            "creating_gemini_llm",
            model=model,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            max_output_tokens=max_tokens,
            google_api_key=SecretStr(api_key),
        )

    def _create_anthropic_llm(
        self, settings: dict[str, Any], credentials: dict[str, Any]
    ) -> ChatAnthropic:
        """
        Create Anthropic (Claude) LLM instance.

        Reads the default model from model_presets.default.model (Anthropic manifest
        convention) and falls back to a sensible default.

        Args:
            settings: Integration settings (may include model_presets)
            credentials: Decrypted credentials

        Returns:
            ChatAnthropic instance
        """
        api_key = credentials.get("api_key")
        if not api_key:
            raise ValueError("Missing API key in Anthropic credentials")

        # Anthropic integration stores model config in model_presets
        model_presets = settings.get("model_presets", {})
        default_preset = model_presets.get("default", {}) or {}
        model = default_preset.get("model") or settings.get(
            "model", "claude-sonnet-4-20250514"
        )
        temperature = settings.get("temperature", 0.7)
        max_tokens = settings.get("max_tokens", 4096)

        logger.info(
            "creating_anthropic_llm",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=SecretStr(api_key),
        )

    async def _get_credentials(
        self, tenant_id: str, integration_id: str, session: AsyncSession | None = None
    ) -> dict[str, Any]:
        """
        Get decrypted credentials for integration.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier
            session: Optional database session to reuse

        Returns:
            Decrypted credentials dictionary
        """
        # Get credentials using credential service
        from uuid import UUID

        from analysi.db.session import AsyncSessionLocal
        from analysi.services.credential_service import CredentialService

        # Use provided session or create a new one
        if session:
            # Use provided session directly
            credential_service = CredentialService(session)

            # Get credential metadata for this integration
            credential_metadata_list = (
                await credential_service.get_integration_credentials(
                    tenant_id, integration_id
                )
            )

            if not credential_metadata_list:
                raise ValueError(
                    f"No credentials configured for integration {integration_id}"
                )

            # For LLM integrations, we expect exactly one credential
            # Use the first (and typically only) credential
            credential_metadata = credential_metadata_list[0]
            credential_id = UUID(credential_metadata["id"])

            # Get the actual decrypted credential data
            credential_data = await credential_service.get_credential(
                tenant_id, credential_id
            )

            if not credential_data:
                raise ValueError(
                    f"Failed to retrieve credential data for integration {integration_id}"
                )

            # The credential_data is already the decrypted secrets dictionary
            if not isinstance(credential_data, dict):
                raise ValueError(
                    f"Invalid credential data format for integration {integration_id}"
                )

            return credential_data
        # Create a new session for credential operations
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
                    f"No credentials configured for integration {integration_id}"
                )

            # For LLM integrations, we expect exactly one credential
            # Use the first (and typically only) credential
            credential_metadata = credential_metadata_list[0]
            credential_id = UUID(credential_metadata["id"])

            # Get the actual decrypted credential data
            credential_data = await credential_service.get_credential(
                tenant_id, credential_id
            )

            if not credential_data:
                raise ValueError(
                    f"Failed to retrieve credential data for integration {integration_id}"
                )

            # The credential_data is already the decrypted secrets dictionary
            if not isinstance(credential_data, dict):
                raise ValueError(
                    f"Invalid credential data format for integration {integration_id}"
                )

            return credential_data

    def _cache_llm(self, cache_key: str, llm: Any, settings: dict[str, Any]) -> None:
        """
        Cache an LLM instance with its settings and timestamp.

        Args:
            cache_key: Cache key (tenant_id:integration_id)
            llm: LLM instance to cache
            settings: Integration settings for change detection
        """
        # Check cache size limit
        if len(self._llm_cache) >= self.MAX_CACHE_SIZE:
            # Remove oldest entry based on timestamp
            oldest_key = min(self._cache_timestamps, key=self._cache_timestamps.get)  # type: ignore
            self._invalidate_cache_entry(oldest_key)
            logger.warning("cache_size_limit_reached_evicted", oldest_key=oldest_key)

        # Store in cache with timestamp
        current_time = time.time()
        self._llm_cache[cache_key] = llm
        self._cache_settings[cache_key] = settings.copy()
        self._cache_timestamps[cache_key] = current_time
        logger.debug(
            "cached_llm_for_at", cache_key=cache_key, current_time=current_time
        )

    def _invalidate_cache_entry(self, cache_key: str) -> None:
        """
        Invalidate a specific cache entry.

        Args:
            cache_key: Cache key to invalidate
        """
        if cache_key in self._llm_cache:
            del self._llm_cache[cache_key]
        if cache_key in self._cache_settings:
            del self._cache_settings[cache_key]
        if cache_key in self._cache_timestamps:
            del self._cache_timestamps[cache_key]
        logger.debug("invalidated_cache_for", cache_key=cache_key)

    @classmethod
    def clear_cache(cls, tenant_id: str | None = None) -> None:
        """
        Clear LLM cache.

        Args:
            tenant_id: Optional tenant ID to clear specific tenant's cache.
                      If None, clears entire cache.
        """
        if tenant_id:
            # Clear specific tenant's cache entries
            keys_to_remove = [
                key for key in cls._llm_cache if key.startswith(f"{tenant_id}:")
            ]
            for key in keys_to_remove:
                if key in cls._llm_cache:
                    del cls._llm_cache[key]
                if key in cls._cache_settings:
                    del cls._cache_settings[key]
                if key in cls._cache_timestamps:
                    del cls._cache_timestamps[key]
            logger.info(
                "cleared_tenant_llm_cache",
                tenant_id=tenant_id,
                entries_removed=len(keys_to_remove),
            )
        else:
            # Clear all cache
            cls._llm_cache.clear()
            cls._cache_settings.clear()
            cls._cache_timestamps.clear()
            logger.info("cleared_entire_llm_cache")

    @classmethod
    def cleanup_expired_entries(cls) -> int:
        """
        Remove expired cache entries (lazy cleanup).

        Returns:
            Number of entries removed
        """
        current_time = time.time()
        expired_keys = [
            key
            for key, timestamp in cls._cache_timestamps.items()
            if current_time - timestamp >= cls.CACHE_TTL_SECONDS
        ]

        for key in expired_keys:
            if key in cls._llm_cache:
                del cls._llm_cache[key]
            if key in cls._cache_settings:
                del cls._cache_settings[key]
            if key in cls._cache_timestamps:
                del cls._cache_timestamps[key]

        if expired_keys:
            logger.info(
                "cleaned_up_expired_cache_entries", expired_keys_count=len(expired_keys)
            )

        return len(expired_keys)

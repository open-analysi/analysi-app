"""Chat model resolver — bridges AI archetype to Pydantic AI Model object.

Resolves the tenant's AI integration to a Pydantic AI Model instance with
credentials from Vault. This ensures the chatbot's LLM calls go through
the integrations framework (credentials, model selection) rather than
relying on environment variables.
"""

from typing import Any

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google_gla import GoogleGLAProvider
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.integrations.framework.base_ai import resolve_model_config
from analysi.integrations.framework.models import Archetype
from analysi.integrations.framework.registry import get_registry
from analysi.repositories.integration_repository import IntegrationRepository
from analysi.services.credential_service import CredentialService

logger = get_logger(__name__)


def _get_provider_type(integration_id: str) -> str:
    """Map integration app ID to provider type."""
    mapping = {
        "openai": "openai",
        "anthropic": "anthropic",
        "anthropic_agent": "anthropic",
        "gemini": "google",
        "google": "google",
    }
    return mapping.get(integration_id, integration_id)


async def _fetch_api_key_for_integration(
    tenant_id: str,
    integration: Any,
    session: AsyncSession,
) -> str:
    """Fetch the API key for an already-resolved integration from Vault.

    Avoids a redundant DB query by accepting the integration object directly
    (the caller already looked it up).

    Args:
        tenant_id: Tenant scope.
        integration: Integration row object (has .integration_id).
        session: Active DB session for credential lookup.

    Returns:
        The decrypted API key string.

    Raises:
        ValueError: If no credentials are configured or api_key is missing.
    """
    from uuid import UUID

    target_id = (
        integration.integration_id
        if hasattr(integration, "integration_id")
        else integration.get("integration_id")
    )

    credential_service = CredentialService(session)
    credential_metadata_list = await credential_service.get_integration_credentials(
        tenant_id, target_id
    )

    if not credential_metadata_list:
        raise ValueError(
            f"No credentials configured for integration '{target_id}'. "
            "Add API key credentials via the integrations API."
        )

    credential_id = UUID(credential_metadata_list[0]["id"])
    credential_data = await credential_service.get_credential(tenant_id, credential_id)

    if not credential_data or not isinstance(credential_data, dict):
        raise ValueError(
            f"Failed to retrieve credentials for integration '{target_id}'"
        )

    api_key = credential_data.get("api_key")
    if not api_key:
        raise ValueError(
            f"No 'api_key' found in credentials for integration '{target_id}'"
        )

    return api_key


def _build_model(
    provider_type: str,
    model_name: str,
    api_key: str,
) -> Model:
    """Build a Pydantic AI Model instance with explicit credentials.

    Args:
        provider_type: One of "openai", "anthropic", "google".
        model_name: The model identifier (e.g., "claude-sonnet-4-20250514").
        api_key: Decrypted API key from Vault.

    Returns:
        A Pydantic AI Model ready for use with Agent.
    """
    if provider_type == "anthropic":
        provider = AnthropicProvider(api_key=api_key)
        return AnthropicModel(model_name, provider=provider)
    if provider_type == "openai":
        provider = OpenAIProvider(api_key=api_key)
        return OpenAIChatModel(model_name, provider=provider)
    if provider_type == "google":
        from pydantic_ai.models.google import GoogleModel

        provider = GoogleGLAProvider(api_key=api_key)
        return GoogleModel(model_name, provider=provider)
    raise ValueError(f"Unsupported AI provider type: '{provider_type}'")


async def resolve_chat_model(
    tenant_id: str,
    session: AsyncSession,
    capability: str = "default",
) -> tuple[Model, dict[str, Any]]:
    """Resolve AI integration to a Pydantic AI Model + settings.

    Discovers AI integrations dynamically from the archetype registry
    (no hardcoded list). Picks the tenant's primary AI integration first,
    then falls back by manifest priority. If one provider's credentials
    are broken, tries the next rather than failing outright.

    Args:
        tenant_id: Tenant scope for credential lookup.
        session: Active DB session.
        capability: Model capability preset (default, thinking, fast, etc.).

    Returns:
        Tuple of (Model, model_settings) where:
          - Model: Pydantic AI Model instance with credentials wired in.
          - model_settings: Provider-specific params, e.g. {"temperature": 0.7}

    Raises:
        ValueError: If no AI provider is configured or credentials are missing.
    """
    integration_repo = IntegrationRepository(session)
    registry = get_registry()

    # Dynamic discovery: all integration types with the AI archetype,
    # sorted by manifest priority (highest first — list, not set)
    ai_manifests = registry.list_by_archetype(Archetype.AI)
    ai_types = [m.id for m in ai_manifests]

    # Collect all tenant AI integrations across all types, preserving
    # priority order. Primary integration (is_primary=True) goes first.
    candidates: list[tuple[str, Any]] = []  # (integration_type, integration)
    for int_type in ai_types:
        integrations = await integration_repo.list_integrations(
            tenant_id=tenant_id,
            integration_type=int_type,
        )
        for integration in integrations:
            candidates.append((int_type, integration))

    if not candidates:
        raise ValueError("No AI provider configured. Set up an AI integration first.")

    # Sort: is_primary first, then preserve the manifest-priority order
    def _sort_key(item: tuple[str, Any]) -> tuple[int, int]:
        _, integration = item
        settings = getattr(integration, "settings", None) or {}
        is_primary = 1 if settings.get("is_primary") else 0
        return (-is_primary, 0)  # primary first, then insertion order

    candidates.sort(key=_sort_key)

    # Try each candidate — skip providers with broken credentials/config
    last_error: str | None = None
    for found_type, found_integration in candidates:
        try:
            model, config = await _resolve_single_integration(
                registry, found_type, found_integration, tenant_id, session, capability
            )
            return model, config
        except ValueError as exc:
            integration_id = getattr(found_integration, "integration_id", found_type)
            logger.warning(
                "chat_model_candidate_skipped",
                integration_id=integration_id,
                integration_type=found_type,
                reason=str(exc)[:200],
            )
            last_error = str(exc)

    # All candidates failed — raise with the last error for diagnostics
    raise ValueError(
        last_error or "No AI provider configured. Set up an AI integration first."
    )


async def _resolve_single_integration(
    registry: Any,
    found_type: str,
    found_integration: Any,
    tenant_id: str,
    session: AsyncSession,
    capability: str,
) -> tuple[Model, dict[str, Any]]:
    """Try to resolve a single AI integration into a usable Model.

    Raises ValueError if this integration can't be used (missing credentials,
    missing model config, etc.).
    """
    # Get the manifest for this integration type
    manifest = registry.get_integration(found_type)
    if manifest is None:
        raise ValueError(f"No manifest found for integration type '{found_type}'")

    # Resolve the model config — merge manifest defaults with tenant overrides
    tenant_settings = getattr(found_integration, "settings", None)
    config = resolve_model_config(
        manifest, capability, settings_overrides=tenant_settings
    )

    model_name = config.pop("model", None)
    if model_name is None:
        raise ValueError(
            f"AI provider '{found_type}' has no model configured "
            f"for capability '{capability}'"
        )

    # Sanitize model settings — only allow known-safe keys.
    # Tenant settings_overrides could inject dangerous params
    # (extra_body, extra_headers, timeout) if not filtered.
    _ALLOWED_SETTINGS = {
        "temperature",
        "max_tokens",
        "top_p",
        "stop_sequences",
        "extended_thinking",
        "max_thinking_tokens",
    }
    _MAX_TOKENS_CEILING = 16384
    _MAX_TOKENS_DEFAULT = 4096
    config = {k: v for k, v in config.items() if k in _ALLOWED_SETTINGS}
    if "max_tokens" in config and isinstance(config["max_tokens"], int):
        config["max_tokens"] = min(config["max_tokens"], _MAX_TOKENS_CEILING)
    else:
        # Always set a default — prevents unbounded LLM output
        config["max_tokens"] = _MAX_TOKENS_DEFAULT

    # Fetch credentials from Vault
    provider_type = _get_provider_type(found_type)
    api_key = await _fetch_api_key_for_integration(
        tenant_id, found_integration, session
    )
    model = _build_model(provider_type, model_name, api_key)

    logger.info(
        "chat_model_resolved",
        provider=found_type,
        provider_type=provider_type,
        capability=capability,
        model_name=model_name,
        extra_settings=list(config.keys()) if config else [],
    )

    return model, config

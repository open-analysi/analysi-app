"""Unit tests for chat model resolver (AI archetype to Pydantic AI Model).

Project Rhodes — validates that resolve_chat_model() builds a Pydantic AI
Model object with credentials from the integrations framework, not env vars.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.integrations.framework.models import IntegrationManifest
from analysi.services.chat_model_resolver import (
    _build_model,
    _get_provider_type,
    resolve_chat_model,
)


def _make_manifest(
    integration_id: str = "openai",
    app: str = "openai",
    model_presets: dict[str, Any] | None = None,
) -> IntegrationManifest:
    """Build a minimal IntegrationManifest for testing."""
    settings_schema: dict[str, Any] = {"type": "object", "properties": {}}
    if model_presets is not None:
        settings_schema["properties"]["model_presets"] = {
            "type": "object",
            "default": model_presets,
        }
    return IntegrationManifest(
        id=integration_id,
        app=app,
        name="Test AI",
        version="1.0.0",
        archetypes=["AI"],
        priority=80,
        archetype_mappings={"AI": {"llm_run": "llm_run"}},
        actions=[{"id": "llm_run", "type": "tool"}],
        settings_schema=settings_schema,
    )


def _mock_integration(
    integration_type: str = "openai",
    is_primary: bool = False,
    integration_id: str | None = None,
):
    """Build a mock Integration DB model."""
    mock = MagicMock()
    mock.integration_id = integration_id or f"{integration_type}-test"
    mock.integration_type = integration_type
    mock.settings = {"is_primary": True} if is_primary else {}
    return mock


class TestGetProviderType:
    """Tests for _get_provider_type()."""

    def test_openai(self):
        assert _get_provider_type("openai") == "openai"

    def test_anthropic(self):
        assert _get_provider_type("anthropic") == "anthropic"

    def test_anthropic_agent(self):
        assert _get_provider_type("anthropic_agent") == "anthropic"

    def test_gemini(self):
        assert _get_provider_type("gemini") == "google"

    def test_unknown_passes_through(self):
        assert _get_provider_type("custom_provider") == "custom_provider"


class TestBuildModel:
    """Tests for _build_model() — creates Pydantic AI Model with explicit API key."""

    def test_anthropic_model(self):
        model = _build_model("anthropic", "claude-sonnet-4-20250514", "sk-test-key")
        assert model.model_name == "claude-sonnet-4-20250514"

    def test_openai_model(self):
        model = _build_model("openai", "gpt-4o", "sk-test-key")
        assert model.model_name == "gpt-4o"

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported AI provider"):
            _build_model("unknown_provider", "some-model", "key")


class TestResolveChatModel:
    """Tests for resolve_chat_model() — finds tenant's AI integration in DB."""

    @patch("analysi.services.chat_model_resolver._fetch_api_key_for_integration")
    @patch("analysi.services.chat_model_resolver.get_registry")
    @patch("analysi.services.chat_model_resolver.IntegrationRepository")
    @pytest.mark.anyio
    async def test_resolve_finds_tenant_integration_in_db(
        self, mock_repo_cls, mock_get_registry, mock_fetch_key
    ):
        """Happy path: finds openai integration in DB, uses its manifest."""
        mock_integration = _mock_integration("openai")

        # DB has an openai integration for this tenant
        mock_repo = AsyncMock()
        mock_repo.list_integrations = AsyncMock(
            side_effect=lambda **kw: (
                [mock_integration] if kw.get("integration_type") == "openai" else []
            )
        )
        mock_repo_cls.return_value = mock_repo

        # Registry has the openai manifest and lists it under AI archetype
        manifest = _make_manifest(
            integration_id="openai",
            model_presets={"default": {"model": "gpt-4o"}},
        )
        registry = MagicMock()
        registry.get_integration.return_value = manifest
        registry.list_by_archetype.return_value = [manifest]
        mock_get_registry.return_value = registry

        mock_fetch_key.return_value = "sk-test-key"

        session = AsyncMock()
        model, settings = await resolve_chat_model(tenant_id="default", session=session)

        assert model.model_name == "gpt-4o"
        # max_tokens is always set as a default (4096) when not in manifest
        assert settings == {"max_tokens": 4096}
        mock_fetch_key.assert_awaited_once_with("default", mock_integration, session)

    @patch("analysi.services.chat_model_resolver.get_registry")
    @patch("analysi.services.chat_model_resolver.IntegrationRepository")
    @pytest.mark.anyio
    async def test_no_integration_in_db_raises(self, mock_repo_cls, mock_get_registry):
        """No AI integrations in DB raises ValueError."""
        mock_repo = AsyncMock()
        mock_repo.list_integrations = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        # Registry lists AI manifests but tenant has none configured
        registry = MagicMock()
        registry.list_by_archetype.return_value = [_make_manifest()]
        mock_get_registry.return_value = registry

        session = AsyncMock()
        with pytest.raises(ValueError, match="No AI provider configured"):
            await resolve_chat_model(tenant_id="default", session=session)

    @patch("analysi.services.chat_model_resolver._fetch_api_key_for_integration")
    @patch("analysi.services.chat_model_resolver.get_registry")
    @patch("analysi.services.chat_model_resolver.IntegrationRepository")
    @pytest.mark.anyio
    async def test_extra_settings_passed_through(
        self, mock_repo_cls, mock_get_registry, mock_fetch_key
    ):
        """Provider-specific settings like extended_thinking are returned."""
        mock_integration = _mock_integration("anthropic_agent")

        mock_repo = AsyncMock()
        mock_repo.list_integrations = AsyncMock(
            side_effect=lambda **kw: (
                [mock_integration]
                if kw.get("integration_type") == "anthropic_agent"
                else []
            )
        )
        mock_repo_cls.return_value = mock_repo

        manifest = _make_manifest(
            integration_id="anthropic_agent",
            app="anthropic_agent",
            model_presets={
                "default": {"model": "claude-sonnet-4-20250514"},
                "thinking": {
                    "model": "claude-sonnet-4-20250514",
                    "extended_thinking": True,
                    "max_thinking_tokens": 10000,
                },
            },
        )
        registry = MagicMock()
        registry.get_integration.return_value = manifest
        registry.list_by_archetype.return_value = [manifest]
        mock_get_registry.return_value = registry

        mock_fetch_key.return_value = "sk-ant-test-key"

        session = AsyncMock()
        model, settings = await resolve_chat_model(
            tenant_id="default", session=session, capability="thinking"
        )

        assert model.model_name == "claude-sonnet-4-20250514"
        assert settings["extended_thinking"] is True
        assert settings["max_thinking_tokens"] == 10000

    @patch("analysi.services.chat_model_resolver._fetch_api_key_for_integration")
    @patch("analysi.services.chat_model_resolver.get_registry")
    @patch("analysi.services.chat_model_resolver.IntegrationRepository")
    @pytest.mark.anyio
    async def test_fallback_when_first_provider_credentials_broken(
        self, mock_repo_cls, mock_get_registry, mock_fetch_key
    ):
        """When the first provider's credentials fail, falls back to the next."""
        # anthropic_agent has priority 90, openai has priority 80
        anthropic_integration = _mock_integration("anthropic_agent")
        openai_integration = _mock_integration("openai")

        mock_repo = AsyncMock()

        async def _list_integrations(**kw):
            t = kw.get("integration_type")
            if t == "anthropic_agent":
                return [anthropic_integration]
            if t == "openai":
                return [openai_integration]
            return []

        mock_repo.list_integrations = AsyncMock(side_effect=_list_integrations)
        mock_repo_cls.return_value = mock_repo

        anthropic_manifest = _make_manifest(
            integration_id="anthropic_agent",
            app="anthropic_agent",
            model_presets={"default": {"model": "claude-sonnet-4-20250514"}},
        )
        openai_manifest = _make_manifest(
            integration_id="openai",
            app="openai",
            model_presets={"default": {"model": "gpt-4o"}},
        )

        registry = MagicMock()
        # Sorted by priority: anthropic first
        registry.list_by_archetype.return_value = [anthropic_manifest, openai_manifest]
        registry.get_integration.side_effect = lambda t: (
            anthropic_manifest if t == "anthropic_agent" else openai_manifest
        )
        mock_get_registry.return_value = registry

        # First call (anthropic) fails, second call (openai) succeeds
        mock_fetch_key.side_effect = [
            ValueError(
                "No 'api_key' found in credentials for integration 'anthropic-agent-test'"
            ),
            "sk-openai-key",
        ]

        session = AsyncMock()
        model, settings = await resolve_chat_model(tenant_id="default", session=session)

        # Should have fallen back to OpenAI
        assert model.model_name == "gpt-4o"

    @patch("analysi.services.chat_model_resolver._fetch_api_key_for_integration")
    @patch("analysi.services.chat_model_resolver.get_registry")
    @patch("analysi.services.chat_model_resolver.IntegrationRepository")
    @pytest.mark.anyio
    async def test_primary_integration_preferred_over_higher_priority(
        self, mock_repo_cls, mock_get_registry, mock_fetch_key
    ):
        """is_primary=True integration is tried first, even if another has higher manifest priority."""
        # anthropic_agent has higher manifest priority but is NOT primary
        anthropic_integration = _mock_integration("anthropic_agent", is_primary=False)
        # openai is primary
        openai_integration = _mock_integration("openai", is_primary=True)

        mock_repo = AsyncMock()

        async def _list_integrations(**kw):
            t = kw.get("integration_type")
            if t == "anthropic_agent":
                return [anthropic_integration]
            if t == "openai":
                return [openai_integration]
            return []

        mock_repo.list_integrations = AsyncMock(side_effect=_list_integrations)
        mock_repo_cls.return_value = mock_repo

        anthropic_manifest = _make_manifest(
            integration_id="anthropic_agent",
            app="anthropic_agent",
            model_presets={"default": {"model": "claude-sonnet-4-20250514"}},
        )
        openai_manifest = _make_manifest(
            integration_id="openai",
            app="openai",
            model_presets={"default": {"model": "gpt-4o"}},
        )

        registry = MagicMock()
        # Sorted by priority: anthropic first
        registry.list_by_archetype.return_value = [anthropic_manifest, openai_manifest]
        registry.get_integration.side_effect = lambda t: (
            anthropic_manifest if t == "anthropic_agent" else openai_manifest
        )
        mock_get_registry.return_value = registry

        mock_fetch_key.return_value = "sk-openai-key"

        session = AsyncMock()
        model, _ = await resolve_chat_model(tenant_id="default", session=session)

        # Primary (OpenAI) should be picked first
        assert model.model_name == "gpt-4o"
        # _fetch_api_key was called with the openai integration (primary), not anthropic
        mock_fetch_key.assert_awaited_once_with("default", openai_integration, session)

    @patch("analysi.services.chat_model_resolver._fetch_api_key_for_integration")
    @patch("analysi.services.chat_model_resolver.get_registry")
    @patch("analysi.services.chat_model_resolver.IntegrationRepository")
    @pytest.mark.anyio
    async def test_all_providers_broken_raises_last_error(
        self, mock_repo_cls, mock_get_registry, mock_fetch_key
    ):
        """When all providers fail, raises the last error (not generic 'no provider')."""
        anthropic_integration = _mock_integration("anthropic_agent")
        openai_integration = _mock_integration("openai")

        mock_repo = AsyncMock()

        async def _list_integrations(**kw):
            t = kw.get("integration_type")
            if t == "anthropic_agent":
                return [anthropic_integration]
            if t == "openai":
                return [openai_integration]
            return []

        mock_repo.list_integrations = AsyncMock(side_effect=_list_integrations)
        mock_repo_cls.return_value = mock_repo

        anthropic_manifest = _make_manifest(
            integration_id="anthropic_agent",
            app="anthropic_agent",
            model_presets={"default": {"model": "claude-sonnet-4-20250514"}},
        )
        openai_manifest = _make_manifest(
            integration_id="openai",
            app="openai",
            model_presets={"default": {"model": "gpt-4o"}},
        )

        registry = MagicMock()
        registry.list_by_archetype.return_value = [anthropic_manifest, openai_manifest]
        registry.get_integration.side_effect = lambda t: (
            anthropic_manifest if t == "anthropic_agent" else openai_manifest
        )
        mock_get_registry.return_value = registry

        # Both fail
        mock_fetch_key.side_effect = ValueError("No 'api_key' found in credentials")

        session = AsyncMock()
        with pytest.raises(ValueError, match="No 'api_key' found"):
            await resolve_chat_model(tenant_id="default", session=session)

"""Regression test: execute_action merges manifest model_presets into action settings.

Bug: AIActionBase.get_model_config("embedding") fell through to the legacy
single-model fallback and returned the chat model (gpt-4o-mini) instead of
the embedding model (text-embedding-3-small).  Root cause: the action's
self.settings came straight from the DB integration record, which had no
model_presets key — only "model": "gpt-4o-mini".  Manifest defaults were
never merged in.

Fix: execute_action now merges _extract_settings_defaults(manifest) with
the DB-level overrides before passing settings to the action.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.integrations.framework.base_ai import _resolve_from_settings
from analysi.services.integration_service import IntegrationService

MODULE = "analysi.services.integration_service"


def _make_manifest_with_presets() -> MagicMock:
    """Build a manifest mock whose settings_schema has model_presets defaults."""
    manifest = MagicMock()
    manifest.id = "openai"
    manifest.settings_schema = {
        "properties": {
            "api_url": {"default": "https://api.openai.com/v1"},
            "model": {"default": "gpt-4o"},
            "model_presets": {
                "default": {
                    "default": {"model": "gpt-4o"},
                    "embedding": {"model": "text-embedding-3-small"},
                    "fast": {"model": "gpt-4o-mini"},
                }
            },
        }
    }
    action_def = MagicMock()
    action_def.id = "llm_embed"
    action_def.type = "tool"
    manifest.actions = [action_def]
    return manifest


class TestExecuteActionMergesModelPresets:
    """Verify that execute_action merges manifest model_presets into action settings."""

    @pytest.fixture
    def service(self):
        repo = AsyncMock()
        return IntegrationService(
            integration_repo=repo,
        )

    @pytest.mark.asyncio
    async def test_embedding_model_resolved_from_manifest_presets(self, service):
        """When DB settings override only 'model', embedding preset still comes from manifest."""
        manifest = _make_manifest_with_presets()

        # DB integration record: only overrides "model" — no model_presets
        mock_integration = MagicMock()
        mock_integration.settings = {
            "model": "gpt-4o-mini",
            "api_url": "https://api.openai.com/v1",
            "is_primary": True,
        }

        service.integration_repo.get_integration = AsyncMock(
            return_value=mock_integration
        )

        # Capture the settings passed to load_action
        captured_settings = {}
        mock_action = AsyncMock()
        mock_action.execute = AsyncMock(
            return_value={"status": "success", "data": {"embedding": [0.1, 0.2]}}
        )

        async def capture_load_action(**kwargs):
            captured_settings.update(kwargs["settings"])
            return mock_action

        mock_registry = MagicMock()
        mock_registry.get_integration.return_value = manifest

        with (
            patch(f"{MODULE}.get_registry", return_value=mock_registry),
            patch(f"{MODULE}.IntegrationLoader") as MockLoader,
        ):
            MockLoader.return_value.load_action = capture_load_action
            await service.execute_action(
                tenant_id="default",
                integration_id="openai-primary",
                integration_type="openai",
                action_id="llm_embed",
                params={"text": "test"},
            )

        # The action should see model_presets from the manifest
        assert "model_presets" in captured_settings, (
            "model_presets missing from action settings — "
            "manifest defaults not merged into action settings"
        )

        # Embedding preset should resolve to text-embedding-3-small, not gpt-4o-mini
        embedding_config = _resolve_from_settings(
            captured_settings, "embedding", "openai"
        )
        assert embedding_config["model"] == "text-embedding-3-small", (
            f"Expected text-embedding-3-small but got {embedding_config['model']}. "
            f"The embedding model is resolving to the chat model instead of the "
            f"embedding preset from the manifest."
        )

    @pytest.mark.asyncio
    async def test_tenant_preset_overrides_win(self, service):
        """When tenant overrides a specific preset, that override wins over manifest default."""
        manifest = _make_manifest_with_presets()

        # Tenant explicitly overrides the embedding model
        mock_integration = MagicMock()
        mock_integration.settings = {
            "model": "gpt-4o-mini",
            "model_presets": {
                "embedding": {"model": "text-embedding-ada-002"},
            },
        }

        service.integration_repo.get_integration = AsyncMock(
            return_value=mock_integration
        )

        captured_settings = {}
        mock_action = AsyncMock()
        mock_action.execute = AsyncMock(
            return_value={"status": "success", "data": {"embedding": [0.1]}}
        )

        async def capture_load_action(**kwargs):
            captured_settings.update(kwargs["settings"])
            return mock_action

        mock_registry = MagicMock()
        mock_registry.get_integration.return_value = manifest

        with (
            patch(f"{MODULE}.get_registry", return_value=mock_registry),
            patch(f"{MODULE}.IntegrationLoader") as MockLoader,
        ):
            MockLoader.return_value.load_action = capture_load_action
            await service.execute_action(
                tenant_id="default",
                integration_id="openai-primary",
                integration_type="openai",
                action_id="llm_embed",
                params={"text": "test"},
            )

        # Tenant's override should win
        embedding_config = _resolve_from_settings(
            captured_settings, "embedding", "openai"
        )
        assert embedding_config["model"] == "text-embedding-ada-002"

        # But manifest defaults for other presets should survive the merge
        fast_config = _resolve_from_settings(captured_settings, "fast", "openai")
        assert fast_config["model"] == "gpt-4o-mini"

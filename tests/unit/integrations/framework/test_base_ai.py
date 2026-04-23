"""
Unit tests for AI archetype base: resolve_model_config() and AIActionBase.

Tests UT-AI-01 through UT-AI-09 from TEST_PLAN.md.
"""

from typing import Any

import pytest

from analysi.integrations.framework.base_ai import AIActionBase, resolve_model_config
from analysi.integrations.framework.models import IntegrationManifest


def _make_manifest(
    settings_schema: dict[str, Any] | None = None,
    integration_id: str = "openai",
    app: str = "openai",
) -> IntegrationManifest:
    """Build a minimal IntegrationManifest for testing."""
    data: dict[str, Any] = {
        "id": integration_id,
        "app": app,
        "name": "Test AI",
        "version": "1.0.0",
        "archetypes": ["AI"],
        "priority": 80,
        "archetype_mappings": {"AI": {"llm_run": "llm_run"}},
        "actions": [{"id": "llm_run", "type": "tool"}],
    }
    if settings_schema is not None:
        data["settings_schema"] = settings_schema
    return IntegrationManifest(**data)


class TestResolveModelConfig:
    """Test resolve_model_config() capability resolution."""

    def test_ut_ai_01_default_capability(self):
        """UT-AI-01: Default capability resolves from presets."""
        manifest = _make_manifest(
            settings_schema={
                "type": "object",
                "properties": {
                    "model_presets": {
                        "type": "object",
                        "default": {
                            "default": {"model": "gpt-4o"},
                            "fast": {"model": "gpt-4o-mini"},
                        },
                    }
                },
            }
        )
        result = resolve_model_config(manifest, capability="default")
        assert result == {"model": "gpt-4o"}

    def test_ut_ai_02_named_capability(self):
        """UT-AI-02: Named capability resolves from presets."""
        manifest = _make_manifest(
            settings_schema={
                "type": "object",
                "properties": {
                    "model_presets": {
                        "type": "object",
                        "default": {
                            "default": {"model": "gpt-4o"},
                            "thinking": {"model": "o3"},
                        },
                    }
                },
            }
        )
        result = resolve_model_config(manifest, capability="thinking")
        assert result == {"model": "o3"}

    def test_ut_ai_03_capability_with_extra_params(self):
        """UT-AI-03: Capability with extra provider-specific params."""
        manifest = _make_manifest(
            settings_schema={
                "type": "object",
                "properties": {
                    "model_presets": {
                        "type": "object",
                        "default": {
                            "default": {"model": "claude-sonnet-4-20250514"},
                            "thinking": {
                                "model": "claude-sonnet-4-20250514",
                                "extended_thinking": True,
                                "max_thinking_tokens": 10000,
                            },
                        },
                    }
                },
            },
            integration_id="anthropic_agent",
            app="anthropic_agent",
        )
        result = resolve_model_config(manifest, capability="thinking")
        assert result == {
            "model": "claude-sonnet-4-20250514",
            "extended_thinking": True,
            "max_thinking_tokens": 10000,
        }

    def test_ut_ai_04_legacy_single_model_fallback(self):
        """UT-AI-04: Legacy fallback when no presets exist — uses settings.model."""
        manifest = _make_manifest(
            settings_schema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "default": "gpt-4o",
                    }
                },
            }
        )
        result = resolve_model_config(manifest, capability="default")
        assert result == {"model": "gpt-4o"}

    def test_ut_ai_05_ai_action_base_get_model_config(self):
        """UT-AI-05: AIActionBase.get_model_config() delegates to resolve_model_config."""

        class StubAction(AIActionBase):
            async def execute(self, **kwargs) -> dict[str, Any]:
                return {"status": "success"}

        action = StubAction(
            integration_id="openai",
            action_id="llm_run",
            settings={
                "model_presets": {
                    "default": {"model": "gpt-4o"},
                    "fast": {"model": "gpt-4o-mini"},
                }
            },
            credentials={"api_key": "test-key"},
        )

        result = action.get_model_config("fast")
        assert result == {"model": "gpt-4o-mini"}

    def test_ut_ai_06_null_preset_raises_value_error(self):
        """UT-AI-06: Explicit null preset raises ValueError (not supported)."""
        manifest = _make_manifest(
            settings_schema={
                "type": "object",
                "properties": {
                    "model_presets": {
                        "type": "object",
                        "default": {
                            "default": {"model": "claude-sonnet-4-20250514"},
                            "embedding": None,
                        },
                    }
                },
            },
            integration_id="anthropic_agent",
        )
        with pytest.raises(ValueError, match="not supported"):
            resolve_model_config(manifest, capability="embedding")

    def test_ut_ai_07_unknown_capability_falls_back_to_default(self):
        """UT-AI-07: Unknown capability falls back to default with warning."""
        manifest = _make_manifest(
            settings_schema={
                "type": "object",
                "properties": {
                    "model_presets": {
                        "type": "object",
                        "default": {
                            "default": {"model": "gpt-4o"},
                        },
                    }
                },
            }
        )
        result = resolve_model_config(manifest, capability="nonexistent_capability")
        assert result == {"model": "gpt-4o"}

    def test_ut_ai_08_unknown_capability_no_presets_legacy_fallback(self):
        """UT-AI-08: Unknown capability, no presets at all, falls back to settings.model."""
        manifest = _make_manifest(
            settings_schema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "default": "gpt-4o",
                    }
                },
            }
        )
        result = resolve_model_config(manifest, capability="nonexistent_capability")
        assert result == {"model": "gpt-4o"}

    def test_ut_ai_09_settings_overrides(self):
        """UT-AI-09: Settings overrides merge over manifest defaults."""
        manifest = _make_manifest(
            settings_schema={
                "type": "object",
                "properties": {
                    "model_presets": {
                        "type": "object",
                        "default": {
                            "default": {"model": "gpt-4o"},
                        },
                    }
                },
            }
        )
        overrides = {
            "model_presets": {
                "default": {"model": "custom-model"},
            }
        }
        result = resolve_model_config(
            manifest, capability="default", settings_overrides=overrides
        )
        assert result == {"model": "custom-model"}

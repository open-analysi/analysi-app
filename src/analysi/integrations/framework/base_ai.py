"""
Base classes for AI archetype actions.

Provides capability-based model resolution and AIActionBase for LLM operations.
"""

from typing import Any

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.models import IntegrationManifest

logger = get_logger(__name__)


def _extract_settings_defaults(manifest: IntegrationManifest) -> dict[str, Any]:
    """Extract default values from a manifest's settings_schema.

    Walks settings_schema.properties and collects each property's "default" value.
    """
    schema = manifest.settings_schema
    if not schema:
        return {}
    properties = schema.get("properties", {})
    defaults: dict[str, Any] = {}
    for key, prop_def in properties.items():
        if "default" in prop_def:
            defaults[key] = prop_def["default"]
    return defaults


def resolve_model_config(
    manifest: IntegrationManifest,
    capability: str = "default",
    settings_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve capability name to model config dict.

    Resolution order:
      1. model_presets[capability]
      2. model_presets["default"]  (with warning if capability was unknown)
      3. settings.model  (legacy single-model fallback)

    Args:
        manifest: Integration manifest with settings_schema defaults.
        capability: Capability name (e.g., "default", "thinking", "fast", "embedding").
        settings_overrides: Tenant-specific setting overrides merged on top of defaults.

    Returns:
        Dict with at least {"model": "<model_name>"} plus provider-specific params.

    Raises:
        ValueError: If the capability is explicitly set to null (not supported).
    """
    # Build effective settings: manifest defaults merged with overrides.
    # Deep-merge model_presets so tenant overrides of one preset don't erase others.
    settings = _extract_settings_defaults(manifest)
    if settings_overrides:
        # Save and deep-merge model_presets before the top-level update overwrites them
        default_presets = settings.get("model_presets", {})
        override_presets = settings_overrides.get("model_presets")
        settings.update(settings_overrides)
        if default_presets and override_presets is not None:
            settings["model_presets"] = {**default_presets, **override_presets}

    return _resolve_from_settings(settings, capability, manifest.id)


def _resolve_from_settings(
    settings: dict[str, Any],
    capability: str,
    integration_id: str = "unknown",
) -> dict[str, Any]:
    """Shared preset resolution logic used by both the free function and the method.

    Args:
        settings: Effective settings dict (already merged with overrides).
        capability: Capability name.
        integration_id: For error/warning messages.

    Returns:
        Model config dict (always a fresh copy).
    """
    presets = settings.get("model_presets", {})
    preset = presets.get(capability)

    # Explicit null means "not supported" (e.g., Anthropic embedding)
    if capability in presets and preset is None:
        raise ValueError(f"Capability '{capability}' not supported by {integration_id}")

    # Unknown capability: fall back to "default"
    if preset is None and capability != "default":
        logger.warning(
            "unknown_capability_fallback",
            capability=capability,
            integration=integration_id,
        )
        preset = presets.get("default")

    # Legacy single-model fallback
    if preset is None:
        return {"model": settings.get("model")}

    return dict(preset) if isinstance(preset, dict) else {"model": preset}


class AIActionBase(IntegrationAction):
    """Base class for AI archetype actions.

    Subclasses implement LLM operations (llm_run, llm_chat, llm_embed).
    Uses resolve_model_config() for capability-based model selection.
    """

    # Subclasses MUST set this to their provider-specific LlmChatAction class.
    # Used by the shared llm_run() implementation below.
    llm_chat_action_class: type["AIActionBase"] | None = None

    def get_model_config(self, capability: str = "default") -> dict[str, Any]:
        """Resolve model config from this action's runtime settings.

        Delegates to shared resolution logic. Always returns a fresh dict
        (safe to .pop() keys from the result).
        """
        return _resolve_from_settings(self.settings, capability, self.integration_id)


class LlmRunActionBase(AIActionBase):
    """Single-turn LLM execution: prompt in, string out.

    Sugar over the provider's LlmChatAction — wraps the prompt in a messages
    array. Subclasses only need to set `llm_chat_action_class` to point to
    their provider-specific chat action.
    """

    async def execute(self, **params: Any) -> dict[str, Any]:
        """Execute single-turn LLM call.

        Args:
            prompt: The user prompt.
            context: Optional system context string.
            capability: Model capability preset (default: "default").

        Returns:
            Standard action result with data.response, data.input_tokens, data.output_tokens.
        """
        if self.llm_chat_action_class is None:
            return self.error_result(
                error="llm_chat_action_class not set on LlmRunAction subclass",
                error_type="configuration_error",
            )

        prompt = params.get("prompt", "")
        context = params.get("context")
        capability = params.get("capability", "default")

        messages: list[dict[str, str]] = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})

        chat_action = self.llm_chat_action_class(
            integration_id=self.integration_id,
            action_id=self.action_id,
            settings=self.settings,
            credentials=self.credentials,
            ctx=self.ctx,
        )

        # Pass through per-call overrides to chat action
        chat_params: dict[str, Any] = {
            "messages": messages,
            "capability": capability,
        }
        if params.get("override_max_tokens"):
            chat_params["override_max_tokens"] = params["override_max_tokens"]
        if params.get("override_temperature") is not None:
            chat_params["override_temperature"] = params["override_temperature"]

        result = await chat_action.execute(**chat_params)

        # Enrich with convenience response string
        if result.get("status") == "success":
            message_content = result["data"]["message"].get("content", "")
            result["data"]["response"] = message_content

        return result

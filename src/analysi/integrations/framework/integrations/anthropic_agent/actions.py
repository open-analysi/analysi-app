"""
Anthropic integration actions.

Provides health check + AI archetype actions (llm_run, llm_chat).
Supports extended thinking for the "thinking" capability preset.
Anthropic does not offer an embedding model, so llm_embed is not implemented.
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.base_ai import AIActionBase, LlmRunActionBase

logger = get_logger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_THINKING_BUDGET_TOKENS = 1024

class HealthCheckAction(IntegrationAction):
    """
    Verify API key or OAuth token is configured.

    Checks for either api_key (for LLM operations) or oauth_token
    (for agentic framework). At least one must be present.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """
        Execute health check.

        Returns:
            Dict with status="success" or status="error" per framework standard
        """
        api_key = self.credentials.get("api_key", "")
        oauth_token = self.credentials.get("oauth_token", "")

        if not api_key and not oauth_token:
            return self.error_result(
                error="Missing both api_key and oauth_token in credentials",
                error_type="configuration_error",
                data={"error": "No credentials configured"},
            )

        # Validate token format
        has_valid_api_key = bool(api_key and api_key.startswith("sk-ant-"))
        has_valid_oauth = bool(oauth_token and oauth_token.startswith("sk-ant-"))

        if not has_valid_api_key and not has_valid_oauth:
            return self.error_result(
                error="Credentials should start with 'sk-ant-'",
                error_type="validation_error",
                data={"error": "Invalid token format"},
            )

        return self.success_result(
            data={
                "status": "healthy",
                "api_key_configured": has_valid_api_key,
                "oauth_token_configured": has_valid_oauth,
                "settings": {
                    "max_turns": self.settings.get("max_turns", 100),
                    "permission_mode": self.settings.get(
                        "permission_mode", "bypassPermissions"
                    ),
                },
            }
        )

class LlmChatAction(AIActionBase):
    """Multi-turn LLM chat: messages in, message out.

    Calls Anthropic's /v1/messages endpoint.
    Supports extended thinking when capability="thinking" and the preset
    includes extended_thinking=true.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Execute chat completion via Anthropic Messages API.

        Args:
            messages: List of message dicts [{"role": "...", "content": "..."}].
            capability: Model capability preset (default: "default").

        Returns:
            Standard action result with data.message, data.input_tokens, data.output_tokens.
        """
        messages = params.get("messages", [])
        capability = params.get("capability", "default")

        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                error="Missing api_key in credentials",
                error_type="configuration_error",
            )

        model_config = self.get_model_config(capability)
        model = model_config.pop("model")
        extended_thinking = model_config.pop("extended_thinking", False)
        max_thinking_tokens = model_config.pop("max_thinking_tokens", None)

        # Separate system messages from conversation messages.
        # Anthropic API accepts a single "system" param — concatenate if multiple.
        system_parts: list[str] = []
        conversation_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(msg.get("content", "").strip())
            else:
                conversation_messages.append(msg)
        system_content = "\n\n".join(system_parts) if system_parts else None

        # Per-call overrides (passed by CyLLMFunctions for llm_summarize etc.)
        override_max_tokens = params.get("override_max_tokens")
        override_temperature = params.get("override_temperature")

        request_body: dict[str, Any] = {
            "model": model,
            "messages": conversation_messages,
            "max_tokens": override_max_tokens or model_config.pop("max_tokens", 4096),
        }

        if override_temperature is not None:
            request_body["temperature"] = override_temperature

        if system_content:
            request_body["system"] = system_content

        # Extended thinking support
        if extended_thinking:
            if not max_thinking_tokens:
                logger.warning(
                    "extended_thinking_missing_budget",
                    integration=self.integration_id,
                    msg="extended_thinking=True but max_thinking_tokens not set, defaulting to 1024",
                )
                max_thinking_tokens = DEFAULT_THINKING_BUDGET_TOKENS
            request_body["thinking"] = {
                "type": "enabled",
                "budget_tokens": max_thinking_tokens,
            }

        # Pass through remaining provider-specific params
        request_body.update(model_config)

        try:
            response = await self.http_request(
                f"{ANTHROPIC_API_URL}/messages",
                method="POST",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": ANTHROPIC_API_VERSION,
                    "Content-Type": "application/json",
                },
                json_data=request_body,
                timeout=60.0,
            )

            data = response.json()
            usage = data.get("usage", {})

            # Extract text from content blocks
            content_blocks = data.get("content", [])
            text_parts = [
                block.get("text", "")
                for block in content_blocks
                if block.get("type") == "text"
            ]
            text_content = "\n".join(text_parts) if text_parts else ""

            return self.success_result(
                data={
                    "message": {"role": "assistant", "content": text_content},
                    "finish_reason": data.get("stop_reason"),
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                }
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(
                error=f"Anthropic API returned status {e.response.status_code}: {e.response.text}",
                error_type="api_error",
            )
        except httpx.TimeoutException:
            return self.error_result(
                error="Anthropic API timeout", error_type="timeout_error"
            )
        except Exception as e:
            self.log_error("anthropic_llm_chat_failed", error=e)
            return self.error_result(error=e)

class LlmRunAction(LlmRunActionBase):
    """Single-turn LLM execution: prompt in, string out."""

    llm_chat_action_class = LlmChatAction  # type: ignore[assignment]

# Keep function-based API for backwards compatibility and tests
def health_check(
    credentials: dict[str, Any],
    settings: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Verify OAuth token is configured.

    DEPRECATED: Use HealthCheckAction class instead.
    This function is kept for backwards compatibility with unit tests.

    Returns standard format: {"status": "success"|"error", "data": {...}, ...}
    """
    oauth_token = credentials.get("oauth_token", "")

    if not oauth_token:
        return {
            "status": "error",
            "error": "Missing oauth_token in credentials",
            "error_type": "configuration_error",
            "data": {"error": "OAuth token not configured"},
            "timestamp": datetime.now(UTC).isoformat(),
        }

    # Check token format (basic validation)
    if not oauth_token.startswith("sk-ant-"):
        return {
            "status": "error",
            "error": "OAuth token should start with 'sk-ant-'",
            "error_type": "validation_error",
            "data": {"error": "Invalid token format"},
            "timestamp": datetime.now(UTC).isoformat(),
        }

    return {
        "status": "success",
        "data": {
            "status": "healthy",
            "token_configured": True,
            "token_prefix": oauth_token[:10] + "...",
            "settings": {
                "max_turns": settings.get("max_turns", 100),
                "permission_mode": settings.get("permission_mode", "bypassPermissions"),
            },
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }

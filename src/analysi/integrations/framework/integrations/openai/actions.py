"""OpenAI integration actions for the Naxos framework.

Provides health check + AI archetype actions (llm_run, llm_chat, llm_embed).
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.base_ai import AIActionBase, LlmRunActionBase

logger = get_logger(__name__)

class HealthCheckAction(IntegrationAction):
    """Health check action for OpenAI."""

    async def _make_request(self, endpoint: str, api_key: str) -> httpx.Response:
        """Make HTTP request to OpenAI API.

        Uses ``self.http_request()`` which applies retry internally via
        ``integration_retry_policy``.

        Args:
            endpoint: Full URL endpoint
            api_key: API key for authorization

        Returns:
            HTTP response
        """
        return await self.http_request(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )

    async def execute(self, **params) -> dict[str, Any]:
        """Execute health check against OpenAI API.

        Checks connectivity by listing available models.
        The /v1/models endpoint is the recommended health check for OpenAI:
        - Requires authentication (validates API key)
        - Lightweight operation (no token consumption)
        - Returns list of available models

        Returns:
            dict: Health check result with status, message, models_available, timestamp
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            logger.error("Missing API key in credentials")
            return {
                "healthy": False,
                "status": "error",
                "message": "Missing API key",
                "models_available": 0,
                "endpoint": "unknown",
                "timestamp": datetime.now(UTC).isoformat(),
            }

        # Get API URL from settings, default to OpenAI
        api_url = self.settings.get("api_url", "https://api.openai.com/v1")
        endpoint = f"{api_url}/models"

        try:
            response = await self._make_request(endpoint, api_key)
            data = response.json()
            models = data.get("data", [])
            model_count = len(models)

            # Log available models for debugging
            model_ids = [m.get("id") for m in models[:5]]  # First 5 for brevity
            logger.info(
                "openai_health_check_successful_models_available_sa",
                model_count=model_count,
                model_ids=model_ids,
            )

            return {
                "healthy": True,
                "status": "success",
                "message": f"OpenAI API connection successful, {model_count} models available",
                "models_available": model_count,
                "endpoint": api_url,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 401:
                logger.error("Invalid API key")
                return {
                    "healthy": False,
                    "status": "error",
                    "message": "Invalid API key",
                    "models_available": 0,
                    "endpoint": api_url,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            logger.error("openai_api_error", status_code=status_code)
            return {
                "healthy": False,
                "status": "error",
                "message": f"API returned status {status_code}",
                "models_available": 0,
                "endpoint": api_url,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except httpx.TimeoutException:
            logger.error("OpenAI API timeout")
            return {
                "healthy": False,
                "status": "error",
                "message": "Connection timeout",
                "models_available": 0,
                "endpoint": api_url,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("openai_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": "error",
                "message": f"Connection failed: {e!s}",
                "models_available": 0,
                "endpoint": api_url,
                "timestamp": datetime.now(UTC).isoformat(),
            }

class LlmChatAction(AIActionBase):
    """Multi-turn LLM chat: messages in, message out.

    Calls OpenAI's /v1/chat/completions endpoint.
    Returns assistant message plus input_tokens / output_tokens for budget tracking.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Execute chat completion.

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
                error="Missing API key in credentials",
                error_type="configuration_error",
            )

        model_config = self.get_model_config(capability)
        model = model_config.pop("model")
        api_url = self.settings.get("api_url", "https://api.openai.com/v1")

        # Per-call overrides (passed by CyLLMFunctions for llm_summarize etc.)
        override_max_tokens = params.get("override_max_tokens")
        override_temperature = params.get("override_temperature")

        request_body: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        # Pass through any extra model config (e.g., temperature, max_tokens)
        request_body.update(model_config)

        # Per-call overrides take precedence over preset config
        if override_max_tokens:
            request_body["max_tokens"] = override_max_tokens
        if override_temperature is not None:
            request_body["temperature"] = override_temperature

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                )

            if response.status_code != 200:
                return self.error_result(
                    error=f"OpenAI API returned status {response.status_code}: {response.text}",
                    error_type="api_error",
                )

            data = response.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})

            return self.success_result(
                data={
                    "message": choice["message"],
                    "finish_reason": choice.get("finish_reason"),
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                }
            )

        except httpx.TimeoutException:
            return self.error_result(
                error="OpenAI API timeout", error_type="timeout_error"
            )
        except Exception as e:
            self.log_error("openai_llm_chat_failed", error=e)
            return self.error_result(error=e)

class LlmRunAction(LlmRunActionBase):
    """Single-turn LLM execution: prompt in, string out."""

    llm_chat_action_class = LlmChatAction  # type: ignore[assignment]

class LlmEmbedAction(AIActionBase):
    """Generate text embeddings: text in, vector out.

    Calls OpenAI's /v1/embeddings endpoint.
    Returns embedding vector plus input_tokens for budget tracking.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Execute embedding generation.

        Args:
            text: Text to embed.

        Returns:
            Standard action result with data.embedding (list[float]), data.input_tokens.
        """
        text = params.get("text", "")

        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                error="Missing API key in credentials",
                error_type="configuration_error",
            )

        model_config = self.get_model_config("embedding")
        model = model_config.get("model", "text-embedding-3-small")
        api_url = self.settings.get("api_url", "https://api.openai.com/v1")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "input": text,
                    },
                )

            if response.status_code != 200:
                return self.error_result(
                    error=f"OpenAI API returned status {response.status_code}: {response.text}",
                    error_type="api_error",
                )

            data = response.json()
            embedding = data["data"][0]["embedding"]
            usage = data.get("usage", {})

            return self.success_result(
                data={
                    "embedding": embedding,
                    "input_tokens": usage.get("prompt_tokens", 0),
                }
            )

        except httpx.TimeoutException:
            return self.error_result(
                error="OpenAI API timeout", error_type="timeout_error"
            )
        except Exception as e:
            self.log_error("openai_llm_embed_failed", error=e)
            return self.error_result(error=e)

"""Google Gemini integration actions for the Naxos framework.

Provides health check + AI archetype actions (llm_run, llm_chat, llm_embed).
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.base_ai import AIActionBase, LlmRunActionBase

logger = get_logger(__name__)

GEMINI_MODELS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

class HealthCheckAction(IntegrationAction):
    """Health check action for Google Gemini."""

    async def _make_request(self, api_key: str) -> httpx.Response:
        """Make HTTP request to Gemini API to list models.

        Uses ``self.http_request()`` which applies retry internally via
        ``integration_retry_policy``.

        Args:
            api_key: Gemini API key

        Returns:
            HTTP response
        """
        return await self.http_request(
            GEMINI_MODELS_ENDPOINT,
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )

    async def execute(self, **params) -> dict[str, Any]:
        """Execute health check against Gemini API.

        Checks connectivity by listing available models.

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
                "endpoint": GEMINI_MODELS_ENDPOINT,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        try:
            response = await self._make_request(api_key)
            response.raise_for_status()
            data = response.json()
            models = data.get("models", [])
            model_count = len(models)

            model_ids = [m.get("name") for m in models[:5]]
            logger.info(
                "gemini_health_check_successful",
                model_count=model_count,
                sample_models=model_ids,
            )

            return {
                "healthy": True,
                "status": "success",
                "message": f"Gemini API connection successful, {model_count} models available",
                "models_available": model_count,
                "endpoint": GEMINI_MODELS_ENDPOINT,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 400:
                logger.error("Invalid API key or request")
                return {
                    "healthy": False,
                    "status": "error",
                    "message": "Invalid API key or request",
                    "models_available": 0,
                    "endpoint": GEMINI_MODELS_ENDPOINT,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            if status_code == 403:
                logger.error("API key does not have permission")
                return {
                    "healthy": False,
                    "status": "error",
                    "message": "API key does not have permission",
                    "models_available": 0,
                    "endpoint": GEMINI_MODELS_ENDPOINT,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            logger.error("gemini_api_error", status_code=status_code)
            return {
                "healthy": False,
                "status": "error",
                "message": f"API returned status {status_code}",
                "models_available": 0,
                "endpoint": GEMINI_MODELS_ENDPOINT,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except httpx.TimeoutException:
            logger.error("Gemini API timeout")
            return {
                "healthy": False,
                "status": "error",
                "message": "Connection timeout",
                "models_available": 0,
                "endpoint": GEMINI_MODELS_ENDPOINT,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("gemini_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": "error",
                "message": f"Connection failed: {e!s}",
                "models_available": 0,
                "endpoint": GEMINI_MODELS_ENDPOINT,
                "timestamp": datetime.now(UTC).isoformat(),
            }

class LlmChatAction(AIActionBase):
    """Multi-turn LLM chat: messages in, message out.

    Calls Gemini's generateContent endpoint.
    Converts OpenAI-style messages to Gemini content format internally.
    """

    def _to_gemini_contents(
        self, messages: list[dict[str, str]]
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Convert OpenAI-style messages to Gemini contents format.

        Returns:
            Tuple of (contents list, system_instruction or None).
        """
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_parts.append(content.strip())
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": content}]})

        system_instruction = "\n\n".join(system_parts) if system_parts else None
        return contents, system_instruction

    async def execute(self, **params) -> dict[str, Any]:
        """Execute chat completion via Gemini API.

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

        contents, system_instruction = self._to_gemini_contents(messages)
        endpoint = f"{GEMINI_API_BASE}/models/{model}:generateContent"

        request_body: dict[str, Any] = {"contents": contents}
        if system_instruction:
            request_body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        # Per-call overrides (passed by CyLLMFunctions for llm_summarize etc.)
        override_max_tokens = params.get("override_max_tokens")
        override_temperature = params.get("override_temperature")

        # Pass through extra provider-specific params (e.g., temperature, top_p)
        if model_config:
            request_body.setdefault("generationConfig", {}).update(model_config)

        # Per-call overrides take precedence over preset config
        if override_max_tokens:
            request_body.setdefault("generationConfig", {})["maxOutputTokens"] = (
                override_max_tokens
            )
        if override_temperature is not None:
            request_body.setdefault("generationConfig", {})["temperature"] = (
                override_temperature
            )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    params={"key": api_key},
                    headers={"Content-Type": "application/json"},
                    json=request_body,
                )

            if response.status_code != 200:
                return self.error_result(
                    error=f"Gemini API returned status {response.status_code}: {response.text}",
                    error_type="api_error",
                )

            data = response.json()
            candidate = data["candidates"][0]
            text_content = candidate["content"]["parts"][0].get("text", "")
            usage = data.get("usageMetadata", {})

            return self.success_result(
                data={
                    "message": {"role": "assistant", "content": text_content},
                    "finish_reason": candidate.get("finishReason"),
                    "input_tokens": usage.get("promptTokenCount", 0),
                    "output_tokens": usage.get("candidatesTokenCount", 0),
                }
            )

        except httpx.TimeoutException:
            return self.error_result(
                error="Gemini API timeout", error_type="timeout_error"
            )
        except Exception as e:
            self.log_error("gemini_llm_chat_failed", error=e)
            return self.error_result(error=e)

class LlmRunAction(LlmRunActionBase):
    """Single-turn LLM execution: prompt in, string out."""

    llm_chat_action_class = LlmChatAction  # type: ignore[assignment]

class LlmEmbedAction(AIActionBase):
    """Generate text embeddings: text in, vector out.

    Calls Gemini's embedContent endpoint.
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
        model = model_config.get("model", "text-embedding-004")
        endpoint = f"{GEMINI_API_BASE}/models/{model}:embedContent"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    params={"key": api_key},
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": f"models/{model}",
                        "content": {"parts": [{"text": text}]},
                    },
                )

            if response.status_code != 200:
                return self.error_result(
                    error=f"Gemini API returned status {response.status_code}: {response.text}",
                    error_type="api_error",
                )

            data = response.json()
            embedding = data["embedding"]["values"]

            return self.success_result(
                data={
                    "embedding": embedding,
                    # Gemini doesn't report token usage for embeddings
                    "input_tokens": 0,
                }
            )

        except httpx.TimeoutException:
            return self.error_result(
                error="Gemini API timeout", error_type="timeout_error"
            )
        except Exception as e:
            self.log_error("gemini_llm_embed_failed", error=e)
            return self.error_result(error=e)

"""
Unit tests for AI archetype actions: llm_run, llm_chat, llm_embed.

Tests UT-AI-10 through UT-AI-23, IT-AI-01 from TEST_PLAN.md.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


# ---------------------------------------------------------------------------
# Manifest validation tests (UT-AI-19 through UT-AI-23)
# ---------------------------------------------------------------------------
class TestManifestWiring:
    """Verify manifest.json files have correct AI archetype mappings."""

    def _load_manifest(self, integration_id: str) -> dict[str, Any]:
        manifest_path = (
            _PROJECT_ROOT
            / "src"
            / "analysi"
            / "integrations"
            / "framework"
            / "integrations"
            / integration_id
            / "manifest.json"
        )
        with open(manifest_path) as f:
            return json.load(f)

    def test_ut_ai_19_openai_manifest_ai_mappings(self):
        """UT-AI-19: OpenAI manifest has AI archetype mappings for llm_run, llm_chat, llm_embed."""
        manifest = self._load_manifest("openai")
        ai_mappings = manifest.get("archetype_mappings", {}).get("AI", {})
        assert "llm_run" in ai_mappings, "OpenAI should map llm_run"
        assert "llm_chat" in ai_mappings, "OpenAI should map llm_chat"
        assert "llm_embed" in ai_mappings, "OpenAI should map llm_embed"

    def test_ut_ai_20_gemini_manifest_ai_mappings(self):
        """UT-AI-20: Gemini manifest has AI archetype mappings for llm_run, llm_chat, llm_embed."""
        manifest = self._load_manifest("gemini")
        ai_mappings = manifest.get("archetype_mappings", {}).get("AI", {})
        assert "llm_run" in ai_mappings, "Gemini should map llm_run"
        assert "llm_chat" in ai_mappings, "Gemini should map llm_chat"
        assert "llm_embed" in ai_mappings, "Gemini should map llm_embed"

    def test_ut_ai_21_anthropic_dual_archetypes(self):
        """UT-AI-21: Anthropic has both AI and AgenticFramework archetypes."""
        manifest = self._load_manifest("anthropic_agent")
        archetypes = manifest.get("archetypes", [])
        assert "AI" in archetypes, "Anthropic should have AI archetype"
        assert "AgenticFramework" in archetypes, (
            "Anthropic should keep AgenticFramework archetype"
        )

    def test_ut_ai_22_anthropic_priority_90(self):
        """UT-AI-22: Anthropic has priority 90."""
        manifest = self._load_manifest("anthropic_agent")
        assert manifest.get("priority") == 90

    def test_ut_ai_23_archetype_doc_no_llm_complete(self):
        """UT-AI-23: Archetype doc AI section no longer lists llm_complete."""
        doc_path = (
            _PROJECT_ROOT
            / "skills"
            / "dev"
            / "integrations-developer"
            / "references"
            / "archetypes.md"
        )
        content = doc_path.read_text()
        # Find the AI section
        ai_section_start = content.find("### 17. AI")
        assert ai_section_start != -1, "Should have AI archetype section"
        # Find next section boundary
        next_section = content.find("### 18.", ai_section_start)
        ai_section = (
            content[ai_section_start:next_section]
            if next_section != -1
            else content[ai_section_start:]
        )
        assert "llm_complete" not in ai_section, (
            "AI archetype section should not mention llm_complete"
        )

    def test_openai_manifest_has_model_presets(self):
        """OpenAI manifest should include model_presets in settings_schema."""
        manifest = self._load_manifest("openai")
        settings = manifest.get("settings_schema", {})
        properties = settings.get("properties", {})
        assert "model_presets" in properties, "OpenAI should have model_presets"
        presets_default = properties["model_presets"].get("default", {})
        assert "default" in presets_default, "Presets should have 'default' capability"
        assert "embedding" in presets_default, (
            "Presets should have 'embedding' capability"
        )

    def test_gemini_manifest_has_model_presets(self):
        """Gemini manifest should include model_presets in settings_schema."""
        manifest = self._load_manifest("gemini")
        settings = manifest.get("settings_schema", {})
        properties = settings.get("properties", {})
        assert "model_presets" in properties, "Gemini should have model_presets"

    def test_anthropic_manifest_has_model_presets(self):
        """Anthropic manifest should include model_presets in settings_schema."""
        manifest = self._load_manifest("anthropic_agent")
        settings = manifest.get("settings_schema", {})
        properties = settings.get("properties", {})
        assert "model_presets" in properties, "Anthropic should have model_presets"
        presets_default = properties["model_presets"].get("default", {})
        # Anthropic has no embedding support
        assert presets_default.get("embedding") is None, (
            "Anthropic embedding preset should be null"
        )


# ---------------------------------------------------------------------------
# OpenAI action tests (UT-AI-10 through UT-AI-15)
# ---------------------------------------------------------------------------
class TestOpenAIActions:
    """Test OpenAI LLM actions with mocked HTTP calls."""

    @pytest.fixture
    def openai_settings(self) -> dict[str, Any]:
        return {
            "api_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "model_presets": {
                "default": {"model": "gpt-4o"},
                "fast": {"model": "gpt-4o-mini"},
                "embedding": {"model": "text-embedding-3-small"},
            },
        }

    @pytest.fixture
    def openai_credentials(self) -> dict[str, Any]:
        return {"api_key": "sk-test-key-123"}

    @pytest.fixture
    def mock_chat_response(self) -> dict[str, Any]:
        """Standard OpenAI chat completions response."""
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello there!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

    @pytest.fixture
    def mock_embedding_response(self) -> dict[str, Any]:
        """Standard OpenAI embeddings response."""
        return {
            "object": "list",
            "data": [{"object": "embedding", "embedding": [0.1, 0.2, 0.3], "index": 0}],
            "usage": {"prompt_tokens": 5, "total_tokens": 5},
        }

    @pytest.mark.asyncio
    async def test_ut_ai_12_openai_llm_chat_success(
        self, openai_settings, openai_credentials, mock_chat_response
    ):
        """UT-AI-12: OpenAI LlmChatAction returns success with token counts."""
        from analysi.integrations.framework.integrations.openai.actions import (
            LlmChatAction,
        )

        action = LlmChatAction(
            integration_id="openai",
            action_id="llm_chat",
            settings=openai_settings,
            credentials=openai_credentials,
        )

        mock_response = httpx.Response(
            status_code=200,
            json=mock_chat_response,
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        )
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(
                messages=[{"role": "user", "content": "Hello"}],
                capability="default",
            )

        assert result["status"] == "success"
        assert result["data"]["message"]["content"] == "Hello there!"
        assert result["data"]["input_tokens"] == 10
        assert result["data"]["output_tokens"] == 5

    @pytest.mark.asyncio
    async def test_ut_ai_13_openai_llm_chat_missing_api_key(self, openai_settings):
        """UT-AI-13: OpenAI LlmChatAction returns error when API key missing."""
        from analysi.integrations.framework.integrations.openai.actions import (
            LlmChatAction,
        )

        action = LlmChatAction(
            integration_id="openai",
            action_id="llm_chat",
            settings=openai_settings,
            credentials={},  # No API key
        )

        result = await action.execute(
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_ut_ai_14_openai_llm_embed_success(
        self, openai_settings, openai_credentials, mock_embedding_response
    ):
        """UT-AI-14: OpenAI LlmEmbedAction returns embedding with token count."""
        from analysi.integrations.framework.integrations.openai.actions import (
            LlmEmbedAction,
        )

        action = LlmEmbedAction(
            integration_id="openai",
            action_id="llm_embed",
            settings=openai_settings,
            credentials=openai_credentials,
        )

        mock_response = httpx.Response(
            status_code=200,
            json=mock_embedding_response,
            request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"),
        )
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(text="Hello world")

        assert result["status"] == "success"
        assert result["data"]["embedding"] == [0.1, 0.2, 0.3]
        assert result["data"]["input_tokens"] == 5

    @pytest.mark.asyncio
    async def test_ut_ai_15_openai_llm_run_delegates_to_chat(
        self, openai_settings, openai_credentials, mock_chat_response
    ):
        """UT-AI-15: OpenAI LlmRunAction wraps prompt in messages and delegates to chat logic."""
        from analysi.integrations.framework.integrations.openai.actions import (
            LlmRunAction,
        )

        action = LlmRunAction(
            integration_id="openai",
            action_id="llm_run",
            settings=openai_settings,
            credentials=openai_credentials,
        )

        mock_response = httpx.Response(
            status_code=200,
            json=mock_chat_response,
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        )
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(prompt="Say hello")

        assert result["status"] == "success"
        # llm_run should extract the response string for convenience
        assert result["data"]["response"] == "Hello there!"
        assert result["data"]["input_tokens"] == 10
        assert result["data"]["output_tokens"] == 5

    @pytest.mark.asyncio
    async def test_ut_ai_10_llm_run_wraps_prompt_in_messages(
        self, openai_settings, openai_credentials, mock_chat_response
    ):
        """UT-AI-10: llm_run wraps prompt in user message."""
        from analysi.integrations.framework.integrations.openai.actions import (
            LlmRunAction,
        )

        action = LlmRunAction(
            integration_id="openai",
            action_id="llm_run",
            settings=openai_settings,
            credentials=openai_credentials,
        )

        # We'll capture what gets sent to the API
        posted_json = {}

        async def capture_post(self_client, url, **kwargs):
            nonlocal posted_json
            posted_json = kwargs.get("json", {})
            return httpx.Response(
                status_code=200,
                json=mock_chat_response,
                request=httpx.Request("POST", url),
            )

        with patch("httpx.AsyncClient.post", capture_post):
            await action.execute(prompt="Say hello")

        messages = posted_json.get("messages", [])
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Say hello"

    @pytest.mark.asyncio
    async def test_ut_ai_11_llm_run_with_context_adds_system_message(
        self, openai_settings, openai_credentials, mock_chat_response
    ):
        """UT-AI-11: llm_run with context adds system message."""
        from analysi.integrations.framework.integrations.openai.actions import (
            LlmRunAction,
        )

        action = LlmRunAction(
            integration_id="openai",
            action_id="llm_run",
            settings=openai_settings,
            credentials=openai_credentials,
        )

        posted_json = {}

        async def capture_post(self_client, url, **kwargs):
            nonlocal posted_json
            posted_json = kwargs.get("json", {})
            return httpx.Response(
                status_code=200,
                json=mock_chat_response,
                request=httpx.Request("POST", url),
            )

        with patch("httpx.AsyncClient.post", capture_post):
            await action.execute(prompt="Say hello", context="You are helpful")

        messages = posted_json.get("messages", [])
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Say hello"


# ---------------------------------------------------------------------------
# Anthropic action tests (UT-AI-16 through UT-AI-18)
# ---------------------------------------------------------------------------
class TestAnthropicActions:
    """Test Anthropic LLM actions with mocked HTTP calls."""

    @pytest.fixture
    def anthropic_settings(self) -> dict[str, Any]:
        return {
            "model_presets": {
                "default": {"model": "claude-sonnet-4-20250514"},
                "thinking": {
                    "model": "claude-sonnet-4-20250514",
                    "extended_thinking": True,
                    "max_thinking_tokens": 10000,
                },
                "fast": {"model": "claude-haiku-3-20250307"},
                "embedding": None,
            },
            "max_turns": 100,
            "permission_mode": "bypassPermissions",
        }

    @pytest.fixture
    def anthropic_credentials(self) -> dict[str, Any]:
        return {"api_key": "sk-ant-test-key-123", "oauth_token": "sk-ant-test-key-123"}

    @pytest.fixture
    def mock_anthropic_response(self) -> dict[str, Any]:
        """Standard Anthropic Messages API response."""
        return {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello there!"}],
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 12,
                "output_tokens": 6,
            },
        }

    @pytest.mark.asyncio
    async def test_ut_ai_16_anthropic_llm_chat_success(
        self, anthropic_settings, anthropic_credentials, mock_anthropic_response
    ):
        """UT-AI-16: Anthropic LlmChatAction returns success with token counts."""
        from unittest.mock import MagicMock

        from analysi.integrations.framework.integrations.anthropic_agent.actions import (
            LlmChatAction,
        )

        action = LlmChatAction(
            integration_id="anthropic_agent",
            action_id="llm_chat",
            settings=anthropic_settings,
            credentials=anthropic_credentials,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_anthropic_response
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute(
                messages=[{"role": "user", "content": "Hello"}],
                capability="default",
            )

        assert result["status"] == "success"
        assert result["data"]["message"]["content"] == "Hello there!"
        assert result["data"]["input_tokens"] == 12
        assert result["data"]["output_tokens"] == 6

    @pytest.mark.asyncio
    async def test_ut_ai_17_anthropic_extended_thinking(
        self, anthropic_settings, anthropic_credentials, mock_anthropic_response
    ):
        """UT-AI-17: Anthropic request includes extended thinking params when capability=thinking."""
        from unittest.mock import MagicMock

        from analysi.integrations.framework.integrations.anthropic_agent.actions import (
            LlmChatAction,
        )

        action = LlmChatAction(
            integration_id="anthropic_agent",
            action_id="llm_chat",
            settings=anthropic_settings,
            credentials=anthropic_credentials,
        )

        captured_kwargs = {}

        async def capture_http_request(url, **kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_anthropic_response
            return mock_resp

        with patch.object(action, "http_request", side_effect=capture_http_request):
            await action.execute(
                messages=[{"role": "user", "content": "Think carefully"}],
                capability="thinking",
            )

        # Verify extended thinking params are in the request body
        posted_json = captured_kwargs.get("json_data", {})
        thinking = posted_json.get("thinking", {})
        assert thinking.get("type") == "enabled"
        assert thinking.get("budget_tokens") == 10000

    @pytest.mark.asyncio
    async def test_ut_ai_18_anthropic_llm_run_delegates_to_chat(
        self, anthropic_settings, anthropic_credentials, mock_anthropic_response
    ):
        """UT-AI-18: Anthropic LlmRunAction delegates to chat logic."""
        from unittest.mock import MagicMock

        from analysi.integrations.framework.base import IntegrationAction
        from analysi.integrations.framework.integrations.anthropic_agent.actions import (
            LlmRunAction,
        )

        action = LlmRunAction(
            integration_id="anthropic_agent",
            action_id="llm_run",
            settings=anthropic_settings,
            credentials=anthropic_credentials,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_anthropic_response
        # Patch at the class level since LlmRunAction creates a new LlmChatAction internally
        with patch.object(
            IntegrationAction,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await action.execute(prompt="Say hello")

        assert result["status"] == "success"
        assert result["data"]["response"] == "Hello there!"
        assert result["data"]["input_tokens"] == 12
        assert result["data"]["output_tokens"] == 6


# ---------------------------------------------------------------------------
# Integration test: end-to-end archetype routing (IT-AI-01)
# ---------------------------------------------------------------------------
class TestAIArchetypeRouting:
    """Integration test for AI archetype routing."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_it_ai_01_llm_run_via_archetype_routing(self):
        """IT-AI-01: Registry resolves AI archetype, loads action, executes with mocked HTTP."""
        from unittest.mock import patch as mock_patch

        from analysi.integrations.framework.loader import IntegrationLoader
        from analysi.integrations.framework.registry import IntegrationRegistryService

        # Patch out real API keys to avoid live calls
        with mock_patch.dict(
            "os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}
        ):
            registry = IntegrationRegistryService()

            # Verify AI archetype has at least one provider
            ai_providers = registry.list_by_archetype("AI")
            assert len(ai_providers) > 0, "Should have at least one AI provider"

            # Get highest priority provider
            primary = registry.get_primary_integration_for_archetype("AI")
            assert primary is not None

            # Resolve llm_run action
            action_id = registry.resolve_archetype_action(primary.id, "AI", "llm_run")
            assert action_id is not None, f"Provider {primary.id} should map llm_run"

            # Load the action class
            loader = IntegrationLoader()
            # Find the action definition
            action_def = next((a for a in primary.actions if a.id == action_id), None)
            assert action_def is not None

            action = await loader.load_action(
                integration_id=primary.id,
                action_id=action_id,
                action_metadata=action_def.model_dump(),
                settings={"model_presets": {"default": {"model": "test-model"}}},
                credentials={"api_key": "test-key"},
            )

            # Execute with mocked HTTP
            mock_response_data = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Test response"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 3,
                    "total_tokens": 8,
                },
            }
            # Handle both OpenAI and Anthropic response formats
            mock_anthropic_data = {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Test response"}],
                "model": "test-model",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 3},
            }

            from unittest.mock import MagicMock

            if "anthropic" in primary.id:
                # Anthropic uses self.http_request() - patch at class level
                from analysi.integrations.framework.base import IntegrationAction

                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = mock_anthropic_data
                with mock_patch.object(
                    IntegrationAction,
                    "http_request",
                    new_callable=AsyncMock,
                    return_value=mock_resp,
                ):
                    result = await action.execute(prompt="Test prompt")
            else:
                # OpenAI still uses httpx.AsyncClient directly for LLM calls
                mock_response = httpx.Response(
                    status_code=200,
                    json=mock_response_data,
                    request=httpx.Request("POST", "https://example.com"),
                )
                with mock_patch(
                    "httpx.AsyncClient.post",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ):
                    result = await action.execute(prompt="Test prompt")

            assert result["status"] == "success"
            assert "response" in result["data"]

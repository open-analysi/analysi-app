"""Tests for LangGraph configuration module.

Verify configuration loading and dependency creation.
Removed filesystem skills tests - skills are now DB-only.
"""

import os
from unittest.mock import patch

import pytest

from analysi.agentic_orchestration.langgraph.config import (
    DEFAULT_MODEL,
    create_langgraph_llm,
)


class TestCreateLangGraphLLM:
    """Tests for create_langgraph_llm() function."""

    def test_create_langgraph_llm_uses_env_api_key(self):
        """LLM created with ANTHROPIC_API_KEY from environment."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-api-key-12345"}):
            llm = create_langgraph_llm()

            # ChatAnthropic stores the API key
            assert llm.anthropic_api_key.get_secret_value() == "test-api-key-12345"

    def test_create_langgraph_llm_default_model(self):
        """Default model is claude-sonnet-4-20250514."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-api-key"}):
            llm = create_langgraph_llm()

            assert llm.model == DEFAULT_MODEL
            assert llm.model == "claude-sonnet-4-20250514"

    def test_create_langgraph_llm_custom_model(self):
        """Can override model parameter."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-api-key"}):
            llm = create_langgraph_llm(model="claude-3-haiku-20240307")

            assert llm.model == "claude-3-haiku-20240307"

    def test_create_langgraph_llm_missing_api_key_raises(self):
        """Raises ValueError when ANTHROPIC_API_KEY is not set."""
        # Clear the API key from environment
        env_without_key = {
            k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"
        }
        with patch.dict(os.environ, env_without_key, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                create_langgraph_llm()


class TestConfigDefaults:
    """Tests for configuration default values."""

    def test_default_model_is_sonnet(self):
        """DEFAULT_MODEL is claude-sonnet-4-20250514."""
        assert DEFAULT_MODEL == "claude-sonnet-4-20250514"

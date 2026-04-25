"""Tests for LangGraph config deprecation warnings."""

import contextlib
import os
import warnings
from unittest.mock import patch


class TestLangGraphConfigDeprecation:
    """Test deprecation warnings for get_langgraph_llm()."""

    def test_get_langgraph_llm_emits_deprecation_warning(self):
        """T9: Test that get_langgraph_llm() emits DeprecationWarning."""
        # Set env var so function doesn't raise ValueError
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")

                from analysi.agentic_orchestration.langgraph.config import (
                    get_langgraph_llm,
                )

                # Call the deprecated function
                with contextlib.suppress(Exception):
                    get_langgraph_llm()

                # Check that deprecation warning was emitted
                deprecation_warnings = [
                    warning
                    for warning in w
                    if issubclass(warning.category, DeprecationWarning)
                ]
                assert len(deprecation_warnings) >= 1

                # Verify warning message mentions LangChainFactory
                warning_msg = str(deprecation_warnings[0].message)
                assert "deprecated" in warning_msg.lower()
                assert "LangChainFactory" in warning_msg

    def test_get_langgraph_llm_still_works(self):
        """Test that get_langgraph_llm() still works despite being deprecated."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)

                from analysi.agentic_orchestration.langgraph.config import (
                    get_langgraph_llm,
                )

                # Should still return an LLM instance
                with patch(
                    "analysi.agentic_orchestration.langgraph.config.ChatAnthropic"
                ) as mock_chat:
                    mock_chat.return_value = "mock-llm"
                    result = get_langgraph_llm()
                    assert result == "mock-llm"

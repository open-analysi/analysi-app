"""
Unit Tests for DefaultTaskExecutor Tool Loading.

Tests for all tool loading methods (TDD red->green->refactor cycle).
"""

from unittest.mock import patch

import pytest

from analysi.services.task_execution import DefaultTaskExecutor


class TestDefaultTaskExecutorToolLoading:
    """Unit tests for DefaultTaskExecutor tool loading functionality."""

    def test_load_tools_method_exists(self):
        """Test that _load_tools method exists - WILL FAIL."""
        executor = DefaultTaskExecutor()

        # This will fail because _load_tools raises NotImplementedError
        # Do NOT catch the exception - let it fail for TDD red->green
        tools = executor._load_tools()

        # If we get here, the method was implemented
        assert isinstance(tools, dict)
        assert len(tools) > 0

        # Should contain native functions from cy-language 0.12.1
        assert "len" in tools
        assert "log" in tools
        assert "from_json" in tools

    def test_configure_mcp_servers_method_exists(self):
        """Test that _configure_mcp_servers method exists - WILL FAIL."""
        executor = DefaultTaskExecutor()

        # This will fail because _configure_mcp_servers raises NotImplementedError
        # Do NOT catch the exception - let it fail for TDD red->green
        mcp_config = executor._configure_mcp_servers()

        # If we get here, the method was implemented
        # Can return None if no MCP servers configured
        assert mcp_config is None or isinstance(mcp_config, dict)

    @pytest.mark.asyncio
    async def test_execute_with_tool_loading_integration(self):
        """Test that execute method calls tool loading methods - WILL FAIL."""
        executor = DefaultTaskExecutor()

        # Simple Cy script that uses native functions
        cy_script = """
test_list = ["a", "b", "c"]
length = len(test_list)
return "List length: ${length}"
"""
        input_data = {}

        # This will fail because the tool loading methods raise NotImplementedError
        # The execute method calls _load_tools() and _configure_mcp_servers()
        # Do NOT catch the exception - let it fail for TDD red->green
        result = await executor.execute(cy_script, input_data)

        # If we get here, tool loading was implemented
        assert result["status"] == "completed"
        assert "List length: 3" in result["output"]


class TestDefaultTaskExecutorToolLoadingMocking:
    """Tests with mocked tool loading to verify method calls."""

    @pytest.mark.asyncio
    async def test_execute_calls_tool_loading_methods(self):
        """Test that execute method calls the tool loading methods - WILL FAIL."""
        executor = DefaultTaskExecutor()

        # Mock the tool loading methods to avoid NotImplementedError
        with (
            patch.object(executor, "_load_tools", return_value={}) as mock_load_tools,
            patch.object(
                executor, "_configure_mcp_servers", return_value=None
            ) as mock_configure_mcp,
        ):
            # This will still fail because the original methods are stubbed
            # But shows what we want to test
            cy_script = 'return "test"'
            input_data = {}

            try:
                await executor.execute(cy_script, input_data)

                # If we get here, the mocking worked
                mock_load_tools.assert_called_once()
                mock_configure_mcp.assert_called_once()

            except NotImplementedError as e:
                # This happens because our stubs raise NotImplementedError
                pytest.fail(f"Tool loading methods not implemented: {e}")

    def test_load_tools_returns_expected_structure(self):
        """Test the expected structure of tools dictionary - WILL FAIL."""
        executor = DefaultTaskExecutor()

        # This will fail because _load_tools raises NotImplementedError
        # Shows the expected behavior once implemented
        try:
            tools = executor._load_tools()

            # Expected tool categories
            assert isinstance(tools, dict)

            # Native functions should be present (cy-language 0.12.1)
            expected_native_functions = [
                "len",
                "log",
                "from_json",
                "to_json",
                "type::str",
            ]  # str is now registered as type::str
            for func_name in expected_native_functions:
                assert func_name in tools
                assert callable(tools[func_name])

            # LLM functions should be present (if OPENAI_API_KEY available)
            potential_llm_functions = [
                "llm_run",
                "llm_evaluate_results",
                "llm_give_feedback",
                "llm_revise_task",
            ]
            # At least some LLM functions should be available
            # We don't assert this because OPENAI_API_KEY might not be available
            # But we can check structure
            llm_funcs_available = any(func in tools for func in potential_llm_functions)
            # Just verify we can check for LLM functions even if not available
            assert isinstance(llm_funcs_available, bool)

        except NotImplementedError:
            pytest.fail("_load_tools not implemented - expected in TDD red phase")

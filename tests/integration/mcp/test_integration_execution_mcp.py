"""Integration tests for integration tool execution MCP tool."""

import pytest

from analysi.mcp import integration_tools


@pytest.mark.asyncio
@pytest.mark.integration
class TestIntegrationExecutionMCP:
    """Integration tests for execute_integration_tool MCP tool."""

    @pytest.mark.asyncio
    async def test_mcp_execute_tool_raw_output(self):
        """
        Test MCP tool execution without schema capture.

        capture_schema=False (default)
        Expected: Returns error since integration doesn't exist in test DB
        """
        result = await integration_tools.execute_integration_tool(
            integration_id="splunk",
            action_id="health_check",
            arguments={},
            capture_schema=False,
            timeout_seconds=30,
        )

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] == "error"
        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_mcp_execute_tool_with_schema_capture(self):
        """
        Test MCP tool execution with schema generation.

        capture_schema=True
        Expected: Returns error since integration doesn't exist in test DB
        """
        result = await integration_tools.execute_integration_tool(
            integration_id="splunk",
            action_id="health_check",
            arguments={},
            capture_schema=True,
            timeout_seconds=30,
        )

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] == "error"
        # output_schema should be None on error
        assert result.get("output_schema") is None

    @pytest.mark.asyncio
    async def test_mcp_execute_tool_error_handling(self):
        """
        Test MCP tool error responses.

        Invalid integration_id should return error gracefully
        """
        result = await integration_tools.execute_integration_tool(
            integration_id="nonexistent",
            action_id="nonexistent",
            arguments={},
            capture_schema=False,
            timeout_seconds=30,
        )

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] == "error"
        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_mcp_execute_tool_timeout_handling(self):
        """
        Test MCP tool timeout handling.

        Short timeout with nonexistent integration
        Expected: Error due to nonexistent integration (not timeout)
        """
        result = await integration_tools.execute_integration_tool(
            integration_id="splunk",
            action_id="health_check",
            arguments={},
            capture_schema=False,
            timeout_seconds=1,  # Very short timeout
        )

        assert isinstance(result, dict)
        assert "status" in result
        # Will error due to nonexistent integration before timeout
        assert result["status"] == "error"
        assert "execution_time_ms" in result

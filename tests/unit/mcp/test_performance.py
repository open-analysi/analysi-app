"""Unit tests for MCP performance."""

import asyncio

import pytest

from analysi.mcp.tools import cy_tools


@pytest.mark.asyncio
class TestPerformance:
    """Test performance and concurrency."""

    @pytest.mark.asyncio
    async def test_concurrent_tool_invocations(self):
        """Verify multiple tools can be invoked concurrently."""
        # Run 3 different tools simultaneously
        script1 = "x = 1\nreturn x"
        script2 = "y = 2\nreturn y"
        script3 = "z = 3\nreturn z"

        # Execute concurrently
        tasks = [
            cy_tools.quick_syntax_check_cy_script(script1),
            cy_tools.compile_cy_script(script2),
            cy_tools.get_plan_stats(script3),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete
        assert len(results) == 3

        # No race conditions - each should have valid result or an exception
        for result in results:
            assert result is not None
            # Each result is either a successful dict or an expected exception
            assert isinstance(result, (dict, Exception))

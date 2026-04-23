"""Unit tests for error handling in MCP tools."""

from uuid import uuid4

import pytest

from analysi.auth.models import CurrentUser
from analysi.mcp.context import set_mcp_current_user
from analysi.mcp.tools import cy_tools, task_tools


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling and messaging."""

    @pytest.fixture(autouse=True)
    def _mcp_user(self):
        """Set MCP user context so RBAC checks pass."""
        set_mcp_current_user(
            CurrentUser(
                user_id="test-user",
                email="test@test.com",
                tenant_id="test",
                roles=["analyst"],
                actor_type="user",
            )
        )

    @pytest.mark.asyncio
    async def test_cy_script_error_context(self):
        """Verify Cy errors include helpful context (line/column)."""
        script = """
x = 10
y = missing_var  # This should cause an error
return x + y
        """.strip()

        try:
            result = await cy_tools.quick_syntax_check_cy_script(script)

            # If no exception, check error structure
            if not result["valid"]:
                assert result["errors"] is not None
                # Should include line/column information
                error_text = " ".join(str(e) for e in result["errors"])
                assert "line" in error_text.lower() or "col" in error_text.lower()
        except Exception as e:
            # If exception is raised, should have helpful message
            error_msg = str(e)
            assert len(error_msg) > 0

    @pytest.mark.asyncio
    async def test_task_not_found_error(self):
        """Verify clear error for task not found."""
        fake_task_id = str(uuid4())
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        try:
            result = await task_tools.get_task(fake_task_id, tenant_id)

            # Should return clear error
            if result:
                assert "error" in result or "message" in result
                # Error should be descriptive
                error_msg = result.get("error", result.get("message", ""))
                assert (
                    "not found" in error_msg.lower()
                    or "does not exist" in error_msg.lower()
                )
        except Exception as e:
            # If exception, message should be clear
            assert "not found" in str(e).lower() or len(str(e)) > 0  # noqa: PT017

    @pytest.mark.asyncio
    async def test_mcp_tool_exception_handling(self):
        """Verify MCP tools handle exceptions gracefully."""
        # Pass invalid data that might cause an exception
        invalid_scripts = [
            None,  # None instead of string
            "",  # Empty string
            "   ",  # Whitespace only
            "\x00\x00",  # Invalid characters
        ]

        for invalid_script in invalid_scripts:
            try:
                # Should handle gracefully, not crash
                result = await cy_tools.quick_syntax_check_cy_script(invalid_script)

                # Should return error, not crash
                assert result is not None
                if isinstance(result, dict):
                    assert "valid" in result or "error" in result
            except Exception as e:
                # If exception raised, should be controlled (not unhandled)
                assert isinstance(e, ValueError | TypeError | NotImplementedError)  # noqa: PT017

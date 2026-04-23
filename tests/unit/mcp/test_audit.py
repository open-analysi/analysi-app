"""Unit tests for MCP audit utilities."""

from analysi.mcp.audit import (
    MAX_ARG_LENGTH,
    TRUNCATION_SUFFIX,
    prepare_mcp_audit_details,
    truncate_value,
)


class TestTruncateValue:
    """Tests for truncate_value function."""

    def test_short_string_not_truncated(self):
        """Short strings should remain unchanged."""
        value = "short string"
        result = truncate_value(value)
        assert result == value

    def test_long_string_truncated(self):
        """Long strings should be truncated with suffix."""
        long_value = "x" * 2000
        result = truncate_value(long_value)

        MAX_ARG_LENGTH - len(TRUNCATION_SUFFIX) + len(TRUNCATION_SUFFIX)
        assert len(result) == MAX_ARG_LENGTH
        assert result.endswith(TRUNCATION_SUFFIX)

    def test_non_string_values_unchanged(self):
        """Non-string values should pass through unchanged."""
        assert truncate_value(123) == 123
        assert truncate_value(3.14) == 3.14
        assert truncate_value(True) is True
        assert truncate_value(None) is None
        assert truncate_value(["a", "b"]) == ["a", "b"]
        assert truncate_value({"key": "value"}) == {"key": "value"}

    def test_custom_max_length(self):
        """Custom max_length should be respected."""
        value = "this is a medium length string"
        result = truncate_value(value, max_length=20)

        assert len(result) == 20
        assert result.endswith(TRUNCATION_SUFFIX)

    def test_exact_boundary(self):
        """String exactly at max_length should not be truncated."""
        value = "x" * MAX_ARG_LENGTH
        result = truncate_value(value)
        # At exact length, should NOT truncate
        assert result == value


class TestPrepareMcpAuditDetails:
    """Tests for prepare_mcp_audit_details function."""

    def test_basic_arguments(self):
        """Basic arguments should be captured correctly."""
        result = prepare_mcp_audit_details(
            tool_name="create_task",
            arguments={"name": "My Task", "description": "A test task"},
        )

        assert result["mcp_tool"] == "create_task"
        assert result["arguments"]["name"] == "My Task"
        assert result["arguments"]["description"] == "A test task"

    def test_none_values_excluded(self):
        """None values should be excluded from arguments."""
        result = prepare_mcp_audit_details(
            tool_name="create_task",
            arguments={"name": "My Task", "optional_field": None},
        )

        assert "name" in result["arguments"]
        assert "optional_field" not in result["arguments"]

    def test_long_script_truncated(self):
        """Long script content should be truncated."""
        long_script = "fn main() { " + "x" * 2000 + " }"
        result = prepare_mcp_audit_details(
            tool_name="create_task",
            arguments={"name": "My Task", "script": long_script},
        )

        assert len(result["arguments"]["script"]) == MAX_ARG_LENGTH
        assert result["arguments"]["script"].endswith(TRUNCATION_SUFFIX)

    def test_custom_max_length(self):
        """Custom max_length should be respected."""
        result = prepare_mcp_audit_details(
            tool_name="test_tool",
            arguments={"data": "x" * 100},
            max_arg_length=50,
        )

        assert len(result["arguments"]["data"]) == 50

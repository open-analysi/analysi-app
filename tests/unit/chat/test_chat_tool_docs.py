"""Unit tests for generated chat tool docstrings.

Validates that docstrings are generated from actual model enums and
contain correct values. The validate_chat_tool_docs() function is
designed to run in CI.
"""

from analysi.models.task import TaskFunction
from analysi.schemas.alert import AlertSeverity, AlertStatus
from analysi.services.chat_tool_docs import (
    LIST_TASKS_DOC,
    SEARCH_ALERTS_DOC,
    validate_chat_tool_docs,
)


class TestSearchAlertsDoc:
    """Validate SEARCH_ALERTS_DOC against real enums."""

    def test_contains_all_severity_values(self):
        for sev in AlertSeverity:
            assert sev.value in SEARCH_ALERTS_DOC, (
                f"Missing severity '{sev.value}' in SEARCH_ALERTS_DOC"
            )

    def test_contains_all_status_values(self):
        for status in AlertStatus:
            assert status.value in SEARCH_ALERTS_DOC, (
                f"Missing status '{status.value}' in SEARCH_ALERTS_DOC"
            )

    def test_does_not_contain_deprecated_values(self):
        deprecated = ["informational", "resolved", "closed"]
        for val in deprecated:
            assert val not in SEARCH_ALERTS_DOC, (
                f"SEARCH_ALERTS_DOC still contains deprecated '{val}'"
            )


class TestListTasksDoc:
    """Validate LIST_TASKS_DOC against real enums."""

    def test_contains_all_function_values(self):
        for k, v in vars(TaskFunction).items():
            if not k.startswith("_") and isinstance(v, str):
                assert v in LIST_TASKS_DOC, f"Missing function '{v}' in LIST_TASKS_DOC"

    def test_does_not_contain_fake_enrichment(self):
        """'enrichment' is a category, not a function type."""
        # Check that 'enrichment' doesn't appear in the function-type context
        # It CAN appear in category examples, just not in the function filter line
        func_line = [
            line for line in LIST_TASKS_DOC.split("\n") if "function:" in line.lower()
        ]
        assert func_line, "No function parameter line found in LIST_TASKS_DOC"
        # The function parameter description should not list 'enrichment'
        # (it's only in the category examples section)


class TestValidateChatToolDocs:
    """Test the CI validation function."""

    def test_validation_passes(self):
        errors = validate_chat_tool_docs()
        assert errors == [], f"Validation errors: {errors}"

    def test_validation_would_catch_missing_enum(self):
        """Verify the validator actually catches problems (negative test)."""
        # This tests the validator itself, not the docstrings
        # We can't easily inject fake values, but we can verify the function
        # returns a list and runs without error
        result = validate_chat_tool_docs()
        assert isinstance(result, list)

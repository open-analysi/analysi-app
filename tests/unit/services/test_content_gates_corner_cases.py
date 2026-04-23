"""Corner-case tests for content gate framework.

Covers edge cases in individual content gates, the python_ast_gate passthrough,
content_policy_gate integration, boundary conditions on content length,
and the all_gates_passed helper.
"""

from analysi.agentic_orchestration.langgraph.content_review.content_gates import (
    MAX_CONTENT_LENGTH,
    all_gates_passed,
    content_length_gate,
    empty_content_gate,
    format_gate,
    python_ast_gate,
    run_content_gates,
)
from analysi.schemas.content_review import ContentGateResult


class TestEmptyContentEdgeCases:
    """Edge cases for empty_content_gate."""

    def test_single_space(self):
        """Single space is whitespace-only, should fail."""
        errors = empty_content_gate(" ", "test.md")
        assert len(errors) == 1

    def test_newlines_only(self):
        """Only newlines should be treated as empty."""
        errors = empty_content_gate("\n\n\n", "test.md")
        assert len(errors) == 1

    def test_single_character(self):
        """A single non-whitespace character should pass."""
        errors = empty_content_gate("a", "test.md")
        assert errors == []

    def test_none_content(self):
        """None content is caught — will fail on `not content`."""
        # The gate uses `not content` which is True for None
        errors = empty_content_gate(None, "test.md")  # type: ignore[arg-type]
        assert len(errors) == 1


class TestContentLengthBoundary:
    """Boundary conditions on content length gate."""

    def test_exactly_at_limit(self):
        """Content at exactly MAX_CONTENT_LENGTH should pass."""
        content = "x" * MAX_CONTENT_LENGTH
        errors = content_length_gate(content, "test.md")
        assert errors == []

    def test_one_over_limit(self):
        """Content at MAX_CONTENT_LENGTH + 1 should fail."""
        content = "x" * (MAX_CONTENT_LENGTH + 1)
        errors = content_length_gate(content, "test.md")
        assert len(errors) == 1
        assert str(MAX_CONTENT_LENGTH) in errors[0].replace(",", "")

    def test_one_under_limit(self):
        """Content at MAX_CONTENT_LENGTH - 1 should pass."""
        content = "x" * (MAX_CONTENT_LENGTH - 1)
        errors = content_length_gate(content, "test.md")
        assert errors == []


class TestFormatGateEdgeCases:
    """Edge cases for format_gate."""

    def test_no_extension_passes(self):
        """File with no extension passes format_gate (blocked by zip import, not here)."""
        # format_gate only checks if ext exists and is blocked — no ext = no error
        errors = format_gate("content", "Makefile")
        assert errors == []

    def test_case_insensitive_extension(self):
        """Extensions should be case-insensitive."""
        errors = format_gate("content", "FILE.MD")
        assert errors == []

    def test_double_extension(self):
        """Double extension — only last one is checked."""
        errors = format_gate("content", "file.txt.exe")
        assert len(errors) == 1
        assert ".exe" in errors[0]

    def test_null_bytes_and_bad_extension(self):
        """Multiple errors: null bytes + bad extension."""
        errors = format_gate("content\x00binary", "file.exe")
        assert len(errors) == 2

    def test_hidden_file_with_valid_extension(self):
        """Hidden file (dot prefix) with valid extension should pass."""
        errors = format_gate("content", ".hidden.md")
        assert errors == []


class TestPythonAstGate:
    """The python_ast_gate passthrough for non-.py files."""

    def test_non_py_file_passes_through(self):
        """Non-.py files should always pass (no errors)."""
        for ext in [".md", ".txt", ".json"]:
            errors = python_ast_gate("import os\nos.system('ls')", f"file{ext}")
            assert errors == [], f"Expected passthrough for {ext}"

    def test_py_file_with_dangerous_code(self):
        """Python file with blocked import should fail."""
        errors = python_ast_gate("import os\nos.system('ls')", "script.py")
        assert len(errors) >= 1
        assert any("os" in e for e in errors)

    def test_py_file_safe_code(self):
        """Python file with safe code should pass."""
        errors = python_ast_gate("import json\ndata = json.loads('{}')", "safe.py")
        assert errors == []

    def test_py_file_syntax_error(self):
        """Python file with syntax error should report it."""
        errors = python_ast_gate("def foo(:\n  pass", "broken.py")
        assert len(errors) >= 1
        assert any("syntax" in e.lower() for e in errors)

    def test_case_insensitive_py_extension(self):
        """'.PY' extension should still trigger AST gate."""
        errors = python_ast_gate("import subprocess", "script.PY")
        assert len(errors) >= 1

    def test_empty_py_file(self):
        """Empty Python file should pass AST gate (valid Python)."""
        errors = python_ast_gate("", "empty.py")
        # Empty content is valid Python but may be caught by empty_content_gate
        # The python_ast_gate itself should pass for empty string
        # (though the gate pipeline will catch it via empty_content_gate)
        assert errors == [] or any("empty" in e.lower() for e in errors)


class TestAllGatesPassed:
    """Edge cases for the all_gates_passed helper."""

    def test_empty_results_list(self):
        """No checks = all passed (vacuous truth)."""
        assert all_gates_passed([]) is True

    def test_single_pass(self):
        result = ContentGateResult(check_name="test", passed=True, errors=[])
        assert all_gates_passed([result]) is True

    def test_single_fail(self):
        result = ContentGateResult(check_name="test", passed=False, errors=["bad"])
        assert all_gates_passed([result]) is False

    def test_mixed_results(self):
        """One pass + one fail = not all passed."""
        results = [
            ContentGateResult(check_name="ok", passed=True, errors=[]),
            ContentGateResult(check_name="bad", passed=False, errors=["err"]),
        ]
        assert all_gates_passed(results) is False


class TestRunContentGatesEdgeCases:
    """Edge cases for run_content_gates."""

    def test_empty_checks_list(self):
        """No checks to run should return empty results."""
        results = run_content_gates("content", "file.md", [])
        assert results == []

    def test_check_name_from_dunder(self):
        """Check name should be extracted from __name__ attribute."""

        def my_custom_check(content: str, filename: str) -> list[str]:
            return []

        results = run_content_gates("content", "file.md", [my_custom_check])
        assert results[0].check_name == "my_custom_check"

    def test_lambda_check_name(self):
        """Lambda check should get a usable name."""
        check = lambda content, filename: []  # noqa: E731
        results = run_content_gates("content", "file.md", [check])
        # Lambda has __name__ = "<lambda>"
        assert results[0].check_name == "<lambda>"
        assert results[0].passed is True

    def test_multiple_errors_from_single_check(self):
        """A single check can return multiple error strings."""

        def multi_error(content: str, filename: str) -> list[str]:
            return ["error 1", "error 2", "error 3"]

        results = run_content_gates("content", "file.md", [multi_error])
        assert len(results) == 1
        assert results[0].passed is False
        assert len(results[0].errors) == 3

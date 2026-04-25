"""Unit tests for content gate framework."""

from analysi.agentic_orchestration.langgraph.content_review.content_gates import (
    content_length_gate,
    empty_content_gate,
    format_gate,
    run_content_gates,
)


class TestEmptyContentGate:
    def test_rejects_empty_string(self):
        errors = empty_content_gate("", "test.md")
        assert len(errors) == 1
        assert "empty" in errors[0].lower()

    def test_rejects_whitespace_only(self):
        errors = empty_content_gate("   \n\t  ", "test.md")
        assert len(errors) == 1

    def test_passes_valid_content(self):
        errors = empty_content_gate("Hello world", "test.md")
        assert errors == []


class TestContentLengthGate:
    def test_rejects_oversized_content(self):
        errors = content_length_gate("x" * 51_000, "test.md")
        assert len(errors) == 1
        assert "50,000" in errors[0]

    def test_passes_normal_content(self):
        errors = content_length_gate("x" * 1000, "test.md")
        assert errors == []


class TestFormatGate:
    def test_rejects_blocked_extension(self):
        errors = format_gate("content", "malware.exe")
        assert len(errors) == 1
        assert ".exe" in errors[0]

    def test_passes_allowed_extension(self):
        for ext in [".md", ".txt", ".json", ".py"]:
            errors = format_gate("content", f"file{ext}")
            assert errors == [], f"Expected {ext} to pass"

    def test_rejects_null_bytes(self):
        errors = format_gate("content\x00binary", "file.md")
        assert len(errors) == 1
        assert "null bytes" in errors[0].lower()


class TestRunContentGates:
    def test_collects_all_errors(self):
        """Multiple gates, all errors are collected."""
        results = run_content_gates("", "test.exe", [empty_content_gate, format_gate])
        assert len(results) == 2
        # empty_content_gate should fail
        assert results[0].passed is False
        assert results[0].check_name == "empty_content_gate"
        # format_gate should fail (exe)
        assert results[1].passed is False
        assert results[1].check_name == "format_gate"

    def test_all_pass_when_valid(self):
        results = run_content_gates(
            "valid content", "test.md", [empty_content_gate, format_gate]
        )
        assert all(r.passed for r in results)

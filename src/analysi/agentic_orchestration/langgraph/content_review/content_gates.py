"""Content gate framework for content review pipelines.

Content gates are deterministic, fast checks that run before the LLM tier.
If any gate fails, the content is rejected with 422 immediately.

Each gate is a callable: (content: str, filename: str) -> list[str]
An empty list means the gate passed. Non-empty means violations found.
"""

from collections.abc import Callable

from analysi.schemas.content_review import ContentGateResult

# Type alias for content gates
ContentGate = Callable[[str, str], list[str]]

# Allowed file extensions for skill content
ALLOWED_EXTENSIONS = {".md", ".txt", ".json", ".py", ".cy"}

# Maximum content length (characters)
MAX_CONTENT_LENGTH = 50_000


def run_content_gates(
    content: str, filename: str, gates: list[ContentGate]
) -> list[ContentGateResult]:
    """Run all content gates and collect results.

    Args:
        content: The content to check.
        filename: Original filename (used for extension checks).
        gates: List of content gate callables.

    Returns:
        List of ContentGateResult objects, one per gate.
    """
    results = []
    for gate in gates:
        gate_name = getattr(gate, "__name__", gate.__class__.__name__)
        errors = gate(content, filename)
        results.append(
            ContentGateResult(
                check_name=gate_name,
                passed=len(errors) == 0,
                errors=errors,
            )
        )
    return results


def all_gates_passed(results: list[ContentGateResult]) -> bool:
    """Return True if all content gates passed."""
    return all(r.passed for r in results)


# Gates skipped for owner role on skill_validation — cybersecurity skills
# legitimately contain attack patterns (XSS, SQLi) and utility scripts.
OWNER_SKIPPED_GATES = {"content_policy_gate", "python_ast_gate"}


def filter_gates_for_owner(gates: list[ContentGate]) -> list[ContentGate]:
    """Remove content_policy_gate and python_ast_gate for owner bypass.

    Structural gates (empty, length, format) always run.
    """
    return [g for g in gates if getattr(g, "__name__", "") not in OWNER_SKIPPED_GATES]


# --- Built-in content gates ---


def empty_content_gate(content: str, filename: str) -> list[str]:
    """Reject empty or whitespace-only content."""
    if not content or not content.strip():
        return ["Content is empty or whitespace-only"]
    return []


def content_length_gate(content: str, filename: str) -> list[str]:
    """Reject content exceeding maximum length."""
    if len(content) > MAX_CONTENT_LENGTH:
        return [
            f"Content exceeds {MAX_CONTENT_LENGTH:,} characters "
            f"({len(content):,} chars)"
        ]
    return []


def format_gate(content: str, filename: str) -> list[str]:
    """Basic format validation: file extension and encoding."""
    import os

    errors = []

    _, ext = os.path.splitext(filename)
    if ext and ext.lower() not in ALLOWED_EXTENSIONS:
        errors.append(
            f"File extension {ext!r} not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Check for null bytes (binary content)
    if "\x00" in content:
        errors.append("Content contains null bytes (binary content not allowed)")

    return errors


def content_policy_gate(content: str, filename: str) -> list[str]:
    """AI content policy check — flags suspicious or malicious patterns."""
    from analysi.agentic_orchestration.content_policy import (
        check_suspicious_content,
    )

    issues = check_suspicious_content(content)
    return [f"Content policy violation: {issue}" for issue in issues]


def python_ast_gate(content: str, filename: str) -> list[str]:
    """Run AST-based static analysis on Python files.

    For non-.py files, this is a passthrough (no errors).
    """
    import os

    _, ext = os.path.splitext(filename)
    if ext.lower() != ".py":
        return []

    from analysi.services.python_script_analyzer import analyze_python_script

    result = analyze_python_script(content)
    if not result.safe:
        return [f"Python safety violation: {issue}" for issue in result.issues]
    return []

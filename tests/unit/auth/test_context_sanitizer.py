"""Unit tests for centralized execution context sanitization."""

from analysi.auth.context_sanitizer import (
    PROTECTED_CONTEXT_KEYS,
    sanitize_execution_context,
)


class TestSanitizeExecutionContext:
    """Verify sanitize_execution_context strips protected keys correctly."""

    def test_strips_tenant_id(self):
        ctx = {"tenant_id": "evil-tenant", "analysis_id": "keep-me"}
        result = sanitize_execution_context(ctx)
        assert "tenant_id" not in result
        assert result["analysis_id"] == "keep-me"

    def test_strips_session(self):
        ctx = {"session": "injected-session"}
        result = sanitize_execution_context(ctx)
        assert "session" not in result

    def test_strips_all_identity_keys(self):
        """Every key from PROTECTED_CONTEXT_KEYS must be removed."""
        ctx = {key: f"injected-{key}" for key in PROTECTED_CONTEXT_KEYS}
        ctx["legit_key"] = "pass-through"
        result = sanitize_execution_context(ctx)

        for key in PROTECTED_CONTEXT_KEYS:
            assert key not in result, f"Protected key '{key}' was not stripped"
        assert result["legit_key"] == "pass-through"

    def test_strips_runtime_keys(self):
        """Runtime keys added in Round 14 must also be stripped."""
        ctx = {
            "knowledge_units": ["injected"],
            "available_tools": ["evil_tool"],
            "llm_model": "attacker-model",
            "runtime_version": "fake-version",
        }
        result = sanitize_execution_context(ctx)
        assert result == {}

    def test_passes_legitimate_keys(self):
        ctx = {
            "analysis_id": "analysis-123",
            "alert_id": "alert-456",
            "custom_key": "custom_value",
        }
        result = sanitize_execution_context(ctx)
        assert result == ctx

    def test_returns_empty_dict_for_none(self):
        assert sanitize_execution_context(None) == {}

    def test_returns_empty_dict_for_empty(self):
        assert sanitize_execution_context({}) == {}

    def test_does_not_mutate_input(self):
        ctx = {"tenant_id": "evil", "keep": "yes"}
        sanitize_execution_context(ctx)
        assert "tenant_id" in ctx, "Original dict should not be mutated"

    def test_protected_keys_is_frozenset(self):
        """Ensure PROTECTED_CONTEXT_KEYS cannot be accidentally mutated."""
        assert isinstance(PROTECTED_CONTEXT_KEYS, frozenset)

    def test_protected_keys_comprehensive(self):
        """Verify all expected keys are in the protected set."""
        expected = {
            "tenant_id",
            "task_id",
            "task_run_id",
            "workflow_run_id",
            "workflow_node_instance_id",
            "session",
            "directive",
            "app",
            "cy_name",
            "knowledge_units",
            "available_tools",
            "llm_model",
            "runtime_version",
        }
        assert expected == PROTECTED_CONTEXT_KEYS

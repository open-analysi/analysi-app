"""Centralized execution context sanitization.

Strips identity and runtime keys from user-supplied execution_context
to prevent cross-tenant pivots and privilege escalation.
"""

from typing import Any

# Keys set by trusted server code (ExecutionContext.build_context and runtime).
# User-supplied execution_context must never override these.
PROTECTED_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        # Identity — set by build_context from authenticated request
        "tenant_id",
        "task_id",
        "task_run_id",
        "workflow_run_id",
        "workflow_node_instance_id",
        "session",
        # Task metadata — resolved from DB, not user input
        "directive",
        "app",
        "cy_name",
        # Runtime — set by the execution engine
        "knowledge_units",
        "available_tools",
        "llm_model",
        "runtime_version",
    }
)


def sanitize_execution_context(ctx: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of *ctx* with all protected keys removed.

    Returns an empty dict when *ctx* is None or empty.
    """
    if not ctx:
        return {}
    return {k: v for k, v in ctx.items() if k not in PROTECTED_CONTEXT_KEYS}

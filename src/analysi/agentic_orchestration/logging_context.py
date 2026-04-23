"""Structured logging with context for workflow generation and alert analysis.

Provides contextual loggers that automatically add prefixes to all log messages,
making it easy to trace execution through different stages, tasks, tenants, and alerts.

Example output (workflow generation):
    [TASK_BUILDING|task-0] Building task: VirusTotal IP Reputation (new)
    [TASK_BUILDING|task-1] Building task: AbuseIPDB Lookup (new)
    [WORKFLOW_ASSEMBLY] Assembling workflow from 5 tasks: ['task1', 'task2', ...]

Example output (alert analysis):
    [acme] Starting alert analysis pipeline
    [acme|alert-1de35905] Fetching alert from database
    [test-tenant-xyz|alert-1de35905] Alert not found (likely test cleanup race)
"""

import logging
from typing import Any

from analysi.agentic_orchestration.observability import WorkflowGenerationStage
from analysi.config.logging import get_logger


class ContextAdapter(logging.LoggerAdapter):
    """Logger adapter that adds context prefix to all log messages.

    Supports both workflow generation context (stage|task_id) and
    alert analysis context (tenant_id|alert_id).
    """

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        """Add context prefix to log message.

        Args:
            msg: Original log message
            kwargs: Log call keyword arguments

        Returns:
            Tuple of (prefixed_message, kwargs)
        """
        extra = self.extra or {}
        # Workflow generation context (stage and optional task_id)
        stage = extra.get("stage")
        task_id = extra.get("task_id")

        # Alert analysis context (tenant_id and optional alert_id)
        tenant_id = extra.get("tenant_id")
        alert_id = extra.get("alert_id")

        # Build prefix based on available context
        if stage:
            # Workflow generation: [STAGE|task-id] or [STAGE]
            prefix = f"[{stage}|{task_id}]" if task_id else f"[{stage}]"
        elif tenant_id:
            # Alert analysis: [tenant|alert-id] or [tenant]
            prefix = f"[{tenant_id}|{alert_id}]" if alert_id else f"[{tenant_id}]"
        else:
            # Fallback: no context
            prefix = "[UNKNOWN]"

        return f"{prefix} {msg}", kwargs


def get_stage_logger(
    stage: WorkflowGenerationStage,
    task_id: str | None = None,
    base_logger: logging.Logger | None = None,
) -> logging.LoggerAdapter:
    """Get a logger with stage and task context.

    Creates a logger that automatically prefixes all messages with stage
    and optional task identifier for easier log tracing.

    Args:
        stage: Current workflow generation stage
        task_id: Optional task identifier (e.g., "task-0" for parallel tasks)
        base_logger: Base logger to wrap (defaults to module logger)

    Returns:
        Logger adapter with contextual prefixes

    Example:
        >>> logger = get_stage_logger(WorkflowGenerationStage.TASK_BUILDING, "task-2")
        >>> logger.info("Starting execution")
        [TASK_BUILDING|task-2] Starting execution

        >>> logger = get_stage_logger(WorkflowGenerationStage.WORKFLOW_ASSEMBLY)
        >>> logger.info("Composing workflow")
        [WORKFLOW_ASSEMBLY] Composing workflow
    """
    if base_logger is None:
        base_logger = get_logger("analysi.agentic_orchestration")

    # Use stage value (string) for cleaner logs
    stage_name = stage.value.upper()

    extra = {"stage": stage_name}
    if task_id:
        extra["task_id"] = task_id

    return ContextAdapter(base_logger, extra)


def get_pipeline_logger(
    tenant_id: str,
    alert_id: str | None = None,
    base_logger: logging.Logger | None = None,
) -> logging.LoggerAdapter:
    """Get a logger with tenant and alert context for alert analysis pipeline.

    Creates a logger that automatically prefixes all messages with tenant
    and optional alert identifier for easier log tracing.

    Args:
        tenant_id: Tenant identifier (e.g., "acme", "test-tenant-xyz")
        alert_id: Optional alert identifier (e.g., "1de35905-349e-4f17-97e1-4084a82d306a")
        base_logger: Base logger to wrap (defaults to alert_analysis logger)

    Returns:
        Logger adapter with contextual prefixes

    Example:
        >>> logger = get_pipeline_logger("acme", "1de35905-349e-4f17-97e1-4084a82d306a")
        >>> logger.info("Starting pipeline execution")
        [acme|alert-1de35905] Starting pipeline execution

        >>> logger = get_pipeline_logger("test-tenant-xyz")
        >>> logger.warning("Alert not found")
        [test-tenant-xyz] Alert not found
    """
    if base_logger is None:
        base_logger = get_logger("analysi.alert_analysis")

    # Truncate alert_id to first 8 chars for readability
    short_alert = None
    if alert_id:
        short_alert = (
            f"alert-{alert_id[:8]}" if len(alert_id) > 8 else f"alert-{alert_id}"
        )

    extra = {"tenant_id": tenant_id}
    if short_alert:
        extra["alert_id"] = short_alert

    return ContextAdapter(base_logger, extra)


def extract_task_id_from_run_id(run_id: str) -> str | None:
    """Extract task identifier from workspace run_id.

    Workspace run_ids for parallel tasks follow pattern:
    '{base_run_id}-task-{idx}'

    Args:
        run_id: Workspace run_id

    Returns:
        Task identifier (e.g., "task-0") or None if not a parallel task

    Example:
        >>> extract_task_id_from_run_id("abc123-task-0")
        "task-0"
        >>> extract_task_id_from_run_id("abc123")
        None
    """
    if "-task-" in run_id:
        # Extract "task-{idx}" from end of run_id
        parts = run_id.split("-task-")
        if len(parts) >= 2:
            return f"task-{parts[-1]}"
    return None


def get_skillsir_logger(
    iteration: int | None = None,
    objective: str | None = None,
    base_logger: logging.Logger | None = None,
) -> logging.LoggerAdapter:
    """Get a logger with SkillsIR context.

    Creates a logger that automatically prefixes all messages with
    [SKILLSIR] or [SKILLSIR|iter-{n}] for easier log tracing.

    Args:
        iteration: Current iteration number (0-indexed)
        objective: The retrieval objective (truncated in logs)
        base_logger: Base logger to wrap (defaults to langgraph.skills logger)

    Returns:
        Logger adapter with contextual prefixes

    Example:
        >>> logger = get_skillsir_logger(iteration=2)
        >>> logger.info("Checking if enough context")
        [SKILLSIR|iter-3] Checking if enough context

        >>> logger = get_skillsir_logger()
        >>> logger.info("Starting retrieval")
        [SKILLSIR] Starting retrieval
    """
    if base_logger is None:
        base_logger = get_logger("analysi.agentic_orchestration.langgraph.skills")

    extra: dict[str, Any] = {}

    # Build context for adapter
    if iteration is not None:
        # Display as 1-indexed for human readability
        extra["skillsir_iteration"] = iteration + 1
    if objective:
        # Truncate long objectives
        extra["skillsir_objective"] = (
            objective[:50] + "..." if len(objective) > 50 else objective
        )

    return SkillsIRContextAdapter(base_logger, extra)


class SkillsIRContextAdapter(logging.LoggerAdapter):
    """Logger adapter for SkillsIR with iteration context."""

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        """Add SkillsIR context prefix to log message."""
        extra = self.extra or {}
        iteration = extra.get("skillsir_iteration")

        if iteration is not None:
            prefix = f"[SKILLSIR|iter-{iteration}]"
        else:
            prefix = "[SKILLSIR]"

        return f"{prefix} {msg}", kwargs

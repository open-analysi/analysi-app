"""Base protocol and types for pluggable workflow generation stages.

This module defines the StageStrategy protocol that all stage implementations
must follow. The framework handles timing, callbacks, and metrics aggregation.
"""

from typing import Any, Protocol

from analysi.agentic_orchestration.observability import WorkflowGenerationStage


class StageStrategy(Protocol):
    """Protocol for workflow generation stage implementations.

    Stages are simple - they receive state and return state updates.
    The framework handles:
    - Timing measurement (duration_ms)
    - Callback invocations (on_stage_start, on_stage_complete)
    - Metrics aggregation
    - Error handling
    """

    stage: WorkflowGenerationStage

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute the stage and return state updates.

        Args:
            state: Current orchestration state containing:
                - alert: alert data
                - tenant_id: Tenant identifier
                - run_id: Unique run identifier
                - Plus any outputs from previous stages

        Returns:
            State updates dict. May include SDK_METRICS_KEY for agent stages.
            Framework handles timing, callbacks, and metrics aggregation.
        """
        ...


# Reserved state key for SDK metrics (agent stages only)
# When present in stage output, framework extracts and uses these metrics
SDK_METRICS_KEY = "_sdk_metrics"

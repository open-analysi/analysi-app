"""REST API client for Task Generations.

This client is used by the orchestration layer via dependency injection.
Per CLAUDE.md: orchestration must NOT access DB directly; use REST API clients.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from analysi.common.internal_auth import internal_auth_headers
from analysi.common.internal_client import InternalAsyncClient
from analysi.common.retry_config import http_retry_policy
from analysi.config.logging import get_logger
from analysi.models.auth import SYSTEM_USER_ID
from analysi.schemas.task_generation import TaskGenerationStatus

if TYPE_CHECKING:
    from analysi.agentic_orchestration.observability import (
        StageExecutionMetrics,
        WorkflowGenerationStage,
    )

logger = get_logger(__name__)


class TaskGenerationApiClient:
    """Client for TaskGeneration REST API - used by orchestration via DI.

    Implements best-effort updates: progress/status failures are logged but
    don't fail the overall task building process.
    """

    def __init__(
        self,
        api_base_url: str,
        tenant_id: str,
        generation_id: str | None = None,
    ):
        """Initialize client with API connection info.

        Args:
            api_base_url: Base URL for REST API (e.g., "http://api:8000")
            tenant_id: Tenant identifier
            generation_id: Parent WorkflowGeneration UUID (None for standalone builds)
        """
        self.api_base_url = api_base_url
        self.tenant_id = tenant_id
        self.generation_id = generation_id
        self._timeout = httpx.Timeout(30.0, connect=5.0)

    @property
    def _headers(self) -> dict[str, str]:
        """Compute per-call so actor from contextvars is always current."""
        return internal_auth_headers()

    @http_retry_policy()
    async def create_run(
        self,
        input_context: dict[str, Any],
        created_by: str = str(SYSTEM_USER_ID),
    ) -> str:
        """Create a TaskGeneration record.

        Args:
            input_context: Full context {proposal, alert, runbook}
            created_by: User/system that triggered the run

        Returns:
            run_id: UUID of created TaskGeneration

        Raises:
            HTTPStatusError: On API errors after retries
            TimeoutException: On timeout after retries
        """
        url = f"{self.api_base_url}/v1/{self.tenant_id}/task-generations-internal"

        payload: dict[str, Any] = {
            "input_context": input_context,
            "created_by": created_by,
        }
        if self.generation_id is not None:
            payload["workflow_generation_id"] = self.generation_id

        async with InternalAsyncClient(
            timeout=self._timeout, headers=self._headers
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

            data = response.json()
            run_id = data["id"]

            logger.info(
                "created_task_generation",
                run_id=run_id,
                generation_id=self.generation_id,
            )
            return run_id

    async def append_progress(
        self,
        run_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Append progress messages to a TaskGeneration.

        Best-effort: failures are logged but don't raise exceptions.
        Messages should have format: {timestamp, message, level, details}

        Args:
            run_id: TaskGeneration UUID
            messages: List of progress messages to append
        """
        url = f"{self.api_base_url}/v1/{self.tenant_id}/task-generations-internal/{run_id}/progress"

        payload = {"messages": messages}

        try:
            async with InternalAsyncClient(
                timeout=self._timeout, headers=self._headers
            ) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                logger.debug(
                    "appended_progress_messages",
                    message_count=len(messages),
                    run_id=run_id,
                )
        except Exception as e:
            # Best-effort: log and continue
            logger.warning(
                "failed_to_append_progress",
                run_id=run_id,
                error=str(e),
            )

    async def update_status(
        self,
        run_id: str,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Update TaskGeneration status and optionally result.

        Best-effort: failures are logged but don't raise exceptions.

        Args:
            run_id: TaskGeneration UUID
            status: New status (new, in_progress, completed, failed, cancelled)
            result: Optional result dict:
                    - Success: {task_id, cy_name, recovered}
                    - Failure: {error, error_type, recovered}
        """
        url = f"{self.api_base_url}/v1/{self.tenant_id}/task-generations-internal/{run_id}/status"

        payload: dict[str, Any] = {"status": status}
        if result is not None:
            payload["result"] = result

        try:
            async with InternalAsyncClient(
                timeout=self._timeout, headers=self._headers
            ) as client:
                response = await client.patch(url, json=payload)
                response.raise_for_status()
                logger.info(
                    "updated_task_generation_status_to", run_id=run_id, status=status
                )
        except Exception as e:
            # Best-effort: log and continue
            logger.warning(
                "task_generation_status_update_failed", run_id=run_id, error=str(e)
            )

    async def mark_running(self, run_id: str) -> None:
        """Convenience method to mark a run as running."""
        await self.update_status(run_id, TaskGenerationStatus.RUNNING)

    # Backward-compatible alias
    mark_in_progress = mark_running

    async def mark_completed(
        self,
        run_id: str,
        task_id: str,
        cy_name: str,
        recovered: bool = False,
    ) -> None:
        """Convenience method to mark a run as completed with task result."""
        await self.update_status(
            run_id,
            "completed",
            result={
                "task_id": task_id,
                "cy_name": cy_name,
                "recovered": recovered,
            },
        )

    async def mark_failed(
        self,
        run_id: str,
        error: str,
        error_type: str | None = None,
        recovered: bool = False,
    ) -> None:
        """Convenience method to mark a run as failed with error details."""
        await self.update_status(
            run_id,
            "failed",
            result={
                "error": error,
                "error_type": error_type or "UnknownError",
                "recovered": recovered,
            },
        )


class TaskGenerationProgressCallback:
    """Progress callback that pushes tool calls to TaskGeneration via REST API.

    Implements the ProgressCallback protocol but only handles on_tool_call.
    Stage lifecycle methods are no-ops since we handle those separately.
    """

    def __init__(
        self,
        client: TaskGenerationApiClient,
        run_id: str,
    ):
        """Initialize callback.

        Args:
            client: REST API client for task generations
            run_id: TaskGeneration UUID to push progress to
        """
        self.client = client
        self.run_id = run_id

    async def on_stage_start(
        self, stage: WorkflowGenerationStage, metadata: dict[str, Any]
    ) -> None:
        """No-op - stage lifecycle handled separately."""
        pass

    async def on_stage_complete(
        self,
        stage: WorkflowGenerationStage,
        result: Any,
        metrics: StageExecutionMetrics,
    ) -> None:
        """No-op - stage lifecycle handled separately."""
        pass

    async def on_stage_error(
        self,
        stage: WorkflowGenerationStage,
        error: Exception,
        partial_result: Any = None,
    ) -> None:
        """No-op - stage lifecycle handled separately."""
        pass

    async def on_tool_call(
        self,
        stage: WorkflowGenerationStage,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> None:
        """Push tool call to progress_messages via REST API."""
        # Format tool input for display (truncate long values)
        input_summary = self._summarize_tool_input(tool_name, tool_input)

        await self.client.append_progress(
            self.run_id,
            [
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "message": f"Tool call: {tool_name}",
                    "level": "info",
                    "details": {"input": input_summary},
                }
            ],
        )

    async def on_tool_result(
        self,
        stage: WorkflowGenerationStage,
        tool_name: str,
        tool_result: Any,
        is_error: bool,
    ) -> None:
        """No-op - we only track tool calls, not results (too verbose)."""
        pass

    async def on_workspace_created(self, workspace_path: str) -> None:
        """Push workspace creation to progress_messages."""
        await self.client.append_progress(
            self.run_id,
            [
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "message": f"Workspace created: {workspace_path}",
                    "level": "info",
                    "details": {},
                }
            ],
        )

    def _summarize_tool_input(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Summarize tool input for progress messages.

        Truncates long values and extracts key information.
        """
        if tool_name == "TodoWrite":
            # Extract just the todo content, not full structure
            todos = tool_input.get("todos", [])
            return {
                "todos": [
                    {"content": t.get("content", ""), "status": t.get("status", "")}
                    for t in todos[:5]  # Limit to first 5 todos
                ]
            }
        if tool_name == "Write":
            # Just show file path, not content
            return {"file_path": tool_input.get("file_path", "")}
        if tool_name == "Edit" or tool_name == "Read":
            return {"file_path": tool_input.get("file_path", "")}
        if tool_name == "Bash":
            cmd = tool_input.get("command", "")
            return {"command": cmd[:200] if len(cmd) > 200 else cmd}
        # Generic: truncate string values
        summary = {}
        for key, value in list(tool_input.items())[:5]:
            if isinstance(value, str) and len(value) > 100:
                summary[key] = value[:100] + "..."
            else:
                summary[key] = value
        return summary


# Backward-compatible aliases
TaskBuildingRunApiClient = TaskGenerationApiClient
TaskBuildingProgressCallback = TaskGenerationProgressCallback

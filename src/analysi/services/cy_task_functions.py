"""
Cy Native Functions for Task Composition.

Provides task_run() function for Cy scripts to call other Cy scripts.

## Subroutine Model

Nested task_run("subtask") calls are SUBROUTINES of the originating task,
not independent task executions. This means:

- No new TaskRun DB record is created for the nested call
- The nested script shares the parent's task_run_id, tenant_id,
  workflow_run_id, and AsyncSession
- Any artifacts created by the subtask are attributed to the parent's
  task_run_id — they are part of the same unit of work
- All DB writes (KU tables, artifacts) commit atomically with the parent
- If the parent task fails, the subtask's writes roll back too (correct)
- The session in execution_context is intentional correct transactional
  scoping, NOT coupling — do not remove it

This model is analogous to a function call: task_run("subtask") is like
calling a helper function defined in another file. The caller's identity
and transaction scope are preserved throughout.

Concurrency operates at the workflow node level, where
each node is a SEPARATE top-level task with its own isolated session.
Subroutine calls within a single task remain sequential and share the
parent's session.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger

logger = get_logger(__name__)

# Maximum recursion depth for task composition
MAX_TASK_RECURSION_DEPTH = 10


class CyTaskFunctions:
    """Native functions for Task composition in Cy scripts."""

    def __init__(
        self, session: AsyncSession, tenant_id: str, execution_context: dict[str, Any]
    ):
        """
        Initialize Task functions with database session and context.

        Args:
            session: Database session for task operations
            tenant_id: Tenant identifier for isolation
            execution_context: Full execution context (must be propagated)
        """
        self.session = session
        self.tenant_id = tenant_id
        self.execution_context = execution_context

    async def task_run(
        self, task_name: str, input_data: dict = None, full_result: bool = False
    ) -> dict:
        """
        Execute another task by its cy_name.

        This is the core function for task composition in Cy scripts.
        Follows the naming pattern of llm_run() and spl_run().

        Args:
            task_name: The cy_name of the task to execute
            input_data: Input data to pass to the task
            full_result: If True, return the entire execution context including status,
                        execution_time, etc. If False (default), return only the output

        Returns:
            If full_result=False: The task's output directly
            If full_result=True: Dict containing the full execution results with
                                status, output, execution_time, error (if failed)

        Raises:
            RecursionError: If maximum recursion depth is exceeded
            ValueError: If task not found or not enabled
        """
        # 1. Check recursion depth limit
        current_depth = self.execution_context.get("task_call_depth", 0)
        if current_depth >= MAX_TASK_RECURSION_DEPTH:
            raise RecursionError(
                f"Maximum task recursion depth ({MAX_TASK_RECURSION_DEPTH}) exceeded"
            )

        # 2. Look up task by cy_name
        from sqlalchemy import select

        from analysi.models.component import Component, ComponentKind
        from analysi.models.task import Task
        from analysi.repositories.task import TaskRepository

        task_repo = TaskRepository(self.session)

        # First try to find in the current app context
        current_app = self.execution_context.get("app", "default")
        task = await task_repo.get_task_by_cy_name(
            tenant_id=self.tenant_id, cy_name=task_name, app=current_app
        )

        # If not found in current app, search across all apps
        if not task:
            stmt = (
                select(Task)
                .join(Component)
                .where(
                    Component.tenant_id == self.tenant_id,
                    Component.cy_name == task_name,
                    Component.kind == ComponentKind.TASK,
                )
            )
            result = await self.session.execute(stmt)
            task = result.scalar_one_or_none()

            # Load the component relationship
            if task:
                await self.session.refresh(task, ["component"])

        if not task:
            raise ValueError(
                f"Task with cy_name '{task_name}' not found in tenant '{self.tenant_id}'"
            )

        # 3. Verify task is enabled
        if task.component.status != "enabled":
            raise ValueError(
                f"Task '{task_name}' is not enabled (status: {task.component.status})"
            )

        # 4. Create new execution context with ALL parent context
        child_context = dict(self.execution_context)
        child_context["task_call_depth"] = current_depth + 1
        child_context["parent_task_name"] = task_name
        # CRITICAL: Update app context to match the task being executed
        child_context["app"] = task.component.app
        child_context["task_id"] = str(task.component_id)
        # Use the child task's directive, not the parent's
        child_context["directive"] = task.directive

        # 5. Execute the task's Cy script
        logger.info(
            "executing_task",
            task_name=task_name,
            input_data=input_data,
            depth=child_context["task_call_depth"],
        )

        # Import task executor to run the Cy script
        from analysi.services.task_execution import DefaultTaskExecutor

        executor = DefaultTaskExecutor()

        # Execute the task's Cy script with the child context
        result = await executor.execute(
            cy_script=task.script,
            input_data=input_data or {},
            execution_context=child_context,
        )

        # 6. Return results based on full_result flag
        if full_result:
            # Return the complete execution context
            return result
        # Default behavior: return just the output
        # If the task failed, still return the full result so errors are visible
        if result.get("status") == "failed":
            return result
        return result.get("output")


def create_cy_task_functions(
    session: AsyncSession, tenant_id: str, execution_context: dict[str, Any]
) -> dict[str, Any]:
    """
    Create dictionary of task functions for Cy interpreter.

    Args:
        session: Database session
        tenant_id: Tenant identifier
        execution_context: Full execution context to propagate

    Returns:
        Dictionary mapping function names to callables
    """
    task_functions = CyTaskFunctions(session, tenant_id, execution_context)

    # Create wrapper for Cy compatibility
    async def task_run_wrapper(
        task_name: str, input_data: dict = None, full_result: bool = False
    ) -> dict:
        """Cy-compatible wrapper for task_run."""
        return await task_functions.task_run(task_name, input_data or {}, full_result)

    return {
        "task_run": task_run_wrapper,
    }

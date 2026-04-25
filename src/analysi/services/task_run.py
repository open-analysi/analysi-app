"""
TaskRun Service

Service layer for task execution management.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select

from analysi.auth.context_sanitizer import sanitize_execution_context
from analysi.constants import TaskConstants
from analysi.models.task_run import TaskRun
from analysi.services.storage import StorageManager
from analysi.services.task_execution import ExecutionContext


class TaskRunService:
    """Service for managing task run lifecycle."""

    def __init__(self):
        self.storage_manager = StorageManager()
        self.repository = TaskRunRepository()

    async def create_execution(
        self,
        session,
        tenant_id: str,
        task_id: UUID | None,
        cy_script: str | None,
        input_data: Any,  # Accept any JSON-serializable type to support fan-in arrays
        executor_config: dict[str, Any] | None = None,
        workflow_run_id: UUID | None = None,  # Link to parent workflow run
        workflow_node_instance_id: UUID | None = None,  # Link to specific node instance
        execution_context: (
            dict[str, Any] | None
        ) = None,  # Context from workflow (e.g., analysis_id)
    ) -> TaskRun:
        """
        Create a new task run for execution.

        Args:
            session: Database session
            tenant_id: Tenant identifier
            task_id: Task ID (None for ad-hoc execution)
            cy_script: Cy script (for ad-hoc execution)
            input_data: Input data for the task
            executor_config: Executor configuration
            workflow_run_id: Link to parent workflow run
            workflow_node_instance_id: Link to specific node instance
            execution_context: Context from workflow (e.g., analysis_id for artifact linking)

        Returns:
            Created TaskRun instance
        """
        # Build base execution context and merge with passed context
        base_context = ExecutionContext.build_context(
            tenant_id=tenant_id,
            task_id=str(task_id) if task_id else None,
            workflow_run_id=str(workflow_run_id) if workflow_run_id else None,
            workflow_node_instance_id=(
                str(workflow_node_instance_id) if workflow_node_instance_id else None
            ),
            available_kus=[],
        )

        # Merge passed execution_context (e.g., analysis_id) into base context.
        # SECURITY: Strip keys that control identity/runtime — these are set
        # by trusted code (build_context) and must not be user-overridable.
        if execution_context:
            base_context.update(sanitize_execution_context(execution_context))

        # Create TaskRun instance
        task_run = TaskRun(
            tenant_id=tenant_id,
            task_id=task_id,
            workflow_run_id=workflow_run_id,  # Link to parent workflow
            workflow_node_instance_id=workflow_node_instance_id,  # Link to node instance
            cy_script=cy_script,
            status=TaskConstants.Status.RUNNING,
            started_at=datetime.now(UTC),
            executor_config=executor_config or {},
            execution_context=base_context,
        )

        # Store input data
        await self.store_input_data(task_run, input_data)

        # Save to database
        task_run = await self.repository.create(session, task_run)

        return task_run

    async def update_status(
        self,
        session,
        task_run_id: UUID,
        status: str,
        output_data: dict[str, Any] | None = None,
        error_info: dict[str, Any] | None = None,
        llm_usage: Any | None = None,
    ) -> None:
        """
        Update task run status and results.

        Args:
            session: Database session
            task_run_id: Task run identifier
            status: New status (running, completed, failed, paused_by_user)
            output_data: Output data (for completed status)
            error_info: Error information (for failed status)
            llm_usage: LLMUsage dataclass with token counts and cost
        """
        from analysi.services.task_execution import DurationCalculator

        # Get the task run
        stmt = select(TaskRun).where(TaskRun.id == task_run_id)
        result = await session.execute(stmt)
        task_run = result.scalar_one_or_none()

        if not task_run:
            raise ValueError(f"TaskRun with id {task_run_id} not found")

        # Update status
        task_run.status = status

        # Set end time and calculate duration for completed statuses
        if status in (TaskConstants.Status.COMPLETED, TaskConstants.Status.FAILED):
            task_run.completed_at = datetime.now(UTC)
            task_run.duration = DurationCalculator.calculate(
                task_run.started_at, task_run.completed_at
            )

        # HITL: extract checkpoint into execution_context
        # BEFORE storing output, so output_location gets the clean status
        # object and the checkpoint blob only lives in execution_context.
        if (
            output_data
            and isinstance(output_data, dict)
            and "_hitl_checkpoint" in output_data
        ):
            ctx = dict(task_run.execution_context or {})
            ctx["_hitl_checkpoint"] = output_data["_hitl_checkpoint"]
            task_run.execution_context = ctx
            # Strip checkpoint from output — it's internal, not user-facing
            output_data = {
                k: v for k, v in output_data.items() if k != "_hitl_checkpoint"
            }

        # Store output data if provided (including falsy values like False, 0, "")
        if output_data is not None:
            await self.store_output_data(task_run, output_data)

        # Store error info if provided
        if error_info:
            await self.store_output_data(task_run, error_info)

        # Persist LLM token/cost metadata in execution_context JSONB
        if llm_usage is not None:
            ctx = dict(task_run.execution_context or {})
            ctx["_llm_usage"] = {
                "input_tokens": llm_usage.input_tokens,
                "output_tokens": llm_usage.output_tokens,
                "total_tokens": llm_usage.total_tokens,
                "cost_usd": llm_usage.cost_usd,
            }
            task_run.execution_context = ctx

        # Update in database
        await self.repository.update(session, task_run)

    async def get_task_run(
        self, session, tenant_id: str, task_run_id: UUID
    ) -> TaskRun | None:
        """
        Get task run by ID with tenant isolation.

        Args:
            session: Database session
            tenant_id: Tenant identifier
            task_run_id: Task run identifier

        Returns:
            TaskRun instance or None if not found
        """
        task_run = await self.repository.get_by_id(session, tenant_id, task_run_id)
        if task_run:
            # Populate task_name by querying Component table if needed
            if hasattr(task_run, "task_name"):
                # Already populated (e.g., from list_task_runs)
                return task_run
            # Need to populate task_name
            from analysi.models.component import Component

            if task_run.task_id:
                # Get component name
                stmt = select(Component.name).where(
                    (Component.id == task_run.task_id)
                    & (Component.tenant_id == tenant_id)
                )
                result = await session.execute(stmt)
                component_name = result.scalar_one_or_none()
                task_run.task_name = component_name or TaskConstants.AD_HOC_TASK_NAME
            else:
                # Ad-hoc execution
                task_run.task_name = TaskConstants.AD_HOC_TASK_NAME
        return task_run

    async def get_task_run_status(
        self, session, tenant_id: str, task_run_id: UUID
    ) -> dict[str, Any] | None:
        """
        Get lightweight task run status for polling.

        Args:
            session: Database session
            tenant_id: Tenant identifier
            task_run_id: Task run identifier

        Returns:
            Status information (status, updated_at) or None
        """
        task_run = await self.repository.get_by_id(session, tenant_id, task_run_id)
        if not task_run:
            return None

        return {
            "status": task_run.status,
            "updated_at": task_run.updated_at,
            "duration": task_run.duration,
        }

    async def store_input_data(
        self, task_run: TaskRun, input_data: dict[str, Any]
    ) -> None:
        """Store input data using appropriate storage strategy."""
        import json

        # Convert input data to JSON string
        content = json.dumps(input_data, ensure_ascii=False, indent=2)
        content_type = "application/json"

        # Store using StorageManager
        storage_info = await self.storage_manager.store(
            content=content,
            content_type=content_type,
            tenant_id=task_run.tenant_id,
            task_run_id=str(task_run.id),
            storage_purpose="input",
        )

        # Update task run with storage information
        task_run.input_type = storage_info["storage_type"]
        task_run.input_location = storage_info["location"]
        task_run.input_content_type = content_type

    async def store_output_data(
        self, task_run: TaskRun, output_data: dict[str, Any]
    ) -> None:
        """Store output data using appropriate storage strategy."""
        import json

        # Convert output data to JSON string
        content = json.dumps(output_data, ensure_ascii=False, indent=2)
        content_type = "application/json"

        # Store using StorageManager
        storage_info = await self.storage_manager.store(
            content=content,
            content_type=content_type,
            tenant_id=task_run.tenant_id,
            task_run_id=str(task_run.id),
            storage_purpose="output",
        )

        # Update task run with storage information
        task_run.output_type = storage_info["storage_type"]
        task_run.output_location = storage_info["location"]
        task_run.output_content_type = content_type

    async def retrieve_input_data(self, task_run: TaskRun) -> dict[str, Any] | None:
        """Retrieve input data from storage."""
        if not task_run.input_type or not task_run.input_location:
            return None

        import json

        # Retrieve content using StorageManager
        content = await self.storage_manager.retrieve(
            storage_type=task_run.input_type,
            location=task_run.input_location,
            content_type=task_run.input_content_type or "application/json",
        )

        # Parse JSON content
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {"raw_content": content}

    async def retrieve_output_data(self, task_run: TaskRun) -> dict[str, Any] | None:
        """Retrieve output data from storage."""
        if not task_run.output_type or not task_run.output_location:
            return None

        import json

        # Retrieve content using StorageManager
        content = await self.storage_manager.retrieve(
            storage_type=task_run.output_type,
            location=task_run.output_location,
            content_type=task_run.output_content_type or "application/json",
        )

        # Parse JSON content
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {"raw_content": content}

    async def list_task_runs(
        self,
        session,
        tenant_id: str,
        task_id: UUID | None = None,
        workflow_run_id: UUID | None = None,
        status: str | None = None,
        run_context_list: list[str] | None = None,
        integration_id: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[TaskRun], int]:
        """
        List task runs with filtering, sorting, and pagination.

        Args:
            session: Database session
            tenant_id: Tenant identifier
            task_id: Filter by task ID
            workflow_run_id: Filter by workflow run ID
            status: Filter by status
            run_context_list: Filter by run_context values (e.g. ["analysis", "ad_hoc"])
            integration_id: Filter by integration ID (tasks linked to this integration)
            sort: Field to sort by
            order: Sort order
            skip: Number of items to skip
            limit: Number of items to return

        Returns:
            Tuple of (task_runs, total_count)
        """
        return await self.repository.list_task_runs(
            session=session,
            tenant_id=tenant_id,
            task_id=task_id,
            workflow_run_id=workflow_run_id,
            status=status,
            run_context_list=run_context_list,
            integration_id=integration_id,
            sort=sort,
            order=order,
            skip=skip,
            limit=limit,
        )


class TaskRunRepository:
    """Repository for TaskRun database operations."""

    async def create(self, session, task_run: TaskRun) -> TaskRun:
        """Create a new task run in database."""
        session.add(task_run)
        await session.flush()
        await session.refresh(task_run)
        return task_run

    async def update(self, session, task_run: TaskRun) -> TaskRun:
        """Update existing task run in database."""
        await session.flush()
        await session.refresh(task_run)
        return task_run

    async def get_by_id(
        self, session, tenant_id: str, task_run_id: UUID
    ) -> TaskRun | None:
        """Get task run by ID with tenant filtering."""
        stmt = select(TaskRun).where(
            TaskRun.id == task_run_id, TaskRun.tenant_id == tenant_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_tenant(
        self, session, tenant_id: str, limit: int = 100, offset: int = 0
    ) -> list[TaskRun]:
        """Get task runs for a tenant with pagination."""
        raise NotImplementedError("TaskRun listing not implemented yet")

    async def get_running_tasks(self, session, tenant_id: str) -> list[TaskRun]:
        """Get all currently running task runs for a tenant."""
        raise NotImplementedError("Running tasks query not implemented yet")

    async def list_task_runs(
        self,
        session,
        tenant_id: str,
        task_id: UUID | None = None,
        workflow_run_id: UUID | None = None,
        status: str | None = None,
        run_context_list: list[str] | None = None,
        integration_id: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[TaskRun], int]:
        """
        List task runs with filtering, sorting, and pagination.

        Args:
            session: Database session
            tenant_id: Tenant identifier
            task_id: Filter by task ID
            workflow_run_id: Filter by workflow run ID
            status: Filter by status
            run_context_list: Filter by run_context values
            integration_id: Filter by integration ID via Task.integration_id
            sort: Field to sort by (created_at, updated_at, status, duration)
            order: Sort order (asc, desc)
            skip: Number of items to skip
            limit: Number of items to return

        Returns:
            Tuple of (task_runs, total_count)
        """
        from analysi.models.component import Component
        from analysi.models.task import Task

        # Query with LEFT JOIN to get task names from Component table
        query = (
            select(TaskRun, Component.name)
            .outerjoin(
                Component,
                (TaskRun.task_id == Component.id) & (Component.tenant_id == tenant_id),
            )
            .where(TaskRun.tenant_id == tenant_id)
        )

        # Apply filters
        if task_id:
            query = query.where(TaskRun.task_id == task_id)
        if workflow_run_id:
            query = query.where(TaskRun.workflow_run_id == workflow_run_id)
        if status:
            query = query.where(TaskRun.status == status)

        if run_context_list:
            query = query.where(TaskRun.run_context.in_(run_context_list))

        if integration_id:
            query = query.join(
                Task,
                TaskRun.task_id == Task.component_id,
                isouter=True,
            ).where(Task.integration_id == integration_id)

        # Count total before pagination (use simpler query for counting)
        count_query = select(func.count(TaskRun.id)).where(
            TaskRun.tenant_id == tenant_id
        )

        # Apply same filters to count query
        if task_id:
            count_query = count_query.where(TaskRun.task_id == task_id)
        if workflow_run_id:
            count_query = count_query.where(TaskRun.workflow_run_id == workflow_run_id)
        if status:
            count_query = count_query.where(TaskRun.status == status)
        if run_context_list:
            count_query = count_query.where(TaskRun.run_context.in_(run_context_list))
        if integration_id:
            count_query = count_query.join(
                Task,
                TaskRun.task_id == Task.component_id,
                isouter=True,
            ).where(Task.integration_id == integration_id)

        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        # Apply sorting
        sort_field = {
            "created_at": TaskRun.created_at,
            "updated_at": TaskRun.updated_at,
            "status": TaskRun.status,
            "duration": TaskRun.duration,
            "started_at": TaskRun.started_at,
            "completed_at": TaskRun.completed_at,
        }.get(sort, TaskRun.created_at)

        if order == "desc":
            query = query.order_by(desc(sort_field))
        else:
            query = query.order_by(sort_field)

        # Apply pagination
        query = query.offset(skip).limit(limit)

        # Execute query
        result = await session.execute(query)
        rows = result.all()

        # Process results to set task_name
        task_runs = []
        for row in rows:
            task_run = row[0]  # TaskRun object
            component_name = row[1]  # Component.name or None

            # Set task_name: use component name or "Ad Hoc Task" for None
            task_run.task_name = component_name or TaskConstants.AD_HOC_TASK_NAME
            task_runs.append(task_run)

        return task_runs, total

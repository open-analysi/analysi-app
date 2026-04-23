"""Task service for business logic."""

from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.component import Component
from analysi.models.kdg_edge import EdgeType, KDGEdge
from analysi.models.knowledge_unit import KUTool, KUType
from analysi.models.task import Task
from analysi.models.task_flat import TaskFlatRepository
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.repositories.task import TaskRepository
from analysi.schemas.audit_context import AuditContext
from analysi.schemas.task import TaskCreate, TaskUpdate

logger = get_logger(__name__)


class TaskService:
    """Service for Task business logic."""

    def __init__(self, session: AsyncSession):
        """Initialize service with database session."""
        self.repository = TaskRepository(session)  # Keep old one for now
        self.flat_repo = TaskFlatRepository(session)  # Use simplified repository
        self.session = session

    async def _log_audit(
        self,
        tenant_id: str,
        action: str,
        resource_id: str,
        audit_context: AuditContext | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an audit event if audit_context is provided."""
        if audit_context is None:
            return  # Skip logging if no context provided

        repo = ActivityAuditRepository(self.session)
        await repo.create(
            tenant_id=tenant_id,
            actor_id=audit_context.actor_user_id,
            actor_type=audit_context.actor_type,
            source=audit_context.source,
            action=action,
            resource_type="task",
            resource_id=resource_id,
            details=details,
            ip_address=audit_context.ip_address,
            user_agent=audit_context.user_agent,
            request_id=audit_context.request_id,
        )

    async def _validate_script_tools(
        self, script: str, tenant_id: str
    ) -> dict[str, Any] | None:
        """Validate all tools referenced in a Cy script exist in the tool registry.

        Returns the analysis result dict on success, or None if the script
        cannot be parsed (syntax errors are not blocking — scripts may be
        saved in a draft state).
        Raises ValueError if any referenced tool FQN is not in the registry.
        """
        from cy_language import analyze_script
        from cy_language.tool_resolver import ToolResolver

        from analysi.services.cy_tool_registry import load_tool_registry_async

        tool_registry = await load_tool_registry_async(self.session, tenant_id)

        # Use ToolResolver as the authoritative source of all cy-language built-ins.
        # This covers every native:: namespace (native::tools::, native::type::,
        # native::str::, native::dict::, native::time::, etc.) without hardcoding
        # prefix strings that break when new namespaces are added.
        #
        # analyze_script returns a mix of full FQNs ("native::type::str") and bare
        # names ("len", "__to_iterable") for compiler-generated iteration nodes.
        # We build both sets from the resolver so both forms are recognised.
        native_resolver = ToolResolver.from_native_tools()
        native_fqns = set(native_resolver.fqn_registry.keys())
        native_short_names = {fqn.split("::")[-1] for fqn in native_fqns}

        # Also collect short names from the tool_registry (app:: and native:: tools)
        # so bare names like "get_checkpoint" match "native::ingest::get_checkpoint".
        registry_short_names = {fqn.split("::")[-1] for fqn in tool_registry}

        try:
            result = analyze_script(code=script, tool_registry=tool_registry)
        except SyntaxError:
            # Script has syntax errors — skip tool validation, allow save
            logger.debug("Script has syntax errors, skipping tool validation")
            return None

        missing = [
            fqn
            for fqn in result["tools_used"]
            if fqn not in tool_registry
            and fqn not in native_fqns
            and fqn not in native_short_names
            and fqn not in registry_short_names
        ]
        if missing:
            raise ValueError(f"Script references unknown tools: {', '.join(missing)}")

        return result

    async def _sync_tool_edges(
        self,
        task: Task,
        tenant_id: str,
        tool_fqns: list[str],
    ) -> None:
        """Best-effort: sync KDG 'uses' edges from task to app:: tools.

        1. Delete existing "uses" edges from this task.
        2. For each app:: FQN, look up the KUTool Component by 2-part name
           and create a new "uses" edge.
        """
        task_component_id = task.component.id

        # 1. Delete old "uses" edges from this task
        old_edges_stmt = select(KDGEdge).where(
            and_(
                KDGEdge.tenant_id == tenant_id,
                KDGEdge.source_id == task_component_id,
                KDGEdge.relationship_type == EdgeType.USES,
            )
        )
        old_edges_result = await self.session.execute(old_edges_stmt)
        for edge in old_edges_result.scalars().all():
            await self.session.delete(edge)

        # Flush deletes before inserts — SQLAlchemy flushes inserts before
        # deletes by default, which would violate the unique constraint.
        await self.session.flush()

        # 2. Create new edges for app:: tools with KUTool records
        for fqn in tool_fqns:
            if not fqn.startswith("app::"):
                continue

            # Extract 2-part name: "app::virustotal::ip_reputation" -> "virustotal::ip_reputation"
            parts = fqn.split("::", 1)
            two_part_name = parts[1] if len(parts) == 2 else fqn

            try:
                # Look up KUTool component by name
                tool_stmt = (
                    select(KUTool)
                    .join(Component, KUTool.component_id == Component.id)
                    .where(
                        Component.tenant_id == tenant_id,
                        Component.name == two_part_name,
                        Component.ku_type == KUType.TOOL,
                    )
                )
                tool_result = await self.session.execute(tool_stmt)
                tool_ku = tool_result.scalar_one_or_none()

                if not tool_ku:
                    logger.debug("No KUTool Component for %s — skipping edge", fqn)
                    continue

                edge = KDGEdge(
                    tenant_id=tenant_id,
                    source_id=task_component_id,
                    target_id=tool_ku.component_id,
                    relationship_type=EdgeType.USES,
                    edge_metadata={"tool_fqn": fqn},
                )
                self.session.add(edge)
            except Exception:
                logger.warning("Failed to create edge for tool %s", fqn, exc_info=True)

        await self.session.flush()

    async def create_task(
        self,
        tenant_id: str,
        task_data: TaskCreate,
        audit_context: AuditContext | None = None,
        created_by: UUID | None = None,
    ) -> Task:
        """
        Create a new task with data_samples validation.

        Validates that data_samples (if provided) match the script's expectations
        using Cy's type inference and JSON Schema validation.
        """
        # Validate data_samples if provided
        if task_data.data_samples:
            from analysi.services.type_propagation.data_sample_validator import (
                generate_schema_from_samples,
            )
            from analysi.services.type_propagation.task_inference import (
                infer_task_output_schema,
            )

            # Generate JSON Schema from data samples
            # This is what the data_samples PROVIDE
            # Data samples may use {name, input, description} structure —
            # extract the "input" values for schema generation since that's
            # what the script actually receives.
            raw_samples = task_data.data_samples
            input_samples = [
                s["input"]
                for s in raw_samples
                if isinstance(s, dict) and "input" in s and isinstance(s["input"], dict)
            ]
            generated_schema = generate_schema_from_samples(
                input_samples if input_samples else raw_samples
            )

            # Create temporary task for validation
            temp_task = Task(
                component_id=None,
                script=task_data.script,
                function=task_data.function,
            )

            # Try to infer output schema using the generated schema
            # Cy validates that the script only accesses fields that exist in the schema.
            # Non-strict mode: allows ?? (null coalesce) patterns that the type checker
            # can't fully resolve, avoiding false positives on defensive scripts.
            result = await infer_task_output_schema(
                temp_task,
                generated_schema,  # Pass SCHEMA, not raw data
                strict_input=False,
                session=self.session,
                tenant_id=tenant_id,
            )

            # Log type inference issues as warnings — Cy's type checker doesn't
            # fully support ?? (null coalesce) and dynamic dict patterns, so we
            # shouldn't block task creation for false positives.
            from analysi.services.type_propagation.errors import TypePropagationError

            if isinstance(result, TypePropagationError):
                logger.warning(
                    "data_samples_type_check_warning",
                    task_name=task_data.name,
                    message=result.message,
                )

        # Validate that all tools in the script exist in the registry
        analysis = await self._validate_script_tools(task_data.script, tenant_id)

        # Convert Pydantic model to dict and add tenant_id
        task_dict = task_data.model_dump()
        task_dict["tenant_id"] = tenant_id

        # Derive created_by: audit_context (REST) takes priority, then explicit param (MCP/workers)
        if audit_context:
            task_dict["created_by"] = audit_context.actor_user_id
        elif created_by is not None:
            task_dict["created_by"] = created_by

        task = await self.repository.create(task_dict)

        # Create KDG edges for app:: tools (best-effort, skip if analysis failed)
        if analysis:
            try:
                await self._sync_tool_edges(task, tenant_id, analysis["tools_used"])
            except Exception:
                logger.warning("Failed to sync tool edges on create", exc_info=True)

        # Log audit event
        await self._log_audit(
            tenant_id=tenant_id,
            action="task.create",
            resource_id=str(task.component.id),
            audit_context=audit_context,
            details={
                "task_name": task.component.name,
                "cy_name": task.component.cy_name,
            },
        )

        return task

    async def get_task(self, component_id: UUID, tenant_id: str) -> Task | None:
        """Get a single task by Component ID."""
        return await self.repository.get_by_id(component_id, tenant_id)

    async def get_task_by_cy_name(self, cy_name: str, tenant_id: str) -> Task | None:
        """
        Get a single task by cy_name.

        Args:
            cy_name: The cy_name identifier (e.g., "virustotal_ip_reputation")
            tenant_id: Tenant ID

        Returns:
            Task if found, None otherwise
        """
        # Use list_tasks with cy_name filter
        tasks, _ = await self.list_tasks(
            tenant_id=tenant_id,
            skip=0,
            limit=1,
            cy_name=cy_name,
        )

        return tasks[0] if tasks else None

    async def update_task(
        self,
        component_id: UUID,
        tenant_id: str,
        update_data: TaskUpdate,
        audit_context: AuditContext | None = None,
    ) -> Task | None:
        """Update an existing task."""
        # First get the existing task
        task = await self.repository.get_by_id(component_id, tenant_id)
        if not task:
            return None

        # Convert update data to dict, excluding None values
        update_dict = update_data.model_dump(exclude_unset=True)

        # Validate tools if script is being updated
        analysis = None
        if "script" in update_dict:
            analysis = await self._validate_script_tools(
                update_dict["script"], tenant_id
            )

        updated_task = await self.repository.update(task, update_dict)

        # Re-sync KDG edges if script changed
        if analysis and updated_task:
            try:
                await self._sync_tool_edges(
                    updated_task, tenant_id, analysis["tools_used"]
                )
            except Exception:
                logger.warning("Failed to sync tool edges on update", exc_info=True)

        # Log audit event
        await self._log_audit(
            tenant_id=tenant_id,
            action="task.update",
            resource_id=str(component_id),
            audit_context=audit_context,
            details={
                "task_name": updated_task.component.name if updated_task else None,
                "updated_fields": list(update_dict.keys()),
            },
        )

        return updated_task

    async def delete_task(
        self,
        component_id: UUID,
        tenant_id: str,
        audit_context: AuditContext | None = None,
    ) -> bool:
        """Delete a task."""
        # First get the existing task
        task = await self.repository.get_by_id(component_id, tenant_id)
        if not task:
            return False

        # Capture task info before deletion for audit
        task_name = task.component.name
        cy_name = task.component.cy_name

        await self.repository.delete(task)

        # Log audit event
        await self._log_audit(
            tenant_id=tenant_id,
            action="task.delete",
            resource_id=str(component_id),
            audit_context=audit_context,
            details={
                "task_name": task_name,
                "cy_name": cy_name,
            },
        )

        return True

    async def list_tasks(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 100,
        function: str | None = None,
        scope: str | None = None,
        status: str | None = None,
        cy_name: str | None = None,
        categories: list[str] | None = None,
        app: str | None = None,
        name_filter: str | None = None,
    ) -> tuple[list[Task], dict[str, Any]]:
        """List tasks with pagination and filters."""
        tasks, total = await self.repository.list_with_filters(
            tenant_id=tenant_id,
            skip=skip,
            limit=limit,
            function=function,
            scope=scope,
            status=status,
            cy_name=cy_name,
            categories=categories,
            app=app,
            name_filter=name_filter,
        )

        # Return pagination metadata
        return tasks, {
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def search_tasks(
        self,
        tenant_id: str,
        query: str,
        skip: int = 0,
        limit: int = 100,
        categories: list[str] | None = None,
    ) -> tuple[list[Task], dict[str, Any]]:
        """Search tasks by name, description, and directive/script."""
        tasks, total = await self.repository.search(
            tenant_id=tenant_id,
            query=query,
            skip=skip,
            limit=limit,
            categories=categories,
        )

        # Return pagination metadata
        return tasks, {
            "total": total,
            "skip": skip,
            "limit": limit,
        }

"""MCP tools for Task CRUD operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from analysi.config.settings import settings
from analysi.mcp.audit import log_mcp_audit
from analysi.mcp.context import (
    check_mcp_permission,
    get_mcp_actor_user_id,
    get_tenant,
)
from analysi.models.task_flat import TaskFlat
from analysi.schemas.task import TaskCreate, TaskUpdate
from analysi.services.task import TaskService


async def _get_db_session():
    """Create database session for MCP tools."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    return async_session()


async def get_task(task_identifier: str) -> dict:
    """
    Get task by ID or cy_name.



    Args:
        task_identifier: Task UUID (component_id) or name

    Returns:
        {
            "id": str,
            "name": str,
            "script": str,
            "description": str | None,
            ...
        }
    """
    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("tasks", "read")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        service = TaskService(session)

        # Try as UUID first
        try:
            task_uuid = UUID(task_identifier)
            task = await service.get_task(task_uuid, tenant)
        except ValueError:
            # Not a UUID - try to find by name or cy_name using TaskFlat
            stmt = (
                select(TaskFlat)
                .where(TaskFlat.tenant_id == tenant)
                .where(
                    (TaskFlat.name == task_identifier)
                    | (TaskFlat.cy_name == task_identifier)
                )
            )
            result = await session.execute(stmt)
            task_flat = result.scalar_one_or_none()

            if not task_flat:
                return {
                    "error": f"Task '{task_identifier}' not found for tenant '{tenant}'"
                }

            # Get full task object
            task = await service.get_task(task_flat.id, tenant)

        if not task:
            return {
                "error": f"Task '{task_identifier}' not found for tenant '{tenant}'"
            }

        # Return task data in same format as REST API
        return {
            "id": str(task.component.id),
            "name": task.component.name,
            "script": task.script,
            "description": task.component.description,
            "cy_name": task.component.cy_name,
            "function": task.function,
            "scope": task.scope,
            "status": task.component.status,
        }


async def update_task_script(
    task_id: str,
    script: str,
    data_samples: list | None = None,
    directive: str | None = None,
    description: str | None = None,
) -> dict:
    """
    Update task's Cy script.



    Args:
        task_id: Task UUID (component_id)
        script: New Cy script content
        data_samples: Optional updated test data samples (list of dicts)
        directive: Optional updated system directive for LLM calls
        description: Optional updated task description

    Returns:
        {
            "success": bool,
            "task": dict
        }
    """
    check_mcp_permission("tasks", "update")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            task_uuid = UUID(task_id)
            service = TaskService(session)

            # Get existing task
            task = await service.get_task(task_uuid, tenant)
            if not task:
                return {
                    "success": False,
                    "task": None,
                    "error": f"Task '{task_id}' not found",
                }

            # Build update fields — script is always included, others only if provided
            update_fields: dict = {"script": script}
            if data_samples is not None:
                update_fields["data_samples"] = data_samples
            if directive is not None:
                update_fields["directive"] = directive
            if description is not None:
                update_fields["description"] = description

            update_data = TaskUpdate(**update_fields)
            updated_task = await service.update_task(
                task_uuid, tenant, update_data, audit_context=None
            )

            # Log MCP audit with full arguments
            await log_mcp_audit(
                session=session,
                tenant_id=tenant,
                action="task.update",
                resource_type="task",
                resource_id=task_id,
                tool_name="update_task_script",
                arguments={
                    "task_id": task_id,
                    "script": script,
                    "data_samples": data_samples is not None,
                    "directive": directive is not None,
                    "description": description is not None,
                },
            )
            await session.commit()

            if not updated_task:
                return {
                    "success": False,
                    "task": None,
                    "error": f"Failed to update task '{task_id}'",
                }

            return {
                "success": True,
                "task": {
                    "id": str(updated_task.component.id),
                    "name": updated_task.component.name,
                    "script": updated_task.script,
                },
            }
        except Exception as e:
            return {"success": False, "task": None, "error": str(e)}


async def create_task(
    name: str,
    script: str,
    description: str | None = None,
    cy_name: str | None = None,
    # Component fields
    app: str = "default",
    status: str = "enabled",
    visible: bool = False,
    system_only: bool = False,
    categories: list[str] | None = None,
    tags: list[str] | None = None,  # Alias for categories
    # Task-specific fields
    directive: str | None = None,
    function: str | None = None,
    scope: str | None = None,
    mode: str = "saved",
    llm_config: dict | None = None,
    data_samples: list | None = None,
) -> dict:
    """
    Create new task with Cy script.



    Args:
        name: Task name
        script: Cy script content
        description: Optional description
        cy_name: Optional script-friendly identifier

        # Component fields
        app: Application/integration name (default: "default")
        status: Task status (default: "enabled")
        visible: Whether task is visible to users (default: False)
        system_only: Whether task can only be modified by system (default: False)
        categories: Task categories/tags (default: [])
        tags: Alias for categories (takes precedence if provided)

        # Task-specific fields
        directive: System message for LLM calls
        function: Task function type (summarization, reasoning, etc.)
        scope: Task scope (input/processing/output)
        mode: Task mode (ad_hoc/saved, default: "saved")
        llm_config: LLM configuration dict
        data_samples: Sample input data for testing

    Returns:
        {
            "id": str,
            "task": dict
        }
    """
    check_mcp_permission("tasks", "create")
    tenant = get_tenant()
    created_by = get_mcp_actor_user_id()

    async with await _get_db_session() as session:
        try:
            service = TaskService(session)

            # Handle tags/categories - tags takes precedence if provided
            # If neither tags nor categories provided, use empty list
            if tags is not None:
                final_categories = tags
            elif categories is not None:
                final_categories = categories
            else:
                final_categories = []

            # Build task data using TaskCreate schema
            task_data_dict: dict[str, Any] = {
                # Required fields
                "name": name,
                "script": script,
                # Optional basic fields
                "description": description,
                "cy_name": cy_name,
                # Component fields
                "app": app,
                "status": status,
                "visible": visible,
                "system_only": system_only,
                "categories": final_categories,
                # Task-specific fields
                "directive": directive,
                "function": function,
                "scope": scope,
                "mode": mode,
                "llm_config": llm_config,
                "data_samples": data_samples,
            }

            task_data = TaskCreate(**task_data_dict)
            # MCP is trusted internal code — pass created_by directly (not via schema)
            task = await service.create_task(
                tenant, task_data, audit_context=None, created_by=created_by
            )

            # Log MCP audit with full arguments
            await log_mcp_audit(
                session=session,
                tenant_id=tenant,
                action="task.create",
                resource_type="task",
                resource_id=str(task.component.id),
                tool_name="create_task",
                arguments={
                    "name": name,
                    "script": script,
                    "description": description,
                    "cy_name": cy_name,
                    "app": app,
                    "function": function,
                    "scope": scope,
                },
                actor_id=created_by,
            )
            await session.commit()

            return {
                "id": str(task.component.id),
                "task": {
                    "id": str(task.component.id),
                    "name": task.component.name,
                    "script": task.script,
                    "description": task.component.description,
                    "cy_name": task.component.cy_name,
                },
            }
        except Exception as e:
            return {"id": None, "task": None, "error": str(e)}


async def list_tasks(filters: dict | None = None) -> dict:
    """
    List tasks with optional filters.



    Args:
        filters: Optional filters (function, scope, status, categories)

    Returns:
        {
            "tasks": list[dict],
            "total": int
        }
    """
    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("tasks", "read")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = TaskService(session)

            # Extract filters
            function = filters.get("function") if filters else None
            scope = filters.get("scope") if filters else None
            status = filters.get("status") if filters else None
            categories = filters.get("categories") if filters else None
            # Normalize: MCP callers may pass a bare string instead of a list
            if isinstance(categories, str):
                categories = [categories]

            # Use service to list tasks
            tasks, metadata = await service.list_tasks(
                tenant_id=tenant,
                skip=0,
                limit=1000,  # High limit for MCP tool usage
                function=function,
                scope=scope,
                status=status,
                categories=categories,
            )

            # Convert to dict list
            tasks_list = [
                {
                    "id": str(task.component.id),
                    "name": task.component.name,
                    "script": task.script,
                    "function": task.function,
                }
                for task in tasks
            ]

            return {"tasks": tasks_list, "total": metadata["total"]}
        except Exception as e:
            return {"tasks": [], "total": 0, "error": str(e)}

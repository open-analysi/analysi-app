"""Task repository for database operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component, ComponentKind
from analysi.models.task import Task
from analysi.repositories.component import (
    categories_contain,
    merge_classification_into_categories,
)


class TaskRepository:
    """Repository for Task database operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session."""
        self.session = session

    async def create(self, task_data: dict[str, Any]) -> Task:
        """Create a new task in the database."""
        # Import component repository for cy_name generation
        from analysi.repositories.component import ComponentRepository

        comp_repo = ComponentRepository(self.session)

        # Auto-populate categories from classification fields.
        # Use the same defaults as the model layer so categories stay consistent.
        # scope/function may be explicitly None from Pydantic, so use `or` fallback.
        categories = task_data.pop("categories", [])
        categories = merge_classification_into_categories(
            categories,
            function=task_data.get("function"),
            scope=task_data.get("scope"),
        )

        # Extract component fields
        component_fields = {
            "tenant_id": task_data.pop("tenant_id"),
            "kind": ComponentKind.TASK,
            "name": task_data.pop("name", ""),
            "description": task_data.pop("description", ""),
            "version": task_data.pop("version", "1.0.0"),
            "status": task_data.pop("status", "enabled"),
            "visible": task_data.pop("visible", False),
            "system_only": task_data.pop("system_only", False),
            "app": task_data.pop("app", "default"),
            "categories": categories,
            "created_by": task_data.pop("created_by", SYSTEM_USER_ID),
        }

        # Handle cy_name - generate if not provided
        cy_name = task_data.pop("cy_name", None)
        if not cy_name:
            # Generate from name and ensure uniqueness
            cy_name = comp_repo.generate_cy_name(
                component_fields["name"], ComponentKind.TASK
            )
            cy_name = await comp_repo.ensure_unique_cy_name(
                cy_name, component_fields["tenant_id"], component_fields["app"]
            )
        else:
            # Check if explicitly provided cy_name already exists
            existing = await comp_repo.get_by_cy_name(
                component_fields["tenant_id"], component_fields["app"], cy_name
            )
            if existing:
                raise ValueError(f"Component with cy_name '{cy_name}' already exists")

        component_fields["cy_name"] = cy_name

        # Create component first
        component = Component(**component_fields)
        self.session.add(component)
        await self.session.flush()  # Get the component ID

        # Create task with remaining fields
        task = Task(
            component_id=component.id,
            script=task_data.get("script"),
            directive=task_data.get("directive"),
            function=task_data.get("function"),
            scope=task_data.get("scope", "processing"),
            schedule=task_data.get("schedule"),
            mode=task_data.get("mode", "saved"),
            llm_config=task_data.get("llm_config", {}),
            data_samples=task_data.get("data_samples"),
            # Project Symi: provenance and integration link
            integration_id=task_data.get("integration_id"),
            origin_type=task_data.get("origin_type", "user"),
            managed_resource_key=task_data.get("managed_resource_key"),
        )
        self.session.add(task)

        await self.session.commit()
        await self.session.refresh(task)
        await self.session.refresh(component)

        # Load the component relationship so response schema works
        await self.session.refresh(task, ["component"])
        return task

    async def get_by_id(self, component_id: UUID, tenant_id: str) -> Task | None:
        """Get a task by Component ID and tenant."""
        stmt = (
            select(Task)
            .join(Component)
            .where(Component.id == component_id, Component.tenant_id == tenant_id)
        )
        result = await self.session.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            return None

        # Load the component relationship explicitly
        await self.session.refresh(task, ["component"])
        return task

    async def update(self, task: Task, update_data: dict[str, Any]) -> Task:
        """Update a task in the database."""
        # Separate component fields from task fields
        component_fields = {
            k: v
            for k, v in update_data.items()
            if k
            in [
                "name",
                "description",
                "version",
                "status",
                "visible",
                "system_only",
                "app",
                "categories",
                "cy_name",
            ]
        }
        task_fields = {
            k: v
            for k, v in update_data.items()
            if k
            in [
                "script",
                "directive",
                "function",
                "scope",
                "schedule",
                "mode",
                "llm_config",
                "data_samples",
            ]
        }

        # Update component fields if present
        if component_fields:
            await self.session.refresh(task, ["component"])
            for field, value in component_fields.items():
                setattr(task.component, field, value)

        # Update task fields
        for field, value in task_fields.items():
            if hasattr(task, field):
                setattr(task, field, value)

        # Additively merge classification values into categories — but only when
        # the user didn't provide explicit categories (explicit categories win).
        if (
            "function" in task_fields or "scope" in task_fields
        ) and "categories" not in component_fields:
            if not component_fields:
                await self.session.refresh(task, ["component"])
            task.component.categories = merge_classification_into_categories(
                task.component.categories or [],
                function=task_fields.get("function"),
                scope=task_fields.get("scope"),
            )

        await self.session.commit()
        await self.session.refresh(task)
        # Ensure component relationship is loaded for response
        await self.session.refresh(task, ["component"])
        return task

    async def delete(self, task: Task) -> None:
        """Delete a task from the database."""
        # Load component relationship if not already loaded
        await self.session.refresh(task, ["component"])

        # Delete the component (cascade will delete the task)
        await self.session.delete(task.component)
        await self.session.commit()

    async def list_with_filters(
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
    ) -> tuple[list[Task], int]:
        """List tasks with filters and pagination."""
        # Base query
        stmt = select(Task).join(Component).where(Component.tenant_id == tenant_id)

        # Apply filters based on actual database fields
        if function is not None:
            stmt = stmt.where(Task.function == function)

        if scope is not None:
            stmt = stmt.where(Task.scope == scope)

        if status is not None:
            stmt = stmt.where(Component.status == status)

        if cy_name is not None:
            stmt = stmt.where(Component.cy_name == cy_name)

        if app is not None:
            stmt = stmt.where(Component.app == app)

        if categories:
            stmt = stmt.where(categories_contain(categories))

        if name_filter:
            stmt = stmt.where(Component.name.ilike(f"%{name_filter}%"))

        # Get total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar()

        # Apply pagination and ordering
        stmt = stmt.order_by(Task.created_at.desc()).offset(skip).limit(limit)

        # Execute query
        result = await self.session.execute(stmt)
        tasks = result.scalars().all()

        # Load component relationships for all tasks
        for task in tasks:
            await self.session.refresh(task, ["component"])

        return list(tasks), total or 0

    async def get_task_by_cy_name(
        self, tenant_id: str, cy_name: str, app: str | None = None
    ) -> Task | None:
        """
        Get a task by its cy_name.

        Args:
            tenant_id: Tenant identifier
            cy_name: Script-friendly identifier
            app: Optional app filter. If None, matches any app.

        Returns:
            Task if found, None otherwise
        """
        conditions = [
            Component.tenant_id == tenant_id,
            Component.cy_name == cy_name,
            Component.kind == ComponentKind.TASK,
        ]
        if app is not None:
            conditions.append(Component.app == app)

        stmt = select(Task).join(Component).where(*conditions)
        result = await self.session.execute(stmt)
        task = result.scalar_one_or_none()

        if task:
            # Load the component relationship explicitly
            await self.session.refresh(task, ["component"])

        return task

    async def search(
        self,
        tenant_id: str,
        query: str,
        skip: int = 0,
        limit: int = 100,
        categories: list[str] | None = None,
    ) -> tuple[list[Task], int]:
        """Search tasks by name, description, and tags."""
        # Create search conditions - search in Component fields and Task fields
        search_conditions = [
            Component.name.ilike(f"%{query}%"),
            Component.description.ilike(f"%{query}%"),
            Task.directive.ilike(f"%{query}%"),
            Task.script.ilike(f"%{query}%"),
        ]

        # Build query
        stmt = (
            select(Task)
            .join(Component)
            .where(Component.tenant_id == tenant_id, or_(*search_conditions))
        )

        if categories:
            stmt = stmt.where(categories_contain(categories))

        # Get total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar()

        # Apply pagination and ordering
        stmt = stmt.order_by(Task.created_at.desc()).offset(skip).limit(limit)

        # Execute query
        result = await self.session.execute(stmt)
        tasks = result.scalars().all()

        # Load component relationships for all tasks
        for task in tasks:
            await self.session.refresh(task, ["component"])

        return list(tasks), total or 0

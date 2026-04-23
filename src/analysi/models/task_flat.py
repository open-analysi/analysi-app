"""
Simplified Task model that abstracts away the Component inheritance complexity.
This provides a flat interface to tasks while maintaining the underlying structure.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component, ComponentKind
from analysi.models.task import Task


class TaskFlat(Base):
    """
    Simplified view of Task that combines Component and Task fields.
    This is a read-only view for queries - use TaskService for mutations.
    """

    __tablename__ = "task_view"
    __table_args__ = {"info": {"is_view": True}}  # Mark as view  # noqa: RUF012

    # Primary key (Component ID from task_view)
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)

    # Component fields (flattened)
    tenant_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    cy_name: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    status: Mapped[str] = mapped_column(String(50), default="enabled")
    visible: Mapped[bool] = mapped_column(default=False)
    system_only: Mapped[bool] = mapped_column(default=False)
    app: Mapped[str] = mapped_column(String(100), default="default")
    categories: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))

    # Task-specific fields (from V039 view: script, directive, function, scope, llm_config, data_samples)
    directive: Mapped[str | None] = mapped_column(Text)
    script: Mapped[str | None] = mapped_column(Text)
    function: Mapped[str | None] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(100), default="user")
    llm_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    data_samples: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def to_dict(self) -> dict:
        """Convert to dictionary with all fields."""
        return {
            "id": str(self.id),
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "cy_name": self.cy_name,
            "version": self.version,
            "status": self.status,
            "visible": self.visible,
            "system_only": self.system_only,
            "app": self.app,
            "categories": self.categories,
            "created_by": str(self.created_by) if self.created_by else None,
            "updated_by": str(self.updated_by) if self.updated_by else None,
            "directive": self.directive,
            "script": self.script,
            "function": self.function,
            "scope": self.scope,
            "llm_config": self.llm_config,
            "data_samples": self.data_samples,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_used_at": (
                self.last_used_at.isoformat() if self.last_used_at else None
            ),
        }

    def __repr__(self) -> str:
        return f"<TaskFlat(id={self.id}, name={self.name}, tenant={self.tenant_id})>"


class TaskFlatRepository:
    """
    Simplified repository that handles the Component/Task complexity internally.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, tenant_id: str, task_data: dict) -> TaskFlat:
        """Create a task, handling the component relationship transparently."""
        # Create component
        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.TASK,
            name=task_data.get("name", ""),
            description=task_data.get("description", ""),
            created_by=task_data.get("created_by", SYSTEM_USER_ID),
            categories=task_data.get("categories", []),
            visible=task_data.get("visible", False),
            system_only=task_data.get("system_only", False),
            app=task_data.get("app", "default"),
        )
        self.session.add(component)
        await self.session.flush()

        # Create task
        task = Task(
            component_id=component.id,
            directive=task_data.get("directive"),
            script=task_data.get("script"),
            function=task_data.get("function"),
            scope=task_data.get("scope", "user"),
            schedule=task_data.get("schedule"),
            llm_config=task_data.get("llm_config", {}),
        )
        self.session.add(task)
        await self.session.commit()

        # Return the flat view
        result = await self.get_by_id(task.id, tenant_id)
        assert result is not None  # We just created it
        return result

    async def get_by_id(self, task_id: UUID, tenant_id: str) -> TaskFlat | None:
        """Get a task by ID."""
        stmt = select(TaskFlat).where(
            TaskFlat.id == task_id, TaskFlat.tenant_id == tenant_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self, tenant_id: str, skip: int = 0, limit: int = 100, **filters: Any
    ) -> tuple[list[TaskFlat], int]:
        """List tasks with pagination."""
        # Base query
        query = select(TaskFlat).where(TaskFlat.tenant_id == tenant_id)

        # Apply filters
        if filters.get("function"):
            query = query.where(TaskFlat.function == filters["function"])
        if filters.get("scope"):
            query = query.where(TaskFlat.scope == filters["scope"])
        if filters.get("status"):
            query = query.where(TaskFlat.status == filters["status"])

        # Get total count
        count_stmt = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_stmt)

        # Apply pagination
        query = query.offset(skip).limit(limit)

        # Execute
        result = await self.session.execute(query)
        tasks = result.scalars().all()

        return list(tasks), total or 0

    async def update(
        self, task_id: UUID, tenant_id: str, updates: dict
    ) -> TaskFlat | None:
        """Update a task, handling component fields transparently."""
        # Separate component and task fields
        component_fields = {
            k: v
            for k, v in updates.items()
            if k in ["name", "description", "categories", "visible", "status"]
        }
        task_fields = {
            k: v
            for k, v in updates.items()
            if k
            in ["directive", "script", "function", "scope", "schedule", "llm_config"]
        }

        # Get the task to find component_id
        task = await self.session.get(Task, task_id)
        if not task:
            return None

        # Update component if needed
        if component_fields:
            component = await self.session.get(Component, task.component_id)
            if component and component.tenant_id == tenant_id:
                for key, value in component_fields.items():
                    setattr(component, key, value)

        # Update task fields
        if task_fields:
            for key, value in task_fields.items():
                setattr(task, key, value)

        await self.session.commit()
        return await self.get_by_id(task_id, tenant_id)

    async def delete(self, task_id: UUID, tenant_id: str) -> bool:
        """Delete a task (component cascade deletes task)."""
        task = await self.get_by_id(task_id, tenant_id)
        if not task:
            return False

        # Delete component (cascade will delete task)
        # TaskFlat.id maps to component.id in the view
        component = await self.session.get(Component, task.id)
        if component:
            await self.session.delete(component)
            await self.session.commit()
            return True
        return False

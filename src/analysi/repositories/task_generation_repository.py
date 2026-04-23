"""Repository for TaskGeneration database operations.

Supports both Kea workflow generation builds and standalone API builds.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.task_generation import TaskGeneration
from analysi.schemas.task_generation import TaskGenerationStatus

# Maximum number of progress messages to keep (FIFO)
MAX_PROGRESS_MESSAGES = 100


class TaskGenerationRepository:
    """Repository for task generation database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: str,
        workflow_generation_id: str | UUID,
        input_context: dict[str, Any],
        created_by: UUID = SYSTEM_USER_ID,
    ) -> TaskGeneration:
        """Create a new task generation for Kea workflow generation.

        Args:
            tenant_id: Tenant identifier
            workflow_generation_id: Parent workflow generation ID
            input_context: Full input context (proposal, alert, runbook)
            created_by: UUID of user/system that triggered the run

        Returns:
            Created TaskGeneration
        """
        run = TaskGeneration(
            tenant_id=tenant_id,
            workflow_generation_id=workflow_generation_id,
            source="workflow_generation",
            input_context=input_context,
            created_by=created_by,
            status=TaskGenerationStatus.PENDING,
            progress_messages=[],
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def create_standalone(
        self,
        tenant_id: str,
        description: str,
        input_context: dict[str, Any],
        alert_id: str | UUID | None = None,
        created_by: UUID = SYSTEM_USER_ID,
    ) -> TaskGeneration:
        """Create a standalone task generation from the REST API.

        Args:
            tenant_id: Tenant identifier
            description: Human-provided task description
            input_context: Context for the agent (description, alert data, etc.)
            alert_id: Optional alert ID used as example context
            created_by: UUID of user/system that triggered the run

        Returns:
            Created TaskGeneration with source='api'
        """
        run = TaskGeneration(
            tenant_id=tenant_id,
            workflow_generation_id=None,
            source="api",
            description=description,
            alert_id=alert_id,
            input_context=input_context,
            created_by=created_by,
            status=TaskGenerationStatus.PENDING,
            progress_messages=[],
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_by_id(
        self, tenant_id: str, run_id: str | UUID
    ) -> TaskGeneration | None:
        """Get task generation by ID with tenant isolation."""
        stmt = select(TaskGeneration).where(
            and_(
                TaskGeneration.tenant_id == tenant_id,
                TaskGeneration.id == run_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_workflow_generation(
        self, tenant_id: str, workflow_generation_id: str | UUID
    ) -> list[TaskGeneration]:
        """List all task generations for a workflow generation."""
        stmt = select(TaskGeneration).where(
            and_(
                TaskGeneration.tenant_id == tenant_id,
                TaskGeneration.workflow_generation_id == workflow_generation_id,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TaskGeneration], int]:
        """List all task generations for a tenant with pagination.

        Args:
            tenant_id: Tenant identifier
            limit: Maximum number of runs to return
            offset: Number of runs to skip

        Returns:
            Tuple of (runs list, total count)
        """
        from sqlalchemy import func

        # Get total count
        count_stmt = (
            select(func.count())
            .select_from(TaskGeneration)
            .where(TaskGeneration.tenant_id == tenant_id)
        )
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Get paginated runs, ordered by created_at descending
        stmt = (
            select(TaskGeneration)
            .where(TaskGeneration.tenant_id == tenant_id)
            .order_by(TaskGeneration.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        runs = list(result.scalars().all())

        return runs, total

    async def list_by_source(
        self,
        tenant_id: str,
        source: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TaskGeneration], int]:
        """List task generations filtered by source (e.g., 'api' or 'workflow_generation').

        Args:
            tenant_id: Tenant identifier
            source: Source filter ('api' or 'workflow_generation')
            limit: Maximum number of runs to return
            offset: Number of runs to skip

        Returns:
            Tuple of (runs list, total count)
        """
        from sqlalchemy import func

        base_filter = and_(
            TaskGeneration.tenant_id == tenant_id,
            TaskGeneration.source == source,
        )

        count_stmt = select(func.count()).select_from(TaskGeneration).where(base_filter)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        stmt = (
            select(TaskGeneration)
            .where(base_filter)
            .order_by(TaskGeneration.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        runs = list(result.scalars().all())

        return runs, total

    async def update_status(
        self,
        tenant_id: str,
        run_id: str | UUID,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> TaskGeneration | None:
        """Update task generation status and optionally result.

        Args:
            tenant_id: Tenant identifier
            run_id: Task generation ID
            status: New status (pending, running, completed, failed, cancelled)
            result: Optional result dict (task_id/cy_name on success, error on failure)

        Returns:
            Updated TaskGeneration or None if not found
        """
        run = await self.get_by_id(tenant_id, run_id)
        if not run:
            return None

        run.status = status
        run.updated_at = datetime.now(UTC)

        if result is not None:
            run.result = result

        await self.session.commit()
        return run

    async def append_progress_messages(
        self,
        tenant_id: str,
        run_id: str | UUID,
        messages: list[dict[str, Any]],
    ) -> TaskGeneration | None:
        """Append progress messages with FIFO limit.

        Appends new messages to progress_messages array, then truncates
        to keep only the last MAX_PROGRESS_MESSAGES (100) messages.

        Args:
            tenant_id: Tenant identifier
            run_id: Task generation ID
            messages: List of progress messages to append

        Returns:
            Updated TaskGeneration or None if not found
        """
        run = await self.get_by_id(tenant_id, run_id)
        if not run:
            return None

        # Get current messages (may be None if not initialized)
        current_messages = run.progress_messages or []

        # Append new messages
        updated_messages = current_messages + messages

        # Apply FIFO limit - keep only last MAX_PROGRESS_MESSAGES
        if len(updated_messages) > MAX_PROGRESS_MESSAGES:
            updated_messages = updated_messages[-MAX_PROGRESS_MESSAGES:]

        # Assign new list to trigger SQLAlchemy change tracking
        run.progress_messages = updated_messages
        run.updated_at = datetime.now(UTC)

        await self.session.commit()
        return run

    async def delete(self, tenant_id: str, run_id: str | UUID) -> bool:
        """Delete a task generation by ID with tenant isolation.

        Returns True if deleted, False if not found.
        """
        run = await self.get_by_id(tenant_id, run_id)
        if not run:
            return False

        await self.session.delete(run)
        await self.session.flush()
        return True


# Backward-compatible alias
TaskBuildingRunRepository = TaskGenerationRepository

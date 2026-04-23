"""
Repository for JobRun operations.

Project Symi: Audit records for scheduled executions. Replaces IntegrationRunRepository.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.job_run import JobRun

logger = get_logger(__name__)


class JobRunRepository:
    """Repository for job run CRUD on the partitioned job_runs table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: str,
        schedule_id: UUID | None,
        target_type: str,
        target_id: UUID,
        *,
        task_run_id: UUID | None = None,
        workflow_run_id: UUID | None = None,
        integration_id: str | None = None,
        action_id: str | None = None,
        status: str = "pending",
    ) -> JobRun:
        """Create a new job run."""
        now = datetime.now(UTC)
        job_run = JobRun(
            id=uuid4(),
            created_at=now,
            tenant_id=tenant_id,
            schedule_id=schedule_id,
            target_type=target_type,
            target_id=target_id,
            task_run_id=task_run_id,
            workflow_run_id=workflow_run_id,
            integration_id=integration_id,
            action_id=action_id,
            status=status,
            triggered_at=now,
        )
        self.session.add(job_run)
        await self.session.flush()
        return job_run

    async def update_status(
        self,
        tenant_id: str,
        job_run_id: UUID,
        status: str,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> JobRun | None:
        """Update job run status and timing. Returns None if not found.

        For partitioned tables, providing created_at improves performance.
        """
        conditions = [
            JobRun.tenant_id == tenant_id,
            JobRun.id == job_run_id,
        ]
        if created_at is not None:
            conditions.append(JobRun.created_at == created_at)

        # Build values dict
        values: dict = {"status": status}
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at

        stmt = (
            update(JobRun).where(and_(*conditions)).values(**values).returning(JobRun)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        await self.session.flush()
        return row

    async def list_by_schedule(
        self,
        tenant_id: str,
        schedule_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[JobRun]:
        """List job runs for a schedule, most recent first."""
        stmt = (
            select(JobRun)
            .where(
                and_(
                    JobRun.tenant_id == tenant_id,
                    JobRun.schedule_id == schedule_id,
                )
            )
            .order_by(desc(JobRun.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_integration(
        self,
        tenant_id: str,
        integration_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[JobRun]:
        """List job runs for an integration, most recent first."""
        stmt = (
            select(JobRun)
            .where(
                and_(
                    JobRun.tenant_id == tenant_id,
                    JobRun.integration_id == integration_id,
                )
            )
            .order_by(desc(JobRun.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

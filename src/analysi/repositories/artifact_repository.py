"""
Artifact Repository.

Handles CRUD operations for artifacts with partition awareness and multi-tenant isolation.
"""

from __future__ import annotations

import builtins
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.artifact import Artifact

# Storage class constants — mirrors ArtifactStorageService.STORAGE_*
_STORAGE_INLINE = "inline"
_STORAGE_OBJECT = "object"

logger = get_logger(__name__)


class ArtifactRepository:
    """Repository for artifact CRUD operations with partition and tenant awareness."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, artifact_data: dict[str, Any]) -> Artifact:
        """
        Create new artifact with partition awareness.

        Args:
            artifact_data: Dictionary with artifact fields

        Returns:
            Created Artifact instance

        Raises:
            ValueError: If required fields missing
            IntegrityError: If constraint violations
        """
        logger.debug("creating_artifact", keys=list(artifact_data.keys()))
        artifact = Artifact(**artifact_data)

        self.session.add(artifact)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(artifact)

        return artifact

    async def get_by_id(self, tenant_id: str, artifact_id: UUID) -> Artifact | None:
        """
        Retrieve artifact by ID with tenant isolation.

        Args:
            tenant_id: Tenant identifier for isolation
            artifact_id: Artifact UUID

        Returns:
            Artifact instance or None if not found
        """
        stmt = select(Artifact).where(
            and_(
                Artifact.id == artifact_id,
                Artifact.tenant_id == tenant_id,
                Artifact.deleted_at.is_(None),
            )
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        tenant_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Artifact], int]:
        """
        List artifacts with filtering, pagination and sorting.

        Args:
            tenant_id: Tenant identifier for isolation
            filters: Optional filters (name, artifact_type, tags, task_run_id, etc.)
            limit: Page size
            offset: Pagination offset
            sort_by: Sort field (name, created_at, size_bytes)
            sort_order: Sort direction (asc, desc)

        Returns:
            Tuple of (artifacts_list, total_count)
        """
        # Base query with tenant isolation and non-deleted items
        base_query = select(Artifact).where(
            and_(Artifact.tenant_id == tenant_id, Artifact.deleted_at.is_(None))
        )

        # Apply filters
        if filters:
            if "name" in filters:
                # Escape SQL LIKE wildcards to prevent unintended pattern matching
                escaped_name = filters["name"].replace("%", r"\%").replace("_", r"\_")
                base_query = base_query.where(Artifact.name.ilike(f"%{escaped_name}%"))
            if "artifact_type" in filters:
                base_query = base_query.where(
                    Artifact.artifact_type == filters["artifact_type"]
                )
            if "task_run_id" in filters:
                base_query = base_query.where(
                    Artifact.task_run_id == filters["task_run_id"]
                )
            if "workflow_run_id" in filters:
                base_query = base_query.where(
                    Artifact.workflow_run_id == filters["workflow_run_id"]
                )
            if "analysis_id" in filters:
                base_query = base_query.where(
                    Artifact.analysis_id == filters["analysis_id"]
                )
            if "alert_id" in filters:
                base_query = base_query.where(Artifact.alert_id == filters["alert_id"])
            if "mime_type" in filters:
                base_query = base_query.where(
                    Artifact.mime_type == filters["mime_type"]
                )
            if "storage_class" in filters:
                base_query = base_query.where(
                    Artifact.storage_class == filters["storage_class"]
                )
            if "integration_id" in filters:
                base_query = base_query.where(
                    Artifact.integration_id == filters["integration_id"]
                )
            if "source" in filters:
                base_query = base_query.where(Artifact.source == filters["source"])
            if "tags" in filters and isinstance(filters["tags"], list):
                # Check if any of the provided tags exist in the artifact's tags array
                for tag in filters["tags"]:
                    base_query = base_query.where(Artifact.tags.contains([tag]))

        # Count query
        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        # Apply sorting
        sort_column = getattr(Artifact, sort_by, Artifact.created_at)
        if sort_order.lower() == "asc":
            base_query = base_query.order_by(sort_column.asc())
        else:
            base_query = base_query.order_by(sort_column.desc())

        # Apply pagination
        base_query = base_query.offset(offset).limit(limit)

        # Execute query
        result = await self.session.execute(base_query)
        artifacts = result.scalars().all()

        return list(artifacts), total

    async def get_by_task_run(
        self, tenant_id: str, task_run_id: UUID
    ) -> builtins.list[Artifact]:
        """
        Get all artifacts created by a specific task run.

        Args:
            tenant_id: Tenant identifier
            task_run_id: Task run UUID

        Returns:
            List of artifacts
        """
        stmt = (
            select(Artifact)
            .where(
                and_(
                    Artifact.tenant_id == tenant_id,
                    Artifact.task_run_id == task_run_id,
                    Artifact.deleted_at.is_(None),
                )
            )
            .order_by(Artifact.created_at.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_workflow_run(
        self, tenant_id: str, workflow_run_id: UUID
    ) -> builtins.list[Artifact]:
        """
        Get all artifacts created by a specific workflow run.

        Args:
            tenant_id: Tenant identifier
            workflow_run_id: Workflow run UUID

        Returns:
            List of artifacts
        """
        stmt = (
            select(Artifact)
            .where(
                and_(
                    Artifact.tenant_id == tenant_id,
                    Artifact.workflow_run_id == workflow_run_id,
                    Artifact.deleted_at.is_(None),
                )
            )
            .order_by(Artifact.created_at.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_analysis(
        self, tenant_id: str, analysis_id: UUID
    ) -> builtins.list[Artifact]:
        """
        Get all artifacts for a specific analysis.

        Args:
            tenant_id: Tenant identifier
            analysis_id: Analysis UUID

        Returns:
            List of artifacts for the analysis
        """
        stmt = (
            select(Artifact)
            .where(
                and_(
                    Artifact.tenant_id == tenant_id,
                    Artifact.analysis_id == analysis_id,
                    Artifact.deleted_at.is_(None),
                )
            )
            .order_by(Artifact.created_at.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete(self, tenant_id: str, artifact_id: UUID) -> bool:
        """
        Soft delete artifact (mark as deleted, preserve data).

        Args:
            tenant_id: Tenant identifier
            artifact_id: Artifact UUID

        Returns:
            True if deleted, False if not found
        """
        # Get the artifact first to check if it exists
        artifact = await self.get_by_id(tenant_id, artifact_id)
        if not artifact:
            return False

        # Mark as soft deleted
        artifact.deleted_at = datetime.now(UTC)

        # Commit the change
        await self.session.commit()

        return True

    async def get_storage_stats(self, tenant_id: str) -> dict[str, Any]:
        """
        Get storage statistics for tenant (inline vs object storage usage).

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary with storage statistics
        """
        stmt = select(
            func.count().label("total"),
            func.coalesce(func.sum(Artifact.size_bytes), 0).label("total_size"),
            func.count(case((Artifact.storage_class == _STORAGE_INLINE, 1))).label(
                "inline_count"
            ),
            func.coalesce(
                func.sum(
                    case(
                        (Artifact.storage_class == _STORAGE_INLINE, Artifact.size_bytes)
                    )
                ),
                0,
            ).label("inline_size"),
            func.count(case((Artifact.storage_class == _STORAGE_OBJECT, 1))).label(
                "object_count"
            ),
            func.coalesce(
                func.sum(
                    case(
                        (Artifact.storage_class == _STORAGE_OBJECT, Artifact.size_bytes)
                    )
                ),
                0,
            ).label("object_size"),
        ).where(
            and_(
                Artifact.tenant_id == tenant_id,
                Artifact.deleted_at.is_(None),
            )
        )

        result = await self.session.execute(stmt)
        row = result.one()

        return {
            "total_artifacts": row.total,
            "total_size_bytes": row.total_size,
            "inline_artifacts": row.inline_count,
            "inline_size_bytes": row.inline_size,
            "object_artifacts": row.object_count,
            "object_size_bytes": row.object_size,
        }

    async def cleanup_old_artifacts(self, days_old: int = 90) -> int:
        """
        Soft-delete artifacts older than specified days that are not already deleted.

        Args:
            days_old: Age threshold in days

        Returns:
            Number of artifacts marked as deleted
        """
        threshold = datetime.now(UTC) - timedelta(days=days_old)

        stmt = (
            update(Artifact)
            .where(
                and_(
                    Artifact.deleted_at.is_(None),
                    Artifact.created_at < threshold,
                )
            )
            .values(deleted_at=func.now())
        )

        result = await self.session.execute(stmt)
        await self.session.commit()

        return result.rowcount

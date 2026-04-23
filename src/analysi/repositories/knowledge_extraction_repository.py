"""Repository for knowledge extraction CRUD operations — Hydra project."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.knowledge_extraction import KnowledgeExtraction
from analysi.schemas.knowledge_extraction import ExtractionStatus


class KnowledgeExtractionRepository:
    """CRUD operations for knowledge_extractions table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        tenant_id: str,
        skill_id: UUID,
        document_id: UUID,
    ) -> KnowledgeExtraction:
        """Create a new extraction record with status=pending."""
        extraction = KnowledgeExtraction(
            tenant_id=tenant_id,
            skill_id=skill_id,
            document_id=document_id,
            status=ExtractionStatus.PENDING,
        )
        self.session.add(extraction)
        await self.session.flush()
        return extraction

    async def get_by_id(
        self,
        tenant_id: str,
        extraction_id: UUID,
    ) -> KnowledgeExtraction | None:
        """Get extraction by ID with tenant isolation."""
        stmt = select(KnowledgeExtraction).where(
            and_(
                KnowledgeExtraction.tenant_id == tenant_id,
                KnowledgeExtraction.id == extraction_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(
        self,
        tenant_id: str,
        extraction_id: UUID,
    ) -> KnowledgeExtraction | None:
        """Get extraction by ID with row-level lock (SELECT FOR UPDATE).

        Use this for state-transition operations (apply, reject) to prevent
        race conditions where two concurrent requests both read status=completed.
        """
        stmt = (
            select(KnowledgeExtraction)
            .where(
                and_(
                    KnowledgeExtraction.tenant_id == tenant_id,
                    KnowledgeExtraction.id == extraction_id,
                )
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_skill(
        self,
        tenant_id: str,
        skill_id: UUID,
        status: str | None = None,
        document_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[KnowledgeExtraction], int]:
        """List extractions for a skill with optional filters."""
        conditions = [
            KnowledgeExtraction.tenant_id == tenant_id,
            KnowledgeExtraction.skill_id == skill_id,
        ]
        if status:
            conditions.append(KnowledgeExtraction.status == status)
        if document_id:
            conditions.append(KnowledgeExtraction.document_id == document_id)

        where = and_(*conditions)

        count_stmt = select(func.count()).select_from(KnowledgeExtraction).where(where)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        stmt = (
            select(KnowledgeExtraction)
            .where(where)
            .order_by(KnowledgeExtraction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        extractions = list(result.scalars().all())
        return extractions, total

    async def update_pipeline_outputs(
        self,
        extraction: KnowledgeExtraction,
        status: str,
        classification: dict[str, Any] | None = None,
        relevance: dict[str, Any] | None = None,
        placement: dict[str, Any] | None = None,
        transformed_content: str | None = None,
        merge_info: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        extraction_summary: str | None = None,
        error_message: str | None = None,
        rejection_reason: str | None = None,
    ) -> KnowledgeExtraction:
        """Update extraction with pipeline results."""
        extraction.status = status
        if classification is not None:
            extraction.classification = classification
        if relevance is not None:
            extraction.relevance = relevance
        if placement is not None:
            extraction.placement = placement
        if transformed_content is not None:
            extraction.transformed_content = transformed_content
        if merge_info is not None:
            extraction.merge_info = merge_info
        if validation is not None:
            extraction.validation = validation
        if extraction_summary is not None:
            extraction.extraction_summary = extraction_summary
        if error_message is not None:
            extraction.error_message = error_message
        if rejection_reason is not None:
            extraction.rejection_reason = rejection_reason
        await self.session.flush()
        return extraction

    async def apply(
        self,
        extraction: KnowledgeExtraction,
        applied_document_id: UUID,
    ) -> KnowledgeExtraction:
        """Mark extraction as applied with the resulting document ID."""
        extraction.status = "applied"
        extraction.applied_document_id = applied_document_id
        extraction.applied_at = datetime.now(UTC)
        await self.session.flush()
        return extraction

    async def reject(
        self,
        extraction: KnowledgeExtraction,
        reason: str | None = None,
    ) -> KnowledgeExtraction:
        """Mark extraction as rejected."""
        extraction.status = "rejected"
        extraction.rejection_reason = reason
        extraction.rejected_at = datetime.now(UTC)
        await self.session.flush()
        return extraction

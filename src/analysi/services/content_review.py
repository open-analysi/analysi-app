"""Content review service.

Manages the lifecycle of content reviews through the conveyor belt:
submit → sync gate → enqueue → worker → complete → apply/reject.
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.agentic_orchestration.langgraph.content_review.content_gates import (
    all_gates_passed,
    filter_gates_for_owner,
    run_content_gates,
)
from analysi.agentic_orchestration.langgraph.content_review.pipeline import (
    get_pipeline_by_name,
)
from analysi.config.logging import get_logger
from analysi.models.content_review import ContentReview, ContentReviewStatus

logger = get_logger(__name__)

S = ContentReviewStatus  # Short alias for status checks

# Only the owner role can bypass LLM tier
BYPASS_ROLES = ["owner"]


class ContentReviewService:
    """Service for content review lifecycle management."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def submit_for_review(
        self,
        content: str,
        filename: str,
        skill_id: UUID,
        tenant_id: str,
        pipeline_name: str,
        trigger_source: str,
        actor_user_id: UUID | None = None,
        actor_roles: list[str] | None = None,
        document_id: UUID | None = None,
    ) -> ContentReview:
        """Submit content for review through the pipeline.

        Runs content gates synchronously. If they fail, raises ContentReviewGateError.
        If they pass:
        - Owner role: creates record with status=approved, bypassed=True (LLM skipped)
        - Other roles: creates record with status=pending, enqueues ARQ job

        Args:
            content: The content to review.
            filename: Original filename.
            skill_id: Target skill ID.
            tenant_id: Tenant scoping.
            pipeline_name: Which pipeline to use ('extraction', 'skill_validation').
            trigger_source: What triggered this review ('ku_create', 'zip_import', etc).
            actor_user_id: User who submitted the content.
            actor_roles: Roles of the submitting user (for bypass check).
            document_id: Reference to source KUDocument if applicable.

        Returns:
            The created ContentReview record.

        Raises:
            ContentReviewGateError: If content gates fail.
            ValueError: If pipeline_name is not registered.
        """
        pipeline = get_pipeline_by_name(pipeline_name)

        # Determine bypass early — owner + skill_validation skips LLM and
        # content_policy_gate (cybersecurity skills legitimately contain XSS
        # payloads, SQL injection examples, etc.).
        # Extraction always goes through full pipeline for all roles.
        bypass = pipeline_name == "skill_validation" and self._should_bypass(
            actor_roles or []
        )

        # Run content gates — owner bypass skips content_policy_gate and
        # python_ast_gate. Structural gates (empty, length, format) always run.
        gates = pipeline.content_gates()
        if bypass:
            gates = filter_gates_for_owner(gates)
        gate_results = run_content_gates(content, filename, gates)
        checks_passed = all_gates_passed(gate_results)

        if not checks_passed:
            raise ContentReviewGateError(
                gate_results=[r.model_dump() for r in gate_results],
            )

        # Create review record
        review = ContentReview(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            skill_id=skill_id,
            pipeline_name=pipeline_name,
            pipeline_mode=pipeline.mode,
            trigger_source=trigger_source,
            document_id=document_id,
            original_filename=filename,
            original_content=content,
            content_gates_passed=True,
            content_gates_result=[r.model_dump() for r in gate_results],
            status=S.APPROVED.value if bypass else S.PENDING.value,
            actor_user_id=actor_user_id,
            bypassed=bypass,
        )

        if bypass:
            review.completed_at = datetime.now(UTC)

        self.session.add(review)
        await self.session.flush()

        if bypass:
            # Owner bypass: auto-apply immediately (create document + link to skill)
            try:
                applied_doc_id = await self._create_and_link_document(
                    tenant_id=tenant_id,
                    skill_id=skill_id,
                    filename=filename,
                    content=content,
                )
                review.status = S.APPLIED.value
                review.applied_at = datetime.now(UTC)
                review.applied_document_id = applied_doc_id
                await self.session.flush()
            except Exception as e:
                from sqlalchemy.exc import IntegrityError

                if isinstance(e, IntegrityError) and "duplicate key" in str(e):
                    logger.warning(
                        "bypass_apply_duplicate_document",
                        filename=filename,
                        skill_id=str(skill_id),
                    )
                    await self.session.rollback()
                    # Re-create review as applied (previous doc already exists)
                    review = ContentReview(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        skill_id=skill_id,
                        pipeline_name=pipeline_name,
                        pipeline_mode=pipeline.mode,
                        trigger_source=trigger_source,
                        document_id=document_id,
                        original_filename=filename,
                        original_content=content,
                        content_gates_passed=True,
                        content_gates_result=[r.model_dump() for r in gate_results],
                        status=S.APPLIED.value,
                        actor_user_id=actor_user_id,
                        bypassed=True,
                        completed_at=datetime.now(UTC),
                        applied_at=datetime.now(UTC),
                    )
                    self.session.add(review)
                    await self.session.flush()
                else:
                    raise
        else:
            await self._enqueue_review_job(
                review, tenant_id, pipeline_name, actor_user_id
            )

        logger.info(
            "content_review_submitted",
            extra={
                "review_id": str(review.id),
                "pipeline_name": pipeline_name,
                "tenant_id": tenant_id,
                "status": review.status,
                "bypassed": bypass,
            },
        )

        return review

    async def complete_review(
        self,
        review_id: UUID,
        pipeline_result: dict[str, Any],
        status: ContentReviewStatus | str,
        transformed_content: str | None = None,
        summary: str | None = None,
        error_message: str | None = None,
        error_code: str | None = None,
        error_detail: dict[str, Any] | None = None,
    ) -> ContentReview:
        """Called by the ARQ worker after pipeline finishes.

        Args:
            review_id: The review to complete.
            pipeline_result: Output from the LangGraph pipeline.
            status: Target status (APPROVED, FLAGGED, or FAILED).
            transformed_content: Transformed content for review_transform mode.
            summary: LLM-generated summary.
            error_message: Error message if status is 'failed'.
            error_code: Machine-readable error code (e.g. 'pipeline_timeout').
            error_detail: Structured detail dict with title, hint, etc.

        Returns:
            The updated ContentReview record.

        Raises:
            ContentReviewStateError: If review is not in 'pending' state.
        """
        review = await self._get_review_by_id(review_id)
        status_val = status.value if isinstance(status, ContentReviewStatus) else status

        # Allow completing a pending review, or marking any review as failed
        # (error recovery path from worker)
        if review.status != S.PENDING.value and status_val != S.FAILED.value:
            raise ContentReviewStateError(
                f"Cannot complete review in status '{review.status}'. "
                f"Must be 'pending'."
            )

        review.pipeline_result = pipeline_result
        review.status = status_val
        review.transformed_content = transformed_content
        review.summary = summary
        review.error_message = error_message
        review.error_code = error_code
        review.error_detail = error_detail
        review.completed_at = datetime.now(UTC)

        await self.session.flush()

        logger.info(
            "content_review_completed",
            extra={
                "review_id": str(review_id),
                "status": status,
            },
        )

        return review

    async def apply_review(
        self,
        review_id: UUID,
        tenant_id: str,
    ) -> ContentReview:
        """Apply an approved or flagged review.

        Creates a KUDocument from the review content (or transformed_content)
        and links it to the skill via a CONTAINS edge.

        Args:
            review_id: The review to apply.
            tenant_id: Tenant scoping (required).

        Returns:
            The updated ContentReview record.

        Raises:
            ContentReviewStateError: If review is not in appliable state.
        """
        review = await self._get_review_for_tenant(review_id, tenant_id)

        # Skill reviews cannot be manually applied — only auto_apply_review
        # (called by the worker) is allowed. This prevents admins from
        # bypassing LLM validation by manually approving their own uploads.
        if review.pipeline_name == "skill_validation":
            raise ContentReviewStateError(
                "Skill reviews cannot be manually applied. "
                "They are auto-applied after passing LLM validation."
            )

        if review.status not in (S.APPROVED.value, S.FLAGGED.value):
            raise ContentReviewStateError(
                f"Cannot apply review in status '{review.status}'. "
                f"Must be 'approved' or 'flagged'."
            )

        # Determine content: prefer transformed, fall back to original
        content = review.transformed_content or review.original_content or ""

        # Create KUDocument and link to skill
        applied_doc_id = await self._create_and_link_document(
            tenant_id=tenant_id,
            skill_id=review.skill_id,
            filename=review.original_filename or "document.md",
            content=content,
        )

        review.status = S.APPLIED.value
        review.applied_at = datetime.now(UTC)
        review.applied_document_id = applied_doc_id

        await self.session.flush()

        logger.info(
            "content_review_applied",
            extra={
                "review_id": str(review_id),
                "document_id": str(applied_doc_id),
            },
        )

        return review

    async def reject_review(
        self,
        review_id: UUID,
        tenant_id: str,
        reason: str | None = None,
    ) -> ContentReview:
        """Reject a review.

        Args:
            review_id: The review to reject.
            tenant_id: Tenant scoping (required).
            reason: Optional rejection reason.

        Returns:
            The updated ContentReview record.

        Raises:
            ContentReviewStateError: If review is not in rejectable state.
        """
        review = await self._get_review_for_tenant(review_id, tenant_id)

        if review.status not in (S.APPROVED.value, S.FLAGGED.value, S.PENDING.value):
            raise ContentReviewStateError(
                f"Cannot reject review in status '{review.status}'. "
                f"Must be 'pending', 'approved', or 'flagged'."
            )

        review.status = S.REJECTED.value
        review.rejection_reason = reason

        await self.session.flush()

        logger.info(
            "content_review_rejected",
            extra={"review_id": str(review_id), "reason": reason},
        )

        return review

    async def get_review(self, review_id: UUID, tenant_id: str) -> ContentReview | None:
        """Get a review by ID, scoped to tenant."""
        result = await self.session.execute(
            select(ContentReview).where(
                ContentReview.id == review_id,
                ContentReview.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_reviews(
        self,
        tenant_id: str,
        skill_id: UUID,
        status: str | None = None,
        pipeline_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentReview], int]:
        """List reviews for a skill, with optional filters.

        Returns:
            Tuple of (reviews, total_count).
        """
        from sqlalchemy import func

        base_where = [
            ContentReview.tenant_id == tenant_id,
            ContentReview.skill_id == skill_id,
        ]
        if status:
            base_where.append(ContentReview.status == status)
        if pipeline_name:
            base_where.append(ContentReview.pipeline_name == pipeline_name)

        # Count total
        count_query = select(func.count()).select_from(ContentReview).where(*base_where)
        total = (await self.session.execute(count_query)).scalar() or 0

        # Fetch page
        query = (
            select(ContentReview)
            .where(*base_where)
            .order_by(ContentReview.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def auto_apply_review(
        self,
        review_id: UUID,
        tenant_id: str,
    ) -> ContentReview:
        """Auto-apply an approved review (called by worker after LLM approval).

        Same as apply_review but doesn't require tenant check since the worker
        already validated the review_id.
        """
        review = await self._get_review_by_id(review_id)

        if review.status != S.APPROVED.value:
            return review  # Not approved, nothing to auto-apply

        content = review.transformed_content or review.original_content or ""

        applied_doc_id = await self._create_and_link_document(
            tenant_id=tenant_id,
            skill_id=review.skill_id,
            filename=review.original_filename or "document.md",
            content=content,
        )

        review.status = S.APPLIED.value
        review.applied_at = datetime.now(UTC)
        review.applied_document_id = applied_doc_id

        await self.session.flush()

        logger.info(
            "content_review_auto_applied",
            extra={
                "review_id": str(review_id),
                "document_id": str(applied_doc_id),
            },
        )

        return review

    async def retry_review(
        self,
        review_id: UUID,
        tenant_id: str,
    ) -> ContentReview:
        """Retry a failed content review by re-enqueuing it.

        Resets the review to pending and enqueues a new ARQ job.

        Args:
            review_id: The review to retry.
            tenant_id: Tenant scoping.

        Returns:
            The updated ContentReview record.

        Raises:
            ContentReviewStateError: If review is not in 'failed' state.
        """
        review = await self._get_review_for_tenant(review_id, tenant_id)

        if review.status != S.FAILED.value:
            raise ContentReviewStateError(
                f"Cannot retry review in status '{review.status}'. "
                f"Only 'failed' reviews can be retried."
            )

        review.status = S.PENDING.value
        review.error_message = None
        review.error_code = None
        review.error_detail = None
        review.pipeline_result = None
        review.completed_at = None
        review.updated_at = datetime.now(UTC)

        await self.session.flush()

        await self._enqueue_review_job(
            review, tenant_id, review.pipeline_name, review.actor_user_id
        )

        logger.info(
            "content_review_retried",
            extra={"review_id": str(review_id)},
        )

        return review

    # --- Private helpers ---

    async def _create_and_link_document(
        self,
        tenant_id: str,
        skill_id: UUID,
        filename: str,
        content: str,
    ) -> UUID:
        """Create a KUDocument from review content and link it to the skill.

        Follows the same pattern as KnowledgeExtractionService._create_new_document.

        Returns:
            The created document's component_id.
        """
        from analysi.models.auth import SYSTEM_USER_ID
        from analysi.repositories.knowledge_module import KnowledgeModuleRepository
        from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
        from analysi.services.knowledge_module import KnowledgeModuleService

        ku_repo = KnowledgeUnitRepository(self.session)
        skill_repo = KnowledgeModuleRepository(self.session)

        # Get skill for namespace scoping
        skill = await skill_repo.get_skill_by_id(skill_id, tenant_id)
        skill_cy_name = (
            skill.component.cy_name if skill and skill.component else "unknown"
        )
        skill_namespace = f"/{skill_cy_name}/"

        # Derive document name from filename (strip extension)
        import os

        doc_name = os.path.splitext(filename)[0]

        # Inherit app from the parent skill
        skill_app = skill.component.app if skill and skill.component else "default"

        doc = await ku_repo.create_document_ku(
            tenant_id=tenant_id,
            data={
                "name": doc_name,
                "content": content,
                "doc_format": "markdown",
                "document_type": "skill_content",
                "content_source": "content_review",
                "created_by": SYSTEM_USER_ID,
                "app": skill_app,
            },
            namespace=skill_namespace,
        )

        # Link document to skill via CONTAINS edge
        km_service = KnowledgeModuleService(self.session)
        await km_service.add_document(
            tenant_id=tenant_id,
            skill_id=skill_id,
            document_id=doc.component_id,
            namespace_path=filename,
        )

        return doc.component_id

    async def cascade_reject_skill(
        self,
        skill_id: UUID,
        tenant_id: str,
        trigger_review_id: UUID,
        reason: str,
    ) -> dict[str, int]:
        """Reject all reviews for a skill and clean up the skill.

        Called when any document in a skill import is rejected or flagged.
        For skill_validation pipeline, there is no human-in-the-loop: a
        single bad document rejects the entire skill.

        Steps:
        1. Reject all pending/approved sibling reviews
        2. Roll back any already-applied documents (delete docs, unlink)
        3. Delete the skill if it has no remaining applied content

        Args:
            skill_id: The skill whose reviews should be cascade-rejected.
            tenant_id: Tenant scoping.
            trigger_review_id: The review that triggered the cascade (skip it).
            reason: Rejection reason to set on sibling reviews.

        Returns:
            Dict with counts: {rejected, rolled_back, skill_deleted}.
        """
        from sqlalchemy import and_

        # Find all sibling reviews for this skill (exclude the trigger)
        result = await self.session.execute(
            select(ContentReview).where(
                and_(
                    ContentReview.skill_id == skill_id,
                    ContentReview.tenant_id == tenant_id,
                    ContentReview.id != trigger_review_id,
                )
            )
        )
        siblings = list(result.scalars().all())

        rejected_count = 0
        rollback_count = 0

        for review in siblings:
            if review.status in (S.PENDING.value, S.APPROVED.value, S.FLAGGED.value):
                review.status = S.REJECTED.value
                review.rejection_reason = reason
                review.completed_at = datetime.now(UTC)
                rejected_count += 1

            if review.status == S.APPLIED.value and review.applied_document_id:
                # Roll back: delete the applied document and unlink from skill
                await self._rollback_applied_document(
                    tenant_id, skill_id, review.applied_document_id
                )
                review.status = S.REJECTED.value
                review.rejection_reason = reason
                review.completed_at = datetime.now(UTC)
                rollback_count += 1

        await self.session.flush()

        # Delete the skill if it has no remaining applied documents
        skill_deleted = await self._delete_skill_if_empty(skill_id, tenant_id)

        logger.info(
            "cascade_reject_skill_completed",
            extra={
                "skill_id": str(skill_id),
                "trigger_review_id": str(trigger_review_id),
                "rejected": rejected_count,
                "rolled_back": rollback_count,
                "skill_deleted": skill_deleted,
            },
        )

        return {
            "rejected": rejected_count,
            "rolled_back": rollback_count,
            "skill_deleted": skill_deleted,
        }

    async def _rollback_applied_document(
        self,
        tenant_id: str,
        skill_id: UUID,
        document_id: UUID,
    ) -> None:
        """Delete an applied document and unlink it from the skill."""
        from analysi.services.knowledge_module import KnowledgeModuleService

        km_service = KnowledgeModuleService(self.session)
        try:
            await km_service.remove_document(
                tenant_id=tenant_id,
                skill_id=skill_id,
                document_id=document_id,
            )
        except Exception:
            logger.warning(
                "rollback_document_failed",
                extra={
                    "skill_id": str(skill_id),
                    "document_id": str(document_id),
                },
            )

    async def _delete_skill_if_empty(
        self,
        skill_id: UUID,
        tenant_id: str,
    ) -> bool:
        """Delete a skill if it has no applied content reviews remaining."""
        remaining = await self.session.execute(
            select(ContentReview.id).where(
                ContentReview.skill_id == skill_id,
                ContentReview.tenant_id == tenant_id,
                ContentReview.status == S.APPLIED.value,
            )
        )
        if remaining.first() is not None:
            return False

        from analysi.services.knowledge_module import KnowledgeModuleService

        km_service = KnowledgeModuleService(self.session)
        try:
            deleted = await km_service.delete_skill(skill_id, tenant_id)
            if deleted:
                logger.info(
                    "rejected_skill_deleted",
                    extra={"skill_id": str(skill_id)},
                )
            return deleted
        except Exception:
            logger.warning(
                "rejected_skill_delete_failed",
                extra={"skill_id": str(skill_id)},
            )
            return False

    def _should_bypass(self, actor_roles: list[str]) -> bool:
        """Check if the actor's roles qualify for bypass."""
        return any(role in BYPASS_ROLES for role in actor_roles)

    async def _get_review_for_tenant(
        self, review_id: UUID, tenant_id: str
    ) -> ContentReview:
        """Fetch a review by ID scoped to tenant, or raise.

        Used by all public methods (apply, reject) that operate through the API.
        """
        result = await self.session.execute(
            select(ContentReview).where(
                ContentReview.id == review_id,
                ContentReview.tenant_id == tenant_id,
            )
        )
        review = result.scalar_one_or_none()
        if review is None:
            raise ValueError("Content review not found")
        return review

    async def _get_review_by_id(self, review_id: UUID) -> ContentReview:
        """Fetch a review by ID only (no tenant check). Internal use only.

        Used by complete_review (called from ARQ worker with trusted review_id).
        """
        result = await self.session.execute(
            select(ContentReview).where(ContentReview.id == review_id)
        )
        review = result.scalar_one_or_none()
        if review is None:
            raise ValueError("Content review not found")
        return review

    async def _enqueue_review_job(
        self,
        review: ContentReview,
        tenant_id: str,
        pipeline_name: str,
        actor_user_id: UUID | None,
    ) -> None:
        """Enqueue ARQ job for async LLM processing."""
        try:
            from arq import create_pool

            from analysi.config.valkey_db import ValkeyDBConfig

            redis = await create_pool(
                ValkeyDBConfig.get_redis_settings(
                    database=ValkeyDBConfig.ALERT_PROCESSING_DB
                )
            )
            try:
                # Use a unique job_id each time so retries aren't blocked
                # by ARQ's job deduplication (it remembers completed job IDs).
                job_id = f"{review.id}:{uuid.uuid4().hex[:8]}"
                await redis.enqueue_job(
                    "analysi.alert_analysis.jobs.content_review.execute_content_review",
                    str(review.id),
                    tenant_id,
                    pipeline_name,
                    str(actor_user_id) if actor_user_id else None,
                    _job_id=job_id,
                    _job_timeout=900,
                )
            finally:
                await redis.aclose()
        except Exception:
            logger.exception(
                "failed_to_enqueue_content_review",
                extra={"review_id": str(review.id)},
            )
            # Mark as failed if we can't enqueue
            review.status = S.FAILED.value
            review.error_message = "Failed to enqueue review job"
            review.error_code = "enqueue_failed"
            review.error_detail = {
                "title": "Processing queue unavailable",
                "hint": "The review could not be queued for processing. Try again later.",
            }
            await self.session.flush()


class ContentReviewGateError(Exception):
    """Raised when content gates fail."""

    def __init__(self, gate_results: list[dict]):
        self.gate_results = gate_results
        failed = [r for r in gate_results if not r["passed"]]
        errors = []
        for r in failed:
            errors.extend(r["errors"])
        super().__init__(f"Content gate violation: {'; '.join(errors)}")


class ContentReviewStateError(Exception):
    """Raised on invalid state transitions."""

    pass

"""ARQ job for content review pipeline execution.

Registered in WorkerSettings.functions. Picks up pending content reviews,
runs the LangGraph pipeline (LLM tier), and stores results.

Pattern follows execute_workflow_generation and execute_control_event:
- @tracked_job decorator for correlation context, timeout, job_tracking JSONB
- AsyncSessionLocal for database access
- Marks review as failed on error, then re-raises for @tracked_job
"""

from typing import Any

from analysi.common.job_tracking import tracked_job
from analysi.config.logging import get_logger
from analysi.db.session import AsyncSessionLocal
from analysi.models.content_review import ContentReview, ContentReviewStatus

logger = get_logger(__name__)


@tracked_job(
    job_type="execute_content_review",
    timeout_seconds=900,
    model_class=ContentReview,
    extract_row_id=lambda ctx, review_id, tenant_id, pipeline_name, actor_user_id=None, **kw: (
        review_id
    ),
)
async def execute_content_review(
    ctx: dict[str, Any],
    review_id: str,
    tenant_id: str,
    pipeline_name: str,
    actor_user_id: str | None = None,
    **_arq_kwargs: Any,
) -> dict[str, Any]:
    """Execute a content review pipeline for a pending review.

    Args:
        ctx: ARQ worker context.
        review_id: UUID of the content review record.
        tenant_id: Tenant scoping.
        pipeline_name: Which pipeline to run ('extraction', 'skill_validation').
        actor_user_id: Optional user ID for tracing.

    Returns:
        Dict with status and review_id.
    """
    # Correlation + tenant context set by @tracked_job (Project Leros)

    logger.info(
        "content_review_job_started",
        extra={
            "review_id": review_id,
            "pipeline_name": pipeline_name,
            "tenant_id": tenant_id,
        },
    )

    try:
        from uuid import UUID

        from analysi.agentic_orchestration.langgraph.content_review.pipeline import (
            get_pipeline_by_name,
        )
        from analysi.models.content_review import ContentReview
        from analysi.services.content_review import ContentReviewService

        # Load review record
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(ContentReview).where(ContentReview.id == UUID(review_id))
            )
            review = result.scalar_one_or_none()
            if review is None:
                logger.error(
                    "content_review_not_found",
                    extra={"review_id": review_id},
                )
                return {"status": "not_found", "review_id": review_id}

            # Load content: prefer original_content (zip imports), fall back to document
            if review.original_content:
                content = review.original_content
            elif review.document_id:
                from analysi.repositories.knowledge_unit import (
                    KnowledgeUnitRepository,
                )

                ku_repo = KnowledgeUnitRepository(session)
                doc = await ku_repo.get_document_by_id(
                    review.document_id, review.tenant_id
                )
                content = doc.content if doc else ""
            else:
                content = ""

            # Get pipeline and LLM
            pipeline = get_pipeline_by_name(pipeline_name)

            # Get LLM from primary integration (same as task execution)
            from analysi.repositories.integration_repository import (
                IntegrationRepository,
            )
            from analysi.services.integration_service import IntegrationService
            from analysi.services.llm_factory import LangChainFactory

            integration_repo = IntegrationRepository(session)
            integration_service = IntegrationService(
                integration_repo=integration_repo,
            )
            llm_factory = LangChainFactory(integration_service)
            llm = await llm_factory.get_primary_llm(tenant_id, session)

            # Create skills store for SkillsIR retrieval
            from analysi.agentic_orchestration.langgraph.config import (
                get_db_skills_store,
            )

            store = get_db_skills_store(tenant_id)

            # Build and run graph
            graph = pipeline.build_graph(llm)
            initial_state = pipeline.initial_state(
                content=content,
                skill_id=str(review.skill_id),
                document_id=str(review.document_id) if review.document_id else None,
                tenant_id=tenant_id,
                store=store,
                original_filename=review.original_filename or "unknown",
            )
            final_state = await graph.ainvoke(initial_state)

            # Extract results
            pipeline_result = pipeline.extract_results(final_state)

            # Determine status from pipeline result
            status = pipeline_result.pop("_status", "approved")
            transformed_content = pipeline_result.pop("_transformed_content", None)
            summary = pipeline_result.pop("_summary", None)

            # Complete the review
            service = ContentReviewService(session)

            # For skill_validation: flagged → rejected (no human in the loop)
            if (
                pipeline_name == "skill_validation"
                and status == ContentReviewStatus.FLAGGED.value
            ):
                status = ContentReviewStatus.REJECTED.value

            await service.complete_review(
                review_id=UUID(review_id),
                pipeline_result=pipeline_result,
                status=status,
                transformed_content=transformed_content,
                summary=summary,
            )

            # Auto-apply approved reviews: create KUDocument and link to skill
            if status == ContentReviewStatus.APPROVED.value:
                await service.auto_apply_review(
                    review_id=UUID(review_id),
                    tenant_id=tenant_id,
                )

            # Skill cascade rejection: one bad document rejects the entire skill
            if (
                pipeline_name == "skill_validation"
                and status == ContentReviewStatus.REJECTED.value
            ):
                rejection_reason = (
                    summary
                    or f"Rejected due to content policy violation in "
                    f"{review.original_filename or 'a document'}"
                )
                await service.cascade_reject_skill(
                    skill_id=review.skill_id,
                    tenant_id=tenant_id,
                    trigger_review_id=UUID(review_id),
                    reason=f"Cascade rejection: {rejection_reason}",
                )

            await session.commit()

        logger.info(
            "content_review_job_completed",
            extra={
                "review_id": review_id,
                "status": status,
            },
        )

        return {"status": "completed", "review_id": review_id}

    except TimeoutError:
        logger.error(
            "content_review_job_timeout",
            extra={"review_id": review_id},
        )
        await _mark_review_failed(review_id, "Pipeline timed out")
        raise

    except Exception as exc:
        logger.exception(
            "content_review_job_failed",
            extra={"review_id": review_id},
        )
        await _mark_review_failed(review_id, str(exc))
        raise


# Default timeout for stuck review detection (must exceed _job_timeout=900 in enqueue)
STUCK_REVIEW_TIMEOUT_SECONDS = 1200  # 20 minutes


async def reconcile_stuck_content_reviews() -> int:
    """Find pending content reviews that exceeded the job timeout and mark them failed.

    When the worker container restarts mid-execution, the ARQ job is lost but the
    review stays in 'pending' forever. This function catches those orphaned reviews.

    Returns:
        Number of reviews marked as failed.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from analysi.models.content_review import ContentReview

    cutoff = datetime.now(UTC) - timedelta(seconds=STUCK_REVIEW_TIMEOUT_SECONDS)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ContentReview).where(
                ContentReview.status == ContentReviewStatus.PENDING.value,
                ContentReview.updated_at < cutoff,
            )
        )
        stuck_reviews = list(result.scalars().all())

        if not stuck_reviews:
            return 0

        logger.info(
            "found_stuck_content_reviews",
            count=len(stuck_reviews),
            cutoff=cutoff.isoformat(),
        )

        marked = 0
        for review in stuck_reviews:
            try:
                review.status = ContentReviewStatus.FAILED.value
                review.error_message = (
                    f"Review stuck in pending for >{STUCK_REVIEW_TIMEOUT_SECONDS}s. "
                    f"Worker likely restarted during execution."
                )
                review.error_code = "pipeline_timeout"
                review.error_detail = {
                    "title": "Review processing timed out",
                    "hint": "The review was not completed in time. Use the retry button to reprocess.",
                }
                marked += 1
                logger.info(
                    "marked_stuck_content_review_failed",
                    review_id=str(review.id),
                    created_at=(
                        review.created_at.isoformat()
                        if review.created_at
                        else "unknown"
                    ),
                )
            except Exception:
                logger.exception(
                    "failed_to_mark_stuck_review",
                    extra={"review_id": str(review.id)},
                )

        await session.commit()
        return marked


async def _mark_review_failed(
    review_id: str,
    error_message: str,
    error_code: str = "pipeline_error",
    error_detail: dict | None = None,
) -> None:
    """Mark a review as failed in the database."""
    try:
        from uuid import UUID

        from analysi.services.content_review import ContentReviewService

        if error_detail is None:
            error_detail = {
                "title": "Review processing failed",
                "hint": "An error occurred during content review. Use the retry button to reprocess.",
            }

        async with AsyncSessionLocal() as session:
            service = ContentReviewService(session)
            await service.complete_review(
                review_id=UUID(review_id),
                pipeline_result={},
                status=ContentReviewStatus.FAILED,
                error_message=error_message,
                error_code=error_code,
                error_detail=error_detail,
            )
            await session.commit()
    except Exception:
        logger.exception(
            "failed_to_mark_review_failed",
            extra={"review_id": review_id},
        )

"""Repository for HITL question tracking."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.constants import HITLQuestionConstants
from analysi.models.hitl_question import HITLQuestion

logger = get_logger(__name__)


class HITLQuestionRepository:
    """Repository for HITL question CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        tenant_id: str,
        question_ref: str,
        channel: str,
        question_text: str,
        options: list[dict],
        timeout_at: datetime,
        task_run_id: UUID,
        workflow_run_id: UUID | None = None,
        node_instance_id: UUID | None = None,
        analysis_id: UUID | None = None,
    ) -> HITLQuestion:
        """
        Create a new HITL question record.

        Called when a task pauses at a hi-latency tool (e.g., Slack ask).
        Must be called within the same transaction as the TaskRun status update
        to ensure atomicity.

        Args:
            tenant_id: Tenant identifier
            question_ref: External reference (e.g., Slack message_ts)
            channel: External channel (e.g., Slack channel ID)
            question_text: The question text shown to the human
            options: List of button option dicts (e.g., [{"value": "Escalate", "label": "Escalate"}])
            timeout_at: When the question expires
            task_run_id: The paused TaskRun UUID
            workflow_run_id: The paused WorkflowRun UUID (None for standalone tasks)
            node_instance_id: The paused WorkflowNodeInstance UUID (None for standalone tasks)
            analysis_id: The paused AlertAnalysis UUID (None for standalone tasks)

        Returns:
            The created HITLQuestion instance
        """
        question = HITLQuestion(
            tenant_id=tenant_id,
            question_ref=question_ref,
            channel=channel,
            question_text=question_text,
            options=options,
            timeout_at=timeout_at,
            task_run_id=task_run_id,
            workflow_run_id=workflow_run_id,
            node_instance_id=node_instance_id,
            analysis_id=analysis_id,
            status=HITLQuestionConstants.Status.PENDING.value,
        )
        self.session.add(question)
        await self.session.flush()
        return question

    async def find_by_ref(self, question_ref: str, channel: str) -> HITLQuestion | None:
        """
        Find a question by its external reference and channel.

        Used by the Slack listener to match an interactive payload
        (button click) to the correct question.

        Bug #12 fix: Uses .first() with ORDER BY created_at DESC instead of
        scalar_one_or_none(). If two questions share the same (question_ref, channel)
        — possible when sender fails and leaves question_ref="" — the most recent
        is returned instead of raising MultipleResultsFound.

        Args:
            question_ref: External reference (e.g., Slack message_ts)
            channel: External channel (e.g., Slack channel ID)

        Returns:
            HITLQuestion or None if not found
        """
        stmt = (
            select(HITLQuestion)
            .where(
                and_(
                    HITLQuestion.question_ref == question_ref,
                    HITLQuestion.channel == channel,
                )
            )
            .order_by(HITLQuestion.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_id(
        self, question_id: UUID, tenant_id: str | None = None
    ) -> HITLQuestion | None:
        """
        Get a question by its UUID, optionally filtered by tenant.

        Bug #11 fix: Accepts optional tenant_id for defense-in-depth
        multi-tenant isolation.

        Note: Does not filter by created_at because the caller typically
        doesn't know the partition. The index on id is sufficient for lookup.
        """
        conditions = [HITLQuestion.id == question_id]
        if tenant_id is not None:
            conditions.append(HITLQuestion.tenant_id == tenant_id)
        stmt = select(HITLQuestion).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def record_answer(
        self,
        question_id: UUID,
        answer: str,
        answered_by: str,
    ) -> bool:
        """
        Record a human's answer to a question.

        Only updates if the question is still in 'pending' status
        (prevents duplicate answers). Returns False if the question
        was already answered or expired.

        Args:
            question_id: Question UUID
            answer: The selected option value
            answered_by: External user identifier (e.g., Slack user ID)

        Returns:
            True if the answer was recorded, False if already answered/expired
        """
        now = datetime.now(UTC)
        stmt = (
            update(HITLQuestion)
            .where(
                and_(
                    HITLQuestion.id == question_id,
                    HITLQuestion.status == HITLQuestionConstants.Status.PENDING.value,
                )
            )
            .values(
                status=HITLQuestionConstants.Status.ANSWERED.value,
                answer=answer,
                answered_by=answered_by,
                answered_at=now,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def find_by_analysis_id(self, analysis_id: UUID) -> HITLQuestion | None:
        """
        Find the most recent question for an analysis.

        Used by reconciliation to check if a question was already answered
        before expiring its analysis (Bug #4 race guard).

        Args:
            analysis_id: The AlertAnalysis UUID

        Returns:
            Most recent HITLQuestion for the analysis, or None
        """
        stmt = (
            select(HITLQuestion)
            .where(HITLQuestion.analysis_id == analysis_id)
            .order_by(HITLQuestion.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def find_pending_by_analysis_id(
        self, analysis_id: UUID
    ) -> HITLQuestion | None:
        """
        Find a pending question for an analysis.

        Used by reconciliation to expire questions alongside their analyses (Bug #5).

        Args:
            analysis_id: The AlertAnalysis UUID

        Returns:
            Pending HITLQuestion for the analysis, or None
        """
        stmt = (
            select(HITLQuestion)
            .where(
                and_(
                    HITLQuestion.analysis_id == analysis_id,
                    HITLQuestion.status == HITLQuestionConstants.Status.PENDING.value,
                )
            )
            .order_by(HITLQuestion.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def find_expired(self) -> list[HITLQuestion]:
        """
        Find questions that have passed their timeout and are still pending.

        Used by reconciliation to expire stale questions and fail their analyses.

        Returns:
            List of expired HITLQuestion records
        """
        now = datetime.now(UTC)
        stmt = (
            select(HITLQuestion)
            .where(
                and_(
                    HITLQuestion.status == HITLQuestionConstants.Status.PENDING.value,
                    HITLQuestion.timeout_at < now,
                )
            )
            .order_by(HITLQuestion.timeout_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_expired(self, question_id: UUID) -> bool:
        """
        Mark a question as expired.

        Args:
            question_id: Question UUID

        Returns:
            True if the question was marked expired, False if not found or already terminal
        """
        stmt = (
            update(HITLQuestion)
            .where(
                and_(
                    HITLQuestion.id == question_id,
                    HITLQuestion.status == HITLQuestionConstants.Status.PENDING.value,
                )
            )
            .values(status=HITLQuestionConstants.Status.EXPIRED.value)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0


def _resolve_options(tool_args: dict[str, Any]) -> list[dict]:
    """Normalize button options from tool args into list-of-dicts format.

    Slack HITL tools use ``responses`` (comma-separated string like
    ``"Approve, Reject, Escalate"``), while other tools might pass
    ``options`` as a list of dicts.  This helper checks both and
    normalizes to ``[{"value": "Approve"}, {"value": "Reject"}, ...]``.
    """
    # Prefer "options" if it's a non-empty list (already in correct format)
    options = tool_args.get("options")
    if isinstance(options, list) and options:
        return options

    # Fall back to "responses" (comma-separated string from Slack tools)
    responses = tool_args.get("responses")
    if isinstance(responses, str) and responses.strip():
        return [{"value": opt.strip()} for opt in responses.split(",") if opt.strip()]

    # Nothing usable
    return options if isinstance(options, list) else []


# ---------------------------------------------------------------------------
# R20 — checkpoint-to-question helper
# ---------------------------------------------------------------------------


async def create_question_from_checkpoint(
    *,
    session: AsyncSession,
    tenant_id: str,
    task_run_id: UUID,
    checkpoint_data: dict[str, Any],
    workflow_run_id: UUID | None = None,
    node_instance_id: UUID | None = None,
    analysis_id: UUID | None = None,
) -> HITLQuestion | None:
    """Create a HITL question from checkpoint data (R20).

    Extracts question metadata from the pending tool args in the checkpoint
    and creates a ``hitl_questions`` row.  Called in the same transaction as
    the TaskRun status update so both writes commit atomically.

    Args:
        session: Active DB session (caller commits).
        tenant_id: Tenant identifier.
        task_run_id: The paused TaskRun UUID.
        checkpoint_data: The ``_hitl_checkpoint`` dict from the execution result.
        workflow_run_id: Paused WorkflowRun UUID (None for standalone tasks).
        node_instance_id: Paused WorkflowNodeInstance UUID (None for standalone).
        analysis_id: Paused AlertAnalysis UUID (None for standalone).

    Returns:
        The created HITLQuestion, or None if no tool args are present.
    """
    tool_args = checkpoint_data.get("pending_tool_args", {})
    if not tool_args:
        logger.debug("no_pending_tool_args_in_checkpoint_skipping_question_creation")
        return None

    # Bug #10 fix: Validate that channel is non-empty.
    # Questions with empty channel can never be matched to a Slack button click,
    # so they would hang silently until the timeout catches them hours later.
    #
    # Bug #17 fix: Slack HITL tools use `destination` as the argument name,
    # not `channel`.  Fall back to `destination` so checkpoints from real
    # Slack tool invocations are handled correctly.
    channel = tool_args.get("channel") or tool_args.get("destination", "")
    if not channel:
        logger.warning(
            "hitl_checkpoint_missing_channel_skipping_question_creation",
            task_run_id=str(task_run_id),
            tool_name=checkpoint_data.get("pending_tool_name", "unknown"),
        )
        return None

    repo = HITLQuestionRepository(session)
    timeout_at = datetime.now(UTC) + timedelta(
        hours=HITLQuestionConstants.DEFAULT_TIMEOUT_HOURS,
    )

    question = await repo.create(
        tenant_id=tenant_id,
        question_ref=tool_args.get("question_ref", ""),
        channel=channel,
        # Bug #19 fix: Slack HITL tools use "question" as the field name,
        # not "text" or "question_text".  Check all three for compatibility.
        question_text=tool_args.get(
            "question", tool_args.get("text", tool_args.get("question_text", ""))
        ),
        # Bug #20 fix: Slack HITL tools use "responses" (comma-separated string),
        # not "options" (list of dicts).  Parse responses into list-of-dicts format
        # for consistent DB storage.
        options=_resolve_options(tool_args),
        timeout_at=timeout_at,
        task_run_id=task_run_id,
        workflow_run_id=workflow_run_id,
        node_instance_id=node_instance_id,
        analysis_id=analysis_id,
    )

    logger.info(
        "hitl_question_created_from_checkpoint",
        question_id=str(question.id),
        task_run_id=str(task_run_id),
        tool_name=checkpoint_data.get("pending_tool_name", "unknown"),
    )
    return question

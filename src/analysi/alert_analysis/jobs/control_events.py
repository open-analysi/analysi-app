"""Control Event Bus jobs for disposition fan-out (Project Tilos)
and internal channel handlers (Project Kalymnos).

ARQ functions:
  consume_control_events — lightweight cron that claims pending events and
                           enqueues one execute_control_event job per event.
  execute_control_event  — ARQ job that loads rules, runs them concurrently,
                           and marks the event completed or failed.
                           Internal channels (e.g., human:responded) are
                           dispatched to hardcoded handlers instead of rules.

Internal handlers:
  handle_human_responded — HITL resume: injects human answer, resumes task/workflow.
"""

import asyncio
from typing import Any
from uuid import UUID

from analysi.alert_analysis.config import AlertAnalysisConfig
from analysi.common.job_tracking import tracked_job
from analysi.config.logging import get_logger
from analysi.constants import HITLQuestionConstants
from analysi.db.session import AsyncSessionLocal
from analysi.models.control_event import ControlEvent, ControlEventRule
from analysi.repositories.control_event_repository import (
    ControlEventDispatchRepository,
    ControlEventRepository,
    ControlEventRuleRepository,
)
from analysi.schemas.activity_audit import ActorType

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Cron: consume_control_events
# ---------------------------------------------------------------------------


async def consume_control_events(ctx: dict[str, Any]) -> dict[str, Any]:
    """
    ARQ cron job — claim pending/failed control events and enqueue workers.

    Runs every 30 seconds.  Lightweight by design:
      1. Reset events stuck in 'claimed' for > CONTROL_EVENT_STUCK_HOURS (handles
         Valkey restart before the ARQ job dequeued the event).
      2. Claim a batch of pending/failed events (FOR UPDATE SKIP LOCKED).
      3. Enqueue one execute_control_event job per event, using the event UUID
         as the ARQ job ID — prevents duplicate enqueues if the cron fires again
         before the job finishes.
    """
    from analysi.common.correlation import generate_correlation_id, set_correlation_id

    set_correlation_id(generate_correlation_id())

    redis = ctx["redis"]

    async with AsyncSessionLocal() as session:
        event_repo = ControlEventRepository(session)
        events = await event_repo.claim_batch(
            batch_size=100,
            max_retries=AlertAnalysisConfig.MAX_CONTROL_EVENT_RETRIES,
            stuck_hours=AlertAnalysisConfig.CONTROL_EVENT_STUCK_HOURS,
        )
        await session.commit()

    if not events:
        logger.debug("consume_control_events: no dispatchable events")
        return {"dispatched": 0}

    dispatched = 0
    for event in events:
        event_id = str(event.id)
        # Job ID includes retry_count so each attempt gets its own Valkey slot.
        # This prevents ARQ from skipping re-enqueue when arq:result:<prev_id> still
        # exists from a prior failed attempt (ARQ refuses to re-enqueue a completed job).
        # The event being in 'claimed' status already prevents concurrent double-dispatch,
        # so the per-attempt ID is the correct idempotency granularity.
        attempt_job_id = f"{event_id}:{event.retry_count}"
        try:
            await redis.enqueue_job(
                "analysi.alert_analysis.jobs.control_events.execute_control_event",
                event_id,
                event.tenant_id,
                _job_id=attempt_job_id,
            )
            dispatched += 1
            logger.info(
                "control_event_enqueued",
                event_id=event_id,
                channel=event.channel,
                attempt=event.retry_count,
            )
        except Exception:
            logger.exception("control_event_enqueue_failed", event_id=event_id)

    logger.info("consume_control_events_complete", extra={"dispatched": dispatched})
    return {"dispatched": dispatched}


# ---------------------------------------------------------------------------
# ARQ job: execute_control_event
# ---------------------------------------------------------------------------


@tracked_job(
    job_type="execute_control_event",
    timeout_seconds=AlertAnalysisConfig.JOB_TIMEOUT,
    model_class=ControlEvent,
    extract_row_id=lambda ctx, event_id, tenant_id: event_id,
)
async def execute_control_event(
    ctx: dict[str, Any], event_id: str, tenant_id: str
) -> dict[str, Any]:
    """
    ARQ job — execute all configured rules for a single control event.

    Steps:
      1. Load the event and enabled rules for its (tenant_id, channel).
      2. For each rule, atomically claim a dispatch slot or skip (already completed).
      3. Run all rule executions concurrently via asyncio.gather.
      4. On success: mark event completed + delete dispatch rows (same transaction).
         On failure: mark event failed + increment retry_count (dispatch rows kept
         so the next retry knows which rules already completed).
    """
    # Correlation + tenant context set by @tracked_job (Project Leros)

    event_uuid = UUID(event_id)

    # Load event
    async with AsyncSessionLocal() as session:
        event_repo = ControlEventRepository(session)
        event = await event_repo.get_by_id(event_uuid)
        if event is None:
            raise ValueError(f"Control event {event_id} not found")

    # Internal channels: dispatch to hardcoded handler (no rule lookup)
    if event.channel in INTERNAL_HANDLERS:
        handler = INTERNAL_HANDLERS[event.channel]
        try:
            await handler(event)
            async with AsyncSessionLocal() as session:
                event_repo = ControlEventRepository(session)
                evt = await event_repo.get_by_id(event_uuid)
                if evt:
                    await event_repo.mark_completed(evt)
                await session.commit()
            logger.info(
                "internal_event_completed",
                extra={"event_id": event_id, "channel": event.channel},
            )
            return {"status": "completed", "channel": event.channel, "internal": True}
        except Exception as e:
            async with AsyncSessionLocal() as session:
                event_repo = ControlEventRepository(session)
                evt = await event_repo.get_by_id(event_uuid)
                if evt:
                    await event_repo.mark_failed(evt)
                await session.commit()
            logger.error(
                "internal_event_failed",
                event_id=event_id,
                channel=event.channel,
                error=str(e),
                exc_info=True,
            )
            raise

    # Fan-out channels: load rules
    async with AsyncSessionLocal() as session:
        rule_repo = ControlEventRuleRepository(session)
        rules = await rule_repo.list_by_channel(
            tenant_id=event.tenant_id,
            channel=event.channel,
            enabled_only=True,
        )

    if not rules:
        logger.info(
            "control_event_no_rules",
            extra={"event_id": event_id, "channel": event.channel},
        )
        async with AsyncSessionLocal() as session:
            event_repo = ControlEventRepository(session)
            evt = await event_repo.get_by_id(event_uuid)
            if evt:
                await event_repo.mark_completed(evt)
            await session.commit()
        return {"status": "completed", "rules_executed": 0}

    # Execute all rules concurrently
    results = await asyncio.gather(
        *[_run_rule_with_dispatch(event, rule) for rule in rules],
        return_exceptions=True,
    )

    failures = [r for r in results if isinstance(r, Exception)]

    # Commit final event status
    async with AsyncSessionLocal() as session:
        event_repo = ControlEventRepository(session)
        dispatch_repo = ControlEventDispatchRepository(session)
        evt = await event_repo.get_by_id(event_uuid)
        if evt is None:
            raise RuntimeError(f"Control event {event_id} missing during finalization")

        if failures:
            await event_repo.mark_failed(evt)
            await session.commit()
            for exc in failures:
                logger.error(
                    "control_event_rule_failed",
                    event_id=event_id,
                    error=str(exc),
                    exc_info=exc,
                )
            if evt.retry_count >= AlertAnalysisConfig.MAX_CONTROL_EVENT_RETRIES:
                logger.error(
                    "control_event_max_retries_reached",
                    event_id=event_id,
                    retry_count=evt.retry_count,
                    channel=event.channel,
                    tenant_id=event.tenant_id,
                )
            raise RuntimeError(
                f"Control event {event_id}: {len(failures)} rule(s) failed"
            )

        # All rules completed
        await event_repo.mark_completed(evt)
        await dispatch_repo.delete_for_event(event_uuid)
        await session.commit()
        logger.info(
            "control_event_completed",
            extra={"event_id": event_id, "rules_executed": len(rules)},
        )
        return {"status": "completed", "rules_executed": len(rules)}


async def _run_rule_with_dispatch(event: ControlEvent, rule: ControlEventRule) -> None:
    """Claim a dispatch slot for the rule, execute it, and record the outcome.

    Returns normally on success.  Raises on failure (required so that
    asyncio.gather result inspection is unambiguous).
    """
    # Atomic claim or skip
    async with AsyncSessionLocal() as session:
        dispatch_repo = ControlEventDispatchRepository(session)
        dispatch_id = await dispatch_repo.claim_or_skip(event.id, rule.id)
        await session.commit()

    if dispatch_id is None:
        # Already completed — idempotency check says skip
        logger.debug(
            "control_event_dispatch_skipped",
            extra={"event_id": str(event.id), "rule_id": str(rule.id)},
        )
        return

    try:
        await execute_rule(event, rule)

        async with AsyncSessionLocal() as session:
            dispatch_repo = ControlEventDispatchRepository(session)
            await dispatch_repo.mark_completed(dispatch_id)
            await session.commit()

    except Exception:
        async with AsyncSessionLocal() as session:
            dispatch_repo = ControlEventDispatchRepository(session)
            await dispatch_repo.mark_failed(dispatch_id)
            await session.commit()
        raise


# ---------------------------------------------------------------------------
# Rule executor
# ---------------------------------------------------------------------------


async def execute_rule(event: ControlEvent, rule: ControlEventRule) -> None:
    """
    Execute a single rule's Task or Workflow target.

    Contract: MUST raise on failure — never return silently on error.
    This makes asyncio.gather(return_exceptions=True) inspection unambiguous.

    Input passed to the target:
      - All fields from event.payload (alert_id, analysis_id, disposition, etc.)
      - "event_id": str(event.id)   — idempotency key for the target
      - "config": rule.config       — operator-configured parameters (JIRA project, Slack channel…)

    execution_context stamped on the TaskRun/WorkflowRun (informational, for debugging):
      - "control_event_id": str(event.id)
      - "rule_id": str(rule.id)
    """
    input_data = {
        **event.payload,
        "event_id": str(event.id),
        "config": rule.config,
    }
    execution_context = {
        "control_event_id": str(event.id),
        "rule_id": str(rule.id),
    }

    if rule.target_type == "task":
        await _execute_task_rule(
            tenant_id=event.tenant_id,
            task_id=rule.target_id,
            input_data=input_data,
            execution_context=execution_context,
        )
    elif rule.target_type == "workflow":
        await _execute_workflow_rule(
            tenant_id=event.tenant_id,
            workflow_id=rule.target_id,
            input_data=input_data,
            execution_context=execution_context,
        )
    else:
        raise ValueError(f"Unknown rule target_type: {rule.target_type!r}")


async def _execute_task_rule(
    tenant_id: str,
    task_id: UUID,
    input_data: dict,
    execution_context: dict,
) -> None:
    """Create a TaskRun, execute it, and persist the result.

    Raises on failure.  PAUSED tasks are persisted as paused (a HITL cycle
    will resume them later via control events).
    """
    from analysi.constants import TaskConstants
    from analysi.schemas.task_execution import TaskExecutionStatus
    from analysi.services.task_execution import TaskExecutionService
    from analysi.services.task_run import TaskRunService

    task_run_svc = TaskRunService()
    task_exec_svc = TaskExecutionService()

    async with AsyncSessionLocal() as session:
        task_run = await task_run_svc.create_execution(
            session,
            tenant_id=tenant_id,
            task_id=task_id,
            cy_script=None,
            input_data=input_data,
            execution_context=execution_context,
        )
        await session.commit()

    result = await task_exec_svc.execute_single_task(task_run.id, tenant_id)

    async with AsyncSessionLocal() as session:
        if result.status == TaskExecutionStatus.COMPLETED:
            await task_run_svc.update_status(
                session,
                result.task_run_id,
                TaskConstants.Status.COMPLETED,
                output_data=result.output_data,
                llm_usage=result.llm_usage,
            )
        elif result.status == TaskExecutionStatus.PAUSED:
            await task_run_svc.update_status(
                session,
                result.task_run_id,
                TaskConstants.Status.PAUSED,
                output_data=result.output_data,
                llm_usage=result.llm_usage,
            )
        else:
            await task_run_svc.update_status(
                session,
                result.task_run_id,
                TaskConstants.Status.FAILED,
                error_info={"error": result.error_message or "Unknown error"},
                llm_usage=result.llm_usage,
            )
        await session.commit()

    if result.status == TaskExecutionStatus.PAUSED:
        # Task awaiting human input — not a failure.  The HITL cycle will
        # resume it later via a human:responded control event.
        #
        # Bug #2 fix: Create the hitl_question row and send the Slack message.
        # Without this, the task pauses but no question is sent — the human
        # never sees the question and the task is stuck forever.
        checkpoint_data = (result.output_data or {}).get("_hitl_checkpoint", {})
        if checkpoint_data:
            from analysi.repositories.hitl_repository import (
                create_question_from_checkpoint,
            )

            async with AsyncSessionLocal() as hitl_session:
                hitl_question = await create_question_from_checkpoint(
                    session=hitl_session,
                    tenant_id=tenant_id,
                    task_run_id=result.task_run_id,
                    checkpoint_data=checkpoint_data,
                )
                if hitl_question is not None:
                    from analysi.slack_listener.sender import send_hitl_question

                    await send_hitl_question(
                        session=hitl_session,
                        hitl_question=hitl_question,
                        pending_tool_args=checkpoint_data.get("pending_tool_args", {}),
                        tenant_id=tenant_id,
                    )
                await hitl_session.commit()

        logger.info(
            "task_rule_paused_awaiting_hitl",
            task_id=str(task_id),
            task_run_id=str(result.task_run_id),
        )
        return

    if result.status != TaskExecutionStatus.COMPLETED:
        raise RuntimeError(
            f"Task rule {task_id} failed: {result.error_message or 'unknown error'}"
        )


async def _execute_workflow_rule(
    tenant_id: str,
    workflow_id: UUID,
    input_data: dict,
    execution_context: dict,
) -> None:
    """Create a WorkflowRun and execute it synchronously in the worker.

    No REST API calls, no polling — the ARQ job IS the execution.
    The ARQ job timeout (default 1 hour) is the outer safety net.
    Progress is committed to DB at every state transition by
    monitor_execution(), so the UI sees real-time updates.

    Raises:
        RuntimeError: If workflow execution ends in FAILED status.
    """
    from sqlalchemy import text

    from analysi.services.workflow_execution import WorkflowExecutor

    # Step 1: Create the WorkflowRun record
    async with AsyncSessionLocal() as session:
        executor = WorkflowExecutor(session)
        workflow_run_id = await executor.create_workflow_run(
            tenant_id, workflow_id, input_data, execution_context=execution_context
        )
        await session.commit()

    # Step 2: Execute synchronously — monitor_execution commits progress
    # to DB at every node transition, so the UI sees real-time updates.
    await WorkflowExecutor._execute_workflow_synchronously(workflow_run_id)

    # Step 3: Check terminal status — monitor_execution marks failed runs
    # in the DB but returns normally (no exception). We must detect this
    # so the dispatch is correctly marked as failed.
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT status, error_message FROM workflow_runs WHERE id = :id"),
            {"id": str(workflow_run_id)},
        )
        row = result.fetchone()
        if row and row.status == "failed":
            raise RuntimeError(f"Workflow rule execution failed: {row.error_message}")


# ---------------------------------------------------------------------------
# Internal channel handlers (Project Kalymnos)
# ---------------------------------------------------------------------------


async def handle_human_responded(event: ControlEvent) -> None:
    """
    HITL — Project Kalymnos (R28/R29): Resume paused task/workflow after human answers.

    Payload:
        question_id: UUID of the hitl_questions row
        answer: The human's selected option
        answered_by: External user identifier (e.g., Slack user ID)

    Flow:
        1. Load the hitl_questions row
        2. Load paused TaskRun, inject answer into checkpoint
        3. Resume task execution via TaskExecutionService.resume_paused_task
        4. If workflow context: continue_after_hitl persists result, marks node,
           creates successors, and re-enters monitor_execution for remaining DAG.
        5. If standalone task: persist the task result status directly.
    """
    from analysi.repositories.hitl_repository import HITLQuestionRepository
    from analysi.services.task_execution import TaskExecutionService

    payload = event.payload
    question_id = UUID(payload["question_id"])
    answer = payload["answer"]

    logger.info(
        "handle_human_responded_start",
        question_id=str(question_id),
        tenant_id=event.tenant_id,
    )

    # Step 1: Load the question
    async with AsyncSessionLocal() as session:
        repo = HITLQuestionRepository(session)
        # Bug #21 fix: Scope lookup to tenant for multi-tenant isolation.
        question = await repo.get_by_id(question_id, tenant_id=event.tenant_id)

    if question is None:
        # Bug #6 fix: Raise instead of returning silently.
        # A silent return causes the control event to be marked "completed",
        # leaving the paused task/workflow stuck forever with no error trail.
        raise ValueError(
            f"HITL question {question_id} not found — cannot resume paused task. "
            f"The question may have been deleted or is in a different partition."
        )

    # Bug #28 fix: Verify the question was actually answered before resuming.
    # The normal Slack flow records the answer (pending→answered) before emitting
    # human:responded, but the control events REST API allows manual event creation.
    # Without this gate, a crafted event could resume a task with an arbitrary answer
    # while the question remains pending/expired.
    if question.status != HITLQuestionConstants.Status.ANSWERED:
        raise ValueError(
            f"HITL question {question_id} is '{question.status}', not 'answered' — "
            f"cannot resume. Only answered questions trigger task resumption."
        )

    # Step 2: Resume the paused task (re-executes the Cy script with the answer)
    task_exec_svc = TaskExecutionService()

    async with AsyncSessionLocal() as session:
        exec_result = await task_exec_svc.resume_paused_task(
            session=session,
            task_run_id=question.task_run_id,
            tenant_id=question.tenant_id,
            human_response=answer,
        )
        # resume_paused_task commits internally (so the inner session can see
        # the checkpoint). No additional commit needed here.

    logger.info(
        "handle_human_responded_task_resumed",
        task_run_id=str(question.task_run_id),
        task_result_status=getattr(exec_result, "status", "unknown"),
    )

    # Step 2b: Audit trail — log HITL response as activity event (Project Kalymnos)
    try:
        from analysi.models.auth import SYSTEM_USER_ID
        from analysi.repositories.activity_audit_repository import (
            ActivityAuditRepository,
        )

        async with AsyncSessionLocal() as audit_session:
            audit_repo = ActivityAuditRepository(audit_session)
            await audit_repo.create(
                tenant_id=event.tenant_id,
                actor_id=SYSTEM_USER_ID,
                actor_type=ActorType.EXTERNAL_USER,
                source="internal",
                action=HITLQuestionConstants.AUDIT_ACTION_ANSWERED,
                resource_type="hitl_question",
                resource_id=str(question_id),
                details={
                    "answer": answer,
                    "answered_by": payload.get("answered_by", "unknown"),
                    "task_run_id": str(question.task_run_id),
                    "workflow_run_id": (
                        str(question.workflow_run_id)
                        if question.workflow_run_id
                        else None
                    ),
                    "analysis_id": (
                        str(question.analysis_id) if question.analysis_id else None
                    ),
                },
            )
            await audit_session.commit()
    except Exception:
        logger.warning(
            "handle_human_responded_audit_failed",
            question_id=str(question_id),
            exc_info=True,
        )

    # Step 3: Persist task result and continue workflow (or standalone task).
    if question.workflow_run_id and not question.node_instance_id:
        logger.warning(
            "handle_human_responded_missing_node_instance_id",
            question_id=str(question_id),
            workflow_run_id=str(question.workflow_run_id),
        )

    if question.workflow_run_id and question.node_instance_id:
        # Workflow context: mark node completed, create successors, re-enter
        # monitor_execution.  continue_after_hitl handles COMPLETED / PAUSED
        # (another HITL in same script) / FAILED branches.
        from analysi.services.workflow_execution import WorkflowExecutor

        logger.info(
            "handle_human_responded_resuming_workflow",
            workflow_run_id=str(question.workflow_run_id),
            node_instance_id=str(question.node_instance_id),
        )

        try:
            await WorkflowExecutor.continue_after_hitl(
                workflow_run_id=question.workflow_run_id,
                node_instance_id=question.node_instance_id,
                task_result=exec_result,
            )

            logger.info(
                "handle_human_responded_workflow_continued",
                workflow_run_id=str(question.workflow_run_id),
            )
        except Exception:
            # Workflow failed — update analysis to failed before re-raising
            if question.analysis_id:
                await _update_analysis_after_hitl(
                    analysis_id=question.analysis_id,
                    tenant_id=question.tenant_id,
                    status="failed",
                    error_message="Workflow execution failed after HITL resume",
                )
            raise

        # Bug #1 fix: Update analysis status after successful workflow continuation.
        # Without this, the analysis stays in paused_human_review forever because
        # the original pipeline ARQ job already returned.
        #
        # Bug #16 fix: Only mark "running" if the task actually succeeded or
        # paused again.  If the task failed, continue_after_hitl drives the
        # workflow to FAILED via monitor_execution — setting the analysis to
        # "running" would overwrite the correct terminal state.
        if question.analysis_id:
            from analysi.schemas.task_execution import TaskExecutionStatus

            if exec_result.status == TaskExecutionStatus.FAILED:
                # Bug #22 fix: Explicitly mark analysis failed.
                # monitor_execution only updates workflow_runs/node_instances,
                # NOT alert_analysis — so we must do it here.
                await _update_analysis_after_hitl(
                    analysis_id=question.analysis_id,
                    tenant_id=question.tenant_id,
                    status="failed",
                    error_message="Task failed after HITL resume",
                )
            elif exec_result.status == TaskExecutionStatus.PAUSED:
                # Bug #18 fix: Task re-paused at another HITL tool — the
                # analysis must stay in paused_human_review so reconciliation
                # tracks it correctly (HITL timeout, not stuck-running).
                logger.info(
                    "skip_analysis_mark_running_task_repaused",
                    analysis_id=str(question.analysis_id),
                )
            else:
                # Workflow completed after HITL resume.  Re-queue the
                # pipeline so step 4 (final disposition update) can run.
                # The pipeline's step 3 was checkpointed on pause, so
                # re-queue skips to step 4.
                #
                # IMPORTANT: enqueue BEFORE marking "running".  If enqueue
                # fails, the analysis stays in paused_human_review so the
                # control event can be safely retried.  If we marked
                # "running" first, a retry would fail at resume_paused_task
                # ("TaskRun is not paused") leaving the analysis stuck.
                await _requeue_pipeline_after_hitl(
                    analysis_id=question.analysis_id,
                    tenant_id=question.tenant_id,
                )
                await _update_analysis_after_hitl(
                    analysis_id=question.analysis_id,
                    tenant_id=question.tenant_id,
                    status="running",
                )
    else:
        # Standalone task (no workflow): persist the task result status.
        # resume_paused_task set status to "running" — update to actual outcome.
        from analysi.constants import TaskConstants
        from analysi.schemas.task_execution import TaskExecutionStatus
        from analysi.services.task_run import TaskRunService

        task_run_service = TaskRunService()
        async with AsyncSessionLocal() as persist_session:
            if exec_result.status == TaskExecutionStatus.COMPLETED:
                await task_run_service.update_status(
                    persist_session,
                    exec_result.task_run_id,
                    TaskConstants.Status.COMPLETED,
                    output_data=exec_result.output_data,
                    llm_usage=exec_result.llm_usage,
                )
            elif exec_result.status == TaskExecutionStatus.PAUSED:
                await task_run_service.update_status(
                    persist_session,
                    exec_result.task_run_id,
                    TaskConstants.Status.PAUSED,
                    output_data=exec_result.output_data,
                    llm_usage=exec_result.llm_usage,
                )

                # Bug #15 fix: Create a new hitl_questions row and send Slack
                # message for the next HITL pause.  Without this, only the
                # status is persisted and the human never sees the question.
                checkpoint_data = (exec_result.output_data or {}).get(
                    "_hitl_checkpoint", {}
                )
                if checkpoint_data:
                    from analysi.repositories.hitl_repository import (
                        create_question_from_checkpoint,
                    )

                    hitl_question = await create_question_from_checkpoint(
                        session=persist_session,
                        tenant_id=question.tenant_id,
                        task_run_id=exec_result.task_run_id,
                        checkpoint_data=checkpoint_data,
                        analysis_id=question.analysis_id,
                    )
                    if hitl_question is not None:
                        from analysi.slack_listener.sender import (
                            send_hitl_question,
                        )

                        await send_hitl_question(
                            session=persist_session,
                            hitl_question=hitl_question,
                            pending_tool_args=checkpoint_data.get(
                                "pending_tool_args", {}
                            ),
                            tenant_id=question.tenant_id,
                        )
            else:
                await task_run_service.update_status(
                    persist_session,
                    exec_result.task_run_id,
                    TaskConstants.Status.FAILED,
                    error_info={"error": exec_result.error_message or "Unknown error"},
                    llm_usage=exec_result.llm_usage,
                )
            await persist_session.commit()

        logger.info(
            "handle_human_responded_standalone_task_persisted",
            task_run_id=str(question.task_run_id),
            status=str(exec_result.status),
        )


# ---------------------------------------------------------------------------
# Analysis status helpers (Bug #1 fix)
# ---------------------------------------------------------------------------


async def _update_analysis_after_hitl(
    *,
    analysis_id: UUID,
    tenant_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """Transition an analysis out of paused_human_review after HITL resume.

    Called by handle_human_responded after continue_after_hitl completes (or fails).
    Without this, the analysis stays in paused_human_review because the original
    pipeline ARQ job already returned — nothing else will update it.
    """
    from analysi.repositories.alert_repository import AlertAnalysisRepository

    try:
        async with AsyncSessionLocal() as session:
            analysis_repo = AlertAnalysisRepository(session)
            if status == "failed":
                await analysis_repo.mark_failed(
                    analysis_id=analysis_id,
                    error_message=error_message or "HITL resume failed",
                    tenant_id=tenant_id,
                )
            else:
                await analysis_repo.mark_running(
                    analysis_id=analysis_id,
                    tenant_id=tenant_id,
                )
            await session.commit()
        logger.info(
            "analysis_status_updated_after_hitl",
            analysis_id=str(analysis_id),
            new_status=status,
        )
    except Exception:
        logger.warning(
            "analysis_status_update_after_hitl_failed",
            analysis_id=str(analysis_id),
            exc_info=True,
        )


async def _requeue_pipeline_after_hitl(
    *,
    analysis_id: UUID,
    tenant_id: str,
) -> None:
    """Re-queue the alert analysis pipeline after HITL resume.

    The original pipeline ARQ job returned early when the workflow paused.
    Step 3 (workflow_execution) was checkpointed with the workflow_run_id,
    so the re-queued pipeline skips steps 1-3 and runs step 4 (final
    disposition update).

    Loads the AlertAnalysis to get the alert_id needed for the pipeline
    job signature.
    """
    from analysi.common.arq_enqueue import enqueue_arq_job
    from analysi.repositories.alert_repository import AlertAnalysisRepository

    try:
        async with AsyncSessionLocal() as session:
            repo = AlertAnalysisRepository(session)
            analysis = await repo.get_by_id(analysis_id, tenant_id)

        if analysis is None:
            logger.error(
                "requeue_pipeline_after_hitl_analysis_not_found",
                analysis_id=str(analysis_id),
            )
            return

        job_id = await enqueue_arq_job(
            "analysi.alert_analysis.worker.process_alert_analysis",
            tenant_id,
            str(analysis.alert_id),
            str(analysis_id),
        )
        logger.info(
            "pipeline_requeued_after_hitl",
            analysis_id=str(analysis_id),
            alert_id=str(analysis.alert_id),
            arq_job_id=job_id,
        )
    except Exception:
        # Let the exception propagate so the execute_control_event ARQ
        # job fails and can be retried by the control event bus.  If we
        # swallow it, the analysis is left in "running" with no ARQ job
        # and eventually marked failed by stuck-detection (false positive).
        logger.error(
            "requeue_pipeline_after_hitl_failed",
            analysis_id=str(analysis_id),
            exc_info=True,
        )
        raise


# ---------------------------------------------------------------------------
# Internal channel registry
# ---------------------------------------------------------------------------


INTERNAL_HANDLERS: dict[str, Any] = {
    HITLQuestionConstants.CHANNEL_HUMAN_RESPONDED: handle_human_responded,
}

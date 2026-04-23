"""Reconciliation job for paused alerts."""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from arq import create_pool
from sqlalchemy import and_, update
from sqlalchemy.exc import SQLAlchemyError

from analysi.alert_analysis.clients import KeaCoordinationClient
from analysi.alert_analysis.config import AlertAnalysisConfig
from analysi.alert_analysis.db import AlertAnalysisDB
from analysi.alert_analysis.steps.workflow_builder import get_global_cache
from analysi.config.logging import get_logger
from analysi.config.valkey_db import ValkeyDBConfig
from analysi.models.alert import AlertAnalysis
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
)
from analysi.repositories.hitl_repository import HITLQuestionRepository
from analysi.repositories.kea_coordination_repository import (
    WorkflowGenerationRepository,
)
from analysi.services.partition_management import run_maintenance

logger = get_logger(__name__)


def should_retry_workflow_generation(analysis: AlertAnalysis) -> tuple[bool, str]:
    """
    Check if alert should retry workflow generation based on retry count and backoff.

    Prevents infinite retry loops by enforcing max retries and exponential backoff.

    Args:
        analysis: AlertAnalysis instance to check

    Returns:
        Tuple of (should_retry: bool, reason: str)
    """
    retry_count = analysis.workflow_gen_retry_count or 0
    max_retries = AlertAnalysisConfig.MAX_WORKFLOW_GEN_RETRIES
    backoff_base = AlertAnalysisConfig.WORKFLOW_GEN_BACKOFF_BASE_MINUTES

    # Check max retries
    if retry_count >= max_retries:
        return (
            False,
            f"Max retries ({max_retries}) exceeded after {retry_count} attempts",
        )

    # Check backoff period
    last_failure = analysis.workflow_gen_last_failure_at
    if last_failure:
        # Exponential backoff: 5min, 10min, 20min, etc.
        backoff_minutes = backoff_base * (2**retry_count)
        next_retry_at = last_failure + timedelta(minutes=backoff_minutes)

        if datetime.now(UTC) < next_retry_at:
            wait_seconds = (next_retry_at - datetime.now(UTC)).total_seconds()
            return (
                False,
                f"Backoff active: wait {wait_seconds:.0f}s until {next_retry_at.isoformat()}",
            )

    return True, f"OK (retry {retry_count + 1}/{max_retries})"


async def reconcile_paused_alerts(ctx: dict[str, Any]) -> dict[str, Any]:
    """
    ARQ cron job to resume paused alerts when workflows complete.

    Runs every 10 seconds on all alert-worker instances.
    First worker to update alert status claims it for processing.

    Args:
        ctx: ARQ context (contains redis pool, job info)

    Returns:
        Dict with reconciliation results
    """
    from analysi.common.correlation import generate_correlation_id, set_correlation_id

    set_correlation_id(generate_correlation_id())

    logger.info("reconciliation_started")

    db = None
    redis = None

    try:
        # Create Redis pool for queue monitoring and alert processing
        redis_settings = ValkeyDBConfig.get_redis_settings(
            database=ValkeyDBConfig.ALERT_PROCESSING_DB
        )
        redis = await create_pool(redis_settings)

        # Create database connection
        db = AlertAnalysisDB()
        await db.initialize()

        # Create repositories
        alert_repo = AlertRepository(db.session)
        analysis_repo = AlertAnalysisRepository(db.session)
        generation_repo = WorkflowGenerationRepository(db.session)
        hitl_repo = HITLQuestionRepository(db.session)

        # Create Kea client
        api_base_url = AlertAnalysisConfig.API_BASE_URL
        kea_client = KeaCoordinationClient(base_url=api_base_url)

        # Count running workflow generations (across all tenants for observability)
        running_workflows = await generation_repo.count_running()

        # Get queue statistics for observability
        try:
            # ARQ uses sorted set (zset) for queue, not list
            queue_length = await redis.zcard("arq:queue")

            # Count in-progress jobs, excluding cron markers (which accumulate due to TTL)
            all_keys = await redis.keys("arq:in-progress:*")
            # Filter: Only count non-cron jobs (actual alert processing work)
            worker_jobs = (
                [k for k in all_keys if b":cron:" not in k] if all_keys else []
            )
            cron_markers = len(all_keys) - len(worker_jobs) if all_keys else 0

            logger.info(
                "worker_status",
                queue=queue_length,
                worker_jobs=len(worker_jobs),
                cron_markers=cron_markers,
                running_workflows=running_workflows,
            )
        except Exception as e:
            logger.warning("could_not_fetch_queue_statistics", error=str(e))

        # 0. Partition maintenance (cleanup old, create new) - rate limited to hourly
        await maintain_partitions()

        # 1-2-6. Stuck detection — consolidated orchestrator
        from analysi.common.stuck_detection import run_all_stuck_detection

        stuck_result = await run_all_stuck_detection(
            alert_repo=alert_repo,
            generation_repo=generation_repo,
        )
        failed_count = stuck_result.counts.get("stuck_generations", 0)
        stuck_count = stuck_result.counts.get("stuck_running_alerts", 0)
        stuck_reviews_count = stuck_result.counts.get("stuck_content_reviews", 0)
        stuck_task_runs_count = stuck_result.counts.get("stuck_task_runs", 0)
        stuck_workflow_runs_count = stuck_result.counts.get("stuck_workflow_runs", 0)

        # 3. Sync mismatched alert statuses (Fix for API 500 during status update) - ALWAYS RUN
        synced_count = await sync_mismatched_alert_statuses(alert_repo)

        # 4. Cleanup orphaned workspace directories - ALWAYS RUN
        cleaned_count = await cleanup_orphaned_workspaces(db)

        # 5. Detect orphaned running analyses (Issue #5) - ALWAYS RUN
        orphaned_count = await detect_orphaned_analyses(analysis_repo, alert_repo)

        # 7. Detect expired HITL-paused analyses (Project Kalymnos) - ALWAYS RUN
        hitl_expired_count = await mark_expired_hitl_paused_analyses(
            analysis_repo,
            alert_repo,
            timeout_hours=AlertAnalysisConfig.PAUSE_TIMEOUT_HOURS,
            hitl_repo=hitl_repo,
        )

        # 8. Find paused alerts waiting for workflow generation
        paused_alerts = await alert_repo.find_paused_at_workflow_builder()

        logger.info(
            "found_paused_alerts_to_check", paused_alerts_count=len(paused_alerts)
        )

        if not paused_alerts:
            logger.info(
                "reconciliation_no_paused_alerts",
                stuck_generations=failed_count,
                stuck_alerts=stuck_count,
                orphaned_analyses=orphaned_count,
                stuck_reviews=stuck_reviews_count,
                stuck_task_runs=stuck_task_runs_count,
                stuck_workflow_runs=stuck_workflow_runs_count,
                hitl_expired=hitl_expired_count,
                synced=synced_count,
                cleaned=cleaned_count,
                running_workflows=running_workflows,
            )
            result = {
                "status": "completed",
                "resumed_count": 0,
                "failed_count": failed_count,
                "stuck_alerts_count": stuck_count,
                "orphaned_count": orphaned_count,
                "stuck_reviews_count": stuck_reviews_count,
                "stuck_task_runs_count": stuck_task_runs_count,
                "stuck_workflow_runs_count": stuck_workflow_runs_count,
                "hitl_expired_count": hitl_expired_count,
                "synced_count": synced_count,
                "cleaned_count": cleaned_count,
                "running_workflows": running_workflows,
            }
            return result

        # Get global cache for updating when workflows are found
        cache = get_global_cache()
        resumed_count = 0
        already_claimed_count = 0
        recovery_count = 0
        retry_count = 0
        backoff_skipped_count = 0
        max_retries_exceeded_count = 0

        # Deduplicate Kea API calls: cache results by (tenant_id, rule_name)
        # so N alerts with the same rule_name only trigger 1 API call
        kea_result_cache: dict[tuple[str, str], dict] = {}

        for alert in paused_alerts:
            try:
                # Get analysis group for this alert (V1: use rule_name)
                group_title = alert.rule_name

                # Check if workflow exists now (deduplicated by tenant+rule)
                kea_key = (alert.tenant_id, group_title)
                if kea_key in kea_result_cache:
                    result = kea_result_cache[kea_key]
                else:
                    result = await kea_client.get_active_workflow(
                        tenant_id=alert.tenant_id,
                        group_title=group_title,
                    )
                    kea_result_cache[kea_key] = result

                if result.get("routing_rule") and result["routing_rule"].get(
                    "workflow_id"
                ):
                    # SUCCESS CASE: Workflow generation completed, routing rule exists
                    routing_rule = result["routing_rule"]
                    group_id = routing_rule.get("analysis_group_id")
                    workflow_id = routing_rule["workflow_id"]

                    # Update cache so subsequent alert processing can benefit (cache invalidation)
                    if group_id:
                        cache.set_group(
                            title=group_title,
                            group_id=str(group_id),
                            workflow_id=str(workflow_id),
                            tenant_id=alert.tenant_id,
                        )

                    # Workflow ready - try to resume alert atomically
                    success = await alert_repo.try_resume_alert(
                        tenant_id=alert.tenant_id,
                        alert_id=str(alert.id),
                    )

                    if success:
                        # Enqueue for processing (using Redis pool created at start)
                        await redis.enqueue_job(
                            "analysi.alert_analysis.worker.process_alert_analysis",
                            alert.tenant_id,
                            str(alert.id),
                            str(alert.current_analysis_id),  # Resume existing analysis
                        )
                        resumed_count += 1
                    else:
                        already_claimed_count += 1

                elif (
                    result.get("generation")
                    and result["generation"].get("status") == "completed"
                    and result["generation"].get("workflow_id")
                    and not result.get("routing_rule")
                ):
                    # RECOVERY CASE (Issue #10): Generation completed with workflow_id
                    # but routing rule creation failed. Create the rule and resume.
                    generation = result["generation"]
                    workflow_id = generation["workflow_id"]
                    group_id = generation["analysis_group_id"]

                    try:
                        await kea_client.create_routing_rule(
                            tenant_id=alert.tenant_id,
                            analysis_group_id=str(group_id),
                            workflow_id=str(workflow_id),
                        )

                        # Update cache
                        if group_id:
                            cache.set_group(
                                title=group_title,
                                group_id=str(group_id),
                                workflow_id=str(workflow_id),
                                tenant_id=alert.tenant_id,
                            )

                        # Resume alert
                        success = await alert_repo.try_resume_alert(
                            tenant_id=alert.tenant_id,
                            alert_id=str(alert.id),
                        )

                        if success:
                            await redis.enqueue_job(
                                "analysi.alert_analysis.worker.process_alert_analysis",
                                alert.tenant_id,
                                str(alert.id),
                                str(alert.current_analysis_id),
                            )
                            resumed_count += 1
                            recovery_count += 1

                    except Exception as rule_err:
                        logger.error(
                            "recovery_routing_rule_failed",
                            alert_id=str(alert.id),
                            error=str(rule_err),
                        )

                elif result.get("generation") and result["generation"].get(
                    "status"
                ) in (
                    "completed",
                    "failed",
                ):
                    # FAILURE CASE: Workflow generation finished but no routing rule
                    # and no workflow_id (e.g., generation timed out or failed)

                    # Check retry limits before resuming
                    analysis = await analysis_repo.get_by_alert_id(
                        tenant_id=alert.tenant_id,
                        alert_id=str(alert.id),
                    )

                    if not analysis:
                        logger.error("no_analysis_found_for_alert", alert_id=alert.id)
                        continue

                    should_retry, reason = should_retry_workflow_generation(analysis)

                    if not should_retry:
                        # Max retries exceeded or backoff active
                        if "Max retries" in reason:
                            max_retries_exceeded_count += 1
                            await analysis_repo.mark_failed(
                                analysis_id=analysis.id,
                                error_message=f"Workflow generation failed after max retries: {reason}",
                                tenant_id=alert.tenant_id,
                            )
                            # Update alert status to failed — but only if this analysis
                            # is still the current one (a retry may have started a newer one).
                            await db.update_alert_status_if_current(
                                str(alert.id), "failed", str(analysis.id)
                            )
                        else:
                            # Backoff active - skip for now, will retry later
                            backoff_skipped_count += 1
                        continue

                    # Increment retry count before resuming
                    await analysis_repo.increment_workflow_gen_retry_count(
                        analysis_id=str(analysis.id),
                    )

                    # Try to resume alert atomically
                    success = await alert_repo.try_resume_alert(
                        tenant_id=alert.tenant_id,
                        alert_id=str(alert.id),
                    )

                    if success:
                        # Enqueue for processing - alert will re-check for workflow
                        # and potentially trigger new generation
                        await redis.enqueue_job(
                            "analysi.alert_analysis.worker.process_alert_analysis",
                            alert.tenant_id,
                            str(alert.id),
                            str(alert.current_analysis_id),
                        )
                        resumed_count += 1
                        retry_count += 1
                    else:
                        already_claimed_count += 1

            except Exception as e:
                logger.error("failed_to_check_alert", alert_id=alert.id, error=str(e))

        result = {
            "status": "completed",
            "resumed_count": resumed_count,
            "failed_count": failed_count,
            "stuck_alerts_count": stuck_count,
            "orphaned_count": orphaned_count,
            "stuck_reviews_count": stuck_reviews_count,
            "stuck_task_runs_count": stuck_task_runs_count,
            "stuck_workflow_runs_count": stuck_workflow_runs_count,
            "hitl_expired_count": hitl_expired_count,
            "synced_count": synced_count,
            "cleaned_count": cleaned_count,
            "running_workflows": running_workflows,
        }

        # Single structured summary (ARQ truncates its own logs)
        logger.info(
            "reconciliation_complete",
            resumed=resumed_count,
            recovered=recovery_count,
            retried=retry_count,
            already_claimed=already_claimed_count,
            max_retries_exceeded=max_retries_exceeded_count,
            backoff_skipped=backoff_skipped_count,
            stuck_generations=failed_count,
            stuck_alerts=stuck_count,
            orphaned=orphaned_count,
            stuck_reviews=stuck_reviews_count,
            stuck_task_runs=stuck_task_runs_count,
            stuck_workflow_runs=stuck_workflow_runs_count,
            hitl_expired=hitl_expired_count,
            synced=synced_count,
            cleaned=cleaned_count,
            running_workflows=running_workflows,
        )

        return result

    except (OSError, SQLAlchemyError) as e:
        # Connection refused / reset / closed — DB or Redis temporarily unavailable (e.g. pod restart)
        logger.warning("reconciliation_skipped_service_unavailable", error=str(e))
        return {
            "status": "skipped",
            "error": str(e),
            "resumed_count": 0,
            "failed_count": 0,
            "stuck_alerts_count": 0,
            "synced_count": 0,
            "cleaned_count": 0,
        }
    except Exception as e:
        logger.error("reconciliation_job_failed", error=str(e), exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "resumed_count": 0,
            "failed_count": 0,
            "stuck_alerts_count": 0,
            "synced_count": 0,
            "cleaned_count": 0,
        }

    finally:
        # Clean up resources
        if redis:
            await redis.aclose()
        if db:
            await db.close()


async def mark_expired_hitl_paused_analyses(
    analysis_repo: AlertAnalysisRepository,
    alert_repo: AlertRepository,
    timeout_hours: int = 24,
    hitl_repo: object | None = None,
) -> int:
    """
    Mark HITL-paused analyses as failed when the human review timeout expires.

    HITL — Project Kalymnos: When a workflow pauses for human input (e.g., Slack
    question), the analysis enters PAUSED_HUMAN_REVIEW status. If no answer arrives
    within the timeout, the analysis is marked as failed to prevent indefinite stalls.

    Bug #3 fix: Also processes question-level timeouts via hitl_repo.find_expired().
    Bug #4 fix: Skips analyses whose question was already answered (answer in flight).
    Bug #5 fix: Marks hitl_questions as expired when expiring their analysis.

    Args:
        analysis_repo: AlertAnalysisRepository instance
        alert_repo: AlertRepository instance
        timeout_hours: Hours after which a HITL pause is considered expired
        hitl_repo: Optional HITLQuestionRepository for question-level expiry.
            When provided, expired questions are processed first (Bug #3),
            answered questions are detected to avoid race conditions (Bug #4),
            and questions are marked expired alongside their analyses (Bug #5).

    Returns:
        int: Number of analyses marked as failed
    """
    # Bug #3 fix: Process question-level timeouts first.
    # Questions have a 4h timeout (DEFAULT_TIMEOUT_HOURS) while analyses have
    # a 24h timeout. Without this, the 4h timeout was dead code.
    #
    # Bug #25 fix: Commit after question expiry. mark_expired uses flush()
    # only, so without an explicit commit these updates would be rolled back
    # if the function returns early (no paused analyses found).
    if hitl_repo is not None:
        try:
            expired_questions = await hitl_repo.find_expired()
            for eq in expired_questions:
                await hitl_repo.mark_expired(eq.id)
                logger.info(
                    "hitl_question_expired",
                    question_id=str(eq.id),
                )
            if expired_questions:
                await analysis_repo.session.commit()
        except Exception:
            logger.warning("hitl_question_expiry_check_failed", exc_info=True)

    paused_analyses = await analysis_repo.find_paused_for_human_review()

    if not paused_analyses:
        return 0

    logger.info(
        "found_hitl_paused_analyses_to_check",
        paused_count=len(paused_analyses),
    )

    now = datetime.now(UTC)
    threshold = now - timedelta(hours=timeout_hours)
    failed_count = 0

    for analysis in paused_analyses:
        # Check if pause has expired based on updated_at (set when status changed)
        pause_time = analysis.updated_at
        if pause_time and pause_time.tzinfo is None:
            pause_time = pause_time.replace(tzinfo=UTC)

        if pause_time and pause_time > threshold:
            # Still within timeout — leave alone
            continue

        # Bug #4 fix: Check if the question was already answered.
        # If so, the human:responded control event is in the pipeline — skip.
        if hitl_repo is not None:
            try:
                question = await hitl_repo.find_by_analysis_id(analysis.id)
                if question is not None and question.status == "answered":
                    logger.info(
                        "hitl_analysis_skip_already_answered",
                        analysis_id=str(analysis.id),
                        question_id=str(question.id),
                    )
                    continue
            except Exception:
                logger.warning(
                    "hitl_question_status_check_failed",
                    analysis_id=str(analysis.id),
                    exc_info=True,
                )

        try:
            error_message = (
                f"Human review timed out after {timeout_hours} hours. "
                f"No response received for HITL question."
            )

            await analysis_repo.mark_failed(
                analysis_id=analysis.id,
                error_message=error_message,
                tenant_id=analysis.tenant_id,
            )

            # Bug #24 fix: Can't use mark_stuck_alert_failed() here — it
            # filters on status == RUNNING, but these analyses are
            # paused_human_review (mark_failed above transitions to FAILED,
            # not RUNNING). Update Alert.analysis_status directly.
            # Same pattern as line 367 for paused_workflow_building alerts.
            from analysi.models.alert import Alert

            alert_stmt = (
                update(Alert)
                .where(
                    and_(
                        Alert.id == analysis.alert_id,
                        Alert.tenant_id == analysis.tenant_id,
                    )
                )
                .values(
                    analysis_status="failed",
                    updated_at=datetime.now(UTC),
                )
            )
            await analysis_repo.session.execute(alert_stmt)
            await analysis_repo.session.commit()

            # Bug #5 fix: Also mark the hitl_question as expired.
            # Without this, a late button click would succeed on a pending question,
            # emit a human:responded event, and try to resume a now-failed task.
            if hitl_repo is not None:
                try:
                    pending_q = await hitl_repo.find_pending_by_analysis_id(analysis.id)
                    if pending_q is not None:
                        await hitl_repo.mark_expired(pending_q.id)
                        # Bug #26 fix: mark_expired only flushes — commit so
                        # the question status change persists even if the loop
                        # exits right after (no subsequent commit would save it).
                        await analysis_repo.session.commit()
                        logger.info(
                            "hitl_question_expired_with_analysis",
                            question_id=str(pending_q.id),
                            analysis_id=str(analysis.id),
                        )
                except Exception:
                    logger.warning(
                        "hitl_question_expire_failed",
                        analysis_id=str(analysis.id),
                        exc_info=True,
                    )

            failed_count += 1
            logger.warning(
                "marked_expired_hitl_paused_analysis",
                analysis_id=str(analysis.id),
                tenant_id=str(analysis.tenant_id),
                timeout_hours=timeout_hours,
            )

        except Exception as e:
            logger.error(
                "mark_expired_hitl_analysis_failed",
                analysis_id=str(analysis.id),
                error=str(e),
                exc_info=True,
            )

    if failed_count > 0:
        logger.info("marked_expired_hitl_analyses_as_failed", failed_count=failed_count)

    return failed_count


async def mark_stuck_generations_as_failed(
    generation_repo: WorkflowGenerationRepository,
) -> int:
    """
    Mark workflow generations stuck in 'running' status as failed.

    .. deprecated::
        Reconciliation now uses ``run_all_stuck_detection()`` from
        ``analysi.common.stuck_detection``.  This function is retained
        for backward-compatible test imports.

    Detect and mark generations that exceeded ARQ timeout.
    ARQ kills jobs externally on timeout, so exception handler never runs.
    This function catches those stuck generations during reconciliation.

    Args:
        generation_repo: WorkflowGenerationRepository instance

    Returns:
        int: Number of generations marked as failed
    """
    # Find stuck generations (running longer than JOB_TIMEOUT)
    # Uses same timeout as ARQ jobs to ensure consistency
    # Complex workflow generation can take up to 50 minutes
    stuck_generations = await generation_repo.find_stuck_generations(
        timeout_seconds=AlertAnalysisConfig.JOB_TIMEOUT
    )

    if not stuck_generations:
        return 0

    logger.info(
        "found_stuck_workflow_generations",
        count=len(stuck_generations),
    )

    failed_count = 0
    for generation in stuck_generations:
        try:
            # Mark as failed with timeout error
            created_at_str = (
                generation.created_at.isoformat()
                if generation.created_at
                else "unknown"
            )
            timeout_minutes = AlertAnalysisConfig.JOB_TIMEOUT // 60
            error_message = (
                f"Workflow generation exceeded timeout threshold "
                f"(created_at: {created_at_str}). "
                f"Likely timed out by ARQ worker after {timeout_minutes} minutes."
            )

            was_marked = await generation_repo.mark_as_failed(generation, error_message)

            # Calculate age safely (handle naive/None datetimes)
            age_str = "unknown"
            if generation.created_at:
                try:
                    created_at = generation.created_at
                    # Ensure timezone-aware for subtraction
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=UTC)
                    age_seconds = (datetime.now(UTC) - created_at).total_seconds()
                    age_str = f"{age_seconds:.0f}s"
                except Exception:
                    pass  # Keep "unknown"

            if was_marked:
                failed_count += 1
                logger.info(
                    "marked_stuck_generation_as_failed",
                    generation_id=str(generation.id),
                    tenant_id=str(generation.tenant_id),
                    age=age_str,
                )
            else:
                # Generation was completed by the job between find and mark — not a bug
                logger.info(
                    "skipped_generation_already_terminal",
                    generation_id=str(generation.id),
                    tenant_id=str(generation.tenant_id),
                    age=age_str,
                )

        except Exception as e:
            logger.error(
                "mark_stuck_generation_failed",
                generation_id=str(generation.id),
                error=str(e),
                exc_info=True,
            )

    if failed_count > 0:
        logger.info("marked_stuck_generations_as_failed", failed_count=failed_count)

    return failed_count


async def cleanup_orphaned_workspaces(db: AlertAnalysisDB) -> int:
    """
    Remove workspace directories for completed workflow generations.

    Database-driven cleanup using workspace_path column.
    Eliminates directory name parsing bugs.

    Args:
        db: Database connection for querying terminal generations

    Returns:
        int: Number of directories cleaned up
    """
    generation_repo = WorkflowGenerationRepository(db.session)

    # Get terminal generations from database
    generations = await generation_repo.find_generations_for_cleanup()

    if not generations:
        return 0

    logger.info(
        "found_terminal_generations_for_cleanup", generations_count=len(generations)
    )

    cleaned = 0
    for gen in generations:
        try:
            workspace_path = Path(gen.workspace_path)

            # Skip placeholder paths from old generations
            if gen.workspace_path == "/tmp/unknown":  # nosec B108
                logger.debug(
                    "skipping_placeholder_workspacepath_for_generation", id=gen.id
                )
                continue

            if workspace_path.exists():
                shutil.rmtree(workspace_path)
                cleaned += 1
                logger.info(
                    "cleaned_workspace_gen_status",
                    workspace_path=workspace_path,
                    id=gen.id,
                    status=gen.status,
                )
            else:
                logger.debug(
                    "workspace_already_removed_gen",
                    workspace_path=workspace_path,
                    id=gen.id,
                )

        except Exception as e:
            logger.error(
                "failed_to_cleanup",
                workspace_path=gen.workspace_path,
                error=str(e),
                exc_info=True,
            )

    if cleaned > 0:
        logger.info("cleanup_complete_cleaned_workspaces", cleaned=cleaned)

    return cleaned


async def sync_mismatched_alert_statuses(alert_repo: AlertRepository) -> int:
    """
    Sync Alert.analysis_status when AlertAnalysis.status is terminal but mismatched.

    Fixes bug where AlertAnalysis.status is 'failed' or 'completed' but
    Alert.analysis_status is still 'in_progress'. This happens when
    update_alert_analysis_status() fails (e.g., API 500 error from partition
    lock exhaustion) after AlertAnalysis.status was successfully updated.

    Args:
        alert_repo: AlertRepository instance

    Returns:
        int: Number of alerts synced
    """
    # Find alerts where:
    # - Alert.analysis_status = 'in_progress'
    # - AlertAnalysis.status IN ('failed', 'completed')
    mismatched = await alert_repo.find_mismatched_alert_statuses()

    if not mismatched:
        return 0

    logger.info(
        "found_alerts_with_mismatched_statuses_to_sync",
        mismatched_count=len(mismatched),
    )

    synced_count = 0
    for alert, analysis in mismatched:
        try:
            success = await alert_repo.sync_alert_status_from_analysis(
                tenant_id=alert.tenant_id,
                alert_id=str(alert.id),
                new_status=analysis.status,
            )

            if success:
                synced_count += 1
                logger.info(
                    "synced_alert_status_from_analysis",
                    alert_id=str(alert.id),
                    new_status=analysis.status,
                )

        except Exception as e:
            logger.error(
                "sync_alert_status_failed",
                alert_id=str(alert.id),
                error=str(e),
                exc_info=True,
            )

    if synced_count > 0:
        logger.info("synced_alert_statuses", synced_count=synced_count)

    return synced_count


async def detect_orphaned_analyses(
    analysis_repo: AlertAnalysisRepository,
    alert_repo: AlertRepository,
) -> int:
    """
    Detect and fail analyses stuck in 'running' with no step progress.

    Issue #5: AlertAnalysis records can end up in "running" status with no ARQ job
    processing them. This happens when Redis silently loses the job or the worker
    crashes before processing starts. Uses a 2-minute threshold (vs 60-minute for
    stuck alerts that have started processing).

    Args:
        analysis_repo: AlertAnalysisRepository instance
        alert_repo: AlertRepository instance

    Returns:
        int: Number of orphaned analyses marked as failed
    """
    orphans = await analysis_repo.find_orphaned_running_analyses(threshold_minutes=2)

    if not orphans:
        return 0

    logger.info(
        "found_orphaned_running_analyses_no_step_progress", orphans_count=len(orphans)
    )

    failed_count = 0
    for analysis in orphans:
        try:
            error_message = "Analysis job was never processed (orphaned)"

            await analysis_repo.mark_failed(
                analysis_id=analysis.id,
                error_message=error_message,
                tenant_id=analysis.tenant_id,
            )

            # Also update the alert's analysis_status to failed
            await alert_repo.mark_stuck_alert_failed(
                tenant_id=analysis.tenant_id,
                alert_id=str(analysis.alert_id),
                analysis_id=str(analysis.id),
                error=error_message,
            )

            failed_count += 1
            logger.warning(
                "marked_orphaned_analysis_as_failed",
                analysis_id=str(analysis.id),
                tenant_id=str(analysis.tenant_id),
                alert_id=str(analysis.alert_id),
            )

        except Exception as e:
            logger.error(
                "mark_orphaned_analysis_failed",
                analysis_id=str(analysis.id),
                error=str(e),
                exc_info=True,
            )

    if failed_count > 0:
        # Bug #27 fix: mark_failed() only flushes — commit so the update persists.
        # Without this, db.close() in the finally block rolls back the transaction
        # if reconciliation returns early (no paused alerts found).
        # Same class of bug as Bug #25 (HITL question expiry).
        await analysis_repo.session.commit()
        logger.info("marked_orphaned_analyses_as_failed", failed_count=failed_count)

    return failed_count


async def mark_stuck_running_alerts_as_failed(alert_repo: AlertRepository) -> int:
    """
    Mark alerts stuck in 'running' status for too long as failed.

    .. deprecated::
        Reconciliation now uses ``run_all_stuck_detection()`` from
        ``analysi.common.stuck_detection``.  This function is retained
        for backward-compatible test imports.

    Detects alerts where the ARQ job was killed
    externally (timeout, crash) but the alert status was never updated.

    Args:
        alert_repo: AlertRepository instance

    Returns:
        int: Number of alerts marked as failed
    """
    timeout_minutes = AlertAnalysisConfig.STUCK_ALERT_TIMEOUT_MINUTES

    # Returns list of (Alert, AlertAnalysis) tuples
    stuck_results = await alert_repo.find_stuck_running_alerts(
        stuck_threshold_minutes=timeout_minutes
    )

    if not stuck_results:
        return 0

    logger.info(
        "found_alerts_stuck_in_running_status", stuck_results_count=len(stuck_results)
    )

    failed_count = 0
    for alert, analysis in stuck_results:
        try:
            # Validate required fields to prevent "None" strings in database
            if not alert.id or not analysis or not analysis.id:
                logger.warning(
                    "skipping_stuck_alert_missing_data",
                    alert_id=str(alert.id),
                    analysis=str(analysis),
                )
                continue

            error_message = (
                f"Alert analysis timed out after {timeout_minutes} minutes. "
                f"Worker may have crashed or been killed externally."
            )

            success = await alert_repo.mark_stuck_alert_failed(
                tenant_id=alert.tenant_id,
                alert_id=str(alert.id),
                analysis_id=str(analysis.id),
                error=error_message,
            )

            if success:
                failed_count += 1
                logger.warning(
                    "marked_stuck_alert_as_failed",
                    alert_id=str(alert.id),
                    tenant_id=str(alert.tenant_id),
                    timeout_minutes=timeout_minutes,
                )
            else:
                logger.debug(
                    "alert_already_handled_by_another_worker", alert_id=alert.id
                )

        except Exception as e:
            logger.error(
                "mark_stuck_alert_failed",
                alert_id=str(alert.id),
                error=str(e),
                exc_info=True,
            )

    if failed_count > 0:
        logger.info("marked_stuck_alerts_as_failed", failed_count=failed_count)

    return failed_count


# Partition maintenance constants
PARTITION_MAINTENANCE_INTERVAL_HOURS = 1  # Only run maintenance every hour
_last_partition_maintenance: datetime | None = None


async def maintain_partitions() -> dict[str, int]:
    """
    Trigger pg_partman maintenance: create new partitions, drop expired ones.

    pg_partman (configured in V094 migration) handles all partition lifecycle.
    This function is a thin wrapper with rate limiting to avoid calling
    run_maintenance_proc() on every reconciliation cycle (every 10s).

    Returns:
        Dict with status, or empty dict if skipped due to rate limiting
    """
    global _last_partition_maintenance

    # Rate limit: only run maintenance once per hour
    now = datetime.now(UTC)
    if _last_partition_maintenance is not None:
        elapsed = now - _last_partition_maintenance
        if elapsed < timedelta(hours=PARTITION_MAINTENANCE_INTERVAL_HOURS):
            logger.debug(
                "skipping_partition_maintenance",
                last_run_seconds_ago=int(elapsed.total_seconds()),
            )
            return {}

    logger.info("Starting pg_partman maintenance")

    try:
        await run_maintenance()
        _last_partition_maintenance = now
        logger.info("pg_partman maintenance completed")
        return {"status": "completed"}

    except Exception as e:
        logger.error("partition_maintenance_failed", error=str(e), exc_info=True)
        return {"status": "failed", "error": str(e)[:200]}

"""ARQ job for standalone task generation.

Runs the cybersec-task-builder agent to create a task from a description.
Simpler than Kea's parallel task building — no BaseException recovery,
no parallel execution. Progress tracked via TaskGenerationApiClient.
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from analysi.agentic_orchestration import (
    AgentWorkspace,
    TaskGenerationApiClient,
    TaskGenerationProgressCallback,
    create_executor,
)
from analysi.agentic_orchestration.nodes.task_building import run_task_builder_agent
from analysi.agentic_orchestration.skills_sync import TenantSkillsSyncer
from analysi.alert_analysis.config import AlertAnalysisConfig
from analysi.common.internal_auth import internal_auth_headers
from analysi.common.internal_client import InternalAsyncClient
from analysi.common.job_tracking import tracked_job
from analysi.config.logging import get_logger
from analysi.db.session import AsyncSessionLocal
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.task_generation import TaskGeneration
from analysi.repositories.integration_repository import IntegrationRepository
from analysi.services.agent_credential_factory import AgentCredentialFactory
from analysi.services.integration_service import IntegrationService

logger = get_logger(__name__)


@tracked_job(
    job_type="execute_task_build",
    timeout_seconds=3600,
    model_class=TaskGeneration,
    extract_row_id=lambda ctx, run_id, tenant_id, description, alert_id=None, input_context=None, actor_id=None: (
        run_id
    ),
)
async def execute_task_build(
    ctx: dict[str, Any],
    run_id: str,
    tenant_id: str,
    description: str,
    alert_id: str | None = None,
    input_context: dict[str, Any] | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Execute a standalone task build (or modification from a starting point).

    Called as an ARQ job from the task-generations API endpoint.

    Args:
        ctx: ARQ context
        run_id: TaskGeneration UUID for progress tracking
        tenant_id: Tenant identifier
        description: Human-provided task description (or modification instruction)
        alert_id: Optional alert UUID for example context
        input_context: Full input context from router, may contain 'existing_task'
            for modification mode
        actor_id: Email of the user who triggered the generation (for attribution)

    Returns:
        {status: completed|failed, task_id: str|None, error: str|None}
    """
    existing_task = (input_context or {}).get("existing_task")
    mode = "modify" if existing_task else "create"
    logger.info(
        "task_build_started",
        run_id=run_id,
        tenant_id=tenant_id,
        mode=mode,
    )

    api_base_url = AlertAnalysisConfig.API_BASE_URL

    # Create client for progress tracking (no generation_id for standalone)
    client = TaskGenerationApiClient(
        api_base_url=api_base_url,
        tenant_id=tenant_id,
        generation_id=None,
    )

    # Mark as in_progress
    await client.mark_in_progress(run_id)

    try:
        job_start_time = datetime.now(UTC)

        # 1. Get credentials
        async with AsyncSessionLocal() as session:
            integration_repo = IntegrationRepository(session)
            integration_service = IntegrationService(
                integration_repo=integration_repo,
            )
            credential_factory = AgentCredentialFactory(integration_service)

            credentials = await credential_factory.get_agent_credentials(tenant_id)
            oauth_token = credentials["oauth_token"]

        logger.info("taskbuild_retrieved_oauth_token_for_tenant", tenant_id=tenant_id)

        # 2. Fetch alert data if alert_id provided
        alert_data = {}
        if alert_id:
            alert_data = await _fetch_alert(api_base_url, tenant_id, alert_id)

        # 3. Create executor and workspace (skills auto-synced by run_agent)
        executor = create_executor(
            tenant_id=tenant_id,
            oauth_token=oauth_token,
            actor_user_id=actor_id,
        )

        skills_syncer = TenantSkillsSyncer(
            tenant_id=tenant_id,
            session_factory=AsyncSessionLocal,
        )

        workspace = AgentWorkspace(
            run_id=f"task-build-{run_id}",
            tenant_id=tenant_id,
            skills_syncer=skills_syncer,
        )

        # 4. Setup progress callback
        progress_callback = TaskGenerationProgressCallback(
            client=client,
            run_id=run_id,
        )

        # 5. Build agent context
        agent_context: dict[str, Any] = {
            "description": description,
            "task_metadata": {
                "created_by": actor_id or str(SYSTEM_USER_ID),
                "tenant_id": tenant_id,
                "source": "standalone-api",
            },
        }
        if alert_data:
            agent_context["alert"] = alert_data
        if existing_task:
            agent_context["existing_task"] = existing_task

        # 6. Run the agent
        try:
            _outputs, _metrics = await run_task_builder_agent(
                workspace=workspace,
                executor=executor,
                context=agent_context,
                callback=progress_callback,
            )
        finally:
            workspace.cleanup()

        # 7. Post-flight verification
        if existing_task:
            # Modification mode: verify the target task was updated
            result_task = await _verify_task_modified(
                api_base_url, tenant_id, existing_task, job_start_time
            )
        else:
            # Creation mode: look for a recently created task
            result_task = await _find_recently_created_task(api_base_url, tenant_id)

        if result_task:
            task_id = result_task.get("id", "")
            cy_name = result_task.get("cy_name", "")
            action = "modified" if existing_task else "created"
            logger.info(
                "task_build_complete", action=action, cy_name=cy_name, task_id=task_id
            )
            await client.mark_completed(run_id, task_id=task_id, cy_name=cy_name)
            return {"status": "completed", "task_id": task_id, "error": None}
        if existing_task:
            error_msg = (
                f"Agent execution completed but task '{existing_task.get('cy_name')}' "
                "was not updated. The agent may have failed to call update_task_script."
            )
        else:
            error_msg = (
                "Agent execution completed but no new task was found. "
                "The agent may have failed to call create_task."
            )
        logger.error("taskbuild", error_msg=error_msg)
        await client.mark_failed(run_id, error=error_msg, error_type="TaskNotCreated")
        raise RuntimeError(error_msg)

    except ValueError as e:
        # Credential errors (no integration configured)
        error_msg = f"Credential error: {e}"
        logger.error("taskbuild", error_msg=error_msg)
        await client.mark_failed(run_id, error=error_msg, error_type="CredentialError")
        raise

    except Exception as e:
        error_msg = f"Task build failed: {e}"
        logger.error("taskbuild", error_msg=error_msg, exc_info=True)
        await client.mark_failed(run_id, error=error_msg, error_type=type(e).__name__)
        raise


async def _fetch_alert(
    api_base_url: str, tenant_id: str, alert_id: str
) -> dict[str, Any]:
    """Fetch alert data via REST API for use as example context."""
    url = f"{api_base_url}/v1/{tenant_id}/alerts/{alert_id}"
    timeout = httpx.Timeout(10.0, connect=5.0)

    try:
        async with InternalAsyncClient(
            timeout=timeout, headers=internal_auth_headers()
        ) as http_client:
            response = await http_client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning(
            "taskbuild_failed_to_fetch_alert", alert_id=alert_id, error=str(e)
        )
        return {}


async def _find_recently_created_task(
    api_base_url: str, tenant_id: str
) -> dict[str, Any] | None:
    """Find the most recently created task within a 5-minute window.

    Checks the most recent tasks by created_at and returns the first one
    created within 5 minutes. No text search — the agent names the task
    differently from the user's description, so keyword matching won't work.

    The 5-minute window + limit of 3 keeps false positives low.
    """
    url = f"{api_base_url}/v1/{tenant_id}/tasks"
    timeout = httpx.Timeout(10.0, connect=5.0)

    try:
        async with InternalAsyncClient(
            timeout=timeout, headers=internal_auth_headers()
        ) as http_client:
            params: dict[str, Any] = {
                "limit": 3,
                "sort_by": "created_at",
                "sort_order": "desc",
            }

            response = await http_client.get(url, params=params)
            response.raise_for_status()
            # InternalAsyncClient unwraps Sifnos envelope:
            # {"data": [...], "meta": {...}} → [...]
            tasks = response.json()
            if not isinstance(tasks, list) or not tasks:
                return None

            from dateutil.parser import parse as parse_dt

            now = datetime.now(UTC)
            for task in tasks:
                created_at = task.get("created_at", "")
                if not created_at:
                    continue

                task_time = parse_dt(created_at)
                if task_time.tzinfo is None:
                    task_time = task_time.replace(tzinfo=UTC)

                age_seconds = (now - task_time).total_seconds()
                if age_seconds < 300:  # 5 minutes
                    return task

            return None
    except Exception as e:
        logger.warning("taskbuild_failed_to_check_recent_tasks", error=str(e))
        return None


async def _verify_task_modified(
    api_base_url: str,
    tenant_id: str,
    existing_task: dict[str, Any],
    job_start_time: datetime,
) -> dict[str, Any] | None:
    """Verify that the target task was actually modified by the agent.

    Uses two independent signals to avoid false positives/negatives:
    1. Timestamp check: updated_at > job_start_time (detects any DB update)
    2. Script diff: fetched script != original script (detects actual content change)

    A concurrent edit by another actor could bump updated_at without the agent
    doing anything, so we require BOTH signals for high-confidence confirmation.
    If only the timestamp bumped but script is unchanged, we still accept it
    (could be a description/directive-only change via update_task_script).

    Args:
        api_base_url: Base URL for API
        tenant_id: Tenant ID for API call
        existing_task: The starting-point task dict from input_context
        job_start_time: When the job started (UTC)

    Returns:
        Task dict if modified, None if not found or not updated
    """
    task_id = existing_task.get("task_id", "")
    if not task_id:
        logger.warning(
            "[TaskBuild] No task_id in existing_task, cannot verify modification"
        )
        return None

    cy_name = existing_task.get("cy_name", "unknown")
    original_script = existing_task.get("script", "")
    url = f"{api_base_url}/v1/{tenant_id}/tasks/{task_id}"
    timeout = httpx.Timeout(10.0, connect=5.0)

    try:
        async with InternalAsyncClient(
            timeout=timeout, headers=internal_auth_headers()
        ) as http_client:
            response = await http_client.get(url)
            response.raise_for_status()
            task = response.json()

            from dateutil.parser import parse as parse_dt

            updated_at_str = task.get("updated_at", "")
            if not updated_at_str:
                logger.warning("taskbuild_task_has_no_updatedat_field", cy_name=cy_name)
                return None

            updated_at = parse_dt(updated_at_str)
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=UTC)

            timestamp_changed = updated_at > job_start_time
            script_changed = task.get("script", "") != original_script

            # Primary gate: updated_at must have bumped DURING this run.
            # Script diff is supplementary info only — a script change without
            # a post-start timestamp could be a stale edit from before the run.
            if timestamp_changed and script_changed:
                logger.info(
                    "task_build_task_confirmed_modified",
                    cy_name=cy_name,
                    updated_at=str(updated_at),
                    job_start=str(job_start_time),
                    script_changed=True,
                )
                return task
            if timestamp_changed:
                # Timestamp bumped but script unchanged — likely a description/directive
                # update, or a component-only change. Accept as modified since
                # update_task_script always requires script (DB trigger fires).
                logger.info(
                    "task_build_task_timestamp_updated_script_unchanged",
                    cy_name=cy_name,
                    note="possible metadata-only change, accepting as modified",
                )
                return task
            if script_changed:
                # Script is different but timestamp didn't bump after job_start_time.
                # This could be a stale edit made before the agent ran — NOT safe
                # to attribute to this run without temporal evidence.
                logger.warning(
                    "task_build_task_script_differs_stale_edit",
                    cy_name=cy_name,
                    updated_at=str(updated_at),
                    job_start=str(job_start_time),
                    note="possible stale edit, not attributing to this run",
                )
                return None
            logger.warning(
                "task_build_task_not_modified",
                cy_name=cy_name,
                updated_at=str(updated_at),
                job_start=str(job_start_time),
                script_changed=False,
            )
            return None

    except Exception as e:
        logger.warning("taskbuild_failed_to_verify_task_modification", error=str(e))
        return None

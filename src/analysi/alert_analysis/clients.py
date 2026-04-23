"""HTTP Clients for Alert Analysis Service"""

import os
from typing import Any

import httpx

from analysi.common.internal_auth import internal_auth_headers
from analysi.common.internal_client import InternalAsyncClient
from analysi.common.retry_config import (
    RetryableHTTPError,
    WorkflowNotFoundError,
    http_retry_policy,
    polling_retry_policy,
)
from analysi.config.logging import get_logger

logger = get_logger(__name__)


class BackendAPIClient:
    """
    HTTP client for calling main backend API from alert analysis worker.
    Handles workflows, artifacts, and other API calls.
    """

    def __init__(self):
        backend_api_host = os.getenv("BACKEND_API_HOST", "api")
        backend_api_port = int(os.getenv("BACKEND_API_PORT", 8000))
        self.base_url = f"http://{backend_api_host}:{backend_api_port}"
        self.timeout = httpx.Timeout(30.0, connect=5.0)

    @property
    def _headers(self) -> dict[str, str]:
        """Compute per-call so actor from contextvars is always current."""
        return internal_auth_headers()

    @http_retry_policy()
    async def execute_workflow(
        self,
        tenant_id: str,
        workflow_id: str,
        input_data: dict[str, Any],
        execution_context: dict[str, Any] | None = None,
    ) -> str:
        """
        Execute a workflow via API with automatic retry on failures.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow UUID to execute
            input_data: Input data for the workflow
            execution_context: Optional context (e.g., analysis_id for artifact linking)

        Returns:
            str: Workflow run ID
        """
        logger.info("executing_workflow_via_api", workflow_id=workflow_id)

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            try:
                request_body = {"input_data": input_data}
                if execution_context:
                    request_body["execution_context"] = execution_context

                response = await client.post(
                    f"{self.base_url}/v1/{tenant_id}/workflows/{workflow_id}/run",
                    json=request_body,
                )

                if response.status_code >= 500 or response.status_code == 429:
                    raise RetryableHTTPError(
                        f"Server error: {response.status_code}", response.status_code
                    )

                # Handle 4xx errors with detailed error messages
                if response.status_code >= 400:
                    try:
                        error_detail = response.json().get("detail", str(response.text))
                    except Exception:
                        error_detail = response.text

                    # Handle 404 specifically - workflow may have been deleted
                    # This allows the pipeline to retry with cache invalidation
                    if response.status_code == 404:
                        raise WorkflowNotFoundError(
                            workflow_id=workflow_id,
                            message=f"Workflow {workflow_id} not found - cache may be stale",
                        )

                    # Extract validation error details for better user feedback
                    if (
                        response.status_code == 400
                        and "validation" in error_detail.lower()
                    ):
                        # Parse validation error to extract required fields
                        raise ValueError(f"Alert validation failed: {error_detail}")
                    raise ValueError(
                        f"Workflow execution failed ({response.status_code}): {error_detail}"
                    )

                result = response.json()
                workflow_run_id = result.get("workflow_run_id")
                logger.info("started_workflow_run", workflow_run_id=workflow_run_id)
                return workflow_run_id

            except httpx.HTTPStatusError as e:
                # This shouldn't be reached anymore since we handle status codes above
                logger.error("failed_to_execute_workflow", error=str(e))
                raise
            except httpx.RequestError as e:
                logger.error("request_error_executing_workflow", error=str(e))
                raise RetryableHTTPError(str(e), 500)

    @http_retry_policy()
    async def get_workflow_by_name(
        self, tenant_id: str, workflow_name: str
    ) -> str | None:
        """
        Get workflow ID by name.

        Returns:
            str: Workflow ID if found, None otherwise
        """
        logger.info("looking_up_workflow_by_name", workflow_name=workflow_name)

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            try:
                response = await client.get(f"{self.base_url}/v1/{tenant_id}/workflows")

                if response.status_code >= 500 or response.status_code == 429:
                    raise RetryableHTTPError(
                        f"Server error: {response.status_code}", response.status_code
                    )

                response.raise_for_status()
                workflows = response.json()

                for workflow in workflows or []:
                    if workflow.get("name") == workflow_name:
                        workflow_id = workflow.get("id")
                        logger.info(
                            "found_workflow",
                            workflow_name=workflow_name,
                            workflow_id=workflow_id,
                        )
                        return workflow_id

                logger.warning("workflow_not_found", workflow_name=workflow_name)
                return None

            except httpx.HTTPStatusError as e:
                logger.error("failed_to_get_workflows", error=str(e))
                raise
            except httpx.RequestError as e:
                logger.error("request_error_getting_workflows", error=str(e))
                raise RetryableHTTPError(str(e), 500)

    @polling_retry_policy(max_wait_seconds=60)
    async def get_workflow_status(self, tenant_id: str, workflow_run_id: str) -> str:
        """
        Get workflow execution status with polling retry.
        """
        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/v1/{tenant_id}/workflow-runs/{workflow_run_id}/status"
                )

                if response.status_code >= 500 or response.status_code == 429:
                    raise RetryableHTTPError(
                        f"Server error: {response.status_code}", response.status_code
                    )

                response.raise_for_status()
                data = response.json()
                status = data.get("status")

                logger.info(
                    "workflow_status", workflow_run_id=workflow_run_id, status=status
                )
                return status

            except httpx.HTTPStatusError as e:
                logger.error("failed_to_get_workflow_status", error=str(e))
                raise
            except httpx.RequestError as e:
                logger.error("request_error_getting_workflow_status", error=str(e))
                raise RetryableHTTPError(str(e), 500)

    @http_retry_policy()
    async def get_artifacts_by_workflow_run(
        self, tenant_id: str, workflow_run_id: str
    ) -> list[dict[str, Any]]:
        """
        Get all artifacts for a workflow run.
        """
        logger.info(
            "getting_artifacts_for_workflow_run", workflow_run_id=workflow_run_id
        )

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/v1/{tenant_id}/artifacts",
                    params={"workflow_run_id": workflow_run_id},
                )

                if response.status_code >= 500 or response.status_code == 429:
                    raise RetryableHTTPError(
                        f"Server error: {response.status_code}", response.status_code
                    )

                response.raise_for_status()
                artifacts = response.json()
                logger.info(
                    "retrieved_artifacts_for_workflow_run",
                    artifacts_count=len(artifacts),
                )
                return artifacts

            except httpx.HTTPStatusError as e:
                logger.error("failed_to_get_artifacts", error=str(e))
                raise
            except httpx.RequestError as e:
                logger.error("request_error_getting_artifacts", error=str(e))
                raise RetryableHTTPError(str(e), 500)

    @http_retry_policy()
    async def download_artifact(self, tenant_id: str, artifact_id: str) -> str | None:
        """
        Download artifact content with automatic retry.
        """
        logger.info(
            "downloading_artifact_for_tenant",
            artifact_id=artifact_id,
            tenant_id=tenant_id,
        )

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/v1/{tenant_id}/artifacts/{artifact_id}/download"
                )

                if response.status_code >= 500 or response.status_code == 429:
                    raise RetryableHTTPError(
                        f"Server error: {response.status_code}", response.status_code
                    )

                if response.status_code == 404:
                    logger.warning("artifact_not_found", artifact_id=artifact_id)
                    return None

                response.raise_for_status()
                content = response.text
                logger.debug(
                    "downloaded_artifact_content_characters", content_count=len(content)
                )
                return content

            except httpx.HTTPStatusError as e:
                logger.error("failed_to_download_artifact", error=str(e))
                return None
            except httpx.RequestError as e:
                logger.error("request_error_downloading_artifact", error=str(e))
                raise RetryableHTTPError(str(e), 500)

    @http_retry_policy()
    async def get_dispositions(self, tenant_id: str) -> list:
        """
        Get all available dispositions with automatic retry.
        """
        logger.info("getting_dispositions_for_tenant", tenant_id=tenant_id)

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/v1/{tenant_id}/dispositions"
                )

                if response.status_code >= 500 or response.status_code == 429:
                    raise RetryableHTTPError(
                        f"Server error: {response.status_code}", response.status_code
                    )

                response.raise_for_status()
                dispositions = response.json()
                logger.info(
                    "retrieved_dispositions", dispositions_count=len(dispositions)
                )
                return dispositions

            except httpx.HTTPStatusError as e:
                logger.error("failed_to_get_dispositions", error=str(e))
                raise
            except httpx.RequestError as e:
                logger.error("request_error_getting_dispositions", error=str(e))
                raise RetryableHTTPError(str(e), 500)

    @http_retry_policy()
    async def update_analysis_status(
        self, tenant_id: str, analysis_id: str, status: str, error: str | None = None
    ) -> bool:
        """
        Update analysis status via REST API.

        Args:
            tenant_id: Tenant identifier
            analysis_id: Analysis UUID
            status: New status (running, failed, paused, completed)
            error: Optional error message for failed status

        Returns:
            True if update succeeded, False otherwise
        """
        logger.info(
            "updating_analysis_status_to", analysis_id=analysis_id, status=status
        )

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            try:
                params = {"status": status}
                if error:
                    params["error"] = error

                response = await client.put(
                    f"{self.base_url}/v1/{tenant_id}/analyses/{analysis_id}/status",
                    params=params,
                )

                if response.status_code >= 500 or response.status_code == 429:
                    raise RetryableHTTPError(
                        f"Server error: {response.status_code}", response.status_code
                    )

                # 409 Conflict means the analysis is in a terminal state (cancelled).
                # Return None so callers can distinguish "rejected" from other errors.
                if response.status_code == 409:
                    logger.warning(
                        "analysis_status_update_rejected",
                        analysis_id=analysis_id,
                        reason="terminal_state_cancelled",
                    )
                    return None

                response.raise_for_status()
                logger.info("successfully_updated_analysis_status_to", status=status)
                return True

            except httpx.HTTPStatusError as e:
                logger.error("failed_to_update_analysis_status", error=str(e))
                return False
            except httpx.RequestError as e:
                logger.error("request_error_updating_analysis_status", error=str(e))
                raise RetryableHTTPError(str(e), 500)

    @http_retry_policy()
    async def update_alert_analysis_status(
        self, tenant_id: str, alert_id: str, analysis_status: str
    ) -> bool:
        """
        Update alert's analysis_status field via REST API.

        Args:
            tenant_id: Tenant identifier
            alert_id: Alert UUID
            analysis_status: New analysis status

        Returns:
            True if update succeeded, False otherwise
        """
        logger.info(
            "updating_alert_analysisstatus_to",
            alert_id=alert_id,
            analysis_status=analysis_status,
        )

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            try:
                response = await client.put(
                    f"{self.base_url}/v1/{tenant_id}/alerts/{alert_id}/analysis-status",
                    params={"analysis_status": analysis_status},
                )

                if response.status_code >= 500 or response.status_code == 429:
                    raise RetryableHTTPError(
                        f"Server error: {response.status_code}", response.status_code
                    )

                response.raise_for_status()
                logger.info(
                    "successfully_updated_alert_analysis_status_to",
                    analysis_status=analysis_status,
                )
                return True

            except httpx.HTTPStatusError as e:
                logger.error("failed_to_update_alert_analysis_status", error=str(e))
                return False
            except httpx.RequestError as e:
                logger.error(
                    "request_error_updating_alert_analysis_status", error=str(e)
                )
                raise RetryableHTTPError(str(e), 500)

    @http_retry_policy()
    async def get_alert(self, tenant_id: str, alert_id: str) -> dict[str, Any] | None:
        """
        Get alert data via REST API.

        Args:
            tenant_id: Tenant identifier
            alert_id: Alert UUID

        Returns:
            Alert data dict or None if not found
        """
        logger.debug("getting_alert_for_tenant", alert_id=alert_id, tenant_id=tenant_id)

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/v1/{tenant_id}/alerts/{alert_id}"
                )

                if response.status_code >= 500 or response.status_code == 429:
                    raise RetryableHTTPError(
                        f"Server error: {response.status_code}", response.status_code
                    )

                if response.status_code == 404:
                    logger.warning("alert_not_found", alert_id=alert_id)
                    return None

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                logger.error("failed_to_get_alert", error=str(e))
                return None
            except httpx.RequestError as e:
                logger.error("request_error_getting_alert", error=str(e))
                raise RetryableHTTPError(str(e), 500)

    @http_retry_policy()
    async def get_analysis(
        self, tenant_id: str, alert_id: str
    ) -> dict[str, Any] | None:
        """
        Get analysis data for an alert via REST API.

        Args:
            tenant_id: Tenant identifier
            alert_id: Alert UUID

        Returns:
            Analysis data dict or None if not found
        """
        logger.debug("getting_analysis_for_alert", alert_id=alert_id)

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            try:
                # Get alert with analysis included
                response = await client.get(
                    f"{self.base_url}/v1/{tenant_id}/alerts/{alert_id}",
                    params={"include_analysis": "true"},
                )

                if response.status_code >= 500 or response.status_code == 429:
                    raise RetryableHTTPError(
                        f"Server error: {response.status_code}", response.status_code
                    )

                if response.status_code == 404:
                    logger.warning("alert_not_found", alert_id=alert_id)
                    return None

                response.raise_for_status()
                alert_data = response.json()

                # Extract analysis from included data
                if alert_data.get("current_analysis"):
                    return alert_data["current_analysis"]

                return None

            except httpx.HTTPStatusError as e:
                logger.error("failed_to_get_analysis", error=str(e))
                return None
            except httpx.RequestError as e:
                logger.error("request_error_getting_analysis", error=str(e))
                raise RetryableHTTPError(str(e), 500)

    @http_retry_policy()
    async def update_step_progress(
        self,
        tenant_id: str,
        analysis_id: str,
        step_name: str,
        completed: bool,
        error: str | None = None,
    ) -> bool:
        """
        Update step progress via REST API.

        Args:
            tenant_id: Tenant identifier
            analysis_id: Analysis UUID
            step_name: Pipeline step name
            completed: Whether step is completed
            error: Optional error message

        Returns:
            True if update succeeded, False otherwise
        """
        logger.info(
            "updating_step_for_analysis", step_name=step_name, analysis_id=analysis_id
        )

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            try:
                params = {"step_name": step_name, "completed": completed}
                if error:
                    params["error"] = error

                response = await client.put(
                    f"{self.base_url}/v1/{tenant_id}/analyses/{analysis_id}/step",
                    params=params,
                )

                if response.status_code >= 500 or response.status_code == 429:
                    raise RetryableHTTPError(
                        f"Server error: {response.status_code}", response.status_code
                    )

                response.raise_for_status()
                logger.info("successfully_updated_step", step_name=step_name)
                return True

            except httpx.HTTPStatusError as e:
                logger.error("failed_to_update_step_progress", error=str(e))
                return False
            except httpx.RequestError as e:
                logger.error("request_error_updating_step_progress", error=str(e))
                raise RetryableHTTPError(str(e), 500)


class KeaCoordinationClient:
    """
    HTTP client for Kea Coordination API endpoints.

    Handles analysis group and workflow generation operations.
    Used by WorkflowBuilderStep to query/create analysis groups and check
    for active workflows.
    """

    def __init__(self, base_url: str):
        """
        Initialize Kea Coordination client.

        Args:
            base_url: Base URL for Kea API (e.g., "http://api:8000")
        """
        self.base_url = base_url
        self.timeout = httpx.Timeout(30.0, connect=5.0)

    @property
    def _headers(self) -> dict[str, str]:
        """Compute per-call so actor from contextvars is always current."""
        return internal_auth_headers()

    async def create_group_with_generation(
        self,
        tenant_id: str,
        title: str,
        triggering_alert_analysis_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Atomically create analysis group + workflow generation.

        This endpoint either:
        1. Creates a new analysis group and workflow_generation (first alert)
        2. Returns existing group if title already exists (subsequent alerts)

        Args:
            tenant_id: Tenant identifier
            title: Analysis group title (e.g., alert rule_name)
            triggering_alert_analysis_id: ID of alert_analysis that triggered this

        Returns:
            {
                "analysis_group": {"id": "uuid", "title": "...", ...},
                "workflow_generation": {"id": "uuid", "status": "running", "workflow_id": null}
            }

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        logger.info(
            "creating_or_getting_analysis_group", title=title, tenant_id=tenant_id
        )

        url = f"{self.base_url}/v1/{tenant_id}/analysis-groups/with-workflow-generation"
        payload = {"title": title}
        if triggering_alert_analysis_id:
            payload["triggering_alert_analysis_id"] = triggering_alert_analysis_id

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

            group_id = result["analysis_group"]["id"]
            gen_status = result["workflow_generation"]["status"]
            logger.info(
                "analysis_group_ready",
                group_id=group_id,
                generation_status=gen_status,
            )

            return result

    async def create_routing_rule(
        self,
        tenant_id: str,
        analysis_group_id: str,
        workflow_id: str,
    ) -> dict[str, Any]:
        """
        Create a routing rule linking an analysis group to a workflow.

        Issue #10 recovery: Used by reconciliation when a workflow generation
        completed successfully but the routing rule creation failed.

        Args:
            tenant_id: Tenant identifier
            analysis_group_id: Analysis group UUID
            workflow_id: Workflow UUID to route to

        Returns:
            Created routing rule dict

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        logger.info(
            "creating_routing_rule",
            analysis_group_id=analysis_group_id,
            workflow_id=workflow_id,
        )

        url = f"{self.base_url}/v1/{tenant_id}/alert-routing-rules"
        payload = {
            "analysis_group_id": analysis_group_id,
            "workflow_id": workflow_id,
        }

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

            logger.info("created_routing_rule", id=result.get("id"))
            return result

    async def get_active_workflow(
        self,
        tenant_id: str,
        group_title: str,
    ) -> dict[str, Any]:
        """
        Get active workflow for analysis group by title.

        Args:
            tenant_id: Tenant identifier
            group_title: Analysis group title (e.g., alert rule_name)

        Returns:
            {
                "routing_rule": {"workflow_id": "uuid", ...} or None,
                "generation": {"id": "uuid", "status": "...", ...} or None
            }

        Raises:
            httpx.HTTPStatusError: If API call fails
        """
        logger.info("getting_active_workflow_for_group", group_title=group_title)

        url = f"{self.base_url}/v1/{tenant_id}/analysis-groups/active-workflow"

        async with InternalAsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            response = await client.get(url, params={"title": group_title})
            response.raise_for_status()
            result = response.json()

            if result.get("routing_rule"):
                workflow_id = result["routing_rule"].get("workflow_id")
                logger.info(
                    "active_workflow_for_group",
                    group_title=group_title,
                    workflow_id=workflow_id,
                )
            else:
                logger.info("no_active_workflow_for_group", group_title=group_title)

            return result

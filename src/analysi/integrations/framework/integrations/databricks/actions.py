"""Databricks integration actions for analytics and data platform operations."""

import asyncio
import json
from typing import Any

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.compute import ClusterSpec, Library
from databricks.sdk.service.iam import AccessControlRequest
from databricks.sdk.service.jobs import (
    GitSource,
    NotebookTask,
    RunResultState,
    SubmitTask,
)
from databricks.sdk.service.sql import (
    AlertOptions,
    AlertOptionsEmptyResultState,
    Disposition,
    ExecuteStatementRequestOnWaitTimeout,
    Format,
)
from databricks.sdk.service.workspace import ObjectType

from . import constants as consts

logger = get_logger(__name__)

# ============================================================================
# UTILITIES
# ============================================================================

def _get_databricks_client(
    host: str, username: str = None, password: str = None, token: str = None
) -> WorkspaceClient:
    """Create Databricks WorkspaceClient with credentials.

    Args:
        host: Databricks host URL (must begin with https://)
        username: Username for basic auth (optional)
        password: Password for basic auth (optional)
        token: Personal access token (optional)

    Returns:
        WorkspaceClient instance
    """
    return WorkspaceClient(
        host=host,
        username=username,
        password=password,
        token=token,
    )

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Databricks API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Databricks API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        # Validate credentials
        if not host:
            return {
                "healthy": False,
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_HOST,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        if not ((username and password) or token):
            return {
                "healthy": False,
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        def sync_health_check():
            """Synchronous health check operation."""
            client = _get_databricks_client(host, username, password, token)
            # Test connectivity by checking DBFS root
            client.dbfs.get_status(consts.TEST_CONNECTIVITY_FILE_PATH)
            return True

        try:
            # Run sync operation in thread pool
            await asyncio.to_thread(sync_health_check)

            return {
                "healthy": True,
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_TEST_CONNECTIVITY_SUCCESS,
                "data": {"healthy": True, "host": host},
            }

        except Exception as e:
            logger.error("databricks_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_TEST_CONNECTIVITY_ERROR}: {e!s}",
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class ListAlertsAction(IntegrationAction):
    """List all Databricks SQL alerts."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all SQL alerts in the workspace.

        Returns:
            Result with list of alerts or error
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        if not host or not ((username and password) or token):
            return {
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
            }

        def sync_list_alerts():
            """Synchronous list alerts operation."""
            client = _get_databricks_client(host, username, password, token)
            alerts = list(client.alerts.list())
            return [alert.as_dict() for alert in alerts]

        try:
            alerts = await asyncio.to_thread(sync_list_alerts)

            return {
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_LIST_ALERTS_SUCCESS,
                "data": {"alerts": alerts, "total_alerts": len(alerts)},
            }

        except Exception as e:
            logger.error("failed_to_list_alerts", error=str(e))
            return {
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_LIST_ALERTS_ERROR}: {e!s}",
                "error_type": type(e).__name__,
            }

class CreateAlertAction(IntegrationAction):
    """Create a Databricks SQL alert."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create a new SQL alert.

        Args:
            **kwargs: Must contain:
                - name: Alert name
                - query_id: Query ID to monitor
                - column: Column to monitor
                - operator: Comparison operator
                - value: Threshold value
                Optional:
                - custom_body: Custom alert body
                - custom_subject: Custom alert subject
                - muted: Whether alert is muted
                - empty_result_state: State when query returns no results
                - rearm: Rearm time in seconds
                - parent: Parent folder path or ID

        Returns:
            Result with alert details or error
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        if not host or not ((username and password) or token):
            return {
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
            }

        # Validate required parameters
        name = kwargs.get("name")
        query_id = kwargs.get("query_id")
        column = kwargs.get("column")
        operator = kwargs.get("operator")
        value = kwargs.get("value")

        if not all([name, query_id, column, operator, value is not None]):
            return {
                "status": consts.STATUS_ERROR,
                "error": "Missing required parameters: name, query_id, column, operator, value",
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }

        def sync_create_alert():
            """Synchronous create alert operation."""
            client = _get_databricks_client(host, username, password, token)

            # Build alert options
            options_kwargs = {
                "column": column,
                "op": operator,
                "value": value,
            }

            if kwargs.get("custom_body"):
                options_kwargs["custom_body"] = kwargs["custom_body"]
            if kwargs.get("custom_subject"):
                options_kwargs["custom_subject"] = kwargs["custom_subject"]
            if "muted" in kwargs:
                options_kwargs["muted"] = kwargs["muted"]
            if "empty_result_state" in kwargs:
                options_kwargs["empty_result_state"] = AlertOptionsEmptyResultState(
                    kwargs["empty_result_state"]
                )

            options = AlertOptions(**options_kwargs)

            # Build alert
            alert_kwargs = {
                "name": name,
                "query_id": query_id,
                "options": options,
            }

            if "rearm" in kwargs:
                alert_kwargs["rearm"] = kwargs["rearm"]

            # Handle parent folder
            if "parent" in kwargs:
                parent_path = kwargs["parent"]
                if parent_path.startswith("folders/"):
                    alert_kwargs["parent"] = parent_path
                else:
                    # Resolve path to folder ID
                    parent_obj = client.workspace.get_status(path=parent_path)
                    if parent_obj.object_type == ObjectType.DIRECTORY:
                        alert_kwargs["parent"] = f"folders/{parent_obj.object_id}"
                    else:
                        raise ValueError(f"parent path is not a folder: {parent_path}")

            result = client.alerts.create(**alert_kwargs)
            return result.as_dict()

        try:
            alert_data = await asyncio.to_thread(sync_create_alert)

            return {
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_CREATE_ALERT_SUCCESS,
                "data": alert_data,
            }

        except ValueError as e:
            return {
                "status": consts.STATUS_ERROR,
                "error": str(e),
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }
        except Exception as e:
            logger.error("failed_to_create_alert", error=str(e))
            return {
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_CREATE_ALERT_ERROR}: {e!s}",
                "error_type": type(e).__name__,
            }

class DeleteAlertAction(IntegrationAction):
    """Delete a Databricks SQL alert."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Delete a SQL alert.

        Args:
            **kwargs: Must contain:
                - alert_id: Alert ID to delete

        Returns:
            Result with status or error
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        if not host or not ((username and password) or token):
            return {
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
            }

        alert_id = kwargs.get("alert_id")
        if not alert_id:
            return {
                "status": consts.STATUS_ERROR,
                "error": "Missing required parameter: alert_id",
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }

        def sync_delete_alert():
            """Synchronous delete alert operation."""
            client = _get_databricks_client(host, username, password, token)
            client.alerts.delete(alert_id)

        try:
            await asyncio.to_thread(sync_delete_alert)

            return {
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_DELETE_ALERT_SUCCESS,
                "data": {"alert_id": alert_id},
            }

        except Exception as e:
            logger.error("failed_to_delete_alert", error=str(e))
            return {
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_DELETE_ALERT_ERROR}: {e!s}",
                "error_type": type(e).__name__,
            }

class ListClustersAction(IntegrationAction):
    """List all Databricks clusters."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all clusters in the workspace.

        Returns:
            Result with list of clusters or error
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        if not host or not ((username and password) or token):
            return {
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
            }

        def sync_list_clusters():
            """Synchronous list clusters operation."""
            client = _get_databricks_client(host, username, password, token)
            clusters = list(client.clusters.list())
            return [cluster.as_dict() for cluster in clusters]

        try:
            clusters = await asyncio.to_thread(sync_list_clusters)

            return {
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_LIST_CLUSTERS_SUCCESS,
                "data": {"clusters": clusters, "total_clusters": len(clusters)},
            }

        except Exception as e:
            logger.error("failed_to_list_clusters", error=str(e))
            return {
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_LIST_CLUSTERS_ERROR}: {e!s}",
                "error_type": type(e).__name__,
            }

class ListWarehousesAction(IntegrationAction):
    """List all SQL warehouses."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all SQL warehouses in the workspace.

        Returns:
            Result with list of warehouses or error
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        if not host or not ((username and password) or token):
            return {
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
            }

        def sync_list_warehouses():
            """Synchronous list warehouses operation."""
            client = _get_databricks_client(host, username, password, token)
            warehouses = list(client.warehouses.list())
            return [warehouse.as_dict() for warehouse in warehouses]

        try:
            warehouses = await asyncio.to_thread(sync_list_warehouses)

            return {
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_LIST_WAREHOUSES_SUCCESS,
                "data": {"warehouses": warehouses, "total_warehouses": len(warehouses)},
            }

        except Exception as e:
            logger.error("failed_to_list_warehouses", error=str(e))
            return {
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_LIST_WAREHOUSES_ERROR}: {e!s}",
                "error_type": type(e).__name__,
            }

class PerformQueryAction(IntegrationAction):
    """Execute a SQL query."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute a SQL query on a warehouse.

        Args:
            **kwargs: Must contain:
                - statement: SQL statement to execute
                - warehouse_id: SQL warehouse ID
                Optional:
                - wait_timeout: Wait timeout in seconds (0 for async)
                - on_wait_timeout: Action on timeout (CONTINUE or CANCEL)
                - byte_limit: Result size limit in bytes
                - catalog: Catalog name
                - schema: Schema name
                - format: Result format (JSON_ARRAY, ARROW_STREAM, CSV)
                - disposition: Result disposition (INLINE or EXTERNAL_LINKS)

        Returns:
            Result with query execution details or error
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        if not host or not ((username and password) or token):
            return {
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
            }

        # Validate required parameters
        statement = kwargs.get("statement")
        warehouse_id = kwargs.get("warehouse_id")

        if not statement or not warehouse_id:
            return {
                "status": consts.STATUS_ERROR,
                "error": "Missing required parameters: statement, warehouse_id",
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }

        def sync_execute_query():
            """Synchronous query execution."""
            client = _get_databricks_client(host, username, password, token)

            data = {
                "statement": statement,
                "warehouse_id": warehouse_id,
            }

            # Add optional parameters
            if "wait_timeout" in kwargs:
                data["wait_timeout"] = f"{kwargs['wait_timeout']}s"

                # on_wait_timeout only valid for synchronous calls
                if kwargs["wait_timeout"] != 0 and "on_wait_timeout" in kwargs:
                    data["on_wait_timeout"] = ExecuteStatementRequestOnWaitTimeout[
                        kwargs["on_wait_timeout"]
                    ]

            if "byte_limit" in kwargs:
                data["byte_limit"] = kwargs["byte_limit"]
            if "catalog" in kwargs:
                data["catalog"] = kwargs["catalog"]
            if "schema" in kwargs:
                data["schema"] = kwargs["schema"]

            # Set format (default to JSON_ARRAY)
            result_format = kwargs.get("format", "JSON_ARRAY")
            data["format"] = Format[result_format]

            # Set disposition (default to INLINE)
            disposition = kwargs.get("disposition", "INLINE")
            data["disposition"] = Disposition[disposition]

            result = client.statement_execution.execute_statement(**data)
            return result.as_dict()

        try:
            result_data = await asyncio.to_thread(sync_execute_query)

            return {
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_PERFORM_QUERY_SUCCESS,
                "data": result_data,
            }

        except Exception as e:
            logger.error("failed_to_execute_query", error=str(e))
            return {
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_PERFORM_QUERY_ERROR}: {e!s}",
                "error_type": type(e).__name__,
            }

class GetQueryStatusAction(IntegrationAction):
    """Get the status of a SQL query."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get query execution status.

        Args:
            **kwargs: Must contain:
                - statement_id: Statement ID to check

        Returns:
            Result with query status or error
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        if not host or not ((username and password) or token):
            return {
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
            }

        statement_id = kwargs.get("statement_id")
        if not statement_id:
            return {
                "status": consts.STATUS_ERROR,
                "error": "Missing required parameter: statement_id",
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }

        def sync_get_query_status():
            """Synchronous get query status operation."""
            client = _get_databricks_client(host, username, password, token)
            result = client.statement_execution.get_statement(statement_id)
            return result.as_dict()

        try:
            status_data = await asyncio.to_thread(sync_get_query_status)

            return {
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_GET_QUERY_STATUS_SUCCESS,
                "data": status_data,
            }

        except Exception as e:
            logger.error("failed_to_get_query_status", error=str(e))
            return {
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_GET_QUERY_STATUS_ERROR}: {e!s}",
                "error_type": type(e).__name__,
            }

class CancelQueryAction(IntegrationAction):
    """Cancel a running SQL query."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Cancel query execution.

        Args:
            **kwargs: Must contain:
                - statement_id: Statement ID to cancel

        Returns:
            Result with cancellation status or error
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        if not host or not ((username and password) or token):
            return {
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
            }

        statement_id = kwargs.get("statement_id")
        if not statement_id:
            return {
                "status": consts.STATUS_ERROR,
                "error": "Missing required parameter: statement_id",
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }

        def sync_cancel_query():
            """Synchronous cancel query operation."""
            client = _get_databricks_client(host, username, password, token)
            client.statement_execution.cancel_execution(statement_id)

        try:
            await asyncio.to_thread(sync_cancel_query)

            return {
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_CANCEL_QUERY_SUCCESS,
                "data": {"statement_id": statement_id},
            }

        except Exception as e:
            logger.error("failed_to_cancel_query", error=str(e))
            return {
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_CANCEL_QUERY_ERROR}: {e!s}",
                "error_type": type(e).__name__,
            }

class GetJobRunAction(IntegrationAction):
    """Get details of a job run."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get job run details.

        Args:
            **kwargs: Must contain:
                - run_id: Job run ID

        Returns:
            Result with job run details or error
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        if not host or not ((username and password) or token):
            return {
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
            }

        run_id = kwargs.get("run_id")
        if not run_id:
            return {
                "status": consts.STATUS_ERROR,
                "error": "Missing required parameter: run_id",
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }

        def sync_get_job_run():
            """Synchronous get job run operation."""
            client = _get_databricks_client(host, username, password, token)
            result = client.jobs.get_run(run_id)
            return result.as_dict()

        try:
            run_data = await asyncio.to_thread(sync_get_job_run)

            return {
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_GET_JOB_RUN_SUCCESS,
                "data": run_data,
            }

        except Exception as e:
            logger.error("failed_to_get_job_run", error=str(e))
            return {
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_GET_JOB_RUN_ERROR}: {e!s}",
                "error_type": type(e).__name__,
            }

class GetJobOutputAction(IntegrationAction):
    """Get output of a job run."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get job run output.

        Args:
            **kwargs: Must contain:
                - run_id: Job run ID

        Returns:
            Result with job outputs or error
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        if not host or not ((username and password) or token):
            return {
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
            }

        run_id = kwargs.get("run_id")
        if not run_id:
            return {
                "status": consts.STATUS_ERROR,
                "error": "Missing required parameter: run_id",
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }

        def sync_get_job_output():
            """Synchronous get job output operation."""
            client = _get_databricks_client(host, username, password, token)

            # Get job run first
            job_run = client.jobs.get_run(run_id)

            if job_run.tasks is None:
                raise ValueError("This job run contains no task runs")

            # Get output for each task
            outputs = []
            for task_run in job_run.tasks:
                if task_run.run_id is not None:
                    task_output = client.jobs.get_run_output(task_run.run_id)
                    outputs.append(task_output.as_dict())

            return outputs

        try:
            outputs = await asyncio.to_thread(sync_get_job_output)

            return {
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_GET_JOB_OUTPUT_SUCCESS,
                "data": {"outputs": outputs, "total_outputs": len(outputs)},
            }

        except ValueError as e:
            return {
                "status": consts.STATUS_ERROR,
                "error": str(e),
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }
        except Exception as e:
            logger.error("failed_to_get_job_output", error=str(e))
            return {
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_GET_JOB_OUTPUT_ERROR}: {e!s}",
                "error_type": type(e).__name__,
            }

class ExecuteNotebookAction(IntegrationAction):
    """Execute a Databricks notebook."""

    async def execute(self, **kwargs) -> dict[str, Any]:  # noqa: C901
        """Execute a notebook.

        Args:
            **kwargs: Must contain:
                - notebook_path: Path to notebook
                One of:
                - new_cluster: JSON string of ClusterSpec
                - existing_cluster_id: ID of existing cluster
                Optional:
                - libraries: JSON array of Library specs
                - git_source: JSON object of GitSource
                - access_control_list: JSON array of AccessControlRequest
                - timeout_seconds: Job timeout
                - run_name: Name for the run
                - idempotency_token: Token for idempotent submission

        Returns:
            Result with execution details or error
        """
        # Extract credentials
        host = self.settings.get(consts.SETTINGS_HOST)
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        token = self.credentials.get(consts.CREDENTIAL_TOKEN)

        if not host or not ((username and password) or token):
            return {
                "status": consts.STATUS_ERROR,
                "error": consts.MSG_MISSING_CREDENTIALS,
                "error_type": consts.ERROR_TYPE_CONFIGURATION,
            }

        # Validate required parameters
        notebook_path = kwargs.get("notebook_path")
        if not notebook_path:
            return {
                "status": consts.STATUS_ERROR,
                "error": "Missing required parameter: notebook_path",
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }

        if not kwargs.get("new_cluster") and not kwargs.get("existing_cluster_id"):
            return {
                "status": consts.STATUS_ERROR,
                "error": "Must provide either new_cluster or existing_cluster_id",
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }

        def sync_execute_notebook():
            """Synchronous execute notebook operation."""
            client = _get_databricks_client(host, username, password, token)

            # Build task
            task_info = SubmitTask(
                task_key="naxos_execute_notebook_action",
                notebook_task=NotebookTask(notebook_path=notebook_path),
            )

            if "new_cluster" in kwargs:
                cluster_json = json.loads(kwargs["new_cluster"])
                task_info.new_cluster = ClusterSpec.from_dict(cluster_json)

            if "existing_cluster_id" in kwargs:
                task_info.existing_cluster_id = kwargs["existing_cluster_id"]

            if "libraries" in kwargs:
                libraries_json = json.loads(kwargs["libraries"])
                task_info.libraries = [Library.from_dict(d) for d in libraries_json]

            # Build run info
            run_info: dict[str, Any] = {"tasks": [task_info]}

            if "git_source" in kwargs:
                git_json = json.loads(kwargs["git_source"])
                run_info["git_source"] = GitSource.from_dict(git_json)

            if "access_control_list" in kwargs:
                acl_json = json.loads(kwargs["access_control_list"])
                run_info["access_control_list"] = [
                    AccessControlRequest.from_dict(d) for d in acl_json
                ]

            if "timeout_seconds" in kwargs:
                run_info["timeout_seconds"] = kwargs["timeout_seconds"]
            if "run_name" in kwargs:
                run_info["run_name"] = kwargs["run_name"]
            if "idempotency_token" in kwargs:
                run_info["idempotency_token"] = kwargs["idempotency_token"]

            # Submit and wait for result
            submitted_run = client.jobs.submit(**run_info)

            # Wait for completion
            result = submitted_run.result()

            # Check result state
            if result.state and result.state.result_state == RunResultState.FAILED:
                raise Exception(
                    f"Notebook execution failed: {result.state.state_message}"
                )

            return result.as_dict()

        try:
            result_data = await asyncio.to_thread(sync_execute_notebook)

            return {
                "status": consts.STATUS_SUCCESS,
                "message": consts.MSG_EXECUTE_NOTEBOOK_SUCCESS,
                "data": result_data,
            }

        except json.JSONDecodeError as e:
            return {
                "status": consts.STATUS_ERROR,
                "error": f"Invalid JSON in parameter: {e!s}",
                "error_type": consts.ERROR_TYPE_VALIDATION,
            }
        except Exception as e:
            logger.error("failed_to_execute_notebook", error=str(e))
            return {
                "status": consts.STATUS_ERROR,
                "error": f"{consts.MSG_EXECUTE_NOTEBOOK_ERROR}: {e!s}",
                "error_type": type(e).__name__,
            }

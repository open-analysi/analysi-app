"""BigQuery integration actions for data warehouse operations."""

import asyncio
import json
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from google.cloud import bigquery
from google.oauth2 import service_account

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    DEFAULT_TIMEOUT,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_QUERY_ERROR,
    ERROR_TYPE_VALIDATION,
    MSG_HEALTH_CHECK_SUCCESS,
    MSG_INVALID_TIMEOUT,
    MSG_LIST_TABLES_SUCCESS,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_JOB_ID,
    MSG_MISSING_QUERY,
    MSG_QUERY_SUCCESS,
    MSG_QUERY_TIMEOUT,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# ============================================================================
# CLIENT CREATION HELPER
# ============================================================================

def _create_bigquery_client(
    service_account_json: str, project_id: str | None = None
) -> bigquery.Client:
    """Create BigQuery client from service account JSON.

    Args:
        service_account_json: JSON string containing service account credentials
        project_id: Optional project ID override (uses service account's project if not provided)

    Returns:
        Configured BigQuery client

    Raises:
        ValueError: If service account JSON is invalid
        Exception: If client creation fails
    """
    try:
        service_account_info = json.loads(service_account_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid service account JSON: {e}")

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info
    )

    # Use provided project_id or extract from service account
    effective_project_id = project_id or service_account_info.get("project_id")
    if not effective_project_id:
        raise ValueError("No project_id found in service account JSON or settings")

    client = bigquery.Client(project=effective_project_id, credentials=credentials)
    return client

def _validate_timeout(timeout: Any) -> tuple[bool, str, int | None]:
    """Validate timeout parameter.

    Args:
        timeout: Timeout value to validate

    Returns:
        Tuple of (is_valid, error_message, validated_timeout)
    """
    if timeout is None:
        return True, "", None

    try:
        timeout_int = int(timeout)
        if timeout_int <= 0:
            return False, MSG_INVALID_TIMEOUT, None
        return True, "", timeout_int
    except (ValueError, TypeError):
        return False, MSG_INVALID_TIMEOUT, None

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for BigQuery API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check BigQuery API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        service_account_json = self.credentials.get("service_account_json")
        if not service_account_json:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        project_id = self.settings.get("project_id")

        def sync_health_check():
            """Synchronous health check operation."""
            try:
                client = _create_bigquery_client(service_account_json, project_id)
                # Try to list datasets as health check
                list(client.list_datasets(max_results=1))
                return {"healthy": True, "message": MSG_HEALTH_CHECK_SUCCESS}
            except Exception as e:
                logger.error("bigquery_health_check_failed", error=str(e))
                raise

        try:
            result = await asyncio.to_thread(sync_health_check)
            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": result["message"],
                "data": {"healthy": result["healthy"]},
            }
        except ValueError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_AUTHENTICATION,
                "data": {"healthy": False},
            }

class ListTablesAction(IntegrationAction):
    """List tables in BigQuery datasets."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List tables in BigQuery.

        Args:
            **kwargs: May contain 'dataset' to filter to specific dataset

        Returns:
            Result with list of tables or error
        """
        service_account_json = self.credentials.get("service_account_json")
        if not service_account_json:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        project_id = self.settings.get("project_id")
        dataset = kwargs.get("dataset")

        def sync_list_tables():
            """Synchronous table listing operation."""
            client = _create_bigquery_client(service_account_json, project_id)

            tables = []

            # If dataset specified, only list tables from that dataset
            if dataset:
                dataset_ref = client.dataset(dataset)
                dataset_ref_list = [dataset_ref]
            else:
                # List all datasets and their tables
                dataset_ref_list = [x.reference for x in client.list_datasets()]

            # Iterate through datasets and collect tables
            for dataset_ref in dataset_ref_list:
                for table in client.list_tables(dataset_ref):
                    tables.append(
                        {
                            "table_id": table.table_id,
                            "dataset_id": dataset_ref.dataset_id,
                            "project_id": dataset_ref.project,
                            "full_table_id": table.full_table_id,
                        }
                    )

            return tables

        try:
            tables = await asyncio.to_thread(sync_list_tables)

            return {
                "status": STATUS_SUCCESS,
                "message": MSG_LIST_TABLES_SUCCESS,
                "data": {"tables": tables, "total_tables": len(tables)},
            }

        except ValueError as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_CONFIGURATION,
            }
        except Exception as e:
            logger.error("bigquery_list_tables_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_QUERY_ERROR,
            }

class RunQueryAction(IntegrationAction):
    """Run a SQL query in BigQuery."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Run a SQL query in BigQuery.

        Args:
            **kwargs: Must contain 'query', may contain 'timeout' (in seconds)

        Returns:
            Result with query results or error
        """
        # Validate required parameters
        query = kwargs.get("query")
        if not query:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_QUERY,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate timeout parameter
        timeout = kwargs.get("timeout")
        is_valid, error_msg, validated_timeout = _validate_timeout(timeout)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        service_account_json = self.credentials.get("service_account_json")
        if not service_account_json:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        project_id = self.settings.get("project_id")
        default_timeout = self.settings.get("default_timeout", DEFAULT_TIMEOUT)
        effective_timeout = (
            validated_timeout if validated_timeout is not None else default_timeout
        )

        def sync_run_query():
            """Synchronous query execution operation."""
            client = _create_bigquery_client(service_account_json, project_id)

            # Start query job
            query_job = client.query(query)

            # Wait for results with timeout
            try:
                result = query_job.result(timeout=effective_timeout)
            except FuturesTimeoutError:
                # Query timed out, return job ID for later retrieval
                return {
                    "timed_out": True,
                    "job_id": query_job.job_id,
                    "message": MSG_QUERY_TIMEOUT,
                }

            # Convert results to list of dicts
            rows = [dict(row) for row in result]

            return {
                "timed_out": False,
                "job_id": query_job.job_id,
                "rows": rows,
                "num_rows": len(rows),
            }

        try:
            result = await asyncio.to_thread(sync_run_query)

            if result["timed_out"]:
                return {
                    "status": STATUS_SUCCESS,
                    "message": result["message"],
                    "data": {"job_id": result["job_id"], "timed_out": True},
                }

            return {
                "status": STATUS_SUCCESS,
                "message": MSG_QUERY_SUCCESS,
                "data": {
                    "job_id": result["job_id"],
                    "rows": result["rows"],
                    "num_rows": result["num_rows"],
                },
            }

        except ValueError as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_CONFIGURATION,
            }
        except Exception as e:
            logger.error("bigquery_query_execution_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_QUERY_ERROR,
            }

class GetResultsAction(IntegrationAction):
    """Get results from a previously started query job."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get results from a BigQuery job.

        Args:
            **kwargs: Must contain 'job_id', may contain 'timeout' (in seconds)

        Returns:
            Result with query results or error
        """
        # Validate required parameters
        job_id = kwargs.get("job_id")
        if not job_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_JOB_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate timeout parameter
        timeout = kwargs.get("timeout")
        is_valid, error_msg, validated_timeout = _validate_timeout(timeout)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        service_account_json = self.credentials.get("service_account_json")
        if not service_account_json:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        project_id = self.settings.get("project_id")
        default_timeout = self.settings.get("default_timeout", DEFAULT_TIMEOUT)
        effective_timeout = (
            validated_timeout if validated_timeout is not None else default_timeout
        )

        def sync_get_results():
            """Synchronous result retrieval operation."""
            client = _create_bigquery_client(service_account_json, project_id)

            # Get the job
            query_job = client.get_job(job_id)

            # Wait for results with timeout
            try:
                result = query_job.result(timeout=effective_timeout)
            except FuturesTimeoutError:
                return {
                    "timed_out": True,
                    "job_id": query_job.job_id,
                    "message": MSG_QUERY_TIMEOUT,
                }

            # Convert results to list of dicts
            rows = [dict(row) for row in result]

            return {
                "timed_out": False,
                "job_id": query_job.job_id,
                "rows": rows,
                "num_rows": len(rows),
            }

        try:
            result = await asyncio.to_thread(sync_get_results)

            if result["timed_out"]:
                return {
                    "status": STATUS_SUCCESS,
                    "message": result["message"],
                    "data": {"job_id": result["job_id"], "timed_out": True},
                }

            return {
                "status": STATUS_SUCCESS,
                "message": MSG_QUERY_SUCCESS,
                "data": {
                    "job_id": result["job_id"],
                    "rows": result["rows"],
                    "num_rows": result["num_rows"],
                },
            }

        except ValueError as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_CONFIGURATION,
            }
        except Exception as e:
            logger.error(
                "bigquery_result_retrieval_failed_for_job", job_id=job_id, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_QUERY_ERROR,
            }

"""Cisco Secure Endpoint integration actions for EDR operations.
(formerly AMP for Endpoints) REST API v1 with HTTP Basic Auth
(client_id:api_key).
"""

import base64
from typing import Any
from uuid import UUID

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_VERSION,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MSG_CONNECTOR_GUID_VALIDATION_FAILED,
    MSG_ENDPOINT_NOT_FOUND,
    MSG_MISSING_CREDENTIALS,
)

logger = get_logger(__name__)

def _build_base_url(settings: dict[str, Any]) -> str:
    """Build the API base URL from settings."""
    base = settings.get("base_url", DEFAULT_BASE_URL)
    return base.rstrip("/")

def _build_auth_header(credentials: dict[str, Any]) -> dict[str, str]:
    """Build HTTP Basic Auth header from client_id and api_key."""
    client_id = credentials.get("api_client_id", "")
    api_key = credentials.get("api_key", "")
    auth_string = f"{client_id}:{api_key}"
    encoded = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def _validate_uuid4(value: str | None) -> bool:
    """Validate that a string is a valid UUID v4."""
    if value is None:
        return False
    try:
        UUID(value, version=4)
        return True
    except (ValueError, AttributeError, TypeError):
        return False

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Cisco Secure Endpoint API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check API connectivity by calling the version endpoint.

        Returns:
            Result with status=success if healthy, status=error if unhealthy.
        """
        client_id = self.credentials.get("api_client_id")
        api_key = self.credentials.get("api_key")

        if not client_id or not api_key:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url = _build_base_url(self.settings)
        headers = _build_auth_header(self.credentials)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                url=f"{base_url}/{API_VERSION}/version",
                headers=headers,
                timeout=timeout,
            )
            version_data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "api_version": version_data.get("version", API_VERSION),
                },
            )
        except Exception as e:
            logger.error("ciscosecureendpoint_health_check_failed", error=str(e))
            return self.error_result(e)

class IsolateHostAction(IntegrationAction):
    """Isolate (quarantine) a device by connector GUID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Start host isolation on the specified endpoint.

        Args:
            **kwargs: Must contain 'connector_guid'.

        Returns:
            Result with isolation status data.
        """
        connector_guid = kwargs.get("connector_guid")
        if not connector_guid:
            return self.error_result(
                "Missing required parameter: connector_guid",
                error_type=ERROR_TYPE_VALIDATION,
            )

        if not _validate_uuid4(connector_guid):
            return self.error_result(
                MSG_CONNECTOR_GUID_VALIDATION_FAILED,
                error_type=ERROR_TYPE_VALIDATION,
            )

        client_id = self.credentials.get("api_client_id")
        api_key = self.credentials.get("api_key")
        if not client_id or not api_key:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url = _build_base_url(self.settings)
        headers = _build_auth_header(self.credentials)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                url=f"{base_url}/{API_VERSION}/computers/{connector_guid}/isolation",
                method="PUT",
                headers=headers,
                timeout=timeout,
            )
            resp_data = response.json()

            return self.success_result(
                data=resp_data,
                message=f"Isolation started on {connector_guid}",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "ciscosecureendpoint_isolate_host_not_found",
                    connector_guid=connector_guid,
                )
                return self.success_result(
                    not_found=True,
                    data={"connector_guid": connector_guid},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class UnisolateHostAction(IntegrationAction):
    """Release a device from isolation by connector GUID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Stop host isolation on the specified endpoint.

        Args:
            **kwargs: Must contain 'connector_guid'.

        Returns:
            Result with isolation status data.
        """
        connector_guid = kwargs.get("connector_guid")
        if not connector_guid:
            return self.error_result(
                "Missing required parameter: connector_guid",
                error_type=ERROR_TYPE_VALIDATION,
            )

        if not _validate_uuid4(connector_guid):
            return self.error_result(
                MSG_CONNECTOR_GUID_VALIDATION_FAILED,
                error_type=ERROR_TYPE_VALIDATION,
            )

        client_id = self.credentials.get("api_client_id")
        api_key = self.credentials.get("api_key")
        if not client_id or not api_key:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url = _build_base_url(self.settings)
        headers = _build_auth_header(self.credentials)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                url=f"{base_url}/{API_VERSION}/computers/{connector_guid}/isolation",
                method="DELETE",
                headers=headers,
                timeout=timeout,
            )
            resp_data = response.json()

            return self.success_result(
                data=resp_data,
                message=f"Isolation stopped on {connector_guid}",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "ciscosecureendpoint_unisolate_host_not_found",
                    connector_guid=connector_guid,
                )
                return self.success_result(
                    not_found=True,
                    data={"connector_guid": connector_guid},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class GetComputerAction(IntegrationAction):
    """Get information about a device by connector GUID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve device info from the Cisco Secure Endpoint API.

        Args:
            **kwargs: Must contain 'connector_guid'.

        Returns:
            Result with device information.
        """
        connector_guid = kwargs.get("connector_guid")
        if not connector_guid:
            return self.error_result(
                "Missing required parameter: connector_guid",
                error_type=ERROR_TYPE_VALIDATION,
            )

        if not _validate_uuid4(connector_guid):
            return self.error_result(
                MSG_CONNECTOR_GUID_VALIDATION_FAILED,
                error_type=ERROR_TYPE_VALIDATION,
            )

        client_id = self.credentials.get("api_client_id")
        api_key = self.credentials.get("api_key")
        if not client_id or not api_key:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url = _build_base_url(self.settings)
        headers = _build_auth_header(self.credentials)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                url=f"{base_url}/{API_VERSION}/computers/{connector_guid}",
                headers=headers,
                timeout=timeout,
            )
            resp_data = response.json()

            return self.success_result(data=resp_data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "ciscosecureendpoint_get_computer_not_found",
                    connector_guid=connector_guid,
                )
                return self.success_result(
                    not_found=True,
                    data={"connector_guid": connector_guid},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListEventsAction(IntegrationAction):
    """Retrieve device events from Cisco Secure Endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve events, optionally filtered by various parameters.

        Args:
            **kwargs: Optional filters: connector_guid, detection_sha256,
                application_sha256, group_guid, start_date, offset,
                event_type, limit.

        Returns:
            Result with events list.
        """
        client_id = self.credentials.get("api_client_id")
        api_key = self.credentials.get("api_key")
        if not client_id or not api_key:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        # Build query params from optional filters
        param_names = [
            "connector_guid",
            "detection_sha256",
            "application_sha256",
            "group_guid",
            "start_date",
            "offset",
            "event_type",
            "limit",
        ]
        query_params = {}
        for name in param_names:
            value = kwargs.get(name)
            if value is not None:
                query_params[name] = value

        base_url = _build_base_url(self.settings)
        headers = _build_auth_header(self.credentials)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                url=f"{base_url}/{API_VERSION}/events",
                headers=headers,
                params=query_params,
                timeout=timeout,
            )
            resp_data = response.json()

            # Reshape to match upstream output: events at top level
            events = resp_data.get("data", [])
            result_data = {
                "events": events,
                "total_events": len(events),
                "metadata": resp_data.get("metadata", {}),
            }

            return self.success_result(data=result_data)
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class GetFileAnalysisAction(IntegrationAction):
    """Hunt for a file hash across all endpoints.

    Searches the /v1/computers/activity endpoint to find endpoints that
    have observed the specified file hash, then optionally checks file
    execution via trajectory data.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search for endpoints that have seen a file hash.

        Args:
            **kwargs: Must contain 'hash'. Optional 'check_execution' (bool).

        Returns:
            Result with list of endpoints and activity details.
        """
        file_hash = kwargs.get("hash")
        if not file_hash:
            return self.error_result(
                "Missing required parameter: hash",
                error_type=ERROR_TYPE_VALIDATION,
            )

        client_id = self.credentials.get("api_client_id")
        api_key = self.credentials.get("api_key")
        if not client_id or not api_key:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        check_execution = kwargs.get("check_execution", False)

        base_url = _build_base_url(self.settings)
        headers = _build_auth_header(self.credentials)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            # Search for endpoints that have seen this hash
            response = await self.http_request(
                url=f"{base_url}/{API_VERSION}/computers/activity",
                headers=headers,
                params={"q": file_hash},
                timeout=timeout,
            )
            resp_data = response.json()

            if isinstance(resp_data, str) and resp_data == MSG_ENDPOINT_NOT_FOUND:
                return self.success_result(
                    not_found=True,
                    data={"hash": file_hash, "device_count": 0},
                )

            endpoints = resp_data.get("data", [])

            # Optionally check file execution on each endpoint
            if check_execution and endpoints:
                endpoints = await self._check_file_execution(
                    endpoints, file_hash, base_url, headers, timeout
                )

            result_data = {
                "hash": file_hash,
                "device_count": len(endpoints),
                "endpoints": endpoints,
                "metadata": resp_data.get("metadata", {}),
            }

            return self.success_result(data=result_data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "ciscosecureendpoint_get_file_analysis_not_found",
                    hash=file_hash,
                )
                return self.success_result(
                    not_found=True,
                    data={"hash": file_hash, "device_count": 0},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

    async def _check_file_execution(
        self,
        endpoints: list[dict],
        file_hash: str,
        base_url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> list[dict]:
        """Check if the file was actually executed on each endpoint.

        Queries the trajectory endpoint for each discovered endpoint to
        determine if the file hash was observed in an 'Executed by' event.
        """
        for endpoint in endpoints:
            guid = endpoint.get("connector_guid")
            if not guid:
                continue

            execution_details = {
                "executed": False,
                "file_name": "",
                "file_path": "",
                "message": "",
            }

            try:
                traj_response = await self.http_request(
                    url=f"{base_url}/{API_VERSION}/computers/{guid}/trajectory",
                    headers=headers,
                    params={"q": file_hash},
                    timeout=timeout,
                )
                traj_data = traj_response.json()
                events = traj_data.get("data", {}).get("events") or []

                for event in events:
                    event_type = event.get("event_type")
                    file_info = event.get("file", {})
                    identity = file_info.get("identity", {})
                    if event_type == "Executed by" and file_hash == identity.get(
                        "sha256"
                    ):
                        execution_details["executed"] = True
                        execution_details["file_name"] = file_info.get("file_name", "")
                        execution_details["file_path"] = file_info.get("file_path", "")
                        execution_details["message"] = "File executed"
                        break

                if not execution_details["message"]:
                    execution_details["message"] = "File not executed"

            except Exception as e:
                execution_details["message"] = (
                    f"Unable to retrieve execution details: {e}"
                )

            endpoint["file_execution_details"] = execution_details

        return endpoints

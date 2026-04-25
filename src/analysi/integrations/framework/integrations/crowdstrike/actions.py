"""
CrowdStrike Falcon EDR integration actions.
Uses OAuth2 client credentials flow for authentication.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.crowdstrike.constants import (
    ACTION_CONTAIN,
    ACTION_LIFT_CONTAINMENT,
    ALERT_PAGE_SIZE,
    CREDENTIAL_CLIENT_ID,
    CREDENTIAL_CLIENT_SECRET,
    DEFAULT_LIMIT,
    DEFAULT_LOOKBACK_MINUTES,
    DEFAULT_MAX_ALERTS,
    DEFAULT_TIMEOUT,
    DETONATE_RESOURCE_ENDPOINT,
    DEVICE_ACTION_ENDPOINT,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_NOT_FOUND,
    ERROR_TYPE_VALIDATION,
    GET_ALERT_DETAILS_ENDPOINT,
    GET_COMBINED_CUSTOM_INDICATORS_ENDPOINT,
    GET_DEVICE_DETAILS_ENDPOINT,
    GET_DEVICE_ID_ENDPOINT,
    GET_EXTRACTED_RTR_FILE_ENDPOINT,
    GET_HOST_GROUP_DETAILS_ENDPOINT,
    GET_HOST_GROUP_ID_ENDPOINT,
    GET_INCIDENT_DETAILS_ENDPOINT,
    GET_INDICATOR_ENDPOINT,
    GET_PROCESSES_RAN_ON_ENDPOINT,
    GET_REPORT_SUMMARY_ENDPOINT,
    GET_RTR_SESSION_DETAILS_ENDPOINT,
    GET_RTR_SESSION_ID_ENDPOINT,
    GROUP_DEVICE_ACTION_ENDPOINT,
    LIST_ALERTS_ENDPOINT,
    LIST_DETECTIONS_DETAILS_ENDPOINT,
    LIST_DETECTIONS_ENDPOINT,
    LIST_INCIDENTS_ENDPOINT,
    MAX_BATCH_SIZE,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAMETER,
    OAUTH_TOKEN_ENDPOINT,
    RESOLVE_DETECTION_ENDPOINT,
    RTR_SESSION_ENDPOINT,
    RUN_COMMAND_ENDPOINT,
    SETTINGS_BASE_URL,
    SETTINGS_DEFAULT_LOOKBACK,
    SETTINGS_TIMEOUT,
    STATUS_ERROR,
    STATUS_SUCCESS,
    UPDATE_INCIDENT_ENDPOINT,
)

logger = get_logger(__name__)

class CrowdStrikeOAuth2Mixin:
    """Mixin to handle OAuth2 token management for CrowdStrike API."""

    _access_token: str | None = None

    async def _get_access_token(self) -> str:
        """Get or refresh OAuth2 access token.

        Returns:
            Access token string

        Raises:
            Exception if authentication fails
        """
        if self._access_token:
            return self._access_token

        base_url = self.settings.get(SETTINGS_BASE_URL, "https://api.crowdstrike.com")
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([base_url, client_id, client_secret]):
            raise ValueError(MSG_MISSING_CREDENTIALS)

        url = f"{base_url.rstrip('/')}{OAUTH_TOKEN_ENDPOINT}"
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        response = await self.http_request(
            url,
            method="POST",
            data=data,
            headers=headers,
            timeout=timeout,
        )
        token_data = response.json()
        self._access_token = token_data.get("access_token")

        if not self._access_token:
            raise ValueError("No access token in response")

        return self._access_token

    async def _make_api_request(
        self,
        endpoint: str,
        method: str = "get",
        params: dict | None = None,
        json_data: dict | None = None,
        data: dict | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Make authenticated API request to CrowdStrike.

        Args:
            endpoint: API endpoint path
            method: HTTP method
            params: Query parameters
            json_data: JSON body data
            data: Form data
            retry_auth: Whether to retry on auth failure

        Returns:
            Response JSON data
        """
        base_url = self.settings.get(SETTINGS_BASE_URL, "https://api.crowdstrike.com")
        url = f"{base_url.rstrip('/')}{endpoint}"

        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                url,
                method=method.upper(),
                params=params,
                json_data=json_data,
                data=data,
                headers=headers,
                timeout=timeout,
            )
        except httpx.HTTPStatusError as e:
            # Handle token expiration
            if e.response.status_code == 401 and retry_auth:
                self._access_token = None
                return await self._make_api_request(
                    endpoint, method, params, json_data, data, retry_auth=False
                )
            raise

        # Handle 204 No Content
        if response.status_code == 204:
            return {"status": "success"}

        return response.json()

class HealthCheckAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Check connectivity to CrowdStrike API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute health check.

        Returns:
            Health check result
        """
        try:
            # Try to get a token to verify credentials
            await self._get_access_token()

            # Try to query devices with limit=1 to test API connectivity
            response = await self._make_api_request(
                GET_DEVICE_ID_ENDPOINT,
                method="get",
                params={"limit": 1},
            )

            if response:
                return {
                    "healthy": True,
                    "status": STATUS_SUCCESS,
                    "message": "Successfully connected to CrowdStrike API",
                }

            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": "Unexpected response from API",
            }

        except httpx.HTTPStatusError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_AUTHENTICATION,
                "error": str(e),
            }

class QueryDeviceAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Query devices using FQL filter."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute device query.

        Args:
            filter: FQL filter string
            limit: Maximum number of results
            offset: Starting offset

        Returns:
            List of device IDs matching filter
        """
        try:
            filter_str = kwargs.get("filter")
            limit = kwargs.get("limit", DEFAULT_LIMIT)
            offset = kwargs.get("offset", 0)

            params = {}
            if filter_str:
                params["filter"] = filter_str
            if limit:
                params["limit"] = limit
            if offset:
                params["offset"] = offset

            response = await self._make_api_request(
                GET_DEVICE_ID_ENDPOINT,
                method="get",
                params=params,
            )

            device_ids = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "device_ids": device_ids,
                "count": len(device_ids),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_query_device_not_found", filter=kwargs.get("filter")
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "device_ids": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class GetDeviceDetailsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Get detailed information about devices."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute get device details.

        Args:
            device_ids: List of device IDs

        Returns:
            Device details
        """
        try:
            device_ids = kwargs.get("device_ids")
            if not device_ids:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("device_ids"),
                }

            if isinstance(device_ids, str):
                device_ids = [device_ids]

            params = {"ids": device_ids}

            response = await self._make_api_request(
                GET_DEVICE_DETAILS_ENDPOINT,
                method="get",
                params=params,
            )

            devices = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "devices": devices,
                "count": len(devices),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_get_device_details_not_found",
                    device_ids=kwargs.get("device_ids"),
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "devices": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class ListGroupsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """List host groups."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute list groups.

        Args:
            filter: FQL filter string
            limit: Maximum number of results

        Returns:
            List of host groups
        """
        try:
            filter_str = kwargs.get("filter")
            limit = kwargs.get("limit", DEFAULT_LIMIT)

            params = {}
            if filter_str:
                params["filter"] = filter_str
            if limit:
                params["limit"] = limit

            # Get group IDs
            response = await self._make_api_request(
                GET_HOST_GROUP_ID_ENDPOINT,
                method="get",
                params=params,
            )

            group_ids = response.get("resources", [])

            if not group_ids:
                return {
                    "status": STATUS_SUCCESS,
                    "groups": [],
                    "count": 0,
                }

            # Get group details
            response = await self._make_api_request(
                GET_HOST_GROUP_DETAILS_ENDPOINT,
                method="get",
                params={"ids": group_ids},
            )

            groups = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "groups": groups,
                "count": len(groups),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_list_groups_not_found", filter=kwargs.get("filter")
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "groups": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class QuarantineDeviceAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Quarantine (contain) a device."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute device quarantine.

        Args:
            device_id: Device ID to quarantine
            hostname: Hostname (alternative to device_id)

        Returns:
            Quarantine result
        """
        try:
            device_id = kwargs.get("device_id")
            hostname = kwargs.get("hostname")

            if not device_id and not hostname:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": "Either device_id or hostname must be provided",
                }

            # If hostname provided, resolve to device_id
            if hostname and not device_id:
                query_response = await self._make_api_request(
                    GET_DEVICE_ID_ENDPOINT,
                    method="get",
                    params={"filter": f"hostname:'{hostname}'"},
                )
                device_ids = query_response.get("resources", [])
                if not device_ids:
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_NOT_FOUND,
                        "error": f"Device not found: {hostname}",
                    }
                device_id = device_ids[0]

            # Perform containment action
            json_data = {
                "action_parameters": [{"name": "action_name", "value": ACTION_CONTAIN}],
                "ids": [device_id],
            }

            response = await self._make_api_request(
                DEVICE_ACTION_ENDPOINT,
                method="post",
                params={"action_name": ACTION_CONTAIN},
                json_data=json_data,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Device quarantined successfully",
                "device_id": device_id,
                "response": response,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class UnquarantineDeviceAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Unquarantine (lift containment) a device."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute device unquarantine.

        Args:
            device_id: Device ID to unquarantine
            hostname: Hostname (alternative to device_id)

        Returns:
            Unquarantine result
        """
        try:
            device_id = kwargs.get("device_id")
            hostname = kwargs.get("hostname")

            if not device_id and not hostname:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": "Either device_id or hostname must be provided",
                }

            # If hostname provided, resolve to device_id
            if hostname and not device_id:
                query_response = await self._make_api_request(
                    GET_DEVICE_ID_ENDPOINT,
                    method="get",
                    params={"filter": f"hostname:'{hostname}'"},
                )
                device_ids = query_response.get("resources", [])
                if not device_ids:
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_NOT_FOUND,
                        "error": f"Device not found: {hostname}",
                    }
                device_id = device_ids[0]

            # Perform lift containment action
            json_data = {
                "action_parameters": [
                    {"name": "action_name", "value": ACTION_LIFT_CONTAINMENT}
                ],
                "ids": [device_id],
            }

            response = await self._make_api_request(
                DEVICE_ACTION_ENDPOINT,
                method="post",
                params={"action_name": ACTION_LIFT_CONTAINMENT},
                json_data=json_data,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Device unquarantined successfully",
                "device_id": device_id,
                "response": response,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class AssignHostsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Assign hosts to a host group."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute assign hosts.

        Args:
            host_group_id: Host group ID
            device_ids: List of device IDs

        Returns:
            Assignment result
        """
        try:
            host_group_id = kwargs.get("host_group_id")
            device_ids = kwargs.get("device_ids")

            if not host_group_id:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("host_group_id"),
                }

            if not device_ids:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("device_ids"),
                }

            if isinstance(device_ids, str):
                device_ids = [device_ids]

            json_data = {"action": "add-hosts", "ids": device_ids}

            response = await self._make_api_request(
                f"{GROUP_DEVICE_ACTION_ENDPOINT}?action_name=add-hosts",
                method="post",
                params={"id": host_group_id},
                json_data=json_data,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Hosts assigned successfully",
                "host_group_id": host_group_id,
                "device_ids": device_ids,
                "response": response,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class RemoveHostsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Remove hosts from a host group."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute remove hosts.

        Args:
            host_group_id: Host group ID
            device_ids: List of device IDs

        Returns:
            Removal result
        """
        try:
            host_group_id = kwargs.get("host_group_id")
            device_ids = kwargs.get("device_ids")

            if not host_group_id:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("host_group_id"),
                }

            if not device_ids:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("device_ids"),
                }

            if isinstance(device_ids, str):
                device_ids = [device_ids]

            json_data = {"action": "remove-hosts", "ids": device_ids}

            response = await self._make_api_request(
                f"{GROUP_DEVICE_ACTION_ENDPOINT}?action_name=remove-hosts",
                method="post",
                params={"id": host_group_id},
                json_data=json_data,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Hosts removed successfully",
                "host_group_id": host_group_id,
                "device_ids": device_ids,
                "response": response,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class CreateSessionAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Create RTR (Real-Time Response) session."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute create session.

        Args:
            device_id: Device ID to create session with

        Returns:
            Session details
        """
        try:
            device_id = kwargs.get("device_id")

            if not device_id:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("device_id"),
                }

            json_data = {"device_id": device_id}

            response = await self._make_api_request(
                RTR_SESSION_ENDPOINT,
                method="post",
                json_data=json_data,
            )

            resources = response.get("resources", [])
            if resources:
                session = resources[0]
                return {
                    "status": STATUS_SUCCESS,
                    "session_id": session.get("session_id"),
                    "session": session,
                }

            return {
                "status": STATUS_ERROR,
                "error": "No session created",
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class DeleteSessionAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Delete RTR session."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute delete session.

        Args:
            session_id: Session ID to delete

        Returns:
            Deletion result
        """
        try:
            session_id = kwargs.get("session_id")

            if not session_id:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("session_id"),
                }

            await self._make_api_request(
                RTR_SESSION_ENDPOINT,
                method="delete",
                params={"session_id": session_id},
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Session deleted successfully",
                "session_id": session_id,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class ListDetectionsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """List detections."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute list detections.

        Args:
            filter: FQL filter string
            limit: Maximum number of results
            sort: Sort order

        Returns:
            List of detections
        """
        try:
            filter_str = kwargs.get("filter")
            limit = kwargs.get("limit", DEFAULT_LIMIT)
            sort = kwargs.get("sort")

            params = {}
            if filter_str:
                params["filter"] = filter_str
            if limit:
                params["limit"] = limit
            if sort:
                params["sort"] = sort

            # Get detection IDs
            response = await self._make_api_request(
                LIST_DETECTIONS_ENDPOINT,
                method="get",
                params=params,
            )

            detection_ids = response.get("resources", [])

            if not detection_ids:
                return {
                    "status": STATUS_SUCCESS,
                    "detections": [],
                    "count": 0,
                }

            # Get detection details
            json_data = {"ids": detection_ids}

            response = await self._make_api_request(
                LIST_DETECTIONS_DETAILS_ENDPOINT,
                method="post",
                json_data=json_data,
            )

            detections = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "detections": detections,
                "count": len(detections),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_list_detections_not_found", filter=kwargs.get("filter")
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "detections": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class GetDetectionDetailsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Get detection details."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute get detection details.

        Args:
            detection_ids: List of detection IDs

        Returns:
            Detection details
        """
        try:
            detection_ids = kwargs.get("detection_ids")

            if not detection_ids:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("detection_ids"),
                }

            if isinstance(detection_ids, str):
                detection_ids = [detection_ids]

            json_data = {"ids": detection_ids}

            response = await self._make_api_request(
                LIST_DETECTIONS_DETAILS_ENDPOINT,
                method="post",
                json_data=json_data,
            )

            detections = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "detections": detections,
                "count": len(detections),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_get_detection_details_not_found",
                    detection_ids=kwargs.get("detection_ids"),
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "detections": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class UpdateDetectionsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Update detection status."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute update detections.

        Args:
            detection_ids: List of detection IDs
            status: New status
            assigned_to_uuid: User UUID to assign to
            show_in_ui: Whether to show in UI

        Returns:
            Update result
        """
        try:
            detection_ids = kwargs.get("detection_ids")
            status = kwargs.get("status")

            if not detection_ids:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("detection_ids"),
                }

            if isinstance(detection_ids, str):
                detection_ids = [detection_ids]

            json_data = {"ids": detection_ids}

            if status:
                json_data["status"] = status
            if kwargs.get("assigned_to_uuid"):
                json_data["assigned_to_uuid"] = kwargs.get("assigned_to_uuid")
            if kwargs.get("show_in_ui") is not None:
                json_data["show_in_ui"] = kwargs.get("show_in_ui")

            response = await self._make_api_request(
                RESOLVE_DETECTION_ENDPOINT,
                method="patch",
                json_data=json_data,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Detections updated successfully",
                "detection_ids": detection_ids,
                "response": response,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class ListAlertsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """List alerts."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute list alerts.

        Args:
            filter: FQL filter string
            limit: Maximum number of results
            sort: Sort order

        Returns:
            List of alerts
        """
        try:
            filter_str = kwargs.get("filter")
            limit = kwargs.get("limit", DEFAULT_LIMIT)
            sort = kwargs.get("sort")

            params = {}
            if filter_str:
                params["filter"] = filter_str
            if limit:
                params["limit"] = min(limit, 10000)
            if sort:
                params["sort"] = sort

            # Get alert composite IDs
            response = await self._make_api_request(
                LIST_ALERTS_ENDPOINT,
                method="get",
                params=params,
            )

            composite_ids = response.get("resources", [])

            if not composite_ids:
                return {
                    "status": STATUS_SUCCESS,
                    "alerts": [],
                    "count": 0,
                }

            all_alerts = []

            # Batch size to 5000 (API limit)
            for i in range(0, len(composite_ids), MAX_BATCH_SIZE):
                batch = composite_ids[i : i + MAX_BATCH_SIZE]
                batch_response = await self._make_api_request(
                    GET_ALERT_DETAILS_ENDPOINT,
                    method="post",
                    json_data={"composite_ids": batch},
                )
                all_alerts.extend(batch_response.get("resources", []))

            return {
                "status": STATUS_SUCCESS,
                "alerts": all_alerts,
                "count": len(all_alerts),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_list_alerts_not_found", filter=kwargs.get("filter")
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "alerts": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class ListSessionsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """List RTR sessions."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute list sessions.

        Args:
            filter: FQL filter string
            limit: Maximum number of results

        Returns:
            List of sessions
        """
        try:
            filter_str = kwargs.get("filter")
            limit = kwargs.get("limit", DEFAULT_LIMIT)

            params = {}
            if filter_str:
                params["filter"] = filter_str
            if limit:
                params["limit"] = limit

            # Get session IDs
            response = await self._make_api_request(
                GET_RTR_SESSION_ID_ENDPOINT,
                method="get",
                params=params,
            )

            session_ids = response.get("resources", [])

            if not session_ids:
                return {
                    "status": STATUS_SUCCESS,
                    "sessions": [],
                    "count": 0,
                }

            # Get session details
            json_data = {"ids": session_ids}

            response = await self._make_api_request(
                GET_RTR_SESSION_DETAILS_ENDPOINT,
                method="post",
                json_data=json_data,
            )

            sessions = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "sessions": sessions,
                "count": len(sessions),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_list_sessions_not_found", filter=kwargs.get("filter")
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "sessions": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class RunCommandAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Run RTR command on a host."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute run command.

        Args:
            session_id: RTR session ID
            base_command: Command to run
            command_string: Full command string

        Returns:
            Command execution result
        """
        try:
            session_id = kwargs.get("session_id")
            base_command = kwargs.get("base_command")
            command_string = kwargs.get("command_string")

            if not session_id:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("session_id"),
                }

            if not base_command:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("base_command"),
                }

            json_data = {
                "session_id": session_id,
                "base_command": base_command,
            }

            if command_string:
                json_data["command_string"] = command_string

            response = await self._make_api_request(
                RUN_COMMAND_ENDPOINT,
                method="post",
                json_data=json_data,
            )

            return {
                "status": STATUS_SUCCESS,
                "response": response,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class GetIncidentDetailsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Get incident details."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute get incident details.

        Args:
            incident_ids: List of incident IDs

        Returns:
            Incident details
        """
        try:
            incident_ids = kwargs.get("incident_ids")

            if not incident_ids:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("incident_ids"),
                }

            if isinstance(incident_ids, str):
                incident_ids = [incident_ids]

            json_data = {"ids": incident_ids}

            response = await self._make_api_request(
                GET_INCIDENT_DETAILS_ENDPOINT,
                method="post",
                json_data=json_data,
            )

            incidents = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "incidents": incidents,
                "count": len(incidents),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_get_incident_details_not_found",
                    incident_ids=kwargs.get("incident_ids"),
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "incidents": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class ListIncidentsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """List incidents."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute list incidents.

        Args:
            filter: FQL filter string
            limit: Maximum number of results
            sort: Sort order

        Returns:
            List of incidents
        """
        try:
            filter_str = kwargs.get("filter")
            limit = kwargs.get("limit", DEFAULT_LIMIT)
            sort = kwargs.get("sort")

            params = {}
            if filter_str:
                params["filter"] = filter_str
            if limit:
                params["limit"] = limit
            if sort:
                params["sort"] = sort

            # Get incident IDs
            response = await self._make_api_request(
                LIST_INCIDENTS_ENDPOINT,
                method="get",
                params=params,
            )

            incident_ids = response.get("resources", [])

            if not incident_ids:
                return {
                    "status": STATUS_SUCCESS,
                    "incidents": [],
                    "count": 0,
                }

            # Get incident details
            json_data = {"ids": incident_ids}

            response = await self._make_api_request(
                GET_INCIDENT_DETAILS_ENDPOINT,
                method="post",
                json_data=json_data,
            )

            incidents = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "incidents": incidents,
                "count": len(incidents),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_list_incidents_not_found", filter=kwargs.get("filter")
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "incidents": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class UpdateIncidentAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Update incident."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute update incident.

        Args:
            incident_ids: List of incident IDs
            action_parameters: Update parameters

        Returns:
            Update result
        """
        try:
            incident_ids = kwargs.get("incident_ids")
            action_parameters = kwargs.get("action_parameters", {})

            if not incident_ids:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("incident_ids"),
                }

            if isinstance(incident_ids, str):
                incident_ids = [incident_ids]

            json_data = {
                "ids": incident_ids,
                "action_parameters": action_parameters,
            }

            response = await self._make_api_request(
                UPDATE_INCIDENT_ENDPOINT,
                method="post",
                json_data=json_data,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Incident updated successfully",
                "incident_ids": incident_ids,
                "response": response,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class GetSessionFileAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Get file from RTR session."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute get session file.

        Args:
            session_id: Session ID
            sha256: File SHA256 hash

        Returns:
            File content
        """
        try:
            session_id = kwargs.get("session_id")
            sha256 = kwargs.get("sha256")

            if not session_id:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("session_id"),
                }

            if not sha256:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("sha256"),
                }

            params = {
                "session_id": session_id,
                "sha256": sha256,
            }

            response = await self._make_api_request(
                GET_EXTRACTED_RTR_FILE_ENDPOINT,
                method="get",
                params=params,
            )

            return {
                "status": STATUS_SUCCESS,
                "response": response,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_get_session_file_not_found",
                    session_id=kwargs.get("session_id"),
                    sha256=kwargs.get("sha256"),
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "session_id": kwargs.get("session_id"),
                    "sha256": kwargs.get("sha256"),
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class GetSystemInfoAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Get system information via RTR."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute get system info.

        Args:
            device_id: Device ID

        Returns:
            System information
        """
        try:
            device_id = kwargs.get("device_id")

            if not device_id:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("device_id"),
                }

            # Get device details
            params = {"ids": [device_id]}

            response = await self._make_api_request(
                GET_DEVICE_DETAILS_ENDPOINT,
                method="get",
                params=params,
            )

            devices = response.get("resources", [])

            if not devices:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_NOT_FOUND,
                    "error": f"Device not found: {device_id}",
                }

            return {
                "status": STATUS_SUCCESS,
                "device_info": devices[0],
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_get_system_info_not_found",
                    device_id=kwargs.get("device_id"),
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "device_id": kwargs.get("device_id"),
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class HuntFileAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Hunt for file hash across hosts."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute hunt file.

        Args:
            hash: File hash (MD5, SHA1, or SHA256)

        Returns:
            List of devices where file was found
        """
        try:
            file_hash = kwargs.get("hash")

            if not file_hash:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("hash"),
                }

            # Query devices where this IOC was found
            params = {
                "type": "sha256",  # CrowdStrike normalizes to SHA256
                "value": file_hash,
            }

            response = await self._make_api_request(
                GET_PROCESSES_RAN_ON_ENDPOINT,
                method="get",
                params=params,
            )

            device_ids = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "hash": file_hash,
                "device_ids": device_ids,
                "count": len(device_ids),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("crowdstrike_hunt_file_not_found", hash=kwargs.get("hash"))
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "hash": kwargs.get("hash"),
                    "device_ids": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class HuntDomainAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Hunt for domain across hosts."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute hunt domain.

        Args:
            domain: Domain name

        Returns:
            List of devices where domain was accessed
        """
        try:
            domain = kwargs.get("domain")

            if not domain:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("domain"),
                }

            # Query devices where this IOC was found
            params = {
                "type": "domain",
                "value": domain,
            }

            response = await self._make_api_request(
                GET_PROCESSES_RAN_ON_ENDPOINT,
                method="get",
                params=params,
            )

            device_ids = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "domain": domain,
                "device_ids": device_ids,
                "count": len(device_ids),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_hunt_domain_not_found", domain=kwargs.get("domain")
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "domain": kwargs.get("domain"),
                    "device_ids": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class HuntIpAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Hunt for IP address across hosts."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute hunt IP.

        Args:
            ip: IP address

        Returns:
            List of devices where IP was contacted
        """
        try:
            ip_address = kwargs.get("ip")

            if not ip_address:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("ip"),
                }

            # Query devices where this IOC was found
            params = {
                "type": "ipv4",
                "value": ip_address,
            }

            response = await self._make_api_request(
                GET_PROCESSES_RAN_ON_ENDPOINT,
                method="get",
                params=params,
            )

            device_ids = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "ip": ip_address,
                "device_ids": device_ids,
                "count": len(device_ids),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("crowdstrike_hunt_ip_not_found", ip=kwargs.get("ip"))
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ip": kwargs.get("ip"),
                    "device_ids": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class ListProcessesAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """List processes that ran with an IOC."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute list processes.

        Args:
            type: IOC type
            value: IOC value

        Returns:
            List of processes
        """
        try:
            ioc_type = kwargs.get("type")
            ioc_value = kwargs.get("value")

            if not ioc_type:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("type"),
                }

            if not ioc_value:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("value"),
                }

            params = {
                "type": ioc_type,
                "value": ioc_value,
            }

            response = await self._make_api_request(
                GET_PROCESSES_RAN_ON_ENDPOINT,
                method="get",
                params=params,
            )

            process_ids = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "process_ids": process_ids,
                "count": len(process_ids),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_list_processes_not_found",
                    type=kwargs.get("type"),
                    value=kwargs.get("value"),
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "process_ids": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class UploadIndicatorAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Upload custom IOC indicator."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute upload indicator.

        Args:
            type: IOC type (sha256, md5, domain, ipv4, ipv6)
            value: IOC value
            policy: Policy (detect or prevent)
            severity: Severity (informational, low, medium, high, critical)
            description: Description

        Returns:
            Upload result
        """
        try:
            ioc_type = kwargs.get("type")
            ioc_value = kwargs.get("value")
            policy = kwargs.get("policy", "detect")
            severity = kwargs.get("severity")

            if not ioc_type:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("type"),
                }

            if not ioc_value:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("value"),
                }

            indicators = [
                {
                    "type": ioc_type,
                    "value": ioc_value,
                    "policy": policy,
                }
            ]

            if severity:
                indicators[0]["severity"] = severity
            if kwargs.get("description"):
                indicators[0]["description"] = kwargs.get("description")
            if kwargs.get("tags"):
                indicators[0]["tags"] = kwargs.get("tags")

            json_data = {"indicators": indicators}

            response = await self._make_api_request(
                GET_INDICATOR_ENDPOINT,
                method="post",
                json_data=json_data,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Indicator uploaded successfully",
                "response": response,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class DeleteIndicatorAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Delete custom IOC indicator."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute delete indicator.

        Args:
            ids: List of indicator IDs

        Returns:
            Deletion result
        """
        try:
            indicator_ids = kwargs.get("ids")

            if not indicator_ids:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("ids"),
                }

            if isinstance(indicator_ids, str):
                indicator_ids = [indicator_ids]

            params = {"ids": indicator_ids}

            await self._make_api_request(
                GET_INDICATOR_ENDPOINT,
                method="delete",
                params=params,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Indicators deleted successfully",
                "indicator_ids": indicator_ids,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class FileReputationAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Get file reputation from CrowdStrike."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute file reputation lookup.

        Args:
            hash: File hash

        Returns:
            File reputation information
        """
        try:
            file_hash = kwargs.get("hash")

            if not file_hash:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("hash"),
                }

            # Query for indicator
            params = {
                "filter": f"value:'{file_hash}'",
            }

            response = await self._make_api_request(
                GET_COMBINED_CUSTOM_INDICATORS_ENDPOINT,
                method="get",
                params=params,
            )

            indicators = response.get("resources", [])

            if indicators:
                return {
                    "status": STATUS_SUCCESS,
                    "hash": file_hash,
                    "found": True,
                    "indicators": indicators,
                }

            return {
                "status": STATUS_SUCCESS,
                "hash": file_hash,
                "found": False,
                "message": "Hash not found in custom indicators",
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_file_reputation_not_found", hash=kwargs.get("hash")
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "hash": kwargs.get("hash"),
                    "found": False,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class UrlReputationAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Get URL reputation from CrowdStrike."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute URL reputation lookup.

        Args:
            url: URL to check

        Returns:
            URL reputation information
        """
        try:
            url = kwargs.get("url")

            if not url:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("url"),
                }

            # Query for indicator
            params = {
                "filter": f"value:'{url}'",
            }

            response = await self._make_api_request(
                GET_COMBINED_CUSTOM_INDICATORS_ENDPOINT,
                method="get",
                params=params,
            )

            indicators = response.get("resources", [])

            if indicators:
                return {
                    "status": STATUS_SUCCESS,
                    "url": url,
                    "found": True,
                    "indicators": indicators,
                }

            return {
                "status": STATUS_SUCCESS,
                "url": url,
                "found": False,
                "message": "URL not found in custom indicators",
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_url_reputation_not_found", url=kwargs.get("url")
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "url": kwargs.get("url"),
                    "found": False,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class DetonateFileAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Detonate file in Falcon Sandbox."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute file detonation.

        Args:
            sha256: File SHA256 hash
            environment_id: Sandbox environment ID

        Returns:
            Detonation submission result
        """
        try:
            sha256 = kwargs.get("sha256")

            if not sha256:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("sha256"),
                }

            environment_id = kwargs.get("environment_id", 160)  # Default: Windows 10

            json_data = {
                "sandbox": [
                    {
                        "sha256": sha256,
                        "environment_id": environment_id,
                    }
                ]
            }

            response = await self._make_api_request(
                DETONATE_RESOURCE_ENDPOINT,
                method="post",
                json_data=json_data,
            )

            resources = response.get("resources", [])
            if resources:
                return {
                    "status": STATUS_SUCCESS,
                    "submission_id": resources[0].get("id"),
                    "response": resources[0],
                }

            return {
                "status": STATUS_ERROR,
                "error": "No submission ID returned",
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class DetonateUrlAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Detonate URL in Falcon Sandbox."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute URL detonation.

        Args:
            url: URL to detonate
            environment_id: Sandbox environment ID

        Returns:
            Detonation submission result
        """
        try:
            url = kwargs.get("url")

            if not url:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("url"),
                }

            environment_id = kwargs.get("environment_id", 160)  # Default: Windows 10

            json_data = {
                "sandbox": [
                    {
                        "url": url,
                        "environment_id": environment_id,
                    }
                ]
            }

            response = await self._make_api_request(
                DETONATE_RESOURCE_ENDPOINT,
                method="post",
                json_data=json_data,
            )

            resources = response.get("resources", [])
            if resources:
                return {
                    "status": STATUS_SUCCESS,
                    "submission_id": resources[0].get("id"),
                    "response": resources[0],
                }

            return {
                "status": STATUS_ERROR,
                "error": "No submission ID returned",
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

class CheckDetonationStatusAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Check detonation analysis status."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute check detonation status.

        Args:
            submission_ids: List of submission IDs

        Returns:
            Detonation status and results
        """
        try:
            submission_ids = kwargs.get("submission_ids")

            if not submission_ids:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_MISSING_PARAMETER.format("submission_ids"),
                }

            if isinstance(submission_ids, str):
                submission_ids = [submission_ids]

            params = {"ids": submission_ids}

            response = await self._make_api_request(
                GET_REPORT_SUMMARY_ENDPOINT,
                method="get",
                params=params,
            )

            reports = response.get("resources", [])

            return {
                "status": STATUS_SUCCESS,
                "reports": reports,
                "count": len(reports),
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "crowdstrike_check_detonation_status_not_found",
                    submission_ids=kwargs.get("submission_ids"),
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "reports": [],
                    "count": 0,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
            }

# ============================================================================
# AlertSource Actions
# ============================================================================

class PullAlertsAction(IntegrationAction, CrowdStrikeOAuth2Mixin):
    """Pull alerts from CrowdStrike Falcon.

    Uses the Alerts v2 API:
    1. POST /alerts/queries/alerts/v2 — get composite IDs with time filter
    2. POST /alerts/entities/alerts/v1 — get full alert details by IDs

    Project Symi: AlertSource archetype requires this action.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Pull alerts from CrowdStrike within a time range.

        Args:
            start_time: Start of time range (datetime or ISO string, optional)
            end_time: End of time range (datetime or ISO string, optional)
            max_results: Maximum number of alerts to return (default: 1000)

        Returns:
            dict: Alerts pulled with count and data

        Note:
            If start_time is not provided, uses the integration's
            default_lookback_minutes setting to determine how far back
            to search (default: 5 minutes).
        """
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not client_id or not client_secret:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        # Determine time range
        now = datetime.now(UTC)
        end_time = params.get("end_time")
        start_time = params.get("start_time")

        if end_time and isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        if not end_time:
            end_time = now

        if start_time and isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if not start_time:
            lookback = self.settings.get(
                SETTINGS_DEFAULT_LOOKBACK, DEFAULT_LOOKBACK_MINUTES
            )
            start_time = end_time - timedelta(minutes=lookback)

        max_results = params.get("max_results", DEFAULT_MAX_ALERTS)

        # Build FQL time filter
        start_iso = start_time.isoformat()
        end_iso = end_time.isoformat()
        fql_filter = (
            f"created_timestamp:>='{start_iso}'+created_timestamp:<='{end_iso}'"
        )

        try:
            all_alerts: list[dict[str, Any]] = []
            offset = 0

            while len(all_alerts) < max_results:
                page_size = min(ALERT_PAGE_SIZE, max_results - len(all_alerts))

                # Step 1: Query alert IDs with time filter
                ids_response = await self._make_api_request(
                    LIST_ALERTS_ENDPOINT,
                    method="get",
                    params={
                        "filter": fql_filter,
                        "limit": page_size,
                        "offset": offset,
                        "sort": "created_timestamp|asc",
                    },
                )

                composite_ids = ids_response.get("resources", [])
                if not composite_ids:
                    break

                # Step 2: Fetch full alert details in batches
                for i in range(0, len(composite_ids), MAX_BATCH_SIZE):
                    batch = composite_ids[i : i + MAX_BATCH_SIZE]
                    details_response = await self._make_api_request(
                        GET_ALERT_DETAILS_ENDPOINT,
                        method="post",
                        json_data={"composite_ids": batch},
                    )
                    all_alerts.extend(details_response.get("resources", []))

                offset += len(composite_ids)

                # Stop if we got fewer results than requested (last page)
                if len(composite_ids) < page_size:
                    break

            return {
                "status": STATUS_SUCCESS,
                "alerts_count": len(all_alerts),
                "alerts": all_alerts,
                "message": f"Retrieved {len(all_alerts)} alerts",
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class AlertsToOcsfAction(IntegrationAction):
    """Normalize raw CrowdStrike alerts to OCSF Detection Finding v1.8.0.

    Delegates to CrowdStrikeOCSFNormalizer which produces full OCSF Detection
    Findings with metadata, evidences, observables, device, actor,
    and MITRE ATT&CK mapping.

    Project Symi: AlertSource archetype requires this action.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Normalize raw CrowdStrike alerts to OCSF format.

        Args:
            raw_alerts: List of raw CrowdStrike alert documents.

        Returns:
            dict with status, normalized_alerts (OCSF dicts), count, and errors.
        """
        from alert_normalizer.crowdstrike_ocsf import CrowdStrikeOCSFNormalizer

        raw_alerts = params.get("raw_alerts", [])
        logger.info("crowdstrike_alerts_to_ocsf_called", count=len(raw_alerts))

        normalizer = CrowdStrikeOCSFNormalizer()
        normalized = []
        errors = 0

        for alert in raw_alerts:
            try:
                ocsf_finding = normalizer.to_ocsf(alert)
                normalized.append(ocsf_finding)
            except Exception:
                logger.exception(
                    "crowdstrike_alert_to_ocsf_failed",
                    alert_id=alert.get("composite_id"),
                    display_name=alert.get("display_name"),
                )
                errors += 1

        return {
            "status": "success" if errors == 0 else "partial",
            "normalized_alerts": normalized,
            "count": len(normalized),
            "errors": errors,
        }

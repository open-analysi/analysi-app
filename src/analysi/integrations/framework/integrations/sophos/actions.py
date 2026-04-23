"""
Sophos Central EDR integration actions.
Uses OAuth2 client credentials flow for authentication.
The API requires a two-step auth: (1) get JWT token, (2) call whoami to get
tenant ID and data-region base URL. All subsequent calls use the data-region
URL with tenant/partner ID header.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.sophos.constants import (
    ALERT_ENDPOINT,
    ALERTS_ENDPOINT,
    BLOCKED_ITEM_ENDPOINT,
    BLOCKED_ITEMS_ENDPOINT,
    CREDENTIAL_CLIENT_ID,
    CREDENTIAL_CLIENT_SECRET,
    DEFAULT_TIMEOUT,
    ENDPOINTS_ENDPOINT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    ID_TYPE_HEADERS,
    ID_TYPE_TENANT,
    ISOLATION_ENDPOINT,
    MSG_AUTHENTICATION_FAILED,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAMETER,
    MSG_WHOAMI_FAILED,
    OAUTH_TOKEN_URL,
    SCAN_ENDPOINT,
    SETTINGS_TIMEOUT,
    WHOAMI_URL,
)

logger = get_logger(__name__)

# ============================================================================
# AUTHENTICATION HELPERS
# ============================================================================

async def _get_access_token(
    client_id: str,
    client_secret: str,
    timeout: int = DEFAULT_TIMEOUT,
    http_request=None,
) -> str:
    """Acquire OAuth2 access token from Sophos Central.

    Args:
        client_id: OAuth2 client ID
        client_secret: OAuth2 client secret
        timeout: Request timeout in seconds
        http_request: The http_request callable from the action instance

    Returns:
        Access token string

    Raises:
        ValueError: If token acquisition fails
    """
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "token",
        "grant_type": "client_credentials",
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    response = await http_request(
        OAUTH_TOKEN_URL,
        method="POST",
        data=data,
        headers=headers,
        timeout=timeout,
    )

    token_data = response.json()
    access_token = token_data.get("access_token")

    if not access_token:
        raise ValueError(MSG_AUTHENTICATION_FAILED)

    return access_token

async def _get_whoami(
    access_token: str,
    timeout: int = DEFAULT_TIMEOUT,
    http_request=None,
) -> dict[str, Any]:
    """Call Sophos whoami endpoint to discover tenant info and data-region URL.

    Args:
        access_token: Bearer token
        timeout: Request timeout in seconds
        http_request: The http_request callable from the action instance

    Returns:
        Dict with keys: base_url, id_type, tenant_id, id_header_name
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    response = await http_request(
        WHOAMI_URL,
        headers=headers,
        timeout=timeout,
    )

    whoami = response.json()

    id_type = whoami.get("idType", ID_TYPE_TENANT)
    tenant_id = whoami.get("id")

    if not tenant_id:
        raise ValueError(MSG_WHOAMI_FAILED)

    api_hosts = whoami.get("apiHosts", {})
    if id_type == ID_TYPE_TENANT:
        base_url = api_hosts.get("dataRegion")
    else:
        base_url = api_hosts.get("global")

    if not base_url:
        raise ValueError(MSG_WHOAMI_FAILED)

    id_header_name = ID_TYPE_HEADERS.get(id_type, "X-Tenant-ID")

    return {
        "base_url": base_url,
        "id_type": id_type,
        "tenant_id": tenant_id,
        "id_header_name": id_header_name,
    }

async def _make_sophos_api_request(
    endpoint: str,
    access_token: str,
    whoami_info: dict[str, Any],
    method: str = "GET",
    params: dict | None = None,
    json_data: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    http_request=None,
) -> httpx.Response:
    """Make authenticated request to the Sophos Central tenant API.

    Args:
        endpoint: API endpoint path (e.g., /endpoint/v1/endpoints)
        access_token: Bearer token
        whoami_info: Output from _get_whoami containing base_url, tenant_id, id_header_name
        method: HTTP method
        params: Query parameters
        json_data: JSON body
        timeout: Request timeout in seconds
        http_request: The http_request callable from the action instance

    Returns:
        httpx.Response
    """
    url = f"{whoami_info['base_url'].rstrip('/')}{endpoint}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        whoami_info["id_header_name"]: whoami_info["tenant_id"],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    return await http_request(
        url,
        method=method,
        headers=headers,
        params=params,
        json_data=json_data,
        timeout=timeout,
    )

async def _authenticate(action: IntegrationAction) -> tuple[str, dict[str, Any]]:
    """Authenticate and return (access_token, whoami_info).

    Helper that validates credentials, gets OAuth token, and resolves tenant info.

    Args:
        action: The IntegrationAction instance providing credentials and http_request

    Returns:
        Tuple of (access_token, whoami_info)

    Raises:
        ValueError: If credentials are missing or authentication fails
    """
    client_id = action.credentials.get(CREDENTIAL_CLIENT_ID)
    client_secret = action.credentials.get(CREDENTIAL_CLIENT_SECRET)

    if not client_id or not client_secret:
        raise ValueError(MSG_MISSING_CREDENTIALS)

    timeout = action.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

    access_token = await _get_access_token(
        client_id=client_id,
        client_secret=client_secret,
        timeout=timeout,
        http_request=action.http_request,
    )

    whoami_info = await _get_whoami(
        access_token=access_token,
        timeout=timeout,
        http_request=action.http_request,
    )

    return access_token, whoami_info

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Test connectivity and authentication with Sophos Central API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute health check.

        Validates OAuth2 credentials by acquiring a token, resolving the
        tenant via whoami, and listing endpoints with limit=1.

        Returns:
            Result with healthy status and tenant info
        """
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not client_id or not client_secret:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
                healthy=False,
            )

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            access_token = await _get_access_token(
                client_id=client_id,
                client_secret=client_secret,
                timeout=timeout,
                http_request=self.http_request,
            )

            whoami_info = await _get_whoami(
                access_token=access_token,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Verify API access by listing endpoints with limit=1
            response = await _make_sophos_api_request(
                ENDPOINTS_ENDPOINT,
                access_token=access_token,
                whoami_info=whoami_info,
                params={"pageSize": 1},
                timeout=timeout,
                http_request=self.http_request,
            )
            resp_json = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "id_type": whoami_info["id_type"],
                    "tenant_id": whoami_info["tenant_id"],
                    "base_url": whoami_info["base_url"],
                    "endpoint_count": resp_json.get("pages", {}).get("items", 0),
                },
            )

        except httpx.HTTPStatusError as e:
            logger.error("sophos_health_check_failed", error=str(e))
            return self.error_result(e, healthy=False)
        except Exception as e:
            logger.error("sophos_health_check_failed", error=str(e))
            return self.error_result(e, healthy=False)

# ============================================================================
# ENDPOINT ACTIONS
# ============================================================================

class GetEndpointAction(IntegrationAction):
    """Get details for a specific endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get endpoint details by ID.

        Args:
            **kwargs: Must contain:
                - endpoint_id (str): Sophos endpoint ID

        Returns:
            Endpoint details
        """
        endpoint_id = kwargs.get("endpoint_id")
        if not endpoint_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("endpoint_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            access_token, whoami_info = await _authenticate(self)
            timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

            response = await _make_sophos_api_request(
                f"{ENDPOINTS_ENDPOINT}/{endpoint_id}",
                access_token=access_token,
                whoami_info=whoami_info,
                timeout=timeout,
                http_request=self.http_request,
            )

            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("sophos_endpoint_not_found", endpoint_id=endpoint_id)
                return self.success_result(
                    not_found=True,
                    data={"endpoint_id": endpoint_id},
                )
            return self.error_result(e)
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

class ListEndpointsAction(IntegrationAction):
    """List endpoints/sensors configured in Sophos Central."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List endpoints with optional filters.

        Args:
            **kwargs: Optional filters:
                - page_size (int): Items per page (default: 50)
                - health_status (str): Filter by health status
                - type (str): Filter by endpoint type
                - search (str): Search query
                - sort (str): Sort field

        Returns:
            List of endpoints
        """
        try:
            access_token, whoami_info = await _authenticate(self)
            timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

            params: dict[str, Any] = {}
            if kwargs.get("page_size"):
                params["pageSize"] = kwargs["page_size"]
            if kwargs.get("health_status"):
                params["healthStatus"] = kwargs["health_status"]
            if kwargs.get("type"):
                params["type"] = kwargs["type"]
            if kwargs.get("search"):
                params["search"] = kwargs["search"]
            if kwargs.get("sort"):
                params["sort"] = kwargs["sort"]

            response = await _make_sophos_api_request(
                ENDPOINTS_ENDPOINT,
                access_token=access_token,
                whoami_info=whoami_info,
                params=params,
                timeout=timeout,
                http_request=self.http_request,
            )

            resp_json = response.json()

            return self.success_result(
                data={
                    "items": resp_json.get("items", []),
                    "pages": resp_json.get("pages", {}),
                    "total": resp_json.get("pages", {}).get("items", 0),
                },
            )

        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# ISOLATION ACTIONS
# ============================================================================

class IsolateEndpointAction(IntegrationAction):
    """Network-isolate one or more endpoints."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Isolate endpoint(s) from the network.

        Args:
            **kwargs: Must contain:
                - ids (str or list): Endpoint ID(s) to isolate
                - comment (str, optional): Reason for isolation

        Returns:
            Isolation result
        """
        ids = kwargs.get("ids")
        if not ids:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("ids"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Normalize ids to list
        if isinstance(ids, str):
            ids = [id_str.strip() for id_str in ids.split(",")]

        comment = kwargs.get("comment", "Isolated via Analysi automation")

        try:
            access_token, whoami_info = await _authenticate(self)
            timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

            json_data = {
                "enabled": True,
                "ids": ids,
                "comment": comment,
            }

            response = await _make_sophos_api_request(
                ISOLATION_ENDPOINT,
                access_token=access_token,
                whoami_info=whoami_info,
                method="POST",
                json_data=json_data,
                timeout=timeout,
                http_request=self.http_request,
            )

            resp_json = response.json()
            items = resp_json.get("items", [])

            return self.success_result(
                data={
                    "items": items,
                    "count": len(items),
                },
            )

        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

class UnisolateEndpointAction(IntegrationAction):
    """Remove network isolation from one or more endpoints."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Remove isolation from endpoint(s).

        Args:
            **kwargs: Must contain:
                - ids (str or list): Endpoint ID(s) to unisolate
                - comment (str, optional): Reason for removal

        Returns:
            Unisolation result
        """
        ids = kwargs.get("ids")
        if not ids:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("ids"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        if isinstance(ids, str):
            ids = [id_str.strip() for id_str in ids.split(",")]

        comment = kwargs.get("comment", "Unisolated via Analysi automation")

        try:
            access_token, whoami_info = await _authenticate(self)
            timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

            json_data = {
                "enabled": False,
                "ids": ids,
                "comment": comment,
            }

            response = await _make_sophos_api_request(
                ISOLATION_ENDPOINT,
                access_token=access_token,
                whoami_info=whoami_info,
                method="POST",
                json_data=json_data,
                timeout=timeout,
                http_request=self.http_request,
            )

            resp_json = response.json()
            items = resp_json.get("items", [])

            return self.success_result(
                data={
                    "items": items,
                    "count": len(items),
                },
            )

        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# SCAN ACTION
# ============================================================================

class ScanEndpointAction(IntegrationAction):
    """Trigger an endpoint scan."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Trigger a scan on the specified endpoint.

        Args:
            **kwargs: Must contain:
                - endpoint_id (str): Endpoint ID to scan

        Returns:
            Scan initiation result
        """
        endpoint_id = kwargs.get("endpoint_id")
        if not endpoint_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("endpoint_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            access_token, whoami_info = await _authenticate(self)
            timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

            response = await _make_sophos_api_request(
                SCAN_ENDPOINT.format(endpoint_id=endpoint_id),
                access_token=access_token,
                whoami_info=whoami_info,
                method="POST",
                json_data={},
                timeout=timeout,
                http_request=self.http_request,
            )

            return self.success_result(
                data={
                    "endpoint_id": endpoint_id,
                    "scan_initiated": True,
                    "response": response.json(),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("sophos_endpoint_not_found", endpoint_id=endpoint_id)
                return self.success_result(
                    not_found=True,
                    data={"endpoint_id": endpoint_id},
                )
            return self.error_result(e)
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# ALERT ACTIONS
# ============================================================================

class ListAlertsAction(IntegrationAction):
    """List security alerts from Sophos Central."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List alerts with optional filters.

        Args:
            **kwargs: Optional parameters:
                - limit (int): Maximum number of alerts (default: 100)
                - category (str): Alert category filter
                - severity (str): Alert severity filter
                - from_date (str): Start date for alerts (ISO 8601)

        Returns:
            List of alerts
        """
        try:
            access_token, whoami_info = await _authenticate(self)
            timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

            params: dict[str, Any] = {}
            if kwargs.get("limit"):
                params["pageSize"] = kwargs["limit"]
            if kwargs.get("category"):
                params["category"] = kwargs["category"]
            if kwargs.get("severity"):
                params["severity"] = kwargs["severity"]
            if kwargs.get("from_date"):
                params["from"] = kwargs["from_date"]

            response = await _make_sophos_api_request(
                ALERTS_ENDPOINT,
                access_token=access_token,
                whoami_info=whoami_info,
                params=params,
                timeout=timeout,
                http_request=self.http_request,
            )

            resp_json = response.json()

            return self.success_result(
                data={
                    "items": resp_json.get("items", []),
                    "pages": resp_json.get("pages", {}),
                    "total": resp_json.get("pages", {}).get("items", 0),
                },
            )

        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

class GetAlertAction(IntegrationAction):
    """Get details for a specific alert."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get alert details by ID.

        Args:
            **kwargs: Must contain:
                - alert_id (str): Sophos alert ID

        Returns:
            Alert details
        """
        alert_id = kwargs.get("alert_id")
        if not alert_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("alert_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            access_token, whoami_info = await _authenticate(self)
            timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

            response = await _make_sophos_api_request(
                ALERT_ENDPOINT.format(alert_id=alert_id),
                access_token=access_token,
                whoami_info=whoami_info,
                timeout=timeout,
                http_request=self.http_request,
            )

            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("sophos_alert_not_found", alert_id=alert_id)
                return self.success_result(
                    not_found=True,
                    data={"alert_id": alert_id},
                )
            return self.error_result(e)
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# BLOCKED ITEMS ACTIONS
# ============================================================================

class BlockItemAction(IntegrationAction):
    """Add an item to the blocked items list."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block a SHA256 hash.

        Args:
            **kwargs: Must contain:
                - sha256 (str): SHA256 hash to block
                - comment (str): Reason for blocking

        Returns:
            Block result with item ID
        """
        sha256 = kwargs.get("sha256")
        if not sha256:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("sha256"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        comment = kwargs.get("comment", "Blocked via Analysi automation")

        try:
            access_token, whoami_info = await _authenticate(self)
            timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

            json_data = {
                "type": "sha256",
                "comment": comment,
                "properties": {
                    "sha256": sha256,
                },
            }

            response = await _make_sophos_api_request(
                BLOCKED_ITEMS_ENDPOINT,
                access_token=access_token,
                whoami_info=whoami_info,
                method="POST",
                json_data=json_data,
                timeout=timeout,
                http_request=self.http_request,
            )

            return self.success_result(data=response.json())

        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

class UnblockItemAction(IntegrationAction):
    """Remove an item from the blocked items list."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Remove a blocked item by its ID.

        Args:
            **kwargs: Must contain:
                - item_id (str): Blocked item ID to remove

        Returns:
            Unblock result
        """
        item_id = kwargs.get("item_id")
        if not item_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("item_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            access_token, whoami_info = await _authenticate(self)
            timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

            response = await _make_sophos_api_request(
                BLOCKED_ITEM_ENDPOINT.format(item_id=item_id),
                access_token=access_token,
                whoami_info=whoami_info,
                method="DELETE",
                timeout=timeout,
                http_request=self.http_request,
            )

            # DELETE returns 200 with {"deleted": true} on success
            if response.status_code == 204:
                return self.success_result(
                    data={"item_id": item_id, "deleted": True},
                )

            return self.success_result(data=response.json())

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("sophos_blocked_item_not_found", item_id=item_id)
                return self.success_result(
                    not_found=True,
                    data={"item_id": item_id},
                )
            return self.error_result(e)
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

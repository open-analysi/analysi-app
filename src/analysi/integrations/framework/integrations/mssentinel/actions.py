"""Microsoft Sentinel integration actions for the Naxos framework.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    DEFAULT_LOOKBACK_MINUTES,
    DEFAULT_PULL_ALERTS_LIMIT,
    DEFAULT_TIMEOUT,
    ERROR_MSG_INVALID_LIMIT,
    ERROR_MSG_INVALID_MAX_ROWS,
    ERROR_MSG_MISSING_CREDENTIALS,
    ERROR_MSG_MISSING_SETTINGS,
    ERROR_MSG_NO_VALUE,
    LOGANALYTICS_API_URL,
    LOGANALYTICS_LOGIN_RESOURCE,
    LOGANALYTICS_LOGIN_URL,
    SENTINEL_API_INCIDENTS,
    SENTINEL_API_URL,
    SENTINEL_API_VERSION,
    SENTINEL_JSON_ACCESS_TOKEN,
    SENTINEL_JSON_NEXT_LINK,
    SENTINEL_JSON_VALUE,
    SENTINEL_LOGIN_SCOPE,
    SENTINEL_LOGIN_URL,
    STATUS_ERROR,
    STATUS_PARTIAL,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

class HealthCheckAction(IntegrationAction):
    """Health check action for Microsoft Sentinel."""

    async def execute(self, **params) -> dict[str, Any]:
        """Execute health check against Microsoft Sentinel.

        Returns:
            dict: Health check result with status, message, timestamp
        """
        try:
            # Get access token
            access_token = await self._get_access_token()

            # Build API URL
            api_url = self._build_api_url()
            endpoint = f"{api_url}{SENTINEL_API_INCIDENTS}"

            # Test connectivity by fetching one incident
            await self.http_request(
                endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"api-version": SENTINEL_API_VERSION, "$top": 1},
                timeout=DEFAULT_TIMEOUT,
            )

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Microsoft Sentinel connection successful",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except httpx.HTTPStatusError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": f"Connection failed: {e!s}",
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def _build_api_url(self) -> str:
        """Build Sentinel API base URL from settings."""
        subscription_id = self.settings.get("subscription_id")
        resource_group = self.settings.get("resource_group_name")
        workspace_name = self.settings.get("workspace_name")

        if not subscription_id or not resource_group or not workspace_name:
            raise ValueError(ERROR_MSG_MISSING_SETTINGS)

        return SENTINEL_API_URL.format(
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
        )

    async def _get_access_token(self) -> str:
        """Get Azure AD access token for Sentinel API."""
        tenant_id = self.settings.get("tenant_id")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")

        if not tenant_id or not client_id or not client_secret:
            raise ValueError(ERROR_MSG_MISSING_CREDENTIALS)

        login_url = SENTINEL_LOGIN_URL.format(tenant_id=tenant_id)

        login_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": SENTINEL_LOGIN_SCOPE,
            "grant_type": "client_credentials",
        }

        response = await self.http_request(
            login_url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=login_payload,
            timeout=DEFAULT_TIMEOUT,
        )
        token_data = response.json()

        return token_data[SENTINEL_JSON_ACCESS_TOKEN]

class ListIncidentsAction(IntegrationAction):
    """List incidents from Microsoft Sentinel."""

    async def execute(self, **params) -> dict[str, Any]:
        """List incidents from Sentinel workspace.

        Args:
            limit: Maximum number of incidents to retrieve (default: 100)
            filter: OData filter expression (optional)

        Returns:
            dict: List of incidents with count
        """
        limit = params.get("limit", 100)
        filter_expr = params.get("filter")

        # Validate limit
        if not isinstance(limit, int) or limit <= 0:
            return {
                "status": STATUS_ERROR,
                "error_type": "ValidationError",
                "error": ERROR_MSG_INVALID_LIMIT,
            }

        try:
            # Get access token
            access_token = await self._get_access_token()

            # Build API URL
            api_url = self._build_api_url()
            endpoint = f"{api_url}{SENTINEL_API_INCIDENTS}"

            # Build query parameters
            query_params = {"api-version": SENTINEL_API_VERSION, "$top": limit}
            if filter_expr:
                query_params["$filter"] = filter_expr

            # Fetch incidents with pagination
            incidents = await self._fetch_paginated(
                endpoint, access_token, query_params, limit
            )

            return {
                "status": STATUS_SUCCESS,
                "total_incidents": len(incidents),
                "incidents": incidents,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    async def _fetch_paginated(
        self, endpoint: str, access_token: str, params: dict, limit: int
    ) -> list[dict]:
        """Fetch paginated results from Sentinel API."""
        results = []
        next_link = None

        while True:
            if next_link:
                # Use next link for pagination
                url = next_link
                current_params = {}
            else:
                url = endpoint
                current_params = params

            response = await self.http_request(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=current_params,
                timeout=DEFAULT_TIMEOUT,
            )
            data = response.json()

            if SENTINEL_JSON_VALUE not in data:
                raise ValueError(ERROR_MSG_NO_VALUE)

            # Add results
            for item in data[SENTINEL_JSON_VALUE]:
                if len(results) >= limit:
                    break
                results.append(item)

            # Check for more pages
            if len(results) >= limit or SENTINEL_JSON_NEXT_LINK not in data:
                break

            next_link = data[SENTINEL_JSON_NEXT_LINK]

        return results[:limit]

    def _build_api_url(self) -> str:
        """Build Sentinel API base URL from settings."""
        subscription_id = self.settings.get("subscription_id")
        resource_group = self.settings.get("resource_group_name")
        workspace_name = self.settings.get("workspace_name")

        if not subscription_id or not resource_group or not workspace_name:
            raise ValueError(ERROR_MSG_MISSING_SETTINGS)

        return SENTINEL_API_URL.format(
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
        )

    async def _get_access_token(self) -> str:
        """Get Azure AD access token for Sentinel API."""
        tenant_id = self.settings.get("tenant_id")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")

        if not tenant_id or not client_id or not client_secret:
            raise ValueError(ERROR_MSG_MISSING_CREDENTIALS)

        login_url = SENTINEL_LOGIN_URL.format(tenant_id=tenant_id)

        login_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": SENTINEL_LOGIN_SCOPE,
            "grant_type": "client_credentials",
        }

        response = await self.http_request(
            login_url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=login_payload,
            timeout=DEFAULT_TIMEOUT,
        )
        token_data = response.json()

        return token_data[SENTINEL_JSON_ACCESS_TOKEN]

class GetIncidentAction(IntegrationAction):
    """Get details of a specific incident."""

    async def execute(self, **params) -> dict[str, Any]:
        """Get incident details.

        Args:
            incident_name: Incident name/ID

        Returns:
            dict: Incident details
        """
        incident_name = params.get("incident_name")

        if not incident_name:
            return {
                "status": STATUS_ERROR,
                "error_type": "ValidationError",
                "error": "Missing required parameter 'incident_name'",
            }

        try:
            # Get access token
            access_token = await self._get_access_token()

            # Build API URL
            api_url = self._build_api_url()
            endpoint = f"{api_url}{SENTINEL_API_INCIDENTS}/{incident_name}"

            response = await self.http_request(
                endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"api-version": SENTINEL_API_VERSION},
                timeout=DEFAULT_TIMEOUT,
            )
            incident = response.json()

            return {
                "status": STATUS_SUCCESS,
                "incident_id": incident.get("id"),
                "incident_name": incident.get("name"),
                "incident": incident,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    def _build_api_url(self) -> str:
        """Build Sentinel API base URL from settings."""
        subscription_id = self.settings.get("subscription_id")
        resource_group = self.settings.get("resource_group_name")
        workspace_name = self.settings.get("workspace_name")

        if not subscription_id or not resource_group or not workspace_name:
            raise ValueError(ERROR_MSG_MISSING_SETTINGS)

        return SENTINEL_API_URL.format(
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
        )

    async def _get_access_token(self) -> str:
        """Get Azure AD access token for Sentinel API."""
        tenant_id = self.settings.get("tenant_id")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")

        if not tenant_id or not client_id or not client_secret:
            raise ValueError(ERROR_MSG_MISSING_CREDENTIALS)

        login_url = SENTINEL_LOGIN_URL.format(tenant_id=tenant_id)

        login_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": SENTINEL_LOGIN_SCOPE,
            "grant_type": "client_credentials",
        }

        response = await self.http_request(
            login_url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=login_payload,
            timeout=DEFAULT_TIMEOUT,
        )
        token_data = response.json()

        return token_data[SENTINEL_JSON_ACCESS_TOKEN]

class UpdateIncidentAction(IntegrationAction):
    """Update an existing incident."""

    async def execute(self, **params) -> dict[str, Any]:
        """Update incident.

        Args:
            incident_name: Incident name/ID
            severity: Updated severity (optional)
            status: Updated status (optional)
            title: Updated title (optional)
            description: Updated description (optional)
            owner_upn: Owner user principal name (optional)
            classification: Classification when closing (optional)
            classification_comment: Comment for classification (optional)
            classification_reason: Reason for classification (optional)

        Returns:
            dict: Updated incident details
        """
        incident_name = params.get("incident_name")

        if not incident_name:
            return {
                "status": STATUS_ERROR,
                "error_type": "ValidationError",
                "error": "Missing required parameter 'incident_name'",
            }

        try:
            # Get access token
            access_token = await self._get_access_token()

            # Build API URL
            api_url = self._build_api_url()
            endpoint = f"{api_url}{SENTINEL_API_INCIDENTS}/{incident_name}"

            # First, get the current incident
            response = await self.http_request(
                endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"api-version": SENTINEL_API_VERSION},
                timeout=DEFAULT_TIMEOUT,
            )
            incident = response.json()

            # Build update payload
            updated_incident = {
                "properties": {
                    "title": incident["properties"]["title"],
                    "severity": incident["properties"]["severity"],
                    "status": incident["properties"]["status"],
                }
            }

            # Apply updates
            if params.get("status"):
                updated_incident["properties"]["status"] = params["status"]
            if params.get("severity"):
                updated_incident["properties"]["severity"] = params["severity"]
            if params.get("title"):
                updated_incident["properties"]["title"] = params["title"]
            if params.get("description"):
                updated_incident["properties"]["description"] = params["description"]
            if params.get("owner_upn"):
                updated_incident["properties"]["owner"] = {
                    "userPrincipalName": params["owner_upn"]
                }

            # Add classification fields if status is Closed
            if updated_incident["properties"]["status"] == "Closed":
                if params.get("classification"):
                    updated_incident["properties"]["classification"] = params[
                        "classification"
                    ]
                if params.get("classification_comment"):
                    updated_incident["properties"]["classificationComment"] = params[
                        "classification_comment"
                    ]
                if params.get("classification_reason"):
                    updated_incident["properties"]["classificationReason"] = params[
                        "classification_reason"
                    ]

            # Send update request
            response = await self.http_request(
                endpoint,
                method="PUT",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"api-version": SENTINEL_API_VERSION},
                json_data=updated_incident,
                timeout=DEFAULT_TIMEOUT,
            )
            result = response.json()

            return {
                "status": STATUS_SUCCESS,
                "incident_id": result.get("id"),
                "incident_name": result.get("name"),
                "incident": result,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    def _build_api_url(self) -> str:
        """Build Sentinel API base URL from settings."""
        subscription_id = self.settings.get("subscription_id")
        resource_group = self.settings.get("resource_group_name")
        workspace_name = self.settings.get("workspace_name")

        if not subscription_id or not resource_group or not workspace_name:
            raise ValueError(ERROR_MSG_MISSING_SETTINGS)

        return SENTINEL_API_URL.format(
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
        )

    async def _get_access_token(self) -> str:
        """Get Azure AD access token for Sentinel API."""
        tenant_id = self.settings.get("tenant_id")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")

        if not tenant_id or not client_id or not client_secret:
            raise ValueError(ERROR_MSG_MISSING_CREDENTIALS)

        login_url = SENTINEL_LOGIN_URL.format(tenant_id=tenant_id)

        login_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": SENTINEL_LOGIN_SCOPE,
            "grant_type": "client_credentials",
        }

        response = await self.http_request(
            login_url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=login_payload,
            timeout=DEFAULT_TIMEOUT,
        )
        token_data = response.json()

        return token_data[SENTINEL_JSON_ACCESS_TOKEN]

class AddIncidentCommentAction(IntegrationAction):
    """Add a comment to an incident."""

    async def execute(self, **params) -> dict[str, Any]:
        """Add comment to incident.

        Args:
            incident_name: Incident name/ID
            message: Comment message

        Returns:
            dict: Comment creation result
        """
        incident_name = params.get("incident_name")
        message = params.get("message")

        if not incident_name or not message:
            return {
                "status": STATUS_ERROR,
                "error_type": "ValidationError",
                "error": "Missing required parameters 'incident_name' and 'message'",
            }

        try:
            # Get access token
            access_token = await self._get_access_token()

            # Build API URL
            api_url = self._build_api_url()

            # Generate comment ID from timestamp
            comment_id = int(datetime.now(UTC).timestamp())
            endpoint = f"{api_url}{SENTINEL_API_INCIDENTS}/{incident_name}/comments/{comment_id}"

            payload = {"properties": {"message": message}}

            response = await self.http_request(
                endpoint,
                method="PUT",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"api-version": SENTINEL_API_VERSION},
                json_data=payload,
                timeout=DEFAULT_TIMEOUT,
            )
            result = response.json()

            return {
                "status": STATUS_SUCCESS,
                "comment": result,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    def _build_api_url(self) -> str:
        """Build Sentinel API base URL from settings."""
        subscription_id = self.settings.get("subscription_id")
        resource_group = self.settings.get("resource_group_name")
        workspace_name = self.settings.get("workspace_name")

        if not subscription_id or not resource_group or not workspace_name:
            raise ValueError(ERROR_MSG_MISSING_SETTINGS)

        return SENTINEL_API_URL.format(
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
        )

    async def _get_access_token(self) -> str:
        """Get Azure AD access token for Sentinel API."""
        tenant_id = self.settings.get("tenant_id")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")

        if not tenant_id or not client_id or not client_secret:
            raise ValueError(ERROR_MSG_MISSING_CREDENTIALS)

        login_url = SENTINEL_LOGIN_URL.format(tenant_id=tenant_id)

        login_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": SENTINEL_LOGIN_SCOPE,
            "grant_type": "client_credentials",
        }

        response = await self.http_request(
            login_url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=login_payload,
            timeout=DEFAULT_TIMEOUT,
        )
        token_data = response.json()

        return token_data[SENTINEL_JSON_ACCESS_TOKEN]

class GetIncidentEntitiesAction(IntegrationAction):
    """Get entities associated with an incident."""

    async def execute(self, **params) -> dict[str, Any]:
        """Get incident entities.

        Args:
            incident_name: Incident name/ID

        Returns:
            dict: List of entities
        """
        incident_name = params.get("incident_name")

        if not incident_name:
            return {
                "status": STATUS_ERROR,
                "error_type": "ValidationError",
                "error": "Missing required parameter 'incident_name'",
            }

        try:
            # Get access token
            access_token = await self._get_access_token()

            # Build API URL
            api_url = self._build_api_url()
            endpoint = f"{api_url}{SENTINEL_API_INCIDENTS}/{incident_name}/entities"

            response = await self.http_request(
                endpoint,
                method="POST",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"api-version": SENTINEL_API_VERSION},
                timeout=DEFAULT_TIMEOUT,
            )
            entities_data = response.json()

            total_entities = len(entities_data.get("entities", []))

            return {
                "status": STATUS_SUCCESS,
                "total_entities": total_entities,
                "entities": entities_data,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    def _build_api_url(self) -> str:
        """Build Sentinel API base URL from settings."""
        subscription_id = self.settings.get("subscription_id")
        resource_group = self.settings.get("resource_group_name")
        workspace_name = self.settings.get("workspace_name")

        if not subscription_id or not resource_group or not workspace_name:
            raise ValueError(ERROR_MSG_MISSING_SETTINGS)

        return SENTINEL_API_URL.format(
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
        )

    async def _get_access_token(self) -> str:
        """Get Azure AD access token for Sentinel API."""
        tenant_id = self.settings.get("tenant_id")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")

        if not tenant_id or not client_id or not client_secret:
            raise ValueError(ERROR_MSG_MISSING_CREDENTIALS)

        login_url = SENTINEL_LOGIN_URL.format(tenant_id=tenant_id)

        login_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": SENTINEL_LOGIN_SCOPE,
            "grant_type": "client_credentials",
        }

        response = await self.http_request(
            login_url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=login_payload,
            timeout=DEFAULT_TIMEOUT,
        )
        token_data = response.json()

        return token_data[SENTINEL_JSON_ACCESS_TOKEN]

class GetIncidentAlertsAction(IntegrationAction):
    """Get alerts associated with an incident."""

    async def execute(self, **params) -> dict[str, Any]:
        """Get incident alerts.

        Args:
            incident_name: Incident name/ID

        Returns:
            dict: List of alerts
        """
        incident_name = params.get("incident_name")

        if not incident_name:
            return {
                "status": STATUS_ERROR,
                "error_type": "ValidationError",
                "error": "Missing required parameter 'incident_name'",
            }

        try:
            # Get access token
            access_token = await self._get_access_token()

            # Build API URL
            api_url = self._build_api_url()
            endpoint = f"{api_url}{SENTINEL_API_INCIDENTS}/{incident_name}/alerts"

            response = await self.http_request(
                endpoint,
                method="POST",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"api-version": SENTINEL_API_VERSION},
                timeout=DEFAULT_TIMEOUT,
            )
            alerts_data = response.json()

            alerts = alerts_data.get("value", [])

            return {
                "status": STATUS_SUCCESS,
                "total_alerts": len(alerts),
                "alerts": alerts,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    def _build_api_url(self) -> str:
        """Build Sentinel API base URL from settings."""
        subscription_id = self.settings.get("subscription_id")
        resource_group = self.settings.get("resource_group_name")
        workspace_name = self.settings.get("workspace_name")

        if not subscription_id or not resource_group or not workspace_name:
            raise ValueError(ERROR_MSG_MISSING_SETTINGS)

        return SENTINEL_API_URL.format(
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
        )

    async def _get_access_token(self) -> str:
        """Get Azure AD access token for Sentinel API."""
        tenant_id = self.settings.get("tenant_id")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")

        if not tenant_id or not client_id or not client_secret:
            raise ValueError(ERROR_MSG_MISSING_CREDENTIALS)

        login_url = SENTINEL_LOGIN_URL.format(tenant_id=tenant_id)

        login_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": SENTINEL_LOGIN_SCOPE,
            "grant_type": "client_credentials",
        }

        response = await self.http_request(
            login_url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=login_payload,
            timeout=DEFAULT_TIMEOUT,
        )
        token_data = response.json()

        return token_data[SENTINEL_JSON_ACCESS_TOKEN]

class RunQueryAction(IntegrationAction):
    """Execute KQL query against Log Analytics workspace."""

    async def execute(self, **params) -> dict[str, Any]:
        """Run KQL query.

        Args:
            query: KQL query string
            timespan: Optional time interval (ISO 8601 duration)
            max_rows: Maximum rows to return (default: 3000)

        Returns:
            dict: Query results
        """
        query = params.get("query")
        timespan = params.get("timespan")
        max_rows = params.get("max_rows", 3000)

        if not query:
            return {
                "status": STATUS_ERROR,
                "error_type": "ValidationError",
                "error": "Missing required parameter 'query'",
            }

        if not isinstance(max_rows, int) or max_rows <= 0:
            return {
                "status": STATUS_ERROR,
                "error_type": "ValidationError",
                "error": ERROR_MSG_INVALID_MAX_ROWS,
            }

        try:
            # Get Log Analytics access token (different from Sentinel token)
            access_token = await self._get_loganalytics_token()

            # Build Log Analytics API URL
            workspace_id = self.settings.get("workspace_id")
            if not workspace_id:
                raise ValueError("Missing required setting 'workspace_id'")

            endpoint = LOGANALYTICS_API_URL.format(workspace_id=workspace_id)

            # Build payload
            payload = {"query": query, "maxRows": max_rows}
            if timespan:
                payload["timespan"] = timespan

            response = await self.http_request(
                endpoint,
                method="POST",
                headers={"Authorization": f"Bearer {access_token}"},
                json_data=payload,
                timeout=DEFAULT_TIMEOUT,
            )
            result_data = response.json()

            # Parse results into rows
            rows = []
            for table in result_data.get("tables", []):
                table_name = table.get("name")
                for row in table.get("rows", []):
                    row_data = {"SentinelTableName": table_name}
                    for i, entry in enumerate(row):
                        col_name = table["columns"][i]["name"]
                        row_data[col_name] = entry
                    rows.append(row_data)

            return {
                "status": STATUS_SUCCESS,
                "total_rows": len(rows),
                "rows": rows,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    async def _get_loganalytics_token(self) -> str:
        """Get Azure AD access token for Log Analytics API."""
        tenant_id = self.settings.get("tenant_id")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")

        if not tenant_id or not client_id or not client_secret:
            raise ValueError(ERROR_MSG_MISSING_CREDENTIALS)

        login_url = LOGANALYTICS_LOGIN_URL.format(tenant_id=tenant_id)

        login_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "resource": LOGANALYTICS_LOGIN_RESOURCE,
            "grant_type": "client_credentials",
        }

        response = await self.http_request(
            login_url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=login_payload,
            timeout=DEFAULT_TIMEOUT,
        )
        token_data = response.json()

        return token_data[SENTINEL_JSON_ACCESS_TOKEN]

# ── AlertSource actions ──────────────────────────────────────────────

class _SentinelAuthMixin:
    """Shared auth and URL helpers for Sentinel actions.

    Avoids repeating the same _build_api_url / _get_access_token on every
    action class.  Mixed into IntegrationAction subclasses.
    """

    def _build_api_url(self) -> str:
        """Build Sentinel API base URL from settings."""
        subscription_id = self.settings.get("subscription_id")
        resource_group = self.settings.get("resource_group_name")
        workspace_name = self.settings.get("workspace_name")

        if not subscription_id or not resource_group or not workspace_name:
            raise ValueError(ERROR_MSG_MISSING_SETTINGS)

        return SENTINEL_API_URL.format(
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
        )

    async def _get_access_token(self) -> str:
        """Get Azure AD access token for Sentinel API."""
        tenant_id = self.settings.get("tenant_id")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")

        if not tenant_id or not client_id or not client_secret:
            raise ValueError(ERROR_MSG_MISSING_CREDENTIALS)

        login_url = SENTINEL_LOGIN_URL.format(tenant_id=tenant_id)

        login_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": SENTINEL_LOGIN_SCOPE,
            "grant_type": "client_credentials",
        }

        response = await self.http_request(
            login_url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=login_payload,
            timeout=DEFAULT_TIMEOUT,
        )
        token_data = response.json()

        return token_data[SENTINEL_JSON_ACCESS_TOKEN]

class PullAlertsAction(_SentinelAuthMixin, IntegrationAction):
    """Pull incidents from Microsoft Sentinel.

    Project Symi: AlertSource archetype requires this action.
    Queries the Sentinel incidents API with time-range filtering.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Pull incidents from Sentinel workspace.

        Args:
            start_time: Start of time range (datetime or ISO string, optional).
                        Defaults to using settings.default_lookback_minutes.
            end_time: End of time range (datetime or ISO string, optional).
                      Defaults to now.

        Returns:
            dict: Alerts pulled with count and data.
        """
        now = datetime.now(UTC)
        start_time = params.get("start_time")
        end_time = params.get("end_time")

        if not end_time:
            end_time = now

        if not start_time:
            lookback_minutes = self.settings.get(
                "default_lookback_minutes", DEFAULT_LOOKBACK_MINUTES
            )
            start_time = end_time - timedelta(minutes=lookback_minutes)

        # Ensure strings are datetimes
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

        try:
            access_token = await self._get_access_token()
            api_url = self._build_api_url()
            endpoint = f"{api_url}{SENTINEL_API_INCIDENTS}"

            # OData filter: incidents created within the time range
            start_iso = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            filter_expr = f"properties/createdTimeUtc ge {start_iso}"

            limit = self.settings.get("pull_alerts_limit", DEFAULT_PULL_ALERTS_LIMIT)

            query_params: dict[str, Any] = {
                "api-version": SENTINEL_API_VERSION,
                "$filter": filter_expr,
                "$orderby": "properties/createdTimeUtc desc",
                "$top": limit,
            }

            incidents = await self._fetch_paginated(
                endpoint, access_token, query_params, limit
            )

            logger.info("sentinel_pull_alerts_success", count=len(incidents))

            return {
                "status": STATUS_SUCCESS,
                "alerts_count": len(incidents),
                "alerts": incidents,
                "message": f"Retrieved {len(incidents)} incidents",
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": "HTTPStatusError",
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "alerts_count": 0,
                "alerts": [],
            }
        except Exception as e:
            logger.error("sentinel_pull_alerts_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": f"Failed to pull alerts: {e!s}",
                "alerts_count": 0,
                "alerts": [],
            }

    async def _fetch_paginated(
        self, endpoint: str, access_token: str, params: dict, limit: int
    ) -> list[dict]:
        """Fetch paginated results from Sentinel API."""
        results: list[dict] = []
        next_link: str | None = None

        while True:
            if next_link:
                url = next_link
                current_params: dict = {}
            else:
                url = endpoint
                current_params = params

            response = await self.http_request(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=current_params,
                timeout=DEFAULT_TIMEOUT,
            )
            data = response.json()

            if SENTINEL_JSON_VALUE not in data:
                raise ValueError(ERROR_MSG_NO_VALUE)

            for item in data[SENTINEL_JSON_VALUE]:
                if len(results) >= limit:
                    break
                results.append(item)

            if len(results) >= limit or SENTINEL_JSON_NEXT_LINK not in data:
                break

            next_link = data[SENTINEL_JSON_NEXT_LINK]

        return results[:limit]

class AlertsToOcsfAction(_SentinelAuthMixin, IntegrationAction):
    """Normalize raw Sentinel incidents to OCSF Detection Finding v1.8.0.

    Delegates to SentinelOCSFNormalizer which produces full OCSF Detection
    Findings with metadata, finding_info, actor, and MITRE ATT&CK mapping.

    Project Symi: AlertSource archetype requires this action.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Normalize raw Sentinel incidents to OCSF format.

        Args:
            raw_alerts: List of raw Sentinel incident objects.

        Returns:
            dict with status, normalized_alerts (OCSF dicts), count, and errors.
        """
        from alert_normalizer.sentinel_ocsf import SentinelOCSFNormalizer

        raw_alerts = params.get("raw_alerts", [])
        logger.info("sentinel_alerts_to_ocsf_called", count=len(raw_alerts))

        normalizer = SentinelOCSFNormalizer()
        normalized = []
        errors = 0

        for alert in raw_alerts:
            try:
                ocsf_finding = normalizer.to_ocsf(alert)
                normalized.append(ocsf_finding)
            except Exception:
                incident_name = (
                    alert.get("name") if isinstance(alert, dict) else str(alert)[:80]
                )
                incident_number = (
                    alert.get("properties", {}).get("incidentNumber")
                    if isinstance(alert, dict)
                    else None
                )
                logger.exception(
                    "sentinel_incident_to_ocsf_failed",
                    incident_name=incident_name,
                    incident_number=incident_number,
                )
                errors += 1

        return {
            "status": STATUS_SUCCESS if errors == 0 else STATUS_PARTIAL,
            "normalized_alerts": normalized,
            "count": len(normalized),
            "errors": errors,
        }

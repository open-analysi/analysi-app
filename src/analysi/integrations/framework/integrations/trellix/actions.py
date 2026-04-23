"""Trellix EDR (formerly FireEye HX) integration actions.

Uses token-based authentication (username/password -> ``x-feapi-token`` header).

Auth flow: POST /hx/api/v3/token with Basic Auth -> receive token in
``x-feapi-token`` response header -> use token in subsequent requests.
"""

import contextlib
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ALERTS_ENDPOINT,
    AUTH_TOKEN_ENDPOINT,
    AUTH_TOKEN_HEADER,
    DEFAULT_LIST_LIMIT,
    DEFAULT_PORT,
    ERR_AUTH_FAILED,
    ERR_MISSING_BASE_URL,
    ERR_MISSING_CREDENTIALS,
    ERR_MISSING_PARAM,
    FILE_ACQUISITIONS_ENDPOINT,
    HOSTS_ENDPOINT,
    INDICATORS_ENDPOINT,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_base_url(settings: dict[str, Any]) -> str | None:
    """Build HX base URL from settings.

    Returns the base URL (scheme + host + port) or None if missing.
    """
    base_url = settings.get("base_url")
    if not base_url:
        return None
    base_url = base_url.rstrip("/")
    port = settings.get("port", DEFAULT_PORT)
    if port and f":{port}" not in base_url:
        base_url = f"{base_url}:{port}"
    return base_url

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

class HealthCheckAction(IntegrationAction):
    """Verify API connectivity by requesting an auth token."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Authenticate to the Trellix HX API and verify connectivity."""
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        if not username or not password:
            return self.error_result(
                ERR_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        base_url = _build_base_url(self.settings)
        if not base_url:
            return self.error_result(
                ERR_MISSING_BASE_URL, error_type="ConfigurationError"
            )

        try:
            response = await self.http_request(
                url=f"{base_url}{AUTH_TOKEN_ENDPOINT}",
                method="GET",
                auth=(username, password),
            )
            # HX returns 204 with token in header on success
            token = response.headers.get(AUTH_TOKEN_HEADER)
            if not token:
                return self.error_result(
                    ERR_AUTH_FAILED, error_type="AuthenticationError"
                )

            return self.success_result(
                data={
                    "healthy": True,
                    "api_version": "v3",
                    "message": "Trellix HX API is accessible",
                }
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                return self.error_result(
                    ERR_AUTH_FAILED, error_type="AuthenticationError"
                )
            return self.error_result(e)
        except Exception as e:
            logger.error("trellix_health_check_failed", error=str(e))
            return self.error_result(e)

    def _get_raise_on_status(self) -> bool:
        """Health check: 204 is success, do not auto-raise for it."""
        return False

class _TrellixAuthMixin:
    """Mixin providing token authentication for Trellix HX actions.

    Each action must authenticate first to obtain a session token. This
    mixin factors out the shared authentication logic.
    """

    async def _authenticate(self) -> tuple[str | None, dict[str, Any] | None]:
        """Authenticate and return (token, None) or (None, error_result).

        Returns:
            Tuple of (token, None) on success or (None, error_dict) on failure.
        """
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        if not username or not password:
            return None, self.error_result(
                ERR_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        base_url = _build_base_url(self.settings)
        if not base_url:
            return None, self.error_result(
                ERR_MISSING_BASE_URL, error_type="ConfigurationError"
            )

        try:
            response = await self.http_request(
                url=f"{base_url}{AUTH_TOKEN_ENDPOINT}",
                method="GET",
                auth=(username, password),
            )
            token = response.headers.get(AUTH_TOKEN_HEADER)
            if not token:
                return None, self.error_result(
                    ERR_AUTH_FAILED, error_type="AuthenticationError"
                )
            return token, None
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                return None, self.error_result(
                    ERR_AUTH_FAILED, error_type="AuthenticationError"
                )
            return None, self.error_result(e)
        except Exception as e:
            return None, self.error_result(e)

    def _token_headers(self, token: str) -> dict[str, str]:
        """Build request headers with the auth token."""
        return {AUTH_TOKEN_HEADER: token, "Accept": "application/json"}

class GetEndpointAction(_TrellixAuthMixin, IntegrationAction):
    """Get system information for an endpoint (host)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get endpoint details by agent ID.

        Args:
            agent_id: HX agent identifier.
        """
        agent_id = kwargs.get("agent_id")
        if not agent_id:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="agent_id"),
                error_type="ValidationError",
            )

        token, err = await self._authenticate()
        if err:
            return err

        base_url = _build_base_url(self.settings)

        try:
            response = await self.http_request(
                url=f"{base_url}{HOSTS_ENDPOINT}/{agent_id}/sysinfo",
                headers=self._token_headers(token),
            )
            result = response.json()
            sysinfo = result.get("data", {})

            return self.success_result(
                data={
                    "agent_id": agent_id,
                    "hostname": sysinfo.get("hostname"),
                    "primary_ip": sysinfo.get("primaryIpAddress"),
                    "os": sysinfo.get("OS"),
                    "domain": sysinfo.get("domain"),
                    "mac": sysinfo.get("MAC"),
                    "full_data": sysinfo,
                }
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("trellix_endpoint_not_found", agent_id=agent_id)
                return self.success_result(
                    not_found=True,
                    data={"agent_id": agent_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListEndpointsAction(_TrellixAuthMixin, IntegrationAction):
    """List and search endpoints on HX."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List endpoints with optional search and limit.

        Args:
            search: Optional search term to filter endpoints.
            limit: Maximum number of results to return.
        """
        token, err = await self._authenticate()
        if err:
            return err

        base_url = _build_base_url(self.settings)
        params: dict[str, Any] = {}

        search = kwargs.get("search")
        if search:
            params["search"] = search

        limit = kwargs.get("limit", DEFAULT_LIST_LIMIT)
        if limit is not None:
            try:
                limit = int(limit)
                if limit <= 0:
                    return self.error_result(
                        "limit must be a positive integer",
                        error_type="ValidationError",
                    )
                params["limit"] = limit
            except (ValueError, TypeError):
                return self.error_result(
                    "limit must be a valid integer",
                    error_type="ValidationError",
                )

        try:
            response = await self.http_request(
                url=f"{base_url}{HOSTS_ENDPOINT}",
                params=params,
                headers=self._token_headers(token),
            )
            result = response.json()
            data = result.get("data", {})

            return self.success_result(
                data={
                    "total": data.get("total", 0),
                    "entries": data.get("entries", []),
                    "full_data": result,
                }
            )
        except Exception as e:
            return self.error_result(e)

class QuarantineEndpointAction(_TrellixAuthMixin, IntegrationAction):
    """Request containment (quarantine) for an endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Contain an endpoint by agent ID.

        Args:
            agent_id: HX agent identifier.
        """
        agent_id = kwargs.get("agent_id")
        if not agent_id:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="agent_id"),
                error_type="ValidationError",
            )

        token, err = await self._authenticate()
        if err:
            return err

        base_url = _build_base_url(self.settings)

        try:
            response = await self.http_request(
                url=f"{base_url}{HOSTS_ENDPOINT}/{agent_id}/containment",
                method="POST",
                headers=self._token_headers(token),
            )
            result = response.json()

            return self.success_result(
                data={
                    "agent_id": agent_id,
                    "message": result.get("message", "Containment requested"),
                    "full_data": result,
                }
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                return self.success_result(
                    data={
                        "agent_id": agent_id,
                        "message": "Endpoint is already contained or containment pending",
                    }
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class UnquarantineEndpointAction(_TrellixAuthMixin, IntegrationAction):
    """Cancel containment (unquarantine) for an endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Release an endpoint from containment by agent ID.

        Args:
            agent_id: HX agent identifier.
        """
        agent_id = kwargs.get("agent_id")
        if not agent_id:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="agent_id"),
                error_type="ValidationError",
            )

        token, err = await self._authenticate()
        if err:
            return err

        base_url = _build_base_url(self.settings)

        try:
            response = await self.http_request(
                url=f"{base_url}{HOSTS_ENDPOINT}/{agent_id}/containment",
                method="DELETE",
                headers=self._token_headers(token),
            )
            # DELETE may return 204 (no content) or JSON
            result = {}
            if response.text:
                with contextlib.suppress(Exception):
                    result = response.json()

            return self.success_result(
                data={
                    "agent_id": agent_id,
                    "message": result.get(
                        "message", "Containment cancellation requested"
                    ),
                    "full_data": result,
                }
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    data={
                        "agent_id": agent_id,
                        "message": "Endpoint is not currently contained",
                    }
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class GetAlertAction(_TrellixAuthMixin, IntegrationAction):
    """Get details for a specific alert by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get alert details by alert ID.

        Args:
            alert_id: HX alert identifier.
        """
        alert_id = kwargs.get("alert_id")
        if not alert_id:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="alert_id"),
                error_type="ValidationError",
            )

        token, err = await self._authenticate()
        if err:
            return err

        base_url = _build_base_url(self.settings)

        try:
            response = await self.http_request(
                url=f"{base_url}{ALERTS_ENDPOINT}/{alert_id}",
                headers=self._token_headers(token),
            )
            result = response.json()
            # connector response flattens the data key
            alert_data = result.get("data", result)

            return self.success_result(data=alert_data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("trellix_alert_not_found", alert_id=alert_id)
                return self.success_result(
                    not_found=True,
                    data={"alert_id": alert_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListAlertsAction(_TrellixAuthMixin, IntegrationAction):
    """List security alerts from HX."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List alerts with optional filtering.

        Args:
            limit: Maximum number of alerts to return.
            offset: Pagination offset.
            sort: Sort field (e.g., 'reported_at+descending').
            min_id: Minimum alert ID for filtering.
            agent_id: Filter by agent/host ID.
        """
        token, err = await self._authenticate()
        if err:
            return err

        base_url = _build_base_url(self.settings)
        params: dict[str, Any] = {}

        limit = kwargs.get("limit", DEFAULT_LIST_LIMIT)
        if limit is not None:
            try:
                params["limit"] = int(limit)
            except (ValueError, TypeError):
                return self.error_result(
                    "limit must be a valid integer",
                    error_type="ValidationError",
                )

        offset = kwargs.get("offset")
        if offset is not None:
            try:
                params["offset"] = int(offset)
            except (ValueError, TypeError):
                return self.error_result(
                    "offset must be a valid integer",
                    error_type="ValidationError",
                )

        sort = kwargs.get("sort")
        if sort:
            params["sort"] = sort

        min_id = kwargs.get("min_id")
        if min_id:
            params["min_id"] = min_id

        agent_id = kwargs.get("agent_id")
        if agent_id:
            params["agent._id"] = agent_id

        try:
            response = await self.http_request(
                url=f"{base_url}{ALERTS_ENDPOINT}",
                params=params,
                headers=self._token_headers(token),
            )
            result = response.json()
            data = result.get("data", {})

            return self.success_result(
                data={
                    "total": data.get("total", 0),
                    "entries": data.get("entries", []),
                    "full_data": result,
                }
            )
        except Exception as e:
            return self.error_result(e)

class SearchIocsAction(_TrellixAuthMixin, IntegrationAction):
    """Search for indicators of compromise (IOCs) in HX."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search IOCs/indicators.

        Args:
            search: Search term to filter indicators.
            limit: Maximum number of results.
            category: IOC category filter.
        """
        token, err = await self._authenticate()
        if err:
            return err

        base_url = _build_base_url(self.settings)
        params: dict[str, Any] = {}

        search = kwargs.get("search")
        if search:
            params["search"] = search

        limit = kwargs.get("limit", DEFAULT_LIST_LIMIT)
        if limit is not None:
            try:
                params["limit"] = int(limit)
            except (ValueError, TypeError):
                return self.error_result(
                    "limit must be a valid integer",
                    error_type="ValidationError",
                )

        category = kwargs.get("category")
        if category:
            params["category"] = category

        try:
            response = await self.http_request(
                url=f"{base_url}{INDICATORS_ENDPOINT}",
                params=params,
                headers=self._token_headers(token),
            )
            result = response.json()
            data = result.get("data", {})

            return self.success_result(
                data={
                    "total": data.get("total", 0),
                    "entries": data.get("entries", []),
                    "full_data": result,
                }
            )
        except Exception as e:
            return self.error_result(e)

class AddIocAction(_TrellixAuthMixin, IntegrationAction):
    """Add an indicator of compromise to HX."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add an IOC to the detection list.

        Args:
            category: IOC category (e.g., 'custom').
            name: Display name for the indicator.
            description: Description of the indicator.
        """
        category = kwargs.get("category")
        if not category:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="category"),
                error_type="ValidationError",
            )

        name = kwargs.get("name")
        if not name:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="name"),
                error_type="ValidationError",
            )

        token, err = await self._authenticate()
        if err:
            return err

        base_url = _build_base_url(self.settings)

        ioc_data: dict[str, Any] = {
            "name": name,
        }
        description = kwargs.get("description")
        if description:
            ioc_data["description"] = description

        try:
            response = await self.http_request(
                url=f"{base_url}{INDICATORS_ENDPOINT}/{category}",
                method="POST",
                headers=self._token_headers(token),
                json_data=ioc_data,
            )
            result = response.json()
            indicator = result.get("data", result)

            return self.success_result(
                data={
                    "category": category,
                    "name": name,
                    "indicator": indicator,
                    "full_data": result,
                }
            )
        except Exception as e:
            return self.error_result(e)

class GetFileAcquisitionAction(_TrellixAuthMixin, IntegrationAction):
    """Get the status and details of a file acquisition."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get file acquisition status by acquisition ID.

        Args:
            acquisition_id: File acquisition identifier.
        """
        acquisition_id = kwargs.get("acquisition_id")
        if not acquisition_id:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="acquisition_id"),
                error_type="ValidationError",
            )

        token, err = await self._authenticate()
        if err:
            return err

        base_url = _build_base_url(self.settings)

        try:
            response = await self.http_request(
                url=f"{base_url}{FILE_ACQUISITIONS_ENDPOINT}/{acquisition_id}",
                headers=self._token_headers(token),
            )
            result = response.json()
            # connector response flattens the data key
            acq_data = result.get("data", result)

            return self.success_result(data=acq_data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "trellix_acquisition_not_found",
                    acquisition_id=acquisition_id,
                )
                return self.success_result(
                    not_found=True,
                    data={"acquisition_id": acquisition_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

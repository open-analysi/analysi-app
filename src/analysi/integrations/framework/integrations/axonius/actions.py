"""Axonius cyber asset management integration actions.

Built from Axonius REST API v2 documentation.
Axonius provides a unified view of all assets (devices, users) across
adapters. Authentication uses api-key + api-secret headers.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_VERSION,
    CREDENTIAL_API_KEY,
    CREDENTIAL_API_SECRET,
    DEFAULT_DEVICE_FIELDS,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_FIELDS,
    ENDPOINT_ABOUT,
    ENDPOINT_DEVICES,
    ENDPOINT_DEVICES_BY_ID,
    ENDPOINT_USERS,
    ENDPOINT_USERS_BY_ID,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    HEADER_API_KEY,
    HEADER_API_SECRET,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_DEVICE_ID,
    MSG_MISSING_QUERY,
    MSG_MISSING_USER_ID,
    MSG_SERVER_CONNECTION,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_api_url(base_url: str, endpoint: str) -> str:
    """Build full API URL from base URL and endpoint.

    Args:
        base_url: Axonius instance base URL (e.g., https://myco.axonius.com)
        endpoint: API endpoint path (e.g., system/meta/about)

    Returns:
        Full URL string
    """
    base = base_url.rstrip("/")
    return f"{base}/api/{API_VERSION}/{endpoint}"

def _get_auth_headers(api_key: str, api_secret: str) -> dict[str, str]:
    """Build authentication headers for Axonius API.

    Args:
        api_key: API key
        api_secret: API secret

    Returns:
        Headers dict with api-key and api-secret
    """
    return {
        HEADER_API_KEY: api_key,
        HEADER_API_SECRET: api_secret,
        "Content-Type": "application/json",
    }

def _validate_credentials(
    credentials: dict[str, Any],
) -> tuple[bool, str, str, str]:
    """Validate and extract credentials.

    Args:
        credentials: Credentials dict from Vault

    Returns:
        Tuple of (is_valid, error_message, api_key, api_secret)
    """
    api_key = credentials.get(CREDENTIAL_API_KEY, "")
    api_secret = credentials.get(CREDENTIAL_API_SECRET, "")
    if not api_key or not api_secret:
        return False, MSG_MISSING_CREDENTIALS, "", ""
    return True, "", api_key, api_secret

def _validate_base_url(settings: dict[str, Any]) -> tuple[bool, str, str]:
    """Validate and extract base URL from settings.

    Args:
        settings: Integration settings dict

    Returns:
        Tuple of (is_valid, error_message, base_url)
    """
    base_url = settings.get(SETTINGS_BASE_URL, "")
    if not base_url:
        return False, MSG_MISSING_BASE_URL, ""
    return True, "", base_url

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Axonius API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Axonius API connectivity.

        Calls GET /api/v2/system/meta/about to verify credentials and connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        # Validate credentials
        valid, error, api_key, api_secret = _validate_credentials(self.credentials)
        if not valid:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": error,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        # Validate base URL
        url_valid, url_error, base_url = _validate_base_url(self.settings)
        if not url_valid:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": url_error,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        url = _get_api_url(base_url, ENDPOINT_ABOUT)
        headers = _get_auth_headers(api_key, api_secret)

        try:
            response = await self.http_request(url, headers=headers, timeout=timeout)
            result = response.json()

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Axonius API is accessible",
                "data": {
                    "healthy": True,
                    "version": result.get("Build Version", ""),
                    "instance_name": result.get("Customer Name", ""),
                },
            }

        except httpx.TimeoutException as e:
            logger.error("axonius_health_check_timeout", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"Request timed out after {timeout} seconds",
                "error_type": ERROR_TYPE_TIMEOUT,
                "data": {"healthy": False},
            }
        except httpx.RequestError as e:
            logger.error("axonius_health_check_connection_error", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_SERVER_CONNECTION,
                "error_type": ERROR_TYPE_HTTP,
                "data": {"healthy": False},
            }
        except Exception as e:
            logger.error("axonius_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP,
                "data": {"healthy": False},
            }

class GetDeviceAction(IntegrationAction):
    """Get device details by internal_axon_id."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get device details from Axonius by internal_axon_id.

        Args:
            **kwargs: Must contain 'internal_axon_id'

        Returns:
            Result with device details or error
        """
        # Validate required parameters
        device_id = kwargs.get("internal_axon_id")
        if not device_id or not isinstance(device_id, str):
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_DEVICE_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        valid, error, api_key, api_secret = _validate_credentials(self.credentials)
        if not valid:
            return {
                "status": STATUS_ERROR,
                "error": error,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Validate base URL
        url_valid, url_error, base_url = _validate_base_url(self.settings)
        if not url_valid:
            return {
                "status": STATUS_ERROR,
                "error": url_error,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        url = _get_api_url(base_url, ENDPOINT_DEVICES_BY_ID.format(device_id))
        headers = _get_auth_headers(api_key, api_secret)

        try:
            response = await self.http_request(url, headers=headers, timeout=timeout)
            result = response.json()

            return {
                "status": STATUS_SUCCESS,
                "internal_axon_id": device_id,
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("axonius_device_not_found", internal_axon_id=device_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "internal_axon_id": device_id,
                    "data": {},
                }
            logger.error(
                "axonius_get_device_failed",
                internal_axon_id=device_id,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP,
            }
        except httpx.TimeoutException:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out after {timeout} seconds",
                "error_type": ERROR_TYPE_TIMEOUT,
            }
        except httpx.RequestError:
            return {
                "status": STATUS_ERROR,
                "error": MSG_SERVER_CONNECTION,
                "error_type": ERROR_TYPE_HTTP,
            }
        except Exception as e:
            logger.error(
                "axonius_get_device_failed",
                internal_axon_id=device_id,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP,
            }

class SearchDevicesAction(IntegrationAction):
    """Search devices by query (hostname, IP, etc.)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search devices in Axonius by query.

        The query uses Axonius Query Language (AQL). The query string is sent
        as-is to the POST /devices endpoint.

        Args:
            **kwargs: Must contain 'query'. Optional: 'fields', 'max_rows'

        Returns:
            Result with matching devices or error
        """
        # Validate required parameters
        query = kwargs.get("query")
        if not query or not isinstance(query, str):
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_QUERY,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        valid, error, api_key, api_secret = _validate_credentials(self.credentials)
        if not valid:
            return {
                "status": STATUS_ERROR,
                "error": error,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Validate base URL
        url_valid, url_error, base_url = _validate_base_url(self.settings)
        if not url_valid:
            return {
                "status": STATUS_ERROR,
                "error": url_error,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        max_rows = kwargs.get("max_rows", DEFAULT_PAGE_SIZE)
        fields = kwargs.get("fields", DEFAULT_DEVICE_FIELDS)

        url = _get_api_url(base_url, ENDPOINT_DEVICES)
        headers = _get_auth_headers(api_key, api_secret)

        body = {
            "filter": query,
            "fields": fields,
            "row_start": 0,
            "page_size": max_rows,
        }

        try:
            response = await self.http_request(
                url,
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )
            result = response.json()

            assets = result.get("assets", [])
            page = result.get("page", {})

            return {
                "status": STATUS_SUCCESS,
                "query": query,
                "summary": {
                    "total_results": page.get("totalResources", len(assets)),
                    "returned": len(assets),
                },
                "devices": assets,
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            logger.error("axonius_search_devices_failed", query=query, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP,
            }
        except httpx.TimeoutException:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out after {timeout} seconds",
                "error_type": ERROR_TYPE_TIMEOUT,
            }
        except httpx.RequestError:
            return {
                "status": STATUS_ERROR,
                "error": MSG_SERVER_CONNECTION,
                "error_type": ERROR_TYPE_HTTP,
            }
        except Exception as e:
            logger.error("axonius_search_devices_failed", query=query, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP,
            }

class GetUserAction(IntegrationAction):
    """Get user details by internal_axon_id."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get user details from Axonius by internal_axon_id.

        Args:
            **kwargs: Must contain 'internal_axon_id'

        Returns:
            Result with user details or error
        """
        # Validate required parameters
        user_id = kwargs.get("internal_axon_id")
        if not user_id or not isinstance(user_id, str):
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_USER_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        valid, error, api_key, api_secret = _validate_credentials(self.credentials)
        if not valid:
            return {
                "status": STATUS_ERROR,
                "error": error,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Validate base URL
        url_valid, url_error, base_url = _validate_base_url(self.settings)
        if not url_valid:
            return {
                "status": STATUS_ERROR,
                "error": url_error,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        url = _get_api_url(base_url, ENDPOINT_USERS_BY_ID.format(user_id))
        headers = _get_auth_headers(api_key, api_secret)

        try:
            response = await self.http_request(url, headers=headers, timeout=timeout)
            result = response.json()

            return {
                "status": STATUS_SUCCESS,
                "internal_axon_id": user_id,
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("axonius_user_not_found", internal_axon_id=user_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "internal_axon_id": user_id,
                    "data": {},
                }
            logger.error(
                "axonius_get_user_failed",
                internal_axon_id=user_id,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP,
            }
        except httpx.TimeoutException:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out after {timeout} seconds",
                "error_type": ERROR_TYPE_TIMEOUT,
            }
        except httpx.RequestError:
            return {
                "status": STATUS_ERROR,
                "error": MSG_SERVER_CONNECTION,
                "error_type": ERROR_TYPE_HTTP,
            }
        except Exception as e:
            logger.error(
                "axonius_get_user_failed",
                internal_axon_id=user_id,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP,
            }

class SearchUsersAction(IntegrationAction):
    """Search users by query (email, username, etc.)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search users in Axonius by query.

        The query uses Axonius Query Language (AQL). The query string is sent
        as-is to the POST /users endpoint.

        Args:
            **kwargs: Must contain 'query'. Optional: 'fields', 'max_rows'

        Returns:
            Result with matching users or error
        """
        # Validate required parameters
        query = kwargs.get("query")
        if not query or not isinstance(query, str):
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_QUERY,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        valid, error, api_key, api_secret = _validate_credentials(self.credentials)
        if not valid:
            return {
                "status": STATUS_ERROR,
                "error": error,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Validate base URL
        url_valid, url_error, base_url = _validate_base_url(self.settings)
        if not url_valid:
            return {
                "status": STATUS_ERROR,
                "error": url_error,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        max_rows = kwargs.get("max_rows", DEFAULT_PAGE_SIZE)
        fields = kwargs.get("fields", DEFAULT_USER_FIELDS)

        url = _get_api_url(base_url, ENDPOINT_USERS)
        headers = _get_auth_headers(api_key, api_secret)

        body = {
            "filter": query,
            "fields": fields,
            "row_start": 0,
            "page_size": max_rows,
        }

        try:
            response = await self.http_request(
                url,
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )
            result = response.json()

            assets = result.get("assets", [])
            page = result.get("page", {})

            return {
                "status": STATUS_SUCCESS,
                "query": query,
                "summary": {
                    "total_results": page.get("totalResources", len(assets)),
                    "returned": len(assets),
                },
                "users": assets,
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            logger.error("axonius_search_users_failed", query=query, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP,
            }
        except httpx.TimeoutException:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out after {timeout} seconds",
                "error_type": ERROR_TYPE_TIMEOUT,
            }
        except httpx.RequestError:
            return {
                "status": STATUS_ERROR,
                "error": MSG_SERVER_CONNECTION,
                "error_type": ERROR_TYPE_HTTP,
            }
        except Exception as e:
            logger.error("axonius_search_users_failed", query=query, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_HTTP,
            }

class GetDeviceByHostnameAction(IntegrationAction):
    """Convenience action: search devices by hostname."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search devices by hostname.

        Builds an AQL query for hostname matching and delegates
        to the search_devices logic.

        Args:
            **kwargs: Must contain 'hostname'. Optional: 'max_rows'

        Returns:
            Result with matching devices or error
        """
        hostname = kwargs.get("hostname")
        if not hostname or not isinstance(hostname, str):
            return {
                "status": STATUS_ERROR,
                "error": "Hostname is required",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Build AQL query for hostname
        query = f'(specific_data.data.hostname == regex("{hostname}", "i"))'

        # Delegate to search_devices logic
        search_action = SearchDevicesAction(
            integration_id=self.integration_id,
            action_id=self.action_id,
            settings=self.settings,
            credentials=self.credentials,
            ctx=self.ctx,
        )

        max_rows = kwargs.get("max_rows", DEFAULT_PAGE_SIZE)
        result = await search_action.execute(query=query, max_rows=max_rows)

        # Add hostname context to result
        if result.get("status") == STATUS_SUCCESS:
            result["hostname"] = hostname

        return result

class GetDeviceByIpAction(IntegrationAction):
    """Convenience action: search devices by IP address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search devices by IP address.

        Builds an AQL query for IP matching and delegates
        to the search_devices logic.

        Args:
            **kwargs: Must contain 'ip'. Optional: 'max_rows'

        Returns:
            Result with matching devices or error
        """
        ip = kwargs.get("ip")
        if not ip or not isinstance(ip, str):
            return {
                "status": STATUS_ERROR,
                "error": "IP address is required",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Build AQL query for IP address
        query = f'(specific_data.data.network_interfaces.ips == "{ip}")'

        # Delegate to search_devices logic
        search_action = SearchDevicesAction(
            integration_id=self.integration_id,
            action_id=self.action_id,
            settings=self.settings,
            credentials=self.credentials,
            ctx=self.ctx,
        )

        max_rows = kwargs.get("max_rows", DEFAULT_PAGE_SIZE)
        result = await search_action.execute(query=query, max_rows=max_rows)

        # Add IP context to result
        if result.get("status") == STATUS_SUCCESS:
            result["ip_address"] = ip

        return result

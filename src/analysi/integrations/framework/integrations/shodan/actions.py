"""Shodan integration actions for threat intelligence lookups."""

from typing import Any

import httpx
import validators

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_API_KEY,
    DEFAULT_TIMEOUT,
    ENDPOINT_API_INFO,
    ENDPOINT_HOST_DETAIL,
    ENDPOINT_HOST_SEARCH,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    MSG_INVALID_DOMAIN,
    MSG_INVALID_IP,
    MSG_INVALID_JSON,
    MSG_MISSING_API_KEY,
    MSG_SERVER_CONNECTION,
    SETTINGS_TIMEOUT,
    SHODAN_BASE_URL,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# ============================================================================
# VALIDATION UTILITIES
# ============================================================================

def _validate_ip_safe(ip_address: str) -> tuple[bool, str]:
    """Validate IP address format.

    Args:
        ip_address: IP address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not ip_address or not isinstance(ip_address, str):
        return False, MSG_INVALID_IP
    if validators.ipv4(ip_address) or validators.ipv6(ip_address):
        return True, ""
    return False, "Invalid IP address format"

def _validate_domain_safe(domain: str) -> tuple[bool, str]:
    """Validate domain format.

    Args:
        domain: Domain to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not domain or not isinstance(domain, str):
        return False, MSG_INVALID_DOMAIN
    if validators.domain(domain):
        return True, ""
    return False, "Invalid domain format"

# ============================================================================
# API CLIENT HELPER
# ============================================================================

async def _make_shodan_request(
    action: IntegrationAction,
    endpoint: str,
    api_key: str,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Make HTTP request to Shodan API.

    Args:
        endpoint: API endpoint (without base URL)
        api_key: Shodan API key
        params: Query parameters
        timeout: Request timeout in seconds

    Returns:
        API response data

    Raises:
        Exception: On API errors
    """
    url = f"{SHODAN_BASE_URL}{endpoint}"

    # Add API key to parameters
    if params is None:
        params = {}
    params["key"] = api_key

    try:
        response = await action.http_request(url, params=params, timeout=timeout)

        # Parse JSON response (Shodan returns JSON even on errors)
        try:
            data = response.json()
        except Exception as e:
            logger.error(
                "failed_to_parse_json_response_from",
                endpoint=endpoint,
                error=str(e),
            )
            raise Exception(MSG_INVALID_JSON)

        # Check for error in response (Shodan may return 200 with error body)
        if "error" in data:
            raise Exception(data["error"])

        return data

    except httpx.TimeoutException as e:
        logger.error("shodan_api_timeout_for", endpoint=endpoint, error=str(e))
        raise Exception(f"Request timed out after {timeout} seconds")
    except httpx.HTTPStatusError as e:
        logger.error(
            "shodan_api_http_error_for",
            endpoint=endpoint,
            status_code=e.response.status_code,
        )
        if e.response.status_code == 401:
            raise Exception("Invalid API key")
        if e.response.status_code == 404:
            raise Exception("Resource not found")
        if e.response.status_code == 429:
            raise Exception("Rate limit exceeded")
        raise Exception(f"HTTP {e.response.status_code}: {e.response.text}")
    except httpx.RequestError as e:
        logger.error("shodan_api_connection_error_for", endpoint=endpoint, error=str(e))
        raise Exception(MSG_SERVER_CONNECTION)
    except Exception as e:
        if "timed out" in str(e).lower() or "timeout" in str(e).lower():
            raise Exception(f"Request timed out: {e}")
        raise

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Shodan API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Shodan API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Test API key with api-info endpoint
            result = await _make_shodan_request(
                self,
                ENDPOINT_API_INFO,
                api_key=api_key,
                timeout=timeout,
            )

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Shodan API is accessible",
                "data": {
                    "healthy": True,
                    "api_info": result,
                },
            }

        except Exception as e:
            logger.error("shodan_health_check_failed", error=str(e))
            error_msg = str(e).lower()
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": (
                    ERROR_TYPE_TIMEOUT
                    if "timeout" in error_msg or "timed out" in error_msg
                    else ERROR_TYPE_HTTP
                ),
                "data": {"healthy": False},
            }

class IpLookupAction(IntegrationAction):
    """Look up IP address information from Shodan."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get IP address information from Shodan.

        Args:
            **kwargs: Must contain 'ip' or 'ip_address'

        Returns:
            Result with IP information data or error
        """
        # Validate inputs - accept both 'ip' and 'ip_address' parameter names
        ip_address = kwargs.get("ip") or kwargs.get("ip_address")
        is_valid, error_msg = _validate_ip_safe(ip_address)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Query Shodan host endpoint
            endpoint = ENDPOINT_HOST_DETAIL.format(ip_address)
            result = await _make_shodan_request(
                self,
                endpoint,
                api_key=api_key,
                timeout=timeout,
            )

            # Extract key information
            data = result.get("data", [])
            open_ports = result.get("ports", [])
            hostnames = result.get("hostnames", [])

            return {
                "status": STATUS_SUCCESS,
                "ip_address": ip_address,
                "summary": {
                    "results": len(data),
                    "country": result.get("country_name", ""),
                    "open_ports": ", ".join(str(x) for x in open_ports)
                    if open_ports
                    else None,
                    "hostnames": ", ".join(str(x) for x in hostnames)
                    if hostnames
                    else None,
                },
                "services": data,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("shodan_ip_not_found", ip_address=ip_address)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ip_address": ip_address,
                    "summary": {"results": 0},
                    "services": [],
                }
            logger.error(
                "shodan_ip_lookup_failed_for", ip_address=ip_address, error=str(e)
            )
            error_msg = str(e).lower()
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": (
                    ERROR_TYPE_TIMEOUT
                    if "timeout" in error_msg or "timed out" in error_msg
                    else ERROR_TYPE_HTTP
                ),
            }

class DomainLookupAction(IntegrationAction):
    """Look up domain information from Shodan."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get domain information from Shodan.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with domain information data or error
        """
        # Validate inputs
        domain = kwargs.get("domain")
        is_valid, error_msg = _validate_domain_safe(domain)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # First try hostname-specific search
            params = {"query": f"hostname:{domain}"}
            result = await _make_shodan_request(
                self,
                ENDPOINT_HOST_SEARCH,
                api_key=api_key,
                params=params,
                timeout=timeout,
            )

            matches = result.get("matches", [])

            # If no results with hostname filter, try general search
            if not matches:
                logger.info(
                    "no_hostname_matches_for_trying_general_search", domain=domain
                )
                params = {"query": domain}
                result = await _make_shodan_request(
                    self,
                    ENDPOINT_HOST_SEARCH,
                    api_key=api_key,
                    params=params,
                    timeout=timeout,
                )
                matches = result.get("matches", [])

            return {
                "status": STATUS_SUCCESS,
                "domain": domain,
                "summary": {
                    "results": len(matches),
                },
                "matches": matches,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("shodan_domain_not_found", domain=domain)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "domain": domain,
                    "summary": {"results": 0},
                    "matches": [],
                }
            logger.error("shodan_domain_lookup_failed_for", domain=domain, error=str(e))
            error_msg = str(e).lower()
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": (
                    ERROR_TYPE_TIMEOUT
                    if "timeout" in error_msg or "timed out" in error_msg
                    else ERROR_TYPE_HTTP
                ),
            }

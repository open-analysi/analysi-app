"""Forescout integration actions for network access control.
Only Web API (REST/JSON) actions are included; DEX XML API actions
are deferred to a later migration.

Auth flow: POST username/password to /api/login, receive a JWT token.
Use that token as the Authorization header value for subsequent calls.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ACCEPT_HEADER,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    LOGIN_CONTENT_TYPE,
    MSG_HOST_IDENTIFIER_REQUIRED,
    MSG_JWT_FAILED,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_CREDENTIALS,
    WEB_HOSTS_ENDPOINT,
    WEB_LOGIN_ENDPOINT,
    WEB_POLICIES_ENDPOINT,
)

logger = get_logger(__name__)

# ============================================================================
# AUTH HELPERS
# ============================================================================

async def _get_jwt_token(action: IntegrationAction) -> tuple[bool, str]:
    """Obtain a JWT token from Forescout Web API.

    Posts username/password to /api/login and returns the raw token string.

    Args:
        action: The IntegrationAction instance (provides credentials, settings,
                http_request, and logging).

    Returns:
        Tuple of (success: bool, token_or_error: str).
        On success the second element is the JWT token.
        On failure the second element is the error message.
    """
    base_url = action.settings.get("base_url", "").rstrip("/")
    username = action.credentials.get("username")
    password = action.credentials.get("password")

    url = f"{base_url}{WEB_LOGIN_ENDPOINT}"

    try:
        response = await action.http_request(
            url=url,
            method="POST",
            headers={"Content-Type": LOGIN_CONTENT_TYPE},
            data={"username": username, "password": password},
        )
        token = response.text
        if not token or not token.strip():
            return False, MSG_JWT_FAILED
        return True, token.strip()
    except httpx.HTTPStatusError as e:
        msg = f"{MSG_JWT_FAILED}: HTTP {e.response.status_code}"
        return False, msg
    except Exception as e:
        msg = f"{MSG_JWT_FAILED}: {e}"
        return False, msg

async def _web_api_request(
    action: IntegrationAction,
    endpoint: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any] | str]:
    """Make an authenticated Web API request.

    Handles JWT acquisition and sets the proper headers.

    Args:
        action: The IntegrationAction instance.
        endpoint: API path (e.g., "/api/hosts").
        method: HTTP method.
        params: Optional query parameters.

    Returns:
        Tuple of (success, response_json_or_error_message).
    """
    base_url = action.settings.get("base_url", "").rstrip("/")

    # Acquire JWT
    ok, token_or_error = await _get_jwt_token(action)
    if not ok:
        return False, token_or_error

    url = f"{base_url}{endpoint}"
    headers = {
        "Authorization": token_or_error,
        "Accept": ACCEPT_HEADER,
    }

    try:
        response = await action.http_request(
            url=url,
            method=method,
            headers=headers,
            params=params,
        )
        return True, response.json()
    except httpx.HTTPStatusError as e:
        msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        return False, msg
    except Exception as e:
        return False, str(e)

def _validate_credentials(action: IntegrationAction) -> str | None:
    """Validate that required credentials are present.

    Returns:
        Error message string if validation fails, None if valid.
    """
    username = action.credentials.get("username")
    password = action.credentials.get("password")
    if not username or not password:
        return MSG_MISSING_CREDENTIALS
    return None

def _validate_base_url(action: IntegrationAction) -> str | None:
    """Validate that base_url setting is present.

    Returns:
        Error message string if validation fails, None if valid.
    """
    base_url = action.settings.get("base_url")
    if not base_url:
        return MSG_MISSING_BASE_URL
    return None

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Verify connectivity to the Forescout Web API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity by fetching hosts from the Web API.

        Returns:
            Success result with connectivity status, or error result.
        """
        cred_error = _validate_credentials(self)
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        url_error = _validate_base_url(self)
        if url_error:
            return self.error_result(url_error, error_type=ERROR_TYPE_CONFIGURATION)

        ok, result = await _web_api_request(self, WEB_HOSTS_ENDPOINT)
        if not ok:
            self.log_error("forescout_health_check_failed", error_msg=result)
            return self.error_result(result, error_type=ERROR_TYPE_AUTHENTICATION)

        return self.success_result(
            data={"healthy": True, "message": "Forescout Web API is accessible"},
            healthy=True,
        )

class ListHostsAction(IntegrationAction):
    """List hosts/endpoints visible to Forescout."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all hosts from the Forescout Web API.

        Returns:
            Success result with hosts array and count, or error result.
        """
        cred_error = _validate_credentials(self)
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        url_error = _validate_base_url(self)
        if url_error:
            return self.error_result(url_error, error_type=ERROR_TYPE_CONFIGURATION)

        ok, result = await _web_api_request(self, WEB_HOSTS_ENDPOINT)
        if not ok:
            return self.error_result(result)

        hosts = result.get("hosts", []) if isinstance(result, dict) else []

        return self.success_result(
            data={
                "hosts": hosts,
                "num_hosts": len(hosts),
            },
        )

class GetHostAction(IntegrationAction):
    """Get detailed properties of a specific host.

    Accepts one of: host_id, host_ip, or host_mac.
    Priority order matches the upstream: host_id > host_ip > host_mac.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get host details by ID, IP address, or MAC address.

        Args:
            **kwargs: Must contain at least one of:
                - host_id (int or str): Forescout host ID
                - host_ip (str): Host IP address
                - host_mac (str): Host MAC address

        Returns:
            Success result with host details, or error result.
        """
        cred_error = _validate_credentials(self)
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        url_error = _validate_base_url(self)
        if url_error:
            return self.error_result(url_error, error_type=ERROR_TYPE_CONFIGURATION)

        host_id = kwargs.get("host_id")
        host_ip = kwargs.get("host_ip")
        host_mac = kwargs.get("host_mac")

        # Validate host_id is a positive integer if provided
        if host_id is not None:
            try:
                host_id_int = int(host_id)
                if host_id_int <= 0:
                    return self.error_result(
                        "host_id must be a positive integer",
                        error_type=ERROR_TYPE_VALIDATION,
                    )
            except (ValueError, TypeError):
                return self.error_result(
                    "host_id must be a valid integer",
                    error_type=ERROR_TYPE_VALIDATION,
                )
            endpoint = f"{WEB_HOSTS_ENDPOINT}/{host_id_int}"
        elif host_ip:
            endpoint = f"{WEB_HOSTS_ENDPOINT}/ip/{host_ip}"
        elif host_mac:
            endpoint = f"{WEB_HOSTS_ENDPOINT}/mac/{host_mac}"
        else:
            return self.error_result(
                MSG_HOST_IDENTIFIER_REQUIRED,
                error_type=ERROR_TYPE_VALIDATION,
            )

        ok, result = await _web_api_request(self, endpoint)
        if not ok:
            # Check if this looks like a 404
            if isinstance(result, str) and "404" in result:
                self.log_info(
                    "forescout_host_not_found",
                    host_id=host_id,
                    host_ip=host_ip,
                    host_mac=host_mac,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "host_id": host_id,
                        "host_ip": host_ip,
                        "host_mac": host_mac,
                    },
                )
            return self.error_result(result)

        host = result.get("host", {}) if isinstance(result, dict) else {}

        return self.success_result(
            data={
                "host": host,
                "host_ip": host.get("ip", ""),
                "host_mac": host.get("mac", ""),
                "host_id": host.get("id", ""),
            },
        )

class ListPoliciesAction(IntegrationAction):
    """List Forescout policies."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all policies from the Forescout Web API.

        Returns:
            Success result with policies array and count, or error result.
        """
        cred_error = _validate_credentials(self)
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        url_error = _validate_base_url(self)
        if url_error:
            return self.error_result(url_error, error_type=ERROR_TYPE_CONFIGURATION)

        ok, result = await _web_api_request(self, WEB_POLICIES_ENDPOINT)
        if not ok:
            return self.error_result(result)

        policies = result.get("policies", []) if isinstance(result, dict) else []

        return self.success_result(
            data={
                "policies": policies,
                "num_policies": len(policies),
            },
        )

class GetActiveSessionsAction(IntegrationAction):
    """Get active sessions filtered by rule IDs and/or property values."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get active sessions from the Forescout Web API.

        Args:
            **kwargs: Optional filters:
                - rule_id (str): Comma-separated list of policy/rule IDs
                - prop_val (str): Comma-separated list of property=value filters

        Returns:
            Success result with hosts/sessions array and count, or error result.
        """
        cred_error = _validate_credentials(self)
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        url_error = _validate_base_url(self)
        if url_error:
            return self.error_result(url_error, error_type=ERROR_TYPE_CONFIGURATION)

        # Build query parameters from optional filters
        rule_id = kwargs.get("rule_id")
        prop_val = kwargs.get("prop_val")

        params: dict[str, str] = {}

        if rule_id:
            # Validate comma-separated format (no empty items)
            rule_id_list = [item.strip() for item in rule_id.split(",")]
            if any(not item for item in rule_id_list):
                return self.error_result(
                    "Invalid rule_id format: contains empty values",
                    error_type=ERROR_TYPE_VALIDATION,
                )
            params["matchRuleId"] = ",".join(rule_id_list)

        # prop_val items are passed as individual query params
        # Format: "Prop_String=Sales,Prop_Int=5"
        extra_params: dict[str, str] = {}
        if prop_val:
            prop_val_list = [item.strip() for item in prop_val.split(",")]
            if any(not item for item in prop_val_list):
                return self.error_result(
                    "Invalid prop_val format: contains empty values",
                    error_type=ERROR_TYPE_VALIDATION,
                )
            for item in prop_val_list:
                if "=" not in item:
                    return self.error_result(
                        f"Invalid prop_val format: '{item}' must be in key=value format",
                        error_type=ERROR_TYPE_VALIDATION,
                    )
                key, value = item.split("=", 1)
                extra_params[key.strip()] = value.strip()

        # Merge params
        all_params = {**params, **extra_params} if params or extra_params else None

        ok, result = await _web_api_request(self, WEB_HOSTS_ENDPOINT, params=all_params)
        if not ok:
            return self.error_result(result)

        hosts = result.get("hosts", []) if isinstance(result, dict) else []

        return self.success_result(
            data={
                "hosts": hosts,
                "num_active_sessions": len(hosts),
            },
        )

"""
Microsoft Entra ID (Azure AD) integration actions.

Uses Microsoft Graph REST API with OAuth2 client credentials flow.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_CLIENT_ID,
    CREDENTIAL_CLIENT_SECRET,
    DEFAULT_TIMEOUT,
    ENDPOINT_GROUP_MEMBERS,
    ENDPOINT_SIGN_INS,
    ENDPOINT_USER,
    ENDPOINT_USER_MEMBER_OF,
    ENDPOINT_USER_REVOKE_SESSIONS,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP_STATUS,
    ERROR_TYPE_TOKEN,
    ERROR_TYPE_VALIDATION,
    GRAPH_API_BASE_URL,
    MSG_MISSING_CLIENT_ID,
    MSG_MISSING_CLIENT_SECRET,
    MSG_MISSING_PARAMETER,
    MSG_MISSING_TENANT_ID,
    MSG_PASSWORD_RESET,
    MSG_SESSIONS_REVOKED,
    MSG_TOKEN_ACQUISITION_FAILED,
    MSG_USER_DISABLED,
    MSG_USER_ENABLED,
    ODATA_NEXT_LINK,
    PAGINATION_PAGE_SIZE,
    SETTINGS_BASE_URL,
    SETTINGS_TENANT_ID,
    SETTINGS_TIMEOUT,
    TOKEN_SCOPE,
    TOKEN_URL_TEMPLATE,
)

logger = get_logger(__name__)

# ============================================================================
# TOKEN ACQUISITION HELPER
# ============================================================================

async def _acquire_token(
    action: IntegrationAction,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[bool, str | dict[str, Any]]:
    """Acquire OAuth2 access token using client credentials flow.

    Args:
        action: Integration action instance (provides http_request).
        tenant_id: Azure AD tenant ID.
        client_id: Application (client) ID.
        client_secret: Client secret value.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (success, access_token_string or error_dict).
    """
    token_url = TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id)

    try:
        response = await action.http_request(
            token_url,
            method="POST",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": TOKEN_SCOPE,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout,
        )

        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return False, {"error": "No access_token in token response"}
        return True, access_token

    except httpx.HTTPStatusError as e:
        try:
            error_data = e.response.json()
            error_desc = error_data.get(
                "error_description", error_data.get("error", str(e))
            )
        except Exception:
            error_desc = str(e)
        return False, {"error": f"Token request failed: {error_desc}"}
    except Exception as e:
        return False, {"error": f"Token request error: {e}"}

# ============================================================================
# GRAPH API REQUEST HELPER
# ============================================================================

async def _graph_request(
    action: IntegrationAction,
    access_token: str,
    base_url: str,
    endpoint: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[bool, dict[str, Any] | list[Any] | None, httpx.Response | None]:
    """Make authenticated request to Microsoft Graph API.

    Args:
        action: Integration action instance.
        access_token: OAuth2 bearer token.
        base_url: Graph API base URL.
        endpoint: API endpoint path (e.g., "/users/{id}").
        method: HTTP method.
        params: Query parameters.
        json_data: Request body data.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (success, response_data, raw_response).
    """
    url = f"{base_url}{endpoint}"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        response = await action.http_request(
            url,
            method=method.upper(),
            headers=headers,
            params=params,
            json_data=json_data,
            timeout=timeout,
        )

        # Handle 204 No Content (success for PATCH/DELETE operations)
        if response.status_code == 204:
            return True, {}, response

        if 200 <= response.status_code < 300:
            try:
                data = response.json()
                return True, data, response
            except Exception:
                return True, {}, response

        return True, {}, response

    except httpx.HTTPStatusError as e:
        try:
            error_data = e.response.json()
            error_obj = error_data.get("error", {})
            if isinstance(error_obj, dict):
                error_msg = error_obj.get("message", e.response.text)
                error_code = error_obj.get("code", "")
                if error_code:
                    error_msg = f"{error_code}: {error_msg}"
            else:
                error_msg = str(error_obj)
        except Exception:
            error_msg = e.response.text

        return (
            False,
            {
                "error": f"HTTP {e.response.status_code}: {error_msg}",
                "status_code": e.response.status_code,
            },
            e.response,
        )
    except httpx.TimeoutException as e:
        return False, {"error": f"Request timed out: {e}"}, None
    except Exception as e:
        return False, {"error": str(e)}, None

async def _graph_paginated_request(
    action: IntegrationAction,
    access_token: str,
    base_url: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    max_results: int | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[bool, list[Any] | dict[str, Any]]:
    """Make paginated GET request to Microsoft Graph API.

    Follows @odata.nextLink for automatic pagination.

    Args:
        action: Integration action instance.
        access_token: OAuth2 bearer token.
        base_url: Graph API base URL.
        endpoint: API endpoint path.
        params: Query parameters.
        max_results: Maximum number of results to return.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (success, results_list or error_dict).
    """
    results: list[Any] = []
    if params is None:
        params = {}
    params.setdefault("$top", PAGINATION_PAGE_SIZE)

    current_endpoint = endpoint
    current_params = params

    while True:
        success, data, response = await _graph_request(
            action,
            access_token,
            base_url,
            current_endpoint,
            method="GET",
            params=current_params,
            timeout=timeout,
        )

        if not success:
            return False, data

        if isinstance(data, dict):
            page_items = data.get("value", [])
            results.extend(page_items)

            if max_results is not None and len(results) >= max_results:
                results = results[:max_results]
                break

            next_link = data.get(ODATA_NEXT_LINK)
            if next_link:
                # For subsequent pages, use the full nextLink URL directly
                # Parse it to extract the path after the base URL
                if next_link.startswith(base_url):
                    current_endpoint = next_link[len(base_url) :]
                else:
                    current_endpoint = next_link
                current_params = {}
            else:
                break
        else:
            break

    return True, results

# ============================================================================
# CREDENTIAL VALIDATION HELPER
# ============================================================================

def _validate_credentials(
    credentials: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> tuple[bool, str | None, str | None, str | None, str | None]:
    """Validate and extract required credentials and settings.

    client_id and client_secret come from credentials (secrets).
    tenant_id comes from settings (public Azure AD directory GUID).

    Returns:
        Tuple of (valid, client_id, client_secret, tenant_id, error_message).
    """
    client_id = credentials.get(CREDENTIAL_CLIENT_ID)
    client_secret = credentials.get(CREDENTIAL_CLIENT_SECRET)
    tenant_id = (settings or {}).get(SETTINGS_TENANT_ID)

    if not client_id:
        return False, None, None, None, MSG_MISSING_CLIENT_ID
    if not client_secret:
        return False, None, None, None, MSG_MISSING_CLIENT_SECRET
    if not tenant_id:
        return False, None, None, None, MSG_MISSING_TENANT_ID

    return True, client_id, client_secret, tenant_id, None

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Verify API connectivity to Microsoft Entra ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Microsoft Graph API connectivity.

        Acquires an OAuth2 token and queries /users?$top=1 to verify
        that credentials are valid and the API is reachable.

        Returns:
            Success result with connectivity status.
        """
        valid, client_id, client_secret, tenant_id, error_msg = _validate_credentials(
            self.credentials, self.settings
        )
        if not valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = self.settings.get(SETTINGS_BASE_URL, GRAPH_API_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Acquire token
        token_ok, token_result = await _acquire_token(
            self, tenant_id, client_id, client_secret, timeout=timeout
        )
        if not token_ok:
            return self.error_result(
                MSG_TOKEN_ACQUISITION_FAILED.format(
                    error=token_result.get("error", "Unknown")
                ),
                error_type=ERROR_TYPE_TOKEN,
            )

        # Verify connectivity by listing one user
        success, data, _ = await _graph_request(
            self,
            token_result,
            base_url,
            "/users?$top=1",
            timeout=timeout,
        )

        if success:
            return self.success_result(
                data={
                    "healthy": True,
                    "api_version": "v1.0",
                    "tenant_id": tenant_id,
                },
            )
        return self.error_result(
            data.get("error", "Failed to connect to Microsoft Graph API"),
            error_type=ERROR_TYPE_HTTP_STATUS,
        )

class GetUserAction(IntegrationAction):
    """Look up a user by UPN, email, or object ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get user details from Entra ID.

        Args:
            user_id: User principal name, email, or object ID.

        Returns:
            Success result with user attributes, or not_found if user
            does not exist.
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="user_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        valid, client_id, client_secret, tenant_id, error_msg = _validate_credentials(
            self.credentials, self.settings
        )
        if not valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = self.settings.get(SETTINGS_BASE_URL, GRAPH_API_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        token_ok, token_result = await _acquire_token(
            self, tenant_id, client_id, client_secret, timeout=timeout
        )
        if not token_ok:
            return self.error_result(
                MSG_TOKEN_ACQUISITION_FAILED.format(
                    error=token_result.get("error", "Unknown")
                ),
                error_type=ERROR_TYPE_TOKEN,
            )

        endpoint = ENDPOINT_USER.format(user_id=user_id)
        success, data, response = await _graph_request(
            self, token_result, base_url, endpoint, timeout=timeout
        )

        if success:
            return self.success_result(data=data)

        # 404 = user not found, return success with not_found flag
        if isinstance(data, dict) and data.get("status_code") == 404:
            self.log_info("entraid_user_not_found", user_id=user_id)
            return self.success_result(
                not_found=True,
                data={"user_id": user_id},
            )

        return self.error_result(
            data.get("error", "Failed to get user"),
            error_type=ERROR_TYPE_HTTP_STATUS,
        )

class DisableUserAction(IntegrationAction):
    """Disable (block sign-in for) a user account."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Disable a user account by setting accountEnabled=false.

        Args:
            user_id: User principal name, email, or object ID.

        Returns:
            Success result confirming the user was disabled.
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="user_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        valid, client_id, client_secret, tenant_id, error_msg = _validate_credentials(
            self.credentials, self.settings
        )
        if not valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = self.settings.get(SETTINGS_BASE_URL, GRAPH_API_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        token_ok, token_result = await _acquire_token(
            self, tenant_id, client_id, client_secret, timeout=timeout
        )
        if not token_ok:
            return self.error_result(
                MSG_TOKEN_ACQUISITION_FAILED.format(
                    error=token_result.get("error", "Unknown")
                ),
                error_type=ERROR_TYPE_TOKEN,
            )

        endpoint = ENDPOINT_USER.format(user_id=user_id)
        success, data, _ = await _graph_request(
            self,
            token_result,
            base_url,
            endpoint,
            method="PATCH",
            json_data={"accountEnabled": False},
            timeout=timeout,
        )

        if success:
            return self.success_result(
                data={
                    "user_id": user_id,
                    "account_enabled": False,
                    "message": MSG_USER_DISABLED,
                },
            )

        return self.error_result(
            data.get("error", "Failed to disable user"),
            error_type=ERROR_TYPE_HTTP_STATUS,
        )

class EnableUserAction(IntegrationAction):
    """Re-enable a user account."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Enable a user account by setting accountEnabled=true.

        Args:
            user_id: User principal name, email, or object ID.

        Returns:
            Success result confirming the user was enabled.
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="user_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        valid, client_id, client_secret, tenant_id, error_msg = _validate_credentials(
            self.credentials, self.settings
        )
        if not valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = self.settings.get(SETTINGS_BASE_URL, GRAPH_API_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        token_ok, token_result = await _acquire_token(
            self, tenant_id, client_id, client_secret, timeout=timeout
        )
        if not token_ok:
            return self.error_result(
                MSG_TOKEN_ACQUISITION_FAILED.format(
                    error=token_result.get("error", "Unknown")
                ),
                error_type=ERROR_TYPE_TOKEN,
            )

        endpoint = ENDPOINT_USER.format(user_id=user_id)
        success, data, _ = await _graph_request(
            self,
            token_result,
            base_url,
            endpoint,
            method="PATCH",
            json_data={"accountEnabled": True},
            timeout=timeout,
        )

        if success:
            return self.success_result(
                data={
                    "user_id": user_id,
                    "account_enabled": True,
                    "message": MSG_USER_ENABLED,
                },
            )

        return self.error_result(
            data.get("error", "Failed to enable user"),
            error_type=ERROR_TYPE_HTTP_STATUS,
        )

class ResetPasswordAction(IntegrationAction):
    """Force a password reset for a user."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Reset user password via PATCH to /users/{id}.

        Args:
            user_id: User principal name, email, or object ID.
            temp_password: Temporary password to set (optional, auto-generated
                if not provided by setting it to empty string).
            force_change: Whether user must change password on next sign-in
                (default: True).

        Returns:
            Success result confirming the password was reset.
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="user_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        temp_password = kwargs.get("temp_password", "")
        force_change = kwargs.get("force_change", True)

        valid, client_id, client_secret, tenant_id, error_msg = _validate_credentials(
            self.credentials, self.settings
        )
        if not valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = self.settings.get(SETTINGS_BASE_URL, GRAPH_API_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        token_ok, token_result = await _acquire_token(
            self, tenant_id, client_id, client_secret, timeout=timeout
        )
        if not token_ok:
            return self.error_result(
                MSG_TOKEN_ACQUISITION_FAILED.format(
                    error=token_result.get("error", "Unknown")
                ),
                error_type=ERROR_TYPE_TOKEN,
            )

        password_profile = {
            "forceChangePasswordNextSignIn": force_change,
            "password": temp_password,
        }

        endpoint = ENDPOINT_USER.format(user_id=user_id)
        success, data, _ = await _graph_request(
            self,
            token_result,
            base_url,
            endpoint,
            method="PATCH",
            json_data={"passwordProfile": password_profile},
            timeout=timeout,
        )

        if success:
            return self.success_result(
                data={
                    "user_id": user_id,
                    "force_change": force_change,
                    "message": MSG_PASSWORD_RESET,
                },
            )

        return self.error_result(
            data.get("error", "Failed to reset password"),
            error_type=ERROR_TYPE_HTTP_STATUS,
        )

class ListGroupsAction(IntegrationAction):
    """List the groups a user belongs to."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List groups for a user via /users/{id}/memberOf.

        Args:
            user_id: User principal name, email, or object ID.

        Returns:
            Success result with list of groups.
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="user_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        valid, client_id, client_secret, tenant_id, error_msg = _validate_credentials(
            self.credentials, self.settings
        )
        if not valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = self.settings.get(SETTINGS_BASE_URL, GRAPH_API_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        token_ok, token_result = await _acquire_token(
            self, tenant_id, client_id, client_secret, timeout=timeout
        )
        if not token_ok:
            return self.error_result(
                MSG_TOKEN_ACQUISITION_FAILED.format(
                    error=token_result.get("error", "Unknown")
                ),
                error_type=ERROR_TYPE_TOKEN,
            )

        endpoint = ENDPOINT_USER_MEMBER_OF.format(user_id=user_id)
        success, data = await _graph_paginated_request(
            self, token_result, base_url, endpoint, timeout=timeout
        )

        if not success:
            return self.error_result(
                data.get("error", "Failed to list groups"),
                error_type=ERROR_TYPE_HTTP_STATUS,
            )

        # Filter to groups only (memberOf may include directory roles etc.)
        groups = [
            item
            for item in data
            if isinstance(item, dict)
            and item.get("@odata.type", "") == "#microsoft.graph.group"
        ]

        return self.success_result(
            data={
                "user_id": user_id,
                "groups": groups,
                "num_groups": len(groups),
            },
        )

class GetGroupMembersAction(IntegrationAction):
    """List members of a group."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get members of a group via /groups/{id}/members.

        Args:
            group_id: Group object ID.

        Returns:
            Success result with list of members.
        """
        group_id = kwargs.get("group_id")
        if not group_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="group_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        valid, client_id, client_secret, tenant_id, error_msg = _validate_credentials(
            self.credentials, self.settings
        )
        if not valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = self.settings.get(SETTINGS_BASE_URL, GRAPH_API_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        token_ok, token_result = await _acquire_token(
            self, tenant_id, client_id, client_secret, timeout=timeout
        )
        if not token_ok:
            return self.error_result(
                MSG_TOKEN_ACQUISITION_FAILED.format(
                    error=token_result.get("error", "Unknown")
                ),
                error_type=ERROR_TYPE_TOKEN,
            )

        endpoint = ENDPOINT_GROUP_MEMBERS.format(group_id=group_id)
        success, data = await _graph_paginated_request(
            self, token_result, base_url, endpoint, timeout=timeout
        )

        if not success:
            return self.error_result(
                data.get("error", "Failed to list group members"),
                error_type=ERROR_TYPE_HTTP_STATUS,
            )

        return self.success_result(
            data={
                "group_id": group_id,
                "members": data,
                "num_members": len(data),
            },
        )

class RevokeSessionsAction(IntegrationAction):
    """Revoke all active sign-in sessions for a user.

    Critical for incident response -- forces re-authentication on
    all devices and applications.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Revoke all sessions via /users/{id}/revokeSignInSessions.

        Args:
            user_id: User principal name, email, or object ID.

        Returns:
            Success result confirming sessions were revoked.
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="user_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        valid, client_id, client_secret, tenant_id, error_msg = _validate_credentials(
            self.credentials, self.settings
        )
        if not valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = self.settings.get(SETTINGS_BASE_URL, GRAPH_API_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        token_ok, token_result = await _acquire_token(
            self, tenant_id, client_id, client_secret, timeout=timeout
        )
        if not token_ok:
            return self.error_result(
                MSG_TOKEN_ACQUISITION_FAILED.format(
                    error=token_result.get("error", "Unknown")
                ),
                error_type=ERROR_TYPE_TOKEN,
            )

        endpoint = ENDPOINT_USER_REVOKE_SESSIONS.format(user_id=user_id)
        success, data, _ = await _graph_request(
            self,
            token_result,
            base_url,
            endpoint,
            method="POST",
            timeout=timeout,
        )

        if success:
            return self.success_result(
                data={
                    "user_id": user_id,
                    "sessions_revoked": True,
                    "message": MSG_SESSIONS_REVOKED,
                },
            )

        return self.error_result(
            data.get("error", "Failed to revoke sessions"),
            error_type=ERROR_TYPE_HTTP_STATUS,
        )

class ListSignInsAction(IntegrationAction):
    """Get recent sign-in activity for a user."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List sign-in logs for a user via /auditLogs/signIns.

        Args:
            user_id: User principal name, email, or object ID.
            top: Maximum number of results (default: 50).

        Returns:
            Success result with list of sign-in records.
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="user_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        top = kwargs.get("top", 50)

        valid, client_id, client_secret, tenant_id, error_msg = _validate_credentials(
            self.credentials, self.settings
        )
        if not valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = self.settings.get(SETTINGS_BASE_URL, GRAPH_API_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        token_ok, token_result = await _acquire_token(
            self, tenant_id, client_id, client_secret, timeout=timeout
        )
        if not token_ok:
            return self.error_result(
                MSG_TOKEN_ACQUISITION_FAILED.format(
                    error=token_result.get("error", "Unknown")
                ),
                error_type=ERROR_TYPE_TOKEN,
            )

        # Filter sign-ins by userPrincipalName
        params = {
            "$filter": f"userPrincipalName eq '{user_id}'",
            "$top": top,
            "$orderby": "createdDateTime desc",
        }

        success, data = await _graph_paginated_request(
            self,
            token_result,
            base_url,
            ENDPOINT_SIGN_INS,
            params=params,
            max_results=top,
            timeout=timeout,
        )

        if not success:
            return self.error_result(
                data.get("error", "Failed to list sign-ins"),
                error_type=ERROR_TYPE_HTTP_STATUS,
            )

        return self.success_result(
            data={
                "user_id": user_id,
                "sign_ins": data,
                "num_sign_ins": len(data),
            },
        )

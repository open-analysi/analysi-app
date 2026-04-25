"""Okta integration actions for identity and access management."""

import asyncio
from typing import Any
from urllib.parse import urljoin

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_API_TOKEN,
    DEFAULT_PAGINATION_LIMIT,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP_ERROR,
    ERROR_TYPE_VALIDATION,
    FACTOR_TYPE_VALUES,
    IDENTITY_PROVIDER_TYPES,
    MSG_GROUP_ADDED,
    MSG_GROUP_ALREADY_EXISTS,
    MSG_MISSING_API_TOKEN,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_PARAMETER,
    MSG_PASSWORD_RESET,
    MSG_PASSWORD_SET,
    MSG_PUSH_NOTIFICATION_SENT,
    MSG_ROLE_ALREADY_ASSIGNED,
    MSG_ROLE_ASSIGNED,
    MSG_ROLE_NOT_ASSIGNED,
    MSG_ROLE_UNASSIGNED,
    MSG_SESSIONS_CLEARED,
    MSG_USER_ADDED_TO_GROUP,
    MSG_USER_ALREADY_DISABLED,
    MSG_USER_ALREADY_ENABLED,
    MSG_USER_DISABLED,
    MSG_USER_ENABLED,
    MSG_USER_REMOVED_FROM_GROUP,
    OKTA_API_VERSION,
    PUSH_NOTIFICATION_MAX_ATTEMPTS,
    PUSH_NOTIFICATION_POLL_INTERVAL,
    RECEIVE_TYPE_VALUES,
    ROLE_TYPES,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
    STATUS_ERROR,
    STATUS_SUCCESS,
    USER_AGENT_BASE,
)

logger = get_logger(__name__)

# ============================================================================
# API CLIENT HELPER
# ============================================================================

async def _make_okta_request(
    action: IntegrationAction,
    base_url: str,
    api_token: str,
    endpoint: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[bool, dict[str, Any] | list[Any] | None, httpx.Response | None]:
    """Make HTTP request to Okta API.

    Args:
        base_url: Okta organization base URL
        api_token: Okta API token (SSWS)
        endpoint: API endpoint (without base URL and /api/v1)
        method: HTTP method
        params: Query parameters
        json_data: Request body data
        timeout: Request timeout in seconds

    Returns:
        Tuple of (success, response_data, response_object)
    """
    # Build full URL
    url = urljoin(base_url, f"/api/{OKTA_API_VERSION}{endpoint}")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": f"{USER_AGENT_BASE}1.0.0",
        "Authorization": f"SSWS {api_token}",
    }

    try:
        response = await action.http_request(
            url,
            method=method.upper(),
            headers=headers,
            params=params,
            json_data=json_data,
            timeout=timeout,
            verify_ssl=True,
        )

        # Handle different response types
        if response.status_code == 204:
            # No content response (successful DELETE)
            return True, {}, response

        if 200 <= response.status_code < 300:
            # Success - try to parse JSON
            try:
                data = response.json()
                return True, data, response
            except Exception:
                # Empty response or non-JSON
                return True, {}, response

        # Should not reach here since http_request raises for non-2xx,
        # but keep for safety
        return True, {}, response

    except httpx.HTTPStatusError as e:
        logger.error(
            "okta_api_http_error_for",
            endpoint=endpoint,
            status_code=e.response.status_code,
        )
        # Extract Okta-specific error details
        try:
            error_data = e.response.json()
            error_msg = error_data.get("errorSummary", e.response.text)
            error_causes = error_data.get("errorCauses", [])
            if error_causes:
                error_msg += (
                    f". Error Causes: {error_causes[0].get('errorSummary', '')}"
                )
        except Exception:
            error_msg = e.response.text
        return (
            False,
            {"error": f"HTTP {e.response.status_code}: {error_msg}"},
            e.response,
        )
    except httpx.TimeoutException as e:
        logger.error("okta_api_timeout_for", endpoint=endpoint, error=str(e))
        return False, {"error": f"Request timed out after {timeout} seconds"}, None
    except Exception as e:
        logger.error("okta_api_error_for", endpoint=endpoint, error=str(e))
        return False, {"error": str(e)}, None

async def _get_paginated_results(
    action: IntegrationAction,
    base_url: str,
    api_token: str,
    endpoint: str,
    limit: int | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[bool, list[Any] | dict[str, Any]]:
    """Get paginated results from Okta API.

    Args:
        base_url: Okta organization base URL
        api_token: Okta API token
        endpoint: API endpoint
        limit: Maximum number of results (None for all)
        params: Query parameters
        timeout: Request timeout

    Returns:
        Tuple of (success, results_list or error_dict)
    """
    results = []
    if params is None:
        params = {}

    params["limit"] = DEFAULT_PAGINATION_LIMIT

    while True:
        success, data, response = await _make_okta_request(
            action,
            base_url,
            api_token,
            endpoint,
            method="GET",
            params=params,
            timeout=timeout,
        )

        if not success:
            return False, data

        if isinstance(data, list):
            if limit is not None:
                remaining = limit - len(results)
                if remaining <= 0:
                    break
                results.extend(data[:remaining])
                if len(data) < remaining:
                    break
            else:
                results.extend(data)
        else:
            # Single item response
            return True, data

        # Check for next page link
        if response and "link" in response.headers:
            link_header = response.headers["link"]
            next_link = None
            for link in link_header.split(","):
                if '"next"' in link and "after=" in link:
                    after_start = link.find("after=") + 6
                    after_end = link.find("&", after_start)
                    if after_end == -1:
                        after_end = link.find(">", after_start)
                    params["after"] = link[after_start:after_end]
                    next_link = True
                    break

            if not next_link:
                break
        else:
            break

        if limit is not None and len(results) >= limit:
            break

    return True, results

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Okta API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Okta API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        if not api_token:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        success, data, _ = await _make_okta_request(
            self, base_url, api_token, "/users/me", timeout=timeout
        )

        if success:
            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Okta API is accessible",
                "data": {
                    "healthy": True,
                    "api_version": OKTA_API_VERSION,
                    "user": data,
                },
            }
        return {
            "healthy": False,
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
            "data": {"healthy": False},
        }

class ListUsersAction(IntegrationAction):
    """List users with optional filtering."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List Okta users.

        Args:
            **kwargs: Optional 'query', 'filter', 'search', 'limit' parameters

        Returns:
            Result with list of users
        """
        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Build parameters
        params = {
            "q": kwargs.get("query", ""),
            "filter": kwargs.get("filter", ""),
            "search": kwargs.get("search", ""),
        }

        limit = kwargs.get("limit")
        if limit is not None:
            try:
                limit = int(limit)
                if limit < 0:
                    return {
                        "status": STATUS_ERROR,
                        "error": "limit must be non-negative",
                        "error_type": ERROR_TYPE_VALIDATION,
                    }
            except (ValueError, TypeError):
                return {
                    "status": STATUS_ERROR,
                    "error": "limit must be an integer",
                    "error_type": ERROR_TYPE_VALIDATION,
                }

        success, data = await _get_paginated_results(
            self,
            base_url,
            api_token,
            "/users",
            limit=limit,
            params=params,
            timeout=timeout,
        )

        if success:
            return {
                "status": STATUS_SUCCESS,
                "users": data,
                "num_users": len(data) if isinstance(data, list) else 1,
            }
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class GetUserAction(IntegrationAction):
    """Get user details by user ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get Okta user details.

        Args:
            **kwargs: Must contain 'user_id'

        Returns:
            Result with user details
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="user_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        success, data, response = await _make_okta_request(
            self, base_url, api_token, f"/users/{user_id}", timeout=timeout
        )

        if success:
            return {"status": STATUS_SUCCESS, "user": data}
        if response is not None and response.status_code == 404:
            return {
                "status": STATUS_SUCCESS,
                "not_found": True,
                "user_id": user_id,
            }
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class DisableUserAction(IntegrationAction):
    """Disable (suspend) a user account."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Disable Okta user.

        Args:
            **kwargs: Must contain 'id' (user_id)

        Returns:
            Result with status
        """
        user_id = kwargs.get("id")
        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        success, data, _ = await _make_okta_request(
            self,
            base_url,
            api_token,
            f"/users/{user_id}/lifecycle/suspend",
            method="POST",
            timeout=timeout,
        )

        if success:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_USER_DISABLED,
                "data": data,
            }
        error_msg = data.get("error", "")
        if "Cannot suspend a user that is not active" in error_msg:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_USER_ALREADY_DISABLED,
                "data": {},
            }
        return {
            "status": STATUS_ERROR,
            "error": error_msg,
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class EnableUserAction(IntegrationAction):
    """Enable (unsuspend) a user account."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Enable Okta user.

        Args:
            **kwargs: Must contain 'id' (user_id)

        Returns:
            Result with status
        """
        user_id = kwargs.get("id")
        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        success, data, _ = await _make_okta_request(
            self,
            base_url,
            api_token,
            f"/users/{user_id}/lifecycle/unsuspend",
            method="POST",
            timeout=timeout,
        )

        if success:
            return {"status": STATUS_SUCCESS, "message": MSG_USER_ENABLED, "data": data}
        error_msg = data.get("error", "")
        if "Cannot unsuspend a user that is not suspended" in error_msg:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_USER_ALREADY_ENABLED,
                "data": {},
            }
        return {
            "status": STATUS_ERROR,
            "error": error_msg,
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class ResetPasswordAction(IntegrationAction):
    """Reset user password and send reset link."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Reset Okta user password.

        Args:
            **kwargs: Must contain 'user_id' and 'receive_type' (Email or UI)

        Returns:
            Result with reset token
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="user_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        receive_type = kwargs.get("receive_type", "Email")
        if receive_type not in RECEIVE_TYPE_VALUES:
            return {
                "status": STATUS_ERROR,
                "error": f"receive_type must be one of {RECEIVE_TYPE_VALUES}",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        params = {"sendEmail": receive_type == "Email"}

        success, data, _ = await _make_okta_request(
            self,
            base_url,
            api_token,
            f"/users/{user_id}/lifecycle/reset_password",
            method="POST",
            params=params,
            timeout=timeout,
        )

        if success:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_PASSWORD_RESET,
                "data": data,
            }
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class SetPasswordAction(IntegrationAction):
    """Set user password directly."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Set Okta user password.

        Args:
            **kwargs: Must contain 'id' (user_id) and 'new_password'

        Returns:
            Result with status
        """
        user_id = kwargs.get("id")
        new_password = kwargs.get("new_password")

        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not new_password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="new_password"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        json_data = {"credentials": {"password": {"value": new_password}}}

        success, data, _ = await _make_okta_request(
            self,
            base_url,
            api_token,
            f"/users/{user_id}",
            method="POST",
            json_data=json_data,
            timeout=timeout,
        )

        if success:
            return {"status": STATUS_SUCCESS, "message": MSG_PASSWORD_SET, "data": data}
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class ClearUserSessionsAction(IntegrationAction):
    """Clear all active sessions for a user."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Clear Okta user sessions.

        Args:
            **kwargs: Must contain 'id' (user_id)

        Returns:
            Result with status
        """
        user_id = kwargs.get("id")
        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        success, data, _ = await _make_okta_request(
            self,
            base_url,
            api_token,
            f"/users/{user_id}/sessions",
            method="DELETE",
            timeout=timeout,
        )

        if success:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_SESSIONS_CLEARED,
                "data": data,
            }
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class ListUserGroupsAction(IntegrationAction):
    """List all groups with optional filtering."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List Okta groups.

        Args:
            **kwargs: Optional 'query', 'filter', 'limit' parameters

        Returns:
            Result with list of groups
        """
        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        params = {"q": kwargs.get("query", ""), "filter": kwargs.get("filter", "")}

        limit = kwargs.get("limit")
        if limit is not None:
            try:
                limit = int(limit)
                if limit < 0:
                    return {
                        "status": STATUS_ERROR,
                        "error": "limit must be non-negative",
                        "error_type": ERROR_TYPE_VALIDATION,
                    }
            except (ValueError, TypeError):
                return {
                    "status": STATUS_ERROR,
                    "error": "limit must be an integer",
                    "error_type": ERROR_TYPE_VALIDATION,
                }

        success, data = await _get_paginated_results(
            self,
            base_url,
            api_token,
            "/groups",
            limit=limit,
            params=params,
            timeout=timeout,
        )

        if success:
            return {
                "status": STATUS_SUCCESS,
                "groups": data,
                "num_groups": len(data) if isinstance(data, list) else 1,
            }
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class GetGroupAction(IntegrationAction):
    """Get group details by group ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get Okta group details.

        Args:
            **kwargs: Must contain 'group_id'

        Returns:
            Result with group details
        """
        group_id = kwargs.get("group_id")
        if not group_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="group_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        success, data, response = await _make_okta_request(
            self, base_url, api_token, f"/groups/{group_id}", timeout=timeout
        )

        if success:
            return {"status": STATUS_SUCCESS, "group": data}
        if response is not None and response.status_code == 404:
            return {
                "status": STATUS_SUCCESS,
                "not_found": True,
                "group_id": group_id,
            }
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class AddGroupAction(IntegrationAction):
    """Create a new group."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create Okta group.

        Args:
            **kwargs: Must contain 'name' and 'description'

        Returns:
            Result with created group details
        """
        name = kwargs.get("name")
        description = kwargs.get("description")

        if not name:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="name"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not description:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="description"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        json_data = {"profile": {"name": name, "description": description}}

        success, data, _ = await _make_okta_request(
            self,
            base_url,
            api_token,
            "/groups",
            method="POST",
            json_data=json_data,
            timeout=timeout,
        )

        if success:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_GROUP_ADDED,
                "group": data,
                "group_id": data.get("id"),
            }
        error_msg = data.get("error", "")
        if "An object with this field already exists" in error_msg:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_GROUP_ALREADY_EXISTS,
                "data": {},
            }
        return {
            "status": STATUS_ERROR,
            "error": error_msg,
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class GetUserGroupsAction(IntegrationAction):
    """Get all groups a user belongs to."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get Okta user's groups.

        Args:
            **kwargs: Must contain 'user_id'

        Returns:
            Result with list of groups
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="user_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        success, data, response = await _make_okta_request(
            self, base_url, api_token, f"/users/{user_id}/groups", timeout=timeout
        )

        if success:
            groups = data if isinstance(data, list) else [data]
            return {
                "status": STATUS_SUCCESS,
                "groups": groups,
                "total_groups": len(groups),
            }
        if response is not None and response.status_code == 404:
            return {
                "status": STATUS_SUCCESS,
                "not_found": True,
                "user_id": user_id,
            }
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class AddGroupUserAction(IntegrationAction):
    """Add a user to a group."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add user to Okta group.

        Args:
            **kwargs: Must contain 'group_id' and 'user_id'

        Returns:
            Result with status
        """
        group_id = kwargs.get("group_id")
        user_id = kwargs.get("user_id")

        if not group_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="group_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="user_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Get user details
        success, user_data, _ = await _make_okta_request(
            self, base_url, api_token, f"/users/{user_id}", timeout=timeout
        )
        if not success:
            return {
                "status": STATUS_ERROR,
                "error": f"Invalid user_id: {user_id}",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }

        user_name = user_data.get("profile", {}).get("login", user_id)

        # Get group details
        success, group_data, _ = await _make_okta_request(
            self, base_url, api_token, f"/groups/{group_id}", timeout=timeout
        )
        if not success:
            return {
                "status": STATUS_ERROR,
                "error": f"Invalid group_id: {group_id}",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }

        group_name = group_data.get("profile", {}).get("name", group_id)

        # Add user to group
        success, data, _ = await _make_okta_request(
            self,
            base_url,
            api_token,
            f"/groups/{group_id}/users/{user_id}",
            method="PUT",
            timeout=timeout,
        )

        if success:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_USER_ADDED_TO_GROUP,
                "user_id": user_id,
                "user_name": user_name,
                "group_id": group_id,
                "group_name": group_name,
            }
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class RemoveGroupUserAction(IntegrationAction):
    """Remove a user from a group."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Remove user from Okta group.

        Args:
            **kwargs: Must contain 'group_id' and 'user_id'

        Returns:
            Result with status
        """
        group_id = kwargs.get("group_id")
        user_id = kwargs.get("user_id")

        if not group_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="group_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="user_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Get user details
        success, user_data, _ = await _make_okta_request(
            self, base_url, api_token, f"/users/{user_id}", timeout=timeout
        )
        if not success:
            return {
                "status": STATUS_ERROR,
                "error": f"Invalid user_id: {user_id}",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }

        user_name = user_data.get("profile", {}).get("login", user_id)

        # Get group details
        success, group_data, _ = await _make_okta_request(
            self, base_url, api_token, f"/groups/{group_id}", timeout=timeout
        )
        if not success:
            return {
                "status": STATUS_ERROR,
                "error": f"Invalid group_id: {group_id}",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }

        group_name = group_data.get("profile", {}).get("name", group_id)

        # Remove user from group
        success, data, _ = await _make_okta_request(
            self,
            base_url,
            api_token,
            f"/groups/{group_id}/users/{user_id}",
            method="DELETE",
            timeout=timeout,
        )

        if success:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_USER_REMOVED_FROM_GROUP,
                "user_id": user_id,
                "user_name": user_name,
                "group_id": group_id,
                "group_name": group_name,
            }
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class ListProvidersAction(IntegrationAction):
    """List identity providers."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List Okta identity providers.

        Args:
            **kwargs: Optional 'query', 'type', 'limit' parameters

        Returns:
            Result with list of identity providers
        """
        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        provider_type = kwargs.get("type", "")
        if provider_type and provider_type not in IDENTITY_PROVIDER_TYPES:
            return {
                "status": STATUS_ERROR,
                "error": f"type must be one of {IDENTITY_PROVIDER_TYPES}",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        params = {"q": kwargs.get("query", ""), "type": provider_type}

        limit = kwargs.get("limit")
        if limit is not None:
            try:
                limit = int(limit)
                if limit < 0:
                    return {
                        "status": STATUS_ERROR,
                        "error": "limit must be non-negative",
                        "error_type": ERROR_TYPE_VALIDATION,
                    }
            except (ValueError, TypeError):
                return {
                    "status": STATUS_ERROR,
                    "error": "limit must be an integer",
                    "error_type": ERROR_TYPE_VALIDATION,
                }

        success, data = await _get_paginated_results(
            self,
            base_url,
            api_token,
            "/idps",
            limit=limit,
            params=params,
            timeout=timeout,
        )

        if success:
            return {
                "status": STATUS_SUCCESS,
                "providers": data,
                "num_idps": len(data) if isinstance(data, list) else 1,
            }
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class ListRolesAction(IntegrationAction):
    """List roles assigned to a user."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List Okta user roles.

        Args:
            **kwargs: Must contain 'user_id'

        Returns:
            Result with list of roles
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="user_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        success, data = await _get_paginated_results(
            self, base_url, api_token, f"/users/{user_id}/roles", timeout=timeout
        )

        if success:
            roles = data if isinstance(data, list) else [data]
            return {"status": STATUS_SUCCESS, "roles": roles, "num_roles": len(roles)}
        return {
            "status": STATUS_ERROR,
            "error": data.get("error", "Unknown error"),
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class AssignRoleAction(IntegrationAction):
    """Assign a role to a user."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Assign role to Okta user.

        Args:
            **kwargs: Must contain 'user_id' and 'type' (role type)

        Returns:
            Result with status
        """
        user_id = kwargs.get("user_id")
        role_type = kwargs.get("type")

        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="user_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not role_type:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="type"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if role_type not in ROLE_TYPES:
            return {
                "status": STATUS_ERROR,
                "error": f"type must be one of {ROLE_TYPES}",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        json_data = {"type": role_type}

        success, data, _ = await _make_okta_request(
            self,
            base_url,
            api_token,
            f"/users/{user_id}/roles",
            method="POST",
            json_data=json_data,
            timeout=timeout,
        )

        if success:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_ROLE_ASSIGNED,
                "role": data,
            }
        error_msg = data.get("error", "")
        if "The role specified is already assigned to the user" in error_msg:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_ROLE_ALREADY_ASSIGNED,
                "data": {},
            }
        return {
            "status": STATUS_ERROR,
            "error": error_msg,
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class UnassignRoleAction(IntegrationAction):
    """Unassign a role from a user."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unassign role from Okta user.

        Args:
            **kwargs: Must contain 'user_id' and 'role_id'

        Returns:
            Result with status
        """
        user_id = kwargs.get("user_id")
        role_id = kwargs.get("role_id")

        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="user_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not role_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="role_id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Verify user exists
        success, _, _ = await _make_okta_request(
            self, base_url, api_token, f"/users/{user_id}", timeout=timeout
        )
        if not success:
            return {
                "status": STATUS_ERROR,
                "error": "Invalid user_id",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }

        # Delete role
        success, data, _ = await _make_okta_request(
            self,
            base_url,
            api_token,
            f"/users/{user_id}/roles/{role_id}",
            method="DELETE",
            timeout=timeout,
        )

        if success:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_ROLE_UNASSIGNED,
                "data": {},
            }
        error_msg = data.get("error", "")
        if "Not found" in error_msg:
            return {
                "status": STATUS_ERROR,
                "message": MSG_ROLE_NOT_ASSIGNED,
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }
        return {
            "status": STATUS_ERROR,
            "error": error_msg,
            "error_type": ERROR_TYPE_HTTP_ERROR,
        }

class SendPushNotificationAction(IntegrationAction):
    """Send MFA push notification to user."""

    async def execute(self, **kwargs) -> dict[str, Any]:  # noqa: C901
        """Send push notification to Okta user.

        Args:
            **kwargs: Must contain 'email' (user identifier) and optional 'factortype'

        Returns:
            Result with push notification status
        """
        email = kwargs.get("email")
        if not email:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format(param="email"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        factor_type = kwargs.get("factortype", "push")
        if factor_type not in FACTOR_TYPE_VALUES:
            return {
                "status": STATUS_ERROR,
                "error": f"factortype must be one of {FACTOR_TYPE_VALUES}",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        base_url = self.settings.get(SETTINGS_BASE_URL)
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)

        if not base_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BASE_URL
                if not base_url
                else MSG_MISSING_API_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Get user
        success, user_data, _ = await _make_okta_request(
            self, base_url, api_token, f"/users/{email}", timeout=timeout
        )
        if not success:
            return {
                "status": STATUS_ERROR,
                "error": f"User not found: {email}",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }

        user_id = user_data.get("id")

        # Get factors
        success, factors_data, _ = await _make_okta_request(
            self, base_url, api_token, f"/users/{user_id}/factors", timeout=timeout
        )
        if not success:
            return {
                "status": STATUS_ERROR,
                "error": "Failed to get user factors",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }

        # Find matching factor
        factor_verify_uri = None
        if isinstance(factors_data, list):
            for factor in factors_data:
                if factor_type in factor.get("factorType", ""):
                    verify_link = (
                        factor.get("_links", {}).get("verify", {}).get("href", "")
                    )
                    if verify_link and "/api/v1" in verify_link:
                        factor_verify_uri = verify_link.split("/api/v1")[1]
                        break

        if not factor_verify_uri:
            return {
                "status": STATUS_ERROR,
                "error": f"Factor type '{factor_type}' not configured for user '{user_id}'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Call verify
        success, verify_data, _ = await _make_okta_request(
            self, base_url, api_token, factor_verify_uri, method="POST", timeout=timeout
        )
        if not success:
            return {
                "status": STATUS_ERROR,
                "error": "Failed to send push notification",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }

        # Get polling URL
        poll_link = verify_data.get("_links", {}).get("poll", {}).get("href", "")
        if not poll_link or "/api/v1" not in poll_link:
            return {
                "status": STATUS_ERROR,
                "error": "Failed to get polling link for push notification",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }

        poll_uri = poll_link.split("/api/v1")[1]

        # Poll for result
        attempts = 0
        while attempts < PUSH_NOTIFICATION_MAX_ATTEMPTS:
            await asyncio.sleep(PUSH_NOTIFICATION_POLL_INTERVAL)
            attempts += 1

            success, poll_data, _ = await _make_okta_request(
                self, base_url, api_token, poll_uri, timeout=timeout
            )
            if not success:
                return {
                    "status": STATUS_ERROR,
                    "error": "Failed to poll push notification status",
                    "error_type": ERROR_TYPE_HTTP_ERROR,
                }

            factor_result = poll_data.get("factorResult", "")
            if factor_result in ["TIMEOUT", "REJECTED", "SUCCESS"]:
                return {
                    "status": STATUS_SUCCESS,
                    "message": MSG_PUSH_NOTIFICATION_SENT,
                    "result": poll_data,
                    "factor_result": factor_result,
                }

        return {
            "status": STATUS_ERROR,
            "error": "Push notification timed out waiting for user response",
            "error_type": "TimeoutError",
        }

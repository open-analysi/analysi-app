"""Exabeam Advanced Analytics integration actions for the Naxos framework.
Analytics) capabilities including user risk scoring, session tracking, asset
monitoring, and watchlist management via a REST API with Basic Auth.
"""

from typing import Any

import httpx

from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    ENDPOINT_ASSET_DATA,
    ENDPOINT_SEARCH_ASSETS,
    ENDPOINT_SEARCH_USERS,
    ENDPOINT_USER_INFO,
    ENDPOINT_WATCHLIST,
    ENDPOINT_WATCHLIST_ADD_USER,
    ENDPOINT_WATCHLIST_BY_ID,
    ENDPOINT_WATCHLIST_REMOVE_USER,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    MSG_CONNECTIVITY_FAILED,
    MSG_CONNECTIVITY_SUCCESS,
    MSG_MISSING_ASSET_ID,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_KEYWORD,
    MSG_MISSING_USERNAME,
    MSG_MISSING_WATCHLIST_ID,
    SETTINGS_BASE_URL,
    SETTINGS_VERIFY_SSL,
)

def _validate_credentials(
    action: IntegrationAction,
) -> tuple[str, str, str, bool] | str:
    """Validate and extract credentials and settings common to all actions.

    Returns either a tuple of (base_url, username, password, verify_ssl) on
    success, or an error message string on failure.
    """
    base_url = action.settings.get(SETTINGS_BASE_URL)
    if not base_url:
        return MSG_MISSING_BASE_URL

    username = action.credentials.get(CREDENTIAL_USERNAME)
    password = action.credentials.get(CREDENTIAL_PASSWORD)
    if not username or not password:
        return MSG_MISSING_CREDENTIALS

    verify_ssl = action.settings.get(SETTINGS_VERIFY_SSL, True)
    return (base_url.rstrip("/"), username, password, verify_ssl)

class HealthCheckAction(IntegrationAction):
    """Verify API connectivity to Exabeam Advanced Analytics."""

    async def execute(self, **params) -> dict[str, Any]:
        """Test connectivity by listing watchlists (matches the upstream pattern).

        Returns:
            dict with healthy flag, status, and watchlist count.
        """
        creds = _validate_credentials(self)
        if isinstance(creds, str):
            return self.error_result(
                creds,
                error_type=ERROR_TYPE_CONFIGURATION,
                healthy=False,
            )
        base_url, username, password, verify_ssl = creds

        try:
            response = await self.http_request(
                f"{base_url}{ENDPOINT_WATCHLIST}",
                auth=(username, password),
                headers={"Accept": "application/json"},
                verify_ssl=verify_ssl,
            )
            data = response.json()
            watchlist_count = len(data.get("users", []))
            return self.success_result(
                data={"watchlist_count": watchlist_count},
                healthy=True,
                message=MSG_CONNECTIVITY_SUCCESS,
            )
        except httpx.TimeoutException as e:
            self.log_error(MSG_CONNECTIVITY_FAILED, error=e)
            return self.error_result(
                f"{MSG_CONNECTIVITY_FAILED}: {e!s}",
                error_type=ERROR_TYPE_TIMEOUT,
                healthy=False,
            )
        except httpx.HTTPStatusError as e:
            self.log_error(MSG_CONNECTIVITY_FAILED, error=e)
            return self.error_result(e, healthy=False)
        except httpx.RequestError as e:
            self.log_error(MSG_CONNECTIVITY_FAILED, error=e)
            return self.error_result(e, healthy=False)
        except Exception as e:
            self.log_error(MSG_CONNECTIVITY_FAILED, error=e)
            return self.error_result(e, healthy=False)

class GetUserAction(IntegrationAction):
    """Retrieve user information and risk score from Exabeam."""

    async def execute(self, **params) -> dict[str, Any]:
        """Get user info including risk score, labels, and account names.

        Args:
            username: Username to look up (required).

        Returns:
            dict with user info, risk score, and manager info.
        """
        username_param = params.get("username")
        if not username_param:
            return self.error_result(
                MSG_MISSING_USERNAME,
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self)
        if isinstance(creds, str):
            return self.error_result(creds, error_type=ERROR_TYPE_CONFIGURATION)
        base_url, username, password, verify_ssl = creds

        try:
            endpoint = ENDPOINT_USER_INFO.format(username=username_param)
            response = await self.http_request(
                f"{base_url}{endpoint}",
                auth=(username, password),
                headers={"Accept": "application/json"},
                verify_ssl=verify_ssl,
            )
            data = response.json()
            return self.success_result(data=data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"username": username_param},
                )
            self.log_error("Get user failed", error=e)
            return self.error_result(e)
        except httpx.TimeoutException as e:
            self.log_error("Get user failed", error=e)
            return self.error_result(
                f"Get user failed: {e!s}",
                error_type=ERROR_TYPE_TIMEOUT,
            )
        except httpx.RequestError as e:
            self.log_error("Get user failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("Get user failed", error=e)
            return self.error_result(e)

class SearchUsersAction(IntegrationAction):
    """Search for users matching a keyword in Exabeam."""

    async def execute(self, **params) -> dict[str, Any]:
        """Search users by keyword with optional result limit.

        Args:
            keyword: Keyword to search for (required).
            limit: Maximum number of results (default 100).

        Returns:
            dict with matching users and match count.
        """
        keyword = params.get("keyword")
        if not keyword:
            return self.error_result(
                MSG_MISSING_KEYWORD,
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self)
        if isinstance(creds, str):
            return self.error_result(creds, error_type=ERROR_TYPE_CONFIGURATION)
        base_url, username, password, verify_ssl = creds

        limit = params.get("limit", 100)

        try:
            response = await self.http_request(
                f"{base_url}{ENDPOINT_SEARCH_USERS}",
                auth=(username, password),
                headers={"Accept": "application/json"},
                params={"keyword": keyword, "limit": limit},
                verify_ssl=verify_ssl,
            )
            data = response.json()
            users = data.get("users", [])
            return self.success_result(
                data=data,
                summary={"matches": len(users)},
                message=f"Found {len(users)} user(s) matching '{keyword}'",
            )
        except httpx.HTTPStatusError as e:
            self.log_error("Search users failed", error=e)
            return self.error_result(e)
        except httpx.TimeoutException as e:
            self.log_error("Search users failed", error=e)
            return self.error_result(
                f"Search users failed: {e!s}",
                error_type=ERROR_TYPE_TIMEOUT,
            )
        except httpx.RequestError as e:
            self.log_error("Search users failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("Search users failed", error=e)
            return self.error_result(e)

class GetWatchlistAction(IntegrationAction):
    """Get members of a specific watchlist in Exabeam."""

    async def execute(self, **params) -> dict[str, Any]:
        """Retrieve watchlist members by watchlist ID.

        Args:
            watchlist_id: ID of the watchlist to retrieve (required).

        Returns:
            dict with watchlist details and user list.
        """
        watchlist_id = params.get("watchlist_id")
        if not watchlist_id:
            return self.error_result(
                MSG_MISSING_WATCHLIST_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self)
        if isinstance(creds, str):
            return self.error_result(creds, error_type=ERROR_TYPE_CONFIGURATION)
        base_url, username, password, verify_ssl = creds

        try:
            endpoint = ENDPOINT_WATCHLIST_BY_ID.format(watchlist_id=watchlist_id)
            response = await self.http_request(
                f"{base_url}{endpoint}",
                auth=(username, password),
                headers={"Accept": "application/json"},
                verify_ssl=verify_ssl,
            )
            data = response.json()
            users = data.get("users", [])
            return self.success_result(
                data=data,
                summary={"users": len(users)},
                message=f"Watchlist '{watchlist_id}' has {len(users)} user(s)",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"watchlist_id": watchlist_id},
                )
            self.log_error("Get watchlist failed", error=e)
            return self.error_result(e)
        except httpx.TimeoutException as e:
            self.log_error("Get watchlist failed", error=e)
            return self.error_result(
                f"Get watchlist failed: {e!s}",
                error_type=ERROR_TYPE_TIMEOUT,
            )
        except httpx.RequestError as e:
            self.log_error("Get watchlist failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("Get watchlist failed", error=e)
            return self.error_result(e)

class ListWatchlistsAction(IntegrationAction):
    """List all watchlists and their IDs in Exabeam."""

    async def execute(self, **params) -> dict[str, Any]:
        """Retrieve all watchlists.

        Returns:
            dict with list of watchlists.
        """
        creds = _validate_credentials(self)
        if isinstance(creds, str):
            return self.error_result(creds, error_type=ERROR_TYPE_CONFIGURATION)
        base_url, username, password, verify_ssl = creds

        try:
            response = await self.http_request(
                f"{base_url}{ENDPOINT_WATCHLIST}",
                auth=(username, password),
                headers={"Accept": "application/json"},
                verify_ssl=verify_ssl,
            )
            data = response.json()
            users = data.get("users", [])
            return self.success_result(
                data={"watchlists": data},
                summary={"matches": len(users)},
                message=f"Found {len(users)} watchlist entry/entries",
            )
        except httpx.HTTPStatusError as e:
            self.log_error("List watchlists failed", error=e)
            return self.error_result(e)
        except httpx.TimeoutException as e:
            self.log_error("List watchlists failed", error=e)
            return self.error_result(
                f"List watchlists failed: {e!s}",
                error_type=ERROR_TYPE_TIMEOUT,
            )
        except httpx.RequestError as e:
            self.log_error("List watchlists failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("List watchlists failed", error=e)
            return self.error_result(e)

class AddToWatchlistAction(IntegrationAction):
    """Add a user to a watchlist in Exabeam."""

    async def execute(self, **params) -> dict[str, Any]:
        """Add user to specified watchlist, with optional duration.

        Args:
            username: User to add (required).
            watchlist_id: Watchlist to modify (required).
            duration: Number of days to watch (optional).

        Returns:
            dict with operation result.
        """
        username_param = params.get("username")
        if not username_param:
            return self.error_result(
                MSG_MISSING_USERNAME,
                error_type=ERROR_TYPE_VALIDATION,
            )

        watchlist_id = params.get("watchlist_id")
        if not watchlist_id:
            return self.error_result(
                MSG_MISSING_WATCHLIST_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self)
        if isinstance(creds, str):
            return self.error_result(creds, error_type=ERROR_TYPE_CONFIGURATION)
        base_url, username, password, verify_ssl = creds

        request_data: dict[str, Any] = {"watchlistId": watchlist_id}
        duration = params.get("duration")
        if duration is not None:
            request_data["duration"] = duration

        try:
            endpoint = ENDPOINT_WATCHLIST_ADD_USER.format(username=username_param)
            response = await self.http_request(
                f"{base_url}{endpoint}",
                method="PUT",
                auth=(username, password),
                headers={"Accept": "application/json"},
                data=request_data,
                verify_ssl=verify_ssl,
            )
            data = response.json()
            return self.success_result(
                data=data,
                message=f"User '{username_param}' added to watchlist '{watchlist_id}'",
            )
        except httpx.HTTPStatusError as e:
            self.log_error("Add to watchlist failed", error=e)
            return self.error_result(e)
        except httpx.TimeoutException as e:
            self.log_error("Add to watchlist failed", error=e)
            return self.error_result(
                f"Add to watchlist failed: {e!s}",
                error_type=ERROR_TYPE_TIMEOUT,
            )
        except httpx.RequestError as e:
            self.log_error("Add to watchlist failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("Add to watchlist failed", error=e)
            return self.error_result(e)

class RemoveFromWatchlistAction(IntegrationAction):
    """Remove a user from a watchlist in Exabeam."""

    async def execute(self, **params) -> dict[str, Any]:
        """Remove user from specified watchlist.

        Args:
            username: User to remove (required).
            watchlist_id: Watchlist to modify (required).

        Returns:
            dict with operation result.
        """
        username_param = params.get("username")
        if not username_param:
            return self.error_result(
                MSG_MISSING_USERNAME,
                error_type=ERROR_TYPE_VALIDATION,
            )

        watchlist_id = params.get("watchlist_id")
        if not watchlist_id:
            return self.error_result(
                MSG_MISSING_WATCHLIST_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self)
        if isinstance(creds, str):
            return self.error_result(creds, error_type=ERROR_TYPE_CONFIGURATION)
        base_url, username, password, verify_ssl = creds

        request_data = {"watchlistId": watchlist_id}

        try:
            endpoint = ENDPOINT_WATCHLIST_REMOVE_USER.format(username=username_param)
            response = await self.http_request(
                f"{base_url}{endpoint}",
                method="PUT",
                auth=(username, password),
                headers={"Accept": "application/json"},
                data=request_data,
                verify_ssl=verify_ssl,
            )
            data = response.json()
            return self.success_result(
                data=data,
                message=f"User '{username_param}' removed from watchlist '{watchlist_id}'",
            )
        except httpx.HTTPStatusError as e:
            self.log_error("Remove from watchlist failed", error=e)
            return self.error_result(e)
        except httpx.TimeoutException as e:
            self.log_error("Remove from watchlist failed", error=e)
            return self.error_result(
                f"Remove from watchlist failed: {e!s}",
                error_type=ERROR_TYPE_TIMEOUT,
            )
        except httpx.RequestError as e:
            self.log_error("Remove from watchlist failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("Remove from watchlist failed", error=e)
            return self.error_result(e)

class SearchAssetsAction(IntegrationAction):
    """Search for assets matching a keyword in Exabeam."""

    async def execute(self, **params) -> dict[str, Any]:
        """Search assets by keyword with optional result limit.

        Args:
            keyword: Keyword to search for (required).
            limit: Maximum number of results (default 100).

        Returns:
            dict with matching assets and match count.
        """
        keyword = params.get("keyword")
        if not keyword:
            return self.error_result(
                MSG_MISSING_KEYWORD,
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self)
        if isinstance(creds, str):
            return self.error_result(creds, error_type=ERROR_TYPE_CONFIGURATION)
        base_url, username, password, verify_ssl = creds

        limit = params.get("limit", 100)

        try:
            response = await self.http_request(
                f"{base_url}{ENDPOINT_SEARCH_ASSETS}",
                auth=(username, password),
                headers={"Accept": "application/json"},
                params={"keyword": keyword, "limit": limit},
                verify_ssl=verify_ssl,
            )
            data = response.json()
            assets = data.get("assets", [])
            return self.success_result(
                data=data,
                summary={"matches": len(assets)},
                message=f"Found {len(assets)} asset(s) matching '{keyword}'",
            )
        except httpx.HTTPStatusError as e:
            self.log_error("Search assets failed", error=e)
            return self.error_result(e)
        except httpx.TimeoutException as e:
            self.log_error("Search assets failed", error=e)
            return self.error_result(
                f"Search assets failed: {e!s}",
                error_type=ERROR_TYPE_TIMEOUT,
            )
        except httpx.RequestError as e:
            self.log_error("Search assets failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("Search assets failed", error=e)
            return self.error_result(e)

class GetAssetAction(IntegrationAction):
    """Retrieve asset information from Exabeam by hostname or IP."""

    async def execute(self, **params) -> dict[str, Any]:
        """Get asset data for a given hostname or IP address.

        Args:
            hostname: Hostname to look up (optional, takes priority).
            ip: IP address to look up (optional, used if hostname absent).

        Returns:
            dict with asset details including risk data.
        """
        asset_id = params.get("hostname") or params.get("ip")
        if not asset_id:
            return self.error_result(
                MSG_MISSING_ASSET_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self)
        if isinstance(creds, str):
            return self.error_result(creds, error_type=ERROR_TYPE_CONFIGURATION)
        base_url, username, password, verify_ssl = creds

        try:
            endpoint = ENDPOINT_ASSET_DATA.format(asset_id=asset_id)
            response = await self.http_request(
                f"{base_url}{endpoint}",
                auth=(username, password),
                headers={"Accept": "application/json"},
                verify_ssl=verify_ssl,
            )
            data = response.json()
            return self.success_result(data=data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"asset_id": asset_id},
                )
            self.log_error("Get asset failed", error=e)
            return self.error_result(e)
        except httpx.TimeoutException as e:
            self.log_error("Get asset failed", error=e)
            return self.error_result(
                f"Get asset failed: {e!s}",
                error_type=ERROR_TYPE_TIMEOUT,
            )
        except httpx.RequestError as e:
            self.log_error("Get asset failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("Get asset failed", error=e)
            return self.error_result(e)

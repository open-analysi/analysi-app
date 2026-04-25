"""CyberArk PAM integration actions for privileged access management.

Uses the CyberArk PVWA REST API with session-based authentication.
Authentication flow: POST /auth/{method}/Logon with username/password -> session token
-> use token as Authorization header for subsequent requests -> POST /auth/Logoff.
"""

import contextlib
from typing import Any
from urllib.parse import quote

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_VERSION,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_AUTH_METHOD,
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_TIMEOUT,
    ENDPOINT_ACCOUNT_BY_ID,
    ENDPOINT_ACCOUNT_CHANGE,
    ENDPOINT_ACCOUNTS,
    ENDPOINT_LOGOFF,
    ENDPOINT_LOGON,
    ENDPOINT_SAFE_BY_NAME,
    ENDPOINT_SAFES,
    ENDPOINT_SERVER_VERIFY,
    ENDPOINT_USER_BY_ID,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP_ERROR,
    ERROR_TYPE_VALIDATION,
    MAX_SEARCH_LIMIT,
    MSG_AUTHENTICATION_FAILED,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_PARAMETER,
    MSG_MISSING_PASSWORD,
    MSG_MISSING_USERNAME,
    SETTINGS_AUTH_METHOD,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
    USER_AGENT,
)

logger = get_logger(__name__)

# ============================================================================
# SESSION MANAGEMENT HELPER
# ============================================================================

async def _authenticate(
    action: IntegrationAction,
    base_url: str,
    username: str,
    password: str,
    auth_method: str = DEFAULT_AUTH_METHOD,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[bool, str | dict[str, Any]]:
    """Authenticate to CyberArk PVWA and obtain a session token.

    Args:
        action: IntegrationAction instance for http_request access.
        base_url: PVWA base URL.
        username: CyberArk username.
        password: CyberArk password.
        auth_method: Authentication method (CyberArk, LDAP, RADIUS, Windows).
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (success, session_token_or_error_dict).
        On success: (True, "session_token_string").
        On failure: (False, {"error": "message"}).
    """
    logon_url = f"{base_url}{ENDPOINT_LOGON.format(auth_method=auth_method)}"

    try:
        response = await action.http_request(
            logon_url,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            json_data={
                "username": username,
                "password": password,
            },
            timeout=timeout,
        )

        # CyberArk Logon returns the session token as a quoted string in the body
        token = response.text.strip().strip('"')
        if not token:
            return False, {"error": MSG_AUTHENTICATION_FAILED}

        return True, token

    except httpx.HTTPStatusError as e:
        logger.error(
            "cyberark_auth_failed",
            status_code=e.response.status_code,
        )
        try:
            error_data = e.response.json()
            error_msg = error_data.get(
                "Details", error_data.get("ErrorMessage", e.response.text)
            )
        except Exception:
            error_msg = e.response.text
        return False, {"error": f"Authentication failed: {error_msg}"}

    except httpx.TimeoutException:
        return False, {"error": f"Authentication timed out after {timeout} seconds"}

    except Exception as e:
        return False, {"error": f"Authentication error: {e!s}"}

async def _logoff(
    action: IntegrationAction,
    base_url: str,
    session_token: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> None:
    """Log off from CyberArk PVWA to invalidate the session token.

    Best-effort; errors are logged but not raised.
    """
    logoff_url = f"{base_url}{ENDPOINT_LOGOFF}"
    try:
        await action.http_request(
            logoff_url,
            method="POST",
            headers={
                "Authorization": session_token,
                "User-Agent": USER_AGENT,
            },
            timeout=timeout,
        )
    except Exception as e:
        logger.warning("cyberark_logoff_failed", error=str(e))

# ============================================================================
# API REQUEST HELPER
# ============================================================================

async def _make_cyberark_request(
    action: IntegrationAction,
    base_url: str,
    session_token: str,
    endpoint: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[bool, dict[str, Any] | list[Any] | None, httpx.Response | None]:
    """Make an authenticated HTTP request to the CyberArk PVWA API.

    Args:
        action: IntegrationAction instance.
        base_url: PVWA base URL.
        session_token: Session token from authentication.
        endpoint: API endpoint path.
        method: HTTP method.
        params: Query parameters.
        json_data: Request body data.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (success, response_data, response_object).
    """
    url = f"{base_url}{endpoint}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": session_token,
        "User-Agent": USER_AGENT,
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
        logger.error(
            "cyberark_api_http_error",
            endpoint=endpoint,
            status_code=e.response.status_code,
        )
        try:
            error_data = e.response.json()
            error_msg = error_data.get(
                "Details", error_data.get("ErrorMessage", e.response.text)
            )
        except Exception:
            error_msg = e.response.text
        return (
            False,
            {"error": f"HTTP {e.response.status_code}: {error_msg}"},
            e.response,
        )
    except httpx.TimeoutException as e:
        logger.error("cyberark_api_timeout", endpoint=endpoint, error=str(e))
        return False, {"error": f"Request timed out after {timeout} seconds"}, None
    except Exception as e:
        logger.error("cyberark_api_error", endpoint=endpoint, error=str(e))
        return False, {"error": str(e)}, None

# ============================================================================
# CREDENTIAL/SETTING EXTRACTION HELPERS
# ============================================================================

def _extract_credentials(
    action: IntegrationAction,
) -> tuple[str | None, str | None, str | None, str]:
    """Extract and return base_url, username, password, auth_method from action.

    Returns:
        (base_url, username, password, auth_method)
    """
    base_url = action.settings.get(SETTINGS_BASE_URL, "").rstrip("/")
    username = action.credentials.get(CREDENTIAL_USERNAME)
    password = action.credentials.get(CREDENTIAL_PASSWORD)
    auth_method = action.settings.get(SETTINGS_AUTH_METHOD, DEFAULT_AUTH_METHOD)
    return base_url, username, password, auth_method

def _validate_credentials(
    action: IntegrationAction,
) -> dict[str, Any] | None:
    """Validate that required credentials and settings are present.

    Returns:
        An error_result dict if validation fails, or None if all is well.
    """
    base_url, username, password, _ = _extract_credentials(action)

    if not base_url:
        return action.error_result(
            MSG_MISSING_BASE_URL, error_type=ERROR_TYPE_CONFIGURATION
        )
    if not username:
        return action.error_result(
            MSG_MISSING_USERNAME, error_type=ERROR_TYPE_CONFIGURATION
        )
    if not password:
        return action.error_result(
            MSG_MISSING_PASSWORD, error_type=ERROR_TYPE_CONFIGURATION
        )
    return None

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for CyberArk PVWA connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Verify connectivity to the CyberArk PVWA server.

        Authenticates, calls the server verify endpoint, then logs off.
        """
        validation_error = _validate_credentials(self)
        if validation_error:
            return validation_error

        base_url, username, password, auth_method = _extract_credentials(self)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Authenticate
        auth_ok, token_or_error = await _authenticate(
            self, base_url, username, password, auth_method, timeout
        )
        if not auth_ok:
            return self.error_result(
                token_or_error.get("error", MSG_AUTHENTICATION_FAILED),
                error_type=ERROR_TYPE_AUTHENTICATION,
                data={"healthy": False},
            )

        session_token = token_or_error

        try:
            # Call the server verify endpoint
            verify_url = f"{base_url}{ENDPOINT_SERVER_VERIFY}"
            try:
                response = await self.http_request(
                    verify_url,
                    method="GET",
                    headers={
                        "Authorization": session_token,
                        "User-Agent": USER_AGENT,
                    },
                    timeout=timeout,
                )
                server_info = {}
                with contextlib.suppress(Exception):
                    server_info = response.json()

                return self.success_result(
                    data={
                        "healthy": True,
                        "api_version": API_VERSION,
                        "server_info": server_info,
                        "auth_method": auth_method,
                    },
                )
            except httpx.HTTPStatusError:
                # Verify endpoint may not exist on all PVWA versions.
                # Authentication success alone is sufficient for health check.
                return self.success_result(
                    data={
                        "healthy": True,
                        "api_version": API_VERSION,
                        "auth_method": auth_method,
                        "message": "Authentication successful (verify endpoint unavailable)",
                    },
                )
        finally:
            await _logoff(self, base_url, session_token, timeout)

class GetAccountAction(IntegrationAction):
    """Get details of a specific privileged account."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get account details by account ID.

        Args:
            **kwargs: Must include 'account_id'.

        Returns:
            Account details including platform, safe, address, username.
        """
        account_id = kwargs.get("account_id")
        if not account_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="account_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        validation_error = _validate_credentials(self)
        if validation_error:
            return validation_error

        base_url, username, password, auth_method = _extract_credentials(self)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        auth_ok, token_or_error = await _authenticate(
            self, base_url, username, password, auth_method, timeout
        )
        if not auth_ok:
            return self.error_result(
                token_or_error.get("error", MSG_AUTHENTICATION_FAILED),
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        session_token = token_or_error

        try:
            endpoint = ENDPOINT_ACCOUNT_BY_ID.format(
                account_id=quote(str(account_id), safe="")
            )
            success, data, _ = await _make_cyberark_request(
                self, base_url, session_token, endpoint, timeout=timeout
            )

            if success:
                return self.success_result(data=data)
            return self.error_result(
                data.get("error", "Failed to get account"),
                error_type=ERROR_TYPE_HTTP_ERROR,
            )
        finally:
            await _logoff(self, base_url, session_token, timeout)

class ListAccountsAction(IntegrationAction):
    """Search and list privileged accounts."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List privileged accounts with optional search filter.

        Args:
            **kwargs: Optional 'search', 'filter', 'safe_name', 'limit', 'offset'.

        Returns:
            List of accounts matching the criteria.
        """
        validation_error = _validate_credentials(self)
        if validation_error:
            return validation_error

        base_url, username, password, auth_method = _extract_credentials(self)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        auth_ok, token_or_error = await _authenticate(
            self, base_url, username, password, auth_method, timeout
        )
        if not auth_ok:
            return self.error_result(
                token_or_error.get("error", MSG_AUTHENTICATION_FAILED),
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        session_token = token_or_error

        try:
            params: dict[str, Any] = {}

            search = kwargs.get("search")
            if search:
                params["search"] = search

            filter_str = kwargs.get("filter")
            if filter_str:
                params["filter"] = filter_str

            safe_name = kwargs.get("safe_name")
            if safe_name:
                params["filter"] = f"safeName eq {safe_name}"

            limit = kwargs.get("limit", DEFAULT_SEARCH_LIMIT)
            if limit:
                params["limit"] = min(int(limit), MAX_SEARCH_LIMIT)

            offset = kwargs.get("offset")
            if offset is not None:
                params["offset"] = int(offset)

            success, data, _ = await _make_cyberark_request(
                self,
                base_url,
                session_token,
                ENDPOINT_ACCOUNTS,
                params=params,
                timeout=timeout,
            )

            if success and isinstance(data, dict):
                accounts = data.get("value", [])
                return self.success_result(
                    data={
                        "accounts": accounts,
                        "total": data.get("count", len(accounts)),
                        "next_offset": data.get("nextLink"),
                    },
                )
            if success:
                return self.success_result(data={"accounts": [], "total": 0})
            return self.error_result(
                data.get("error", "Failed to list accounts"),
                error_type=ERROR_TYPE_HTTP_ERROR,
            )
        finally:
            await _logoff(self, base_url, session_token, timeout)

class ChangeCredentialAction(IntegrationAction):
    """Trigger credential rotation for a privileged account."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Initiate an immediate credential change (password rotation).

        This triggers CyberArk's CPM (Central Policy Manager) to change the
        credential for the specified account. The actual change happens
        asynchronously on the CPM.

        Args:
            **kwargs: Must include 'account_id'.

        Returns:
            Confirmation that the change was initiated.
        """
        account_id = kwargs.get("account_id")
        if not account_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="account_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        validation_error = _validate_credentials(self)
        if validation_error:
            return validation_error

        base_url, username, password, auth_method = _extract_credentials(self)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        auth_ok, token_or_error = await _authenticate(
            self, base_url, username, password, auth_method, timeout
        )
        if not auth_ok:
            return self.error_result(
                token_or_error.get("error", MSG_AUTHENTICATION_FAILED),
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        session_token = token_or_error

        try:
            endpoint = ENDPOINT_ACCOUNT_CHANGE.format(
                account_id=quote(str(account_id), safe="")
            )

            # The Change endpoint accepts an optional ChangeEntireGroup flag
            json_data = {}
            change_entire_group = kwargs.get("change_entire_group")
            if change_entire_group is not None:
                json_data["ChangeEntireGroup"] = bool(change_entire_group)

            success, data, _ = await _make_cyberark_request(
                self,
                base_url,
                session_token,
                endpoint,
                method="POST",
                json_data=json_data,
                timeout=timeout,
            )

            if success:
                return self.success_result(
                    data={
                        "account_id": account_id,
                        "message": "Credential change initiated successfully",
                        "details": data,
                    },
                )
            return self.error_result(
                data.get("error", "Failed to initiate credential change"),
                error_type=ERROR_TYPE_HTTP_ERROR,
            )
        finally:
            await _logoff(self, base_url, session_token, timeout)

class GetSafeAction(IntegrationAction):
    """Get details of a specific safe (credential container)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get safe details by safe name.

        Args:
            **kwargs: Must include 'safe_name'.

        Returns:
            Safe details including description, members, retention policy.
        """
        safe_name = kwargs.get("safe_name")
        if not safe_name:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="safe_name"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        validation_error = _validate_credentials(self)
        if validation_error:
            return validation_error

        base_url, username, password, auth_method = _extract_credentials(self)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        auth_ok, token_or_error = await _authenticate(
            self, base_url, username, password, auth_method, timeout
        )
        if not auth_ok:
            return self.error_result(
                token_or_error.get("error", MSG_AUTHENTICATION_FAILED),
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        session_token = token_or_error

        try:
            endpoint = ENDPOINT_SAFE_BY_NAME.format(
                safe_name=quote(str(safe_name), safe="")
            )
            success, data, response = await _make_cyberark_request(
                self, base_url, session_token, endpoint, timeout=timeout
            )

            if success:
                return self.success_result(data=data)

            # Safe not found
            if response and response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"safe_name": safe_name},
                )
            return self.error_result(
                data.get("error", "Failed to get safe"),
                error_type=ERROR_TYPE_HTTP_ERROR,
            )
        finally:
            await _logoff(self, base_url, session_token, timeout)

class ListSafesAction(IntegrationAction):
    """List available safes (credential containers)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List safes with optional search filter.

        Args:
            **kwargs: Optional 'search', 'limit', 'offset'.

        Returns:
            List of safes.
        """
        validation_error = _validate_credentials(self)
        if validation_error:
            return validation_error

        base_url, username, password, auth_method = _extract_credentials(self)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        auth_ok, token_or_error = await _authenticate(
            self, base_url, username, password, auth_method, timeout
        )
        if not auth_ok:
            return self.error_result(
                token_or_error.get("error", MSG_AUTHENTICATION_FAILED),
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        session_token = token_or_error

        try:
            params: dict[str, Any] = {}

            search = kwargs.get("search")
            if search:
                params["search"] = search

            limit = kwargs.get("limit", DEFAULT_SEARCH_LIMIT)
            if limit:
                params["limit"] = min(int(limit), MAX_SEARCH_LIMIT)

            offset = kwargs.get("offset")
            if offset is not None:
                params["offset"] = int(offset)

            success, data, _ = await _make_cyberark_request(
                self,
                base_url,
                session_token,
                ENDPOINT_SAFES,
                params=params,
                timeout=timeout,
            )

            if success and isinstance(data, dict):
                safes = data.get("value", data.get("Safes", []))
                return self.success_result(
                    data={
                        "safes": safes,
                        "total": data.get("count", len(safes)),
                        "next_offset": data.get("nextLink"),
                    },
                )
            if success:
                return self.success_result(data={"safes": [], "total": 0})
            return self.error_result(
                data.get("error", "Failed to list safes"),
                error_type=ERROR_TYPE_HTTP_ERROR,
            )
        finally:
            await _logoff(self, base_url, session_token, timeout)

class AddAccountAction(IntegrationAction):
    """Add a new privileged account to CyberArk."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add a new account to a safe.

        Args:
            **kwargs: Must include 'safe_name', 'platform_id', 'name'.
                Optional: 'address', 'account_username', 'secret',
                'secret_type', 'properties'.

        Returns:
            Newly created account details.
        """
        safe_name = kwargs.get("safe_name")
        platform_id = kwargs.get("platform_id")
        name = kwargs.get("name")

        if not safe_name:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="safe_name"),
                error_type=ERROR_TYPE_VALIDATION,
            )
        if not platform_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="platform_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )
        if not name:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="name"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        validation_error = _validate_credentials(self)
        if validation_error:
            return validation_error

        base_url, username, password, auth_method = _extract_credentials(self)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        auth_ok, token_or_error = await _authenticate(
            self, base_url, username, password, auth_method, timeout
        )
        if not auth_ok:
            return self.error_result(
                token_or_error.get("error", MSG_AUTHENTICATION_FAILED),
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        session_token = token_or_error

        try:
            account_data: dict[str, Any] = {
                "safeName": safe_name,
                "platformId": platform_id,
                "name": name,
            }

            address = kwargs.get("address")
            if address:
                account_data["address"] = address

            account_username = kwargs.get("account_username")
            if account_username:
                account_data["userName"] = account_username

            secret = kwargs.get("secret")
            if secret:
                account_data["secret"] = secret

            secret_type = kwargs.get("secret_type", "password")
            account_data["secretType"] = secret_type

            properties = kwargs.get("properties")
            if properties and isinstance(properties, dict):
                account_data["platformAccountProperties"] = properties

            success, data, _ = await _make_cyberark_request(
                self,
                base_url,
                session_token,
                ENDPOINT_ACCOUNTS,
                method="POST",
                json_data=account_data,
                timeout=timeout,
            )

            if success:
                return self.success_result(data=data)
            return self.error_result(
                data.get("error", "Failed to add account"),
                error_type=ERROR_TYPE_HTTP_ERROR,
            )
        finally:
            await _logoff(self, base_url, session_token, timeout)

class GetUserAction(IntegrationAction):
    """Get CyberArk user details."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get user details by user ID.

        Args:
            **kwargs: Must include 'user_id'.

        Returns:
            User details including username, source, type, groups.
        """
        user_id = kwargs.get("user_id")
        if not user_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format(param="user_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        validation_error = _validate_credentials(self)
        if validation_error:
            return validation_error

        base_url, username, password, auth_method = _extract_credentials(self)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        auth_ok, token_or_error = await _authenticate(
            self, base_url, username, password, auth_method, timeout
        )
        if not auth_ok:
            return self.error_result(
                token_or_error.get("error", MSG_AUTHENTICATION_FAILED),
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        session_token = token_or_error

        try:
            endpoint = ENDPOINT_USER_BY_ID.format(user_id=quote(str(user_id), safe=""))
            success, data, response = await _make_cyberark_request(
                self, base_url, session_token, endpoint, timeout=timeout
            )

            if success:
                return self.success_result(data=data)

            # User not found
            if response and response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"user_id": user_id},
                )
            return self.error_result(
                data.get("error", "Failed to get user"),
                error_type=ERROR_TYPE_HTTP_ERROR,
            )
        finally:
            await _logoff(self, base_url, session_token, timeout)

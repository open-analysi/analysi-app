"""
Jamf Pro MDM integration actions.
Uses requests/Basic Auth in upstream -> self.http_request() with token auth in Naxos.

Jamf Pro authentication flow:
  1. POST /api/v1/auth/token with Basic Auth (username:password)
  2. Response contains bearer token
  3. Subsequent requests use Authorization: Bearer <token>

Supports both Classic API (/JSSResource) and Jamf Pro API (/api/v1, /api/v2).
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.jamf.constants import (
    AUTH_TOKEN_ENDPOINT,
    CLASSIC_ACCOUNTS_ENDPOINT,
    CLASSIC_COMPUTERS_BY_ID_ENDPOINT,
    CLASSIC_COMPUTERS_ENDPOINT,
    CLASSIC_MOBILE_DEVICES_BY_ID_ENDPOINT,
    CLASSIC_MOBILE_DEVICES_ENDPOINT,
    CLASSIC_USERS_BY_NAME_ENDPOINT,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_LOCK_PASSCODE,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    LOCK_COMPUTER_ENDPOINT,
    MSG_INVALID_DEVICE_ID,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAMETER,
    MSG_TOKEN_FAILED,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
    WIPE_COMPUTER_ENDPOINT,
)

logger = get_logger(__name__)

# ============================================================================
# AUTHENTICATION MIXIN
# ============================================================================

class JamfAuthMixin:
    """Mixin to handle Jamf Pro token-based authentication.

    Jamf Pro API uses Basic Auth to obtain a bearer token via
    POST /api/v1/auth/token. The token is then used for all
    subsequent API calls.
    """

    _access_token: str | None = None

    def _get_base_url(self) -> str:
        """Get and validate the Jamf Pro base URL from settings."""
        base_url = self.settings.get(SETTINGS_BASE_URL, "")
        if not base_url:
            raise ValueError(MSG_MISSING_BASE_URL)
        return base_url.rstrip("/")

    def _get_credentials(self) -> tuple[str, str]:
        """Get and validate username/password from credentials."""
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        if not username or not password:
            raise ValueError(MSG_MISSING_CREDENTIALS)
        return username, password

    async def _get_access_token(self) -> str:
        """Obtain or reuse a bearer token from Jamf Pro.

        Returns:
            Bearer token string.

        Raises:
            ValueError: If credentials or base_url are missing.
            httpx.HTTPStatusError: If token request fails.
        """
        if self._access_token:
            return self._access_token

        base_url = self._get_base_url()
        username, password = self._get_credentials()
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        url = f"{base_url}{AUTH_TOKEN_ENDPOINT}"

        response = await self.http_request(
            url,
            method="POST",
            auth=(username, password),
            timeout=timeout,
        )

        token_data = response.json()
        self._access_token = token_data.get("token")

        if not self._access_token:
            raise ValueError(MSG_TOKEN_FAILED)

        return self._access_token

    async def _make_api_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict | None = None,
        json_data: dict | None = None,
        retry_auth: bool = True,
    ) -> httpx.Response:
        """Make an authenticated API request to Jamf Pro.

        Args:
            endpoint: API endpoint path (appended to base_url).
            method: HTTP method.
            params: Query parameters.
            json_data: JSON request body.
            retry_auth: Whether to retry on 401 with a fresh token.

        Returns:
            httpx.Response object.
        """
        base_url = self._get_base_url()
        url = f"{base_url}{endpoint}"

        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                url,
                method=method.upper(),
                params=params,
                json_data=json_data,
                headers=headers,
                timeout=timeout,
            )
        except httpx.HTTPStatusError as e:
            # Handle token expiration: retry once with a fresh token
            if e.response.status_code == 401 and retry_auth:
                self._access_token = None
                return await self._make_api_request(
                    endpoint, method, params, json_data, retry_auth=False
                )
            raise

        return response

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(IntegrationAction, JamfAuthMixin):
    """Verify connectivity to the Jamf Pro instance."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity by obtaining a token and querying accounts.

        Mirrors the upstream connector's test_connectivity which hits /accounts.
        """
        try:
            await self._get_access_token()

            # Hit the accounts endpoint (same as upstream test_connectivity)
            response = await self._make_api_request(CLASSIC_ACCOUNTS_ENDPOINT)
            response_data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Successfully connected to Jamf Pro",
                    "accounts": response_data,
                }
            )

        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except httpx.HTTPStatusError as e:
            return self.error_result(
                f"HTTP {e.response.status_code}: {e!s}",
                error_type=ERROR_TYPE_AUTHENTICATION
                if e.response.status_code == 401
                else ERROR_TYPE_CONFIGURATION,
            )
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# DEVICE ACTIONS (Computers)
# ============================================================================

def _validate_device_id(device_id: Any) -> int | None:
    """Validate and convert device_id to a positive integer.

    Returns:
        Validated integer ID, or None if invalid.
    """
    if device_id is None:
        return None
    try:
        value = int(device_id)
        if value <= 0:
            return None
        return value
    except (ValueError, TypeError):
        return None

class GetDeviceAction(IntegrationAction, JamfAuthMixin):
    """Get detailed information about a managed computer/device by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve computer details from Jamf Pro Classic API.

        Args:
            id: Computer ID (positive integer).
        """
        raw_id = kwargs.get("id")
        if raw_id is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        device_id = _validate_device_id(raw_id)
        if device_id is None:
            return self.error_result(
                MSG_INVALID_DEVICE_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            endpoint = CLASSIC_COMPUTERS_BY_ID_ENDPOINT.format(id=device_id)
            response = await self._make_api_request(endpoint)
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("jamf_device_not_found", device_id=device_id)
                return self.success_result(
                    not_found=True,
                    data={"id": device_id},
                )
            return self.error_result(e)
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

class ListDevicesAction(IntegrationAction, JamfAuthMixin):
    """List or search managed computers in Jamf Pro."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List computers from the Classic API.

        Args:
            query: Optional search/match string to filter computers.
        """
        query = kwargs.get("query")

        try:
            if query:
                endpoint = f"{CLASSIC_COMPUTERS_ENDPOINT}/match/{query}"
            else:
                endpoint = CLASSIC_COMPUTERS_ENDPOINT

            response = await self._make_api_request(endpoint)
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# MOBILE DEVICE ACTIONS
# ============================================================================

class GetMobileDeviceAction(IntegrationAction, JamfAuthMixin):
    """Get detailed information about a managed mobile device by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve mobile device details from Jamf Pro Classic API.

        Args:
            id: Mobile device ID (positive integer).
        """
        raw_id = kwargs.get("id")
        if raw_id is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        device_id = _validate_device_id(raw_id)
        if device_id is None:
            return self.error_result(
                MSG_INVALID_DEVICE_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            endpoint = CLASSIC_MOBILE_DEVICES_BY_ID_ENDPOINT.format(id=device_id)
            response = await self._make_api_request(endpoint)
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("jamf_mobile_device_not_found", device_id=device_id)
                return self.success_result(
                    not_found=True,
                    data={"id": device_id},
                )
            return self.error_result(e)
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

class ListMobileDevicesAction(IntegrationAction, JamfAuthMixin):
    """List managed mobile devices in Jamf Pro."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List mobile devices from the Classic API."""
        try:
            response = await self._make_api_request(CLASSIC_MOBILE_DEVICES_ENDPOINT)
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# DEVICE MANAGEMENT COMMANDS
# ============================================================================

class LockDeviceAction(IntegrationAction, JamfAuthMixin):
    """Send a remote lock command to a managed computer."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Send DeviceLock command to a computer.

        Args:
            id: Computer ID (positive integer).
            passcode: Lock passcode (6-digit string, defaults to "000000").
        """
        raw_id = kwargs.get("id")
        if raw_id is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        device_id = _validate_device_id(raw_id)
        if device_id is None:
            return self.error_result(
                MSG_INVALID_DEVICE_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        passcode = kwargs.get("passcode", DEFAULT_LOCK_PASSCODE)

        try:
            endpoint = LOCK_COMPUTER_ENDPOINT.format(id=device_id)
            # The Classic API lock command uses passcode as a query param
            response = await self._make_api_request(
                endpoint,
                method="POST",
                params={"passcode": passcode},
            )
            data = response.json()

            return self.success_result(
                data={
                    "device_id": device_id,
                    "command": "DeviceLock",
                    "response": data,
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("jamf_lock_device_not_found", device_id=device_id)
                return self.success_result(
                    not_found=True,
                    data={"id": device_id},
                )
            return self.error_result(e)
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

class WipeDeviceAction(IntegrationAction, JamfAuthMixin):
    """Send a remote wipe (erase) command to a managed computer."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Send EraseDevice command to a computer.

        Args:
            id: Computer ID (positive integer).
            passcode: Wipe passcode (6-digit string, defaults to "000000").
        """
        raw_id = kwargs.get("id")
        if raw_id is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        device_id = _validate_device_id(raw_id)
        if device_id is None:
            return self.error_result(
                MSG_INVALID_DEVICE_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        passcode = kwargs.get("passcode", DEFAULT_LOCK_PASSCODE)

        try:
            endpoint = WIPE_COMPUTER_ENDPOINT.format(id=device_id)
            response = await self._make_api_request(
                endpoint,
                method="POST",
                params={"passcode": passcode},
            )
            data = response.json()

            return self.success_result(
                data={
                    "device_id": device_id,
                    "command": "EraseDevice",
                    "response": data,
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("jamf_wipe_device_not_found", device_id=device_id)
                return self.success_result(
                    not_found=True,
                    data={"id": device_id},
                )
            return self.error_result(e)
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# USER ACTIONS
# ============================================================================

class GetUserAction(IntegrationAction, JamfAuthMixin):
    """Get information about a Jamf Pro user by username."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve user details from the Classic API.

        Args:
            username: Username to look up.
        """
        username = kwargs.get("username")
        if not username:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("username"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            endpoint = CLASSIC_USERS_BY_NAME_ENDPOINT.format(username=username)
            response = await self._make_api_request(endpoint)
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("jamf_user_not_found", username=username)
                return self.success_result(
                    not_found=True,
                    data={"username": username},
                )
            return self.error_result(e)
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_CONFIGURATION)
        except Exception as e:
            return self.error_result(e)

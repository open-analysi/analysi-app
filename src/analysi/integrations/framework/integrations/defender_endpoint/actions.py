"""Microsoft Defender for Endpoint integration actions."""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.defender_endpoint.constants import (
    ALERT_STATUS_IN_PROGRESS,
    ALERT_STATUS_NEW,
    ALERT_STATUS_RESOLVED,
    CREDENTIAL_CLIENT_ID,
    CREDENTIAL_CLIENT_SECRET,
    DEFAULT_ALERT_LIMIT,
    DEFAULT_TIMEOUT,
    DEFENDER_API_BASE_URL,
    DEFENDER_API_GCC_BASE_URL,
    DEFENDER_API_GCC_HIGH_BASE_URL,
    DEFENDER_LOGIN_BASE_URL,
    DEFENDER_LOGIN_GCC_BASE_URL,
    DEFENDER_LOGIN_GCC_HIGH_BASE_URL,
    DEFENDER_RESOURCE_GCC_HIGH_URL,
    DEFENDER_RESOURCE_GCC_URL,
    DEFENDER_RESOURCE_URL,
    ENDPOINT_DEVICE_DETAILS,
    ENDPOINT_GET_ALERT,
    ENDPOINT_ISOLATE,
    ENDPOINT_LIST_ALERTS,
    ENDPOINT_MACHINES,
    ENDPOINT_QUARANTINE_FILE,
    ENDPOINT_REMOVE_APP_RESTRICTION,
    ENDPOINT_RESTRICT_APP,
    ENDPOINT_RUN_QUERY,
    ENDPOINT_SCAN_DEVICE,
    ENDPOINT_UNISOLATE,
    ENDPOINT_UPDATE_ALERT,
    ENVIRONMENT_GCC,
    ENVIRONMENT_GCC_HIGH,
    ENVIRONMENT_PUBLIC,
    ERROR_ACTION_ID_UNAVAILABLE,
    ERROR_INVALID_ISOLATION_TYPE,
    ERROR_INVALID_SCAN_TYPE,
    ERROR_MISSING_ALERT_ID,
    ERROR_MISSING_COMMENT,
    ERROR_MISSING_CREDENTIALS,
    ERROR_MISSING_DEVICE_ID,
    ERROR_TOKEN_FAILED,
    ISOLATION_TYPE_FULL,
    ISOLATION_TYPE_SELECTIVE,
    SCAN_TYPE_FULL,
    SCAN_TYPE_QUICK,
    SETTINGS_ENVIRONMENT,
    SETTINGS_TENANT_ID,
    SETTINGS_TIMEOUT,
    SUCCESS_ALERT_UPDATED,
    SUCCESS_APP_RESTRICTED,
    SUCCESS_APP_RESTRICTION_REMOVED,
    SUCCESS_DEVICE_ISOLATED,
    SUCCESS_DEVICE_RELEASED,
    SUCCESS_FILE_QUARANTINED,
    SUCCESS_SCAN_INITIATED,
)

logger = get_logger(__name__)

# ============================================================================
# AUTHENTICATION & API HELPERS
# ============================================================================

async def _get_access_token(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    environment: str = ENVIRONMENT_PUBLIC,
    timeout: int = DEFAULT_TIMEOUT,
    http_request=None,
) -> str:
    """Acquire OAuth2 access token for Microsoft Defender API.

    Args:
        tenant_id: Azure AD tenant ID
        client_id: Application (client) ID
        client_secret: Client secret
        environment: Cloud environment (Public, GCC, GCC High)
        timeout: Request timeout in seconds

    Returns:
        Access token string

    Raises:
        Exception: If token acquisition fails
    """
    # Determine login URL based on environment
    if environment == ENVIRONMENT_GCC:
        login_url = DEFENDER_LOGIN_GCC_BASE_URL
        resource = DEFENDER_RESOURCE_GCC_URL
    elif environment == ENVIRONMENT_GCC_HIGH:
        login_url = DEFENDER_LOGIN_GCC_HIGH_BASE_URL
        resource = DEFENDER_RESOURCE_GCC_HIGH_URL
    else:
        login_url = DEFENDER_LOGIN_BASE_URL
        resource = DEFENDER_RESOURCE_URL

    token_url = f"{login_url}/{tenant_id}/oauth2/token"

    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "resource": resource,
    }

    try:
        if http_request:
            response = await http_request(
                token_url,
                method="POST",
                data=data,
                timeout=timeout,
            )
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(token_url, data=data)
                response.raise_for_status()
        token_data = response.json()
        return token_data["access_token"]
    except httpx.HTTPStatusError as e:
        logger.error(
            "token_acquisition_failed_http", status_code=e.response.status_code
        )
        raise Exception(f"{ERROR_TOKEN_FAILED}: HTTP {e.response.status_code}")
    except KeyError:
        logger.error("Token acquisition failed: Invalid response format")
        raise Exception(f"{ERROR_TOKEN_FAILED}: Invalid response format")
    except Exception as e:
        logger.error("token_acquisition_failed", error=str(e))
        raise Exception(f"{ERROR_TOKEN_FAILED}: {e!s}")

async def _make_defender_request(
    endpoint: str,
    access_token: str,
    environment: str = ENVIRONMENT_PUBLIC,
    method: str = "GET",
    data: dict | None = None,
    params: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    http_request=None,
) -> dict[str, Any]:
    """Make HTTP request to Microsoft Defender API.

    Args:
        endpoint: API endpoint path
        access_token: OAuth2 access token
        environment: Cloud environment
        method: HTTP method
        data: Request body data
        params: Query parameters
        timeout: Request timeout in seconds
        http_request: Optional http_request callable (from IntegrationAction)

    Returns:
        API response data

    Raises:
        Exception: On API errors
    """
    # Determine API base URL based on environment
    if environment == ENVIRONMENT_GCC:
        base_url = DEFENDER_API_GCC_BASE_URL
    elif environment == ENVIRONMENT_GCC_HIGH:
        base_url = DEFENDER_API_GCC_HIGH_BASE_URL
    else:
        base_url = DEFENDER_API_BASE_URL

    url = f"{base_url}{endpoint}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        if http_request:
            response = await http_request(
                url,
                method=method,
                headers=headers,
                params=params if method == "GET" else None,
                json_data=data if method in ("GET", "POST", "PATCH") else None,
                timeout=timeout,
            )
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method == "POST":
                    response = await client.post(url, headers=headers, json=data)
                elif method == "PATCH":
                    response = await client.patch(url, headers=headers, json=data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                response.raise_for_status()

        return response.json()

    except httpx.TimeoutException as e:
        logger.error("defender_api_timeout_for", endpoint=endpoint, error=str(e))
        raise Exception(f"Request timed out after {timeout} seconds")
    except httpx.HTTPStatusError as e:
        logger.error("defender_api_http_error", status_code=e.response.status_code)
        error_detail = e.response.text
        if e.response.status_code == 401:
            raise Exception("Authentication failed - invalid or expired token")
        if e.response.status_code == 403:
            raise Exception("Access forbidden - insufficient permissions")
        if e.response.status_code == 404:
            raise Exception("Resource not found")
        if e.response.status_code == 429:
            raise Exception("Rate limit exceeded")
        raise Exception(f"HTTP {e.response.status_code}: {error_detail}")
    except Exception as e:
        logger.error("defender_api_error", error=str(e))
        raise

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Microsoft Defender for Endpoint API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Microsoft Defender API connectivity and authentication.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "healthy": False,
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
                "data": {"healthy": False},
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
                environment=environment,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Test API connectivity by listing machines (with limit 1)
            await _make_defender_request(
                endpoint=ENDPOINT_MACHINES,
                access_token=access_token,
                environment=environment,
                params={"$top": "1"},
                timeout=timeout,
                http_request=self.http_request,
            )

            return {
                "healthy": True,
                "status": "success",
                "message": "Microsoft Defender for Endpoint API is accessible",
                "data": {
                    "healthy": True,
                    "environment": environment,
                    "tenant_id": tenant_id,
                },
            }

        except Exception as e:
            logger.error("defender_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class IsolateDeviceAction(IntegrationAction):
    """Isolate a device from the network."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Isolate device (quarantine).

        Args:
            **kwargs: Must contain:
                - device_id: Device identifier
                - comment: Reason for isolation
                - isolation_type: 'Full' or 'Selective' (optional, default: Full)

        Returns:
            Result with isolation action details
        """
        # Validate required parameters
        device_id = kwargs.get("device_id")
        if not device_id:
            return {
                "status": "error",
                "error": ERROR_MISSING_DEVICE_ID,
                "error_type": "ValidationError",
            }

        comment = kwargs.get("comment")
        if not comment:
            return {
                "status": "error",
                "error": ERROR_MISSING_COMMENT,
                "error_type": "ValidationError",
            }

        isolation_type = kwargs.get("isolation_type", ISOLATION_TYPE_FULL)
        if isolation_type not in [ISOLATION_TYPE_FULL, ISOLATION_TYPE_SELECTIVE]:
            return {
                "status": "error",
                "error": ERROR_INVALID_ISOLATION_TYPE,
                "error_type": "ValidationError",
            }

        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # Isolate device
            endpoint = ENDPOINT_ISOLATE.format(device_id=device_id)
            request_data = {"Comment": comment, "IsolationType": isolation_type}

            response = await _make_defender_request(
                endpoint=endpoint,
                access_token=access_token,
                environment=environment,
                method="POST",
                data=request_data,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Extract action ID
            action_id = response.get("id")
            if not action_id:
                return {
                    "status": "error",
                    "error": ERROR_ACTION_ID_UNAVAILABLE,
                    "error_type": "APIError",
                }

            return {
                "status": "success",
                "message": SUCCESS_DEVICE_ISOLATED,
                "device_id": device_id,
                "action_id": action_id,
                "isolation_type": isolation_type,
                "action_status": response.get("status"),
                "full_data": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("defender_isolate_device_not_found", device_id=device_id)
                return {
                    "status": "success",
                    "not_found": True,
                    "device_id": device_id,
                    "message": "Device not found",
                }
            logger.error(
                "device_isolation_failed_for", device_id=device_id, error=str(e)
            )
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ReleaseDeviceAction(IntegrationAction):
    """Release a device from isolation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Release device from isolation (unquarantine).

        Args:
            **kwargs: Must contain:
                - device_id: Device identifier
                - comment: Reason for release

        Returns:
            Result with release action details
        """
        # Validate required parameters
        device_id = kwargs.get("device_id")
        if not device_id:
            return {
                "status": "error",
                "error": ERROR_MISSING_DEVICE_ID,
                "error_type": "ValidationError",
            }

        comment = kwargs.get("comment")
        if not comment:
            return {
                "status": "error",
                "error": ERROR_MISSING_COMMENT,
                "error_type": "ValidationError",
            }

        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # Release device
            endpoint = ENDPOINT_UNISOLATE.format(device_id=device_id)
            request_data = {"Comment": comment}

            response = await _make_defender_request(
                endpoint=endpoint,
                access_token=access_token,
                environment=environment,
                method="POST",
                data=request_data,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Extract action ID
            action_id = response.get("id")
            if not action_id:
                return {
                    "status": "error",
                    "error": ERROR_ACTION_ID_UNAVAILABLE,
                    "error_type": "APIError",
                }

            return {
                "status": "success",
                "message": SUCCESS_DEVICE_RELEASED,
                "device_id": device_id,
                "action_id": action_id,
                "action_status": response.get("status"),
                "full_data": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("defender_release_device_not_found", device_id=device_id)
                return {
                    "status": "success",
                    "not_found": True,
                    "device_id": device_id,
                    "message": "Device not found",
                }
            logger.error("device_release_failed_for", device_id=device_id, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ScanDeviceAction(IntegrationAction):
    """Run antivirus scan on a device."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Run antivirus scan on device.

        Args:
            **kwargs: Must contain:
                - device_id: Device identifier
                - comment: Reason for scan
                - scan_type: 'Quick' or 'Full' (optional, default: Quick)

        Returns:
            Result with scan action details
        """
        # Validate required parameters
        device_id = kwargs.get("device_id")
        if not device_id:
            return {
                "status": "error",
                "error": ERROR_MISSING_DEVICE_ID,
                "error_type": "ValidationError",
            }

        comment = kwargs.get("comment")
        if not comment:
            return {
                "status": "error",
                "error": ERROR_MISSING_COMMENT,
                "error_type": "ValidationError",
            }

        scan_type = kwargs.get("scan_type", SCAN_TYPE_QUICK)
        if scan_type not in [SCAN_TYPE_QUICK, SCAN_TYPE_FULL]:
            return {
                "status": "error",
                "error": ERROR_INVALID_SCAN_TYPE,
                "error_type": "ValidationError",
            }

        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # Initiate scan
            endpoint = ENDPOINT_SCAN_DEVICE.format(device_id=device_id)
            request_data = {"Comment": comment, "ScanType": scan_type}

            response = await _make_defender_request(
                endpoint=endpoint,
                access_token=access_token,
                environment=environment,
                method="POST",
                data=request_data,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Extract action ID
            action_id = response.get("id")
            if not action_id:
                return {
                    "status": "error",
                    "error": ERROR_ACTION_ID_UNAVAILABLE,
                    "error_type": "APIError",
                }

            return {
                "status": "success",
                "message": SUCCESS_SCAN_INITIATED,
                "device_id": device_id,
                "action_id": action_id,
                "scan_type": scan_type,
                "action_status": response.get("status"),
                "full_data": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("defender_scan_device_not_found", device_id=device_id)
                return {
                    "status": "success",
                    "not_found": True,
                    "device_id": device_id,
                    "message": "Device not found",
                }
            logger.error("device_scan_failed_for", device_id=device_id, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class QuarantineFileAction(IntegrationAction):
    """Quarantine a file on a device."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Quarantine file on device.

        Args:
            **kwargs: Must contain:
                - device_id: Device identifier
                - file_hash: SHA1 hash of file to quarantine
                - comment: Reason for quarantine

        Returns:
            Result with quarantine action details
        """
        # Validate required parameters
        device_id = kwargs.get("device_id")
        if not device_id:
            return {
                "status": "error",
                "error": ERROR_MISSING_DEVICE_ID,
                "error_type": "ValidationError",
            }

        file_hash = kwargs.get("file_hash")
        if not file_hash:
            return {
                "status": "error",
                "error": "Missing required parameter 'file_hash'",
                "error_type": "ValidationError",
            }

        comment = kwargs.get("comment")
        if not comment:
            return {
                "status": "error",
                "error": ERROR_MISSING_COMMENT,
                "error_type": "ValidationError",
            }

        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # Quarantine file
            endpoint = ENDPOINT_QUARANTINE_FILE.format(device_id=device_id)
            request_data = {"Comment": comment, "Sha1": file_hash}

            response = await _make_defender_request(
                endpoint=endpoint,
                access_token=access_token,
                environment=environment,
                method="POST",
                data=request_data,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Extract action ID
            action_id = response.get("id")
            if not action_id:
                return {
                    "status": "error",
                    "error": ERROR_ACTION_ID_UNAVAILABLE,
                    "error_type": "APIError",
                }

            return {
                "status": "success",
                "message": SUCCESS_FILE_QUARANTINED,
                "device_id": device_id,
                "file_hash": file_hash,
                "action_id": action_id,
                "action_status": response.get("status"),
                "full_data": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info(
                    "defender_quarantine_file_not_found",
                    device_id=device_id,
                    file_hash=file_hash,
                )
                return {
                    "status": "success",
                    "not_found": True,
                    "device_id": device_id,
                    "message": "Device not found",
                }
            logger.error(
                "file_quarantine_failed_for_on",
                file_hash=file_hash,
                device_id=device_id,
                error=str(e),
            )
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class RestrictAppExecutionAction(IntegrationAction):
    """Restrict application execution on a device."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Restrict app execution on device.

        Args:
            **kwargs: Must contain:
                - device_id: Device identifier
                - comment: Reason for restriction

        Returns:
            Result with restriction action details
        """
        # Validate required parameters
        device_id = kwargs.get("device_id")
        if not device_id:
            return {
                "status": "error",
                "error": ERROR_MISSING_DEVICE_ID,
                "error_type": "ValidationError",
            }

        comment = kwargs.get("comment")
        if not comment:
            return {
                "status": "error",
                "error": ERROR_MISSING_COMMENT,
                "error_type": "ValidationError",
            }

        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # Restrict app execution
            endpoint = ENDPOINT_RESTRICT_APP.format(device_id=device_id)
            request_data = {"Comment": comment}

            response = await _make_defender_request(
                endpoint=endpoint,
                access_token=access_token,
                environment=environment,
                method="POST",
                data=request_data,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Extract action ID
            action_id = response.get("id")
            if not action_id:
                return {
                    "status": "error",
                    "error": ERROR_ACTION_ID_UNAVAILABLE,
                    "error_type": "APIError",
                }

            return {
                "status": "success",
                "message": SUCCESS_APP_RESTRICTED,
                "device_id": device_id,
                "action_id": action_id,
                "action_status": response.get("status"),
                "full_data": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("defender_restrict_app_not_found", device_id=device_id)
                return {
                    "status": "success",
                    "not_found": True,
                    "device_id": device_id,
                    "message": "Device not found",
                }
            logger.error(
                "app_execution_restriction_failed_for",
                device_id=device_id,
                error=str(e),
            )
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class UnrestrictAppExecutionAction(IntegrationAction):
    """Remove application execution restriction from a device."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Remove app execution restriction from device.

        Args:
            **kwargs: Must contain:
                - device_id: Device identifier
                - comment: Reason for removing restriction

        Returns:
            Result with unrestriction action details
        """
        # Validate required parameters
        device_id = kwargs.get("device_id")
        if not device_id:
            return {
                "status": "error",
                "error": ERROR_MISSING_DEVICE_ID,
                "error_type": "ValidationError",
            }

        comment = kwargs.get("comment")
        if not comment:
            return {
                "status": "error",
                "error": ERROR_MISSING_COMMENT,
                "error_type": "ValidationError",
            }

        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # Remove app execution restriction
            endpoint = ENDPOINT_REMOVE_APP_RESTRICTION.format(device_id=device_id)
            request_data = {"Comment": comment}

            response = await _make_defender_request(
                endpoint=endpoint,
                access_token=access_token,
                environment=environment,
                method="POST",
                data=request_data,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Extract action ID
            action_id = response.get("id")
            if not action_id:
                return {
                    "status": "error",
                    "error": ERROR_ACTION_ID_UNAVAILABLE,
                    "error_type": "APIError",
                }

            return {
                "status": "success",
                "message": SUCCESS_APP_RESTRICTION_REMOVED,
                "device_id": device_id,
                "action_id": action_id,
                "action_status": response.get("status"),
                "full_data": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("defender_unrestrict_app_not_found", device_id=device_id)
                return {
                    "status": "success",
                    "not_found": True,
                    "device_id": device_id,
                    "message": "Device not found",
                }
            logger.error(
                "app_execution_unrestriction_failed_for",
                device_id=device_id,
                error=str(e),
            )
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ListDevicesAction(IntegrationAction):
    """List devices in Microsoft Defender."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List devices.

        Args:
            **kwargs: Optional:
                - limit: Maximum number of devices to return

        Returns:
            Result with device list
        """
        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)
        limit = kwargs.get("limit", 100)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # List devices
            params = {"$top": str(limit)}
            response = await _make_defender_request(
                endpoint=ENDPOINT_MACHINES,
                access_token=access_token,
                environment=environment,
                params=params,
                timeout=timeout,
                http_request=self.http_request,
            )

            devices = response.get("value", [])
            return {
                "status": "success",
                "device_count": len(devices),
                "devices": devices,
                "full_data": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("defender_list_devices_not_found")
                return {
                    "status": "success",
                    "not_found": True,
                    "device_count": 0,
                    "devices": [],
                }
            logger.error("list_devices_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ListAlertsAction(IntegrationAction):
    """List alerts in Microsoft Defender."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List alerts.

        Args:
            **kwargs: Optional:
                - limit: Maximum number of alerts to return
                - status: Filter by alert status (New, InProgress, Resolved)

        Returns:
            Result with alert list
        """
        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)
        limit = kwargs.get("limit", DEFAULT_ALERT_LIMIT)
        status_filter = kwargs.get("status")

        # Validate status filter before token acquisition
        if status_filter and status_filter not in [
            ALERT_STATUS_NEW,
            ALERT_STATUS_IN_PROGRESS,
            ALERT_STATUS_RESOLVED,
        ]:
            return {
                "status": "error",
                "error": f"Invalid status. Must be one of: {ALERT_STATUS_NEW}, {ALERT_STATUS_IN_PROGRESS}, {ALERT_STATUS_RESOLVED}",
                "error_type": "ValidationError",
            }

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # Build query parameters
            params = {"$top": str(limit)}
            if status_filter:
                params["$filter"] = f"status eq '{status_filter}'"

            # List alerts
            response = await _make_defender_request(
                endpoint=ENDPOINT_LIST_ALERTS,
                access_token=access_token,
                environment=environment,
                params=params,
                timeout=timeout,
                http_request=self.http_request,
            )

            alerts = response.get("value", [])
            return {
                "status": "success",
                "alert_count": len(alerts),
                "alerts": alerts,
                "full_data": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("defender_list_alerts_not_found")
                return {
                    "status": "success",
                    "not_found": True,
                    "alert_count": 0,
                    "alerts": [],
                }
            logger.error("list_alerts_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetAlertAction(IntegrationAction):
    """Get details of a specific alert."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get alert details.

        Args:
            **kwargs: Must contain:
                - alert_id: Alert identifier

        Returns:
            Result with alert details
        """
        # Validate required parameters
        alert_id = kwargs.get("alert_id")
        if not alert_id:
            return {
                "status": "error",
                "error": ERROR_MISSING_ALERT_ID,
                "error_type": "ValidationError",
            }

        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # Get alert
            endpoint = ENDPOINT_GET_ALERT.format(alert_id=alert_id)
            response = await _make_defender_request(
                endpoint=endpoint,
                access_token=access_token,
                environment=environment,
                timeout=timeout,
                http_request=self.http_request,
            )

            return {
                "status": "success",
                "alert_id": alert_id,
                "alert": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("defender_get_alert_not_found", alert_id=alert_id)
                return {
                    "status": "success",
                    "not_found": True,
                    "alert_id": alert_id,
                }
            logger.error("get_alert_failed_for", alert_id=alert_id, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetDeviceDetailsAction(IntegrationAction):
    """Get details of a specific device."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get device details.

        Args:
            **kwargs: Must contain:
                - device_id: Device identifier

        Returns:
            Result with device details
        """
        # Validate required parameters
        device_id = kwargs.get("device_id")
        if not device_id:
            return {
                "status": "error",
                "error": ERROR_MISSING_DEVICE_ID,
                "error_type": "ValidationError",
            }

        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # Get device details
            endpoint = ENDPOINT_DEVICE_DETAILS.format(device_id=device_id)
            response = await _make_defender_request(
                endpoint=endpoint,
                access_token=access_token,
                environment=environment,
                timeout=timeout,
                http_request=self.http_request,
            )

            return {
                "status": "success",
                "device_id": device_id,
                "device": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("defender_get_device_not_found", device_id=device_id)
                return {
                    "status": "success",
                    "not_found": True,
                    "device_id": device_id,
                }
            logger.error(
                "get_device_details_failed_for", device_id=device_id, error=str(e)
            )
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class UpdateAlertAction(IntegrationAction):
    """Update an alert's status or assignment."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update alert.

        Args:
            **kwargs: Must contain:
                - alert_id: Alert identifier
                - status: New status (New, InProgress, Resolved) - optional
                - assigned_to: User to assign alert to - optional
                - classification: Alert classification - optional
                - determination: Alert determination - optional
                - comment: Comment for the update - optional

        Returns:
            Result with updated alert details
        """
        # Validate required parameters
        alert_id = kwargs.get("alert_id")
        if not alert_id:
            return {
                "status": "error",
                "error": ERROR_MISSING_ALERT_ID,
                "error_type": "ValidationError",
            }

        # Build update data
        update_data = {}
        if "status" in kwargs:
            status = kwargs["status"]
            if status not in [
                ALERT_STATUS_NEW,
                ALERT_STATUS_IN_PROGRESS,
                ALERT_STATUS_RESOLVED,
            ]:
                return {
                    "status": "error",
                    "error": f"Invalid status. Must be one of: {ALERT_STATUS_NEW}, {ALERT_STATUS_IN_PROGRESS}, {ALERT_STATUS_RESOLVED}",
                    "error_type": "ValidationError",
                }
            update_data["status"] = status

        if "assigned_to" in kwargs:
            update_data["assignedTo"] = kwargs["assigned_to"]
        if "classification" in kwargs:
            update_data["classification"] = kwargs["classification"]
        if "determination" in kwargs:
            update_data["determination"] = kwargs["determination"]
        if "comment" in kwargs:
            update_data["comment"] = kwargs["comment"]

        if not update_data:
            return {
                "status": "error",
                "error": "At least one update field must be provided (status, assigned_to, classification, determination, comment)",
                "error_type": "ValidationError",
            }

        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # Update alert
            endpoint = ENDPOINT_UPDATE_ALERT.format(alert_id=alert_id)
            response = await _make_defender_request(
                endpoint=endpoint,
                access_token=access_token,
                environment=environment,
                method="PATCH",
                data=update_data,
                timeout=timeout,
                http_request=self.http_request,
            )

            return {
                "status": "success",
                "message": SUCCESS_ALERT_UPDATED,
                "alert_id": alert_id,
                "alert": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("defender_update_alert_not_found", alert_id=alert_id)
                return {
                    "status": "success",
                    "not_found": True,
                    "alert_id": alert_id,
                    "message": "Alert not found",
                }
            logger.error("update_alert_failed_for", alert_id=alert_id, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class RunAdvancedQueryAction(IntegrationAction):
    """Run advanced hunting query."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Run advanced hunting query.

        Args:
            **kwargs: Must contain:
                - query: KQL query string

        Returns:
            Result with query results
        """
        # Validate required parameters
        query = kwargs.get("query")
        if not query:
            return {
                "status": "error",
                "error": "Missing required parameter 'query'",
                "error_type": "ValidationError",
            }

        # Validate credentials
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not all([tenant_id, client_id, client_secret]):
            return {
                "status": "error",
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        environment = self.settings.get(SETTINGS_ENVIRONMENT, ENVIRONMENT_PUBLIC)

        try:
            # Acquire access token
            access_token = await _get_access_token(
                tenant_id,
                client_id,
                client_secret,
                environment,
                timeout,
                http_request=self.http_request,
            )

            # Run query
            request_data = {"Query": query}
            response = await _make_defender_request(
                endpoint=ENDPOINT_RUN_QUERY,
                access_token=access_token,
                environment=environment,
                method="POST",
                data=request_data,
                timeout=timeout,
                http_request=self.http_request,
            )

            results = response.get("Results", [])
            return {
                "status": "success",
                "query": query,
                "result_count": len(results),
                "results": results,
                "full_data": response,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("defender_run_query_not_found")
                return {
                    "status": "success",
                    "not_found": True,
                    "query": query,
                    "result_count": 0,
                    "results": [],
                }
            logger.error("run_advanced_query_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

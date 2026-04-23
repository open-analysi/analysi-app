"""
Palo Alto Cortex XDR integration actions.
"""

import hashlib
import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ALERT_SEVERITIES,
    CREDENTIAL_API_KEY,
    CREDENTIAL_API_KEY_ID,
    DEFAULT_LOOKBACK_MINUTES,
    DEFAULT_MAX_ALERTS,
    DEFAULT_TIMEOUT,
    ENDPOINT_ABORT_SCAN,
    ENDPOINT_ALLOWLIST,
    ENDPOINT_BLOCKLIST,
    ENDPOINT_FILE_RETRIEVAL,
    ENDPOINT_FILE_RETRIEVAL_DETAILS,
    ENDPOINT_GET_ACTION_STATUS,
    ENDPOINT_GET_ALERTS,
    ENDPOINT_GET_ENDPOINTS,
    ENDPOINT_GET_INCIDENT_DETAILS,
    ENDPOINT_GET_INCIDENTS,
    ENDPOINT_GET_POLICY,
    ENDPOINT_ISOLATE,
    ENDPOINT_QUARANTINE,
    ENDPOINT_RESTORE,
    ENDPOINT_SCAN,
    ENDPOINT_UNISOLATE,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_REQUEST,
    ERROR_TYPE_VALIDATION,
    HEADER_AUTH_ID,
    HEADER_AUTHORIZATION,
    HEADER_NONCE,
    HEADER_TIMESTAMP,
    INCIDENT_STATUSES,
    MSG_INVALID_ACTION_ID,
    MSG_INVALID_ALERT_ID,
    MSG_INVALID_INCIDENT_ID,
    MSG_MISSING_ACTION_ID,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_ENDPOINT_ID,
    MSG_MISSING_FILE_HASH,
    MSG_MISSING_FILE_PATH,
    MSG_MISSING_SCAN_CRITERIA,
    SETTINGS_ADVANCED,
    SETTINGS_DEFAULT_LOOKBACK,
    SETTINGS_FQDN,
    SETTINGS_TIMEOUT,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

class HealthCheckAction(IntegrationAction):
    """Test connectivity to Cortex XDR API."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            # Advanced authentication with nonce and timestamp
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        # Simple authentication
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute health check action."""
        # Validate credentials
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        fqdn = self.settings.get(SETTINGS_FQDN)

        if not api_key or not api_key_id or not fqdn:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            response = await self.http_request(
                f"{base_url}{ENDPOINT_GET_ENDPOINTS}",
                method="POST",
                headers=headers,
                json_data={},
                timeout=timeout,
            )
            data = response.json()

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Successfully connected to Cortex XDR API",
                "endpoint_count": len(data.get("reply", [])),
            }
        except httpx.HTTPStatusError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class ListEndpointsAction(IntegrationAction):
    """List all endpoints/sensors configured on Cortex XDR."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute list endpoints action."""
        # Validate credentials
        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            response = await self.http_request(
                f"{base_url}{ENDPOINT_GET_ENDPOINTS}",
                method="POST",
                headers=headers,
                json_data={},
                timeout=timeout,
            )
            data = response.json()

            endpoints = data.get("reply", [])
            return {
                "status": STATUS_SUCCESS,
                "endpoint_count": len(endpoints),
                "endpoints": endpoints,
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("cortex_xdr_endpoints_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "endpoint_count": 0,
                    "endpoints": [],
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class GetPolicyAction(IntegrationAction):
    """Get the policy name for a specific endpoint."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute get policy action."""
        endpoint_id = kwargs.get("endpoint_id")
        if not endpoint_id:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_ENDPOINT_ID,
            }

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {"endpoint_id": endpoint_id}
            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_GET_POLICY}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            policy_name = data.get("reply", {}).get("policy_name")
            return {
                "status": STATUS_SUCCESS,
                "policy_name": policy_name,
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("cortex_xdr_policy_not_found", endpoint_id=endpoint_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "endpoint_id": endpoint_id,
                    "policy_name": None,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class GetActionStatusAction(IntegrationAction):
    """Retrieve the status of requested actions according to the action ID."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute get action status action."""
        action_id = kwargs.get("action_id")
        if action_id is None:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_ACTION_ID,
            }

        # Validate action_id is a positive integer
        try:
            action_id = int(action_id)
            if action_id < 0:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_INVALID_ACTION_ID,
                }
        except (ValueError, TypeError):
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_INVALID_ACTION_ID,
            }

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {"group_action_id": action_id}
            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_GET_ACTION_STATUS}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "action_status": data.get("reply", {}).get("data"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("cortex_xdr_action_status_not_found", action_id=action_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "action_id": action_id,
                    "action_status": None,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class RetrieveFileAction(IntegrationAction):
    """Retrieve files from a specified endpoint."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute retrieve file action."""
        endpoint_id = kwargs.get("endpoint_id")
        if not endpoint_id:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_ENDPOINT_ID,
            }

        windows_path = kwargs.get("windows_path")
        linux_path = kwargs.get("linux_path")
        macos_path = kwargs.get("macos_path")

        if not windows_path and not linux_path and not macos_path:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_FILE_PATH,
            }

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            filters = [
                {"field": "endpoint_id_list", "operator": "in", "value": [endpoint_id]}
            ]

            files = {}
            if windows_path:
                files["windows"] = [windows_path]
            if linux_path:
                files["linux"] = [linux_path]
            if macos_path:
                files["macos"] = [macos_path]

            request_data = {"filters": filters, "files": files}
            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_FILE_RETRIEVAL}",
                headers=headers,
                json_data=payload,
                method="POST",
                timeout=timeout,
            )
            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "action_id": data.get("reply", {}).get("action_id"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "cortex_xdr_file_retrieval_not_found",
                    endpoint_id=endpoint_id,
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "endpoint_id": endpoint_id,
                    "action_id": None,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class RetrieveFileDetailsAction(IntegrationAction):
    """View the file retrieved by the Retrieve File action according to the action ID."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute retrieve file details action."""
        action_id = kwargs.get("action_id")
        if action_id is None:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_ACTION_ID,
            }

        # Validate action_id is a positive integer
        try:
            action_id = int(action_id)
            if action_id < 0:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_INVALID_ACTION_ID,
                }
        except (ValueError, TypeError):
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_INVALID_ACTION_ID,
            }

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {"group_action_id": action_id}
            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_FILE_RETRIEVAL_DETAILS}",
                headers=headers,
                json_data=payload,
                method="POST",
                timeout=timeout,
            )
            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "file_data": data.get("reply", {}).get("data"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("cortex_xdr_file_details_not_found", action_id=action_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "action_id": action_id,
                    "file_data": None,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class QuarantineFileAction(IntegrationAction):
    """Quarantine file on a specified endpoint."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute quarantine file action."""
        endpoint_id = kwargs.get("endpoint_id")
        file_path = kwargs.get("file_path")
        file_hash = kwargs.get("file_hash")

        if not endpoint_id:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_ENDPOINT_ID,
            }
        if not file_hash:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_FILE_HASH,
            }
        if not file_path:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": "Missing required parameter 'file_path'",
            }

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            filters = [
                {"field": "endpoint_id_list", "operator": "in", "value": [endpoint_id]}
            ]
            request_data = {
                "filters": filters,
                "file_path": file_path,
                "file_hash": file_hash,
            }
            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_QUARANTINE}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "action_id": data.get("reply", {}).get("action_id"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class UnquarantineFileAction(IntegrationAction):
    """Restore a quarantined file on a specified endpoint."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute unquarantine file action."""
        file_hash = kwargs.get("file_hash")
        endpoint_id = kwargs.get("endpoint_id")

        if not file_hash:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_FILE_HASH,
            }
        if not endpoint_id:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_ENDPOINT_ID,
            }

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {"file_hash": file_hash, "endpoint_id": endpoint_id}
            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_RESTORE}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "action_id": data.get("reply", {}).get("action_id"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class BlockHashAction(IntegrationAction):
    """Add a hash that does not exist in the allow or block list to a block list."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute block hash action."""
        file_hash = kwargs.get("file_hash")
        if not file_hash:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_FILE_HASH,
            }

        comment = kwargs.get("comment")
        incident_id = kwargs.get("incident_id")

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {"hash_list": [file_hash]}

            if comment:
                request_data["comment"] = comment
            if incident_id is not None:
                # Validate incident_id
                try:
                    incident_id = int(incident_id)
                    if incident_id < 0:
                        return {
                            "status": STATUS_ERROR,
                            "error_type": ERROR_TYPE_VALIDATION,
                            "error": MSG_INVALID_INCIDENT_ID,
                        }
                    request_data["incident_id"] = str(incident_id)
                except (ValueError, TypeError):
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_VALIDATION,
                        "error": MSG_INVALID_INCIDENT_ID,
                    }

            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_BLOCKLIST}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "list_updated": data.get("reply"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class AllowHashAction(IntegrationAction):
    """Add files that do not exist in the allow or block list to an allow list."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute allow hash action."""
        file_hash = kwargs.get("file_hash")
        if not file_hash:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_FILE_HASH,
            }

        comment = kwargs.get("comment")
        incident_id = kwargs.get("incident_id")

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {"hash_list": [file_hash]}

            if comment:
                request_data["comment"] = comment
            if incident_id is not None:
                # Validate incident_id
                try:
                    incident_id = int(incident_id)
                    if incident_id < 0:
                        return {
                            "status": STATUS_ERROR,
                            "error_type": ERROR_TYPE_VALIDATION,
                            "error": MSG_INVALID_INCIDENT_ID,
                        }
                    request_data["incident_id"] = str(incident_id)
                except (ValueError, TypeError):
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_VALIDATION,
                        "error": MSG_INVALID_INCIDENT_ID,
                    }

            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_ALLOWLIST}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "list_updated": data.get("reply"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class QuarantineDeviceAction(IntegrationAction):
    """Isolate a specified endpoint from the network."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute quarantine device action."""
        endpoint_id = kwargs.get("endpoint_id")
        if not endpoint_id:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_ENDPOINT_ID,
            }

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {"endpoint_id": endpoint_id}
            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_ISOLATE}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "action_id": data.get("reply", {}).get("action_id"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class UnquarantineDeviceAction(IntegrationAction):
    """Release a specified endpoint from isolation."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute unquarantine device action."""
        endpoint_id = kwargs.get("endpoint_id")
        if not endpoint_id:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_MISSING_ENDPOINT_ID,
            }

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {"endpoint_id": endpoint_id}
            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_UNISOLATE}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "action_id": data.get("reply", {}).get("action_id"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class ScanEndpointAction(IntegrationAction):
    """Run a scan on selected endpoints."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute scan endpoint action."""
        scan_all = kwargs.get("scan_all", False)
        endpoint_id = kwargs.get("endpoint_id")
        hostname = kwargs.get("hostname")

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {}

            if scan_all:
                request_data["filters"] = "all"
            else:
                filters = []
                if endpoint_id:
                    filters.append(
                        {
                            "field": "endpoint_id_list",
                            "operator": "in",
                            "value": [endpoint_id],
                        }
                    )
                if hostname:
                    filters.append(
                        {"field": "hostname", "operator": "in", "value": [hostname]}
                    )

                if not filters:
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_VALIDATION,
                        "error": MSG_MISSING_SCAN_CRITERIA,
                    }

                request_data["filters"] = filters

            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_SCAN}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            reply = data.get("reply", {})
            return {
                "status": STATUS_SUCCESS,
                "action_id": reply.get("action_id"),
                "endpoints_scanning": reply.get("endpoints_count"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class CancelScanEndpointAction(IntegrationAction):
    """Cancel the scan of selected endpoints."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute cancel scan endpoint action."""
        scan_all = kwargs.get("scan_all", False)
        endpoint_id = kwargs.get("endpoint_id")
        hostname = kwargs.get("hostname")

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {}

            if scan_all:
                request_data["filters"] = "all"
            else:
                filters = []
                if endpoint_id:
                    filters.append(
                        {
                            "field": "endpoint_id_list",
                            "operator": "in",
                            "value": [endpoint_id],
                        }
                    )
                if hostname:
                    filters.append(
                        {"field": "hostname", "operator": "in", "value": [hostname]}
                    )

                if not filters:
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_VALIDATION,
                        "error": MSG_MISSING_SCAN_CRITERIA,
                    }

                request_data["filters"] = filters

            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_ABORT_SCAN}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            reply = data.get("reply", {})
            return {
                "status": STATUS_SUCCESS,
                "action_id": reply.get("action_id"),
                "endpoints_cancelled": reply.get("endpoints_count"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class GetIncidentsAction(IntegrationAction):
    """Get a list of incidents filtered by incident IDs, modification time, or creation time."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute get incidents action."""
        modification_time = kwargs.get("modification_time")
        creation_time = kwargs.get("creation_time")
        incident_id = kwargs.get("incident_id")
        status = kwargs.get("status")

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {}
            filters = []

            if modification_time is not None:
                try:
                    modification_time = int(modification_time)
                    filters.append(
                        {
                            "field": "modification_time",
                            "operator": "gte",
                            "value": modification_time,
                        }
                    )
                except (ValueError, TypeError):
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_VALIDATION,
                        "error": "Invalid modification_time",
                    }

            if creation_time is not None:
                try:
                    creation_time = int(creation_time)
                    filters.append(
                        {
                            "field": "creation_time",
                            "operator": "gte",
                            "value": creation_time,
                        }
                    )
                except (ValueError, TypeError):
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_VALIDATION,
                        "error": "Invalid creation_time",
                    }

            if incident_id is not None:
                try:
                    incident_id = int(incident_id)
                    filters.append(
                        {
                            "field": "incident_id_list",
                            "operator": "in",
                            "value": [str(incident_id)],
                        }
                    )
                except (ValueError, TypeError):
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_VALIDATION,
                        "error": MSG_INVALID_INCIDENT_ID,
                    }

            if status and status in INCIDENT_STATUSES:
                filters.append({"field": "status", "operator": "eq", "value": status})
            elif status:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": f"Invalid status: {status}",
                }

            if filters:
                request_data["filters"] = filters

            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_GET_INCIDENTS}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            reply = data.get("reply", {})
            return {
                "status": STATUS_SUCCESS,
                "total_count": reply.get("total_count"),
                "result_count": reply.get("result_count"),
                "incidents": reply.get("incidents", []),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("cortex_xdr_incidents_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "total_count": 0,
                    "result_count": 0,
                    "incidents": [],
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class GetIncidentDetailsAction(IntegrationAction):
    """Get extra data fields of a specific incident including alerts and key artifacts."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute get incident details action."""
        incident_id = kwargs.get("incident_id")
        if incident_id is None:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": "Missing required parameter 'incident_id'",
            }

        try:
            incident_id = int(incident_id)
            if incident_id < 0:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": MSG_INVALID_INCIDENT_ID,
                }
        except (ValueError, TypeError):
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_VALIDATION,
                "error": MSG_INVALID_INCIDENT_ID,
            }

        alerts_limit = kwargs.get("alerts_limit")

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {"incident_id": str(incident_id)}

            if alerts_limit is not None:
                try:
                    alerts_limit = int(alerts_limit)
                    request_data["alerts_limit"] = alerts_limit
                except (ValueError, TypeError):
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_VALIDATION,
                        "error": "Invalid alerts_limit",
                    }

            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_GET_INCIDENT_DETAILS}",
                headers=headers,
                json_data=payload,
                method="POST",
                timeout=timeout,
            )
            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "incident_details": data.get("reply"),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "cortex_xdr_incident_details_not_found",
                    incident_id=incident_id,
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "incident_id": incident_id,
                    "incident_details": None,
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class GetAlertsAction(IntegrationAction):
    """Get a list of alerts with multiple events."""

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute get alerts action."""
        alert_id = kwargs.get("alert_id")
        alert_source = kwargs.get("alert_source")
        severity = kwargs.get("severity")
        creation_time = kwargs.get("creation_time")

        fqdn = self.settings.get(SETTINGS_FQDN)
        if not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()
            request_data = {}
            filters = []

            if alert_id is not None:
                try:
                    alert_id = int(alert_id)
                    filters.append(
                        {
                            "field": "alert_id_list",
                            "operator": "in",
                            "value": [alert_id],
                        }
                    )
                except (ValueError, TypeError):
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_VALIDATION,
                        "error": MSG_INVALID_ALERT_ID,
                    }

            if alert_source:
                filters.append(
                    {"field": "alert_source", "operator": "in", "value": [alert_source]}
                )

            if severity and severity in ALERT_SEVERITIES:
                filters.append(
                    {"field": "severity", "operator": "in", "value": [severity]}
                )
            elif severity:
                return {
                    "status": STATUS_ERROR,
                    "error_type": ERROR_TYPE_VALIDATION,
                    "error": f"Invalid severity: {severity}",
                }

            if creation_time is not None:
                try:
                    creation_time = int(creation_time)
                    filters.append(
                        {
                            "field": "creation_time",
                            "operator": "gte",
                            "value": creation_time,
                        }
                    )
                except (ValueError, TypeError):
                    return {
                        "status": STATUS_ERROR,
                        "error_type": ERROR_TYPE_VALIDATION,
                        "error": "Invalid creation_time",
                    }

            if filters:
                request_data["filters"] = filters

            payload = {"request_data": request_data}

            response = await self.http_request(
                f"{base_url}{ENDPOINT_GET_ALERTS}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            reply = data.get("reply", {})
            return {
                "status": STATUS_SUCCESS,
                "total_count": reply.get("total_count"),
                "result_count": reply.get("result_count"),
                "alerts": reply.get("alerts", []),
                "response": data,
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("cortex_xdr_alerts_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "total_count": 0,
                    "result_count": 0,
                    "alerts": [],
                }
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class PullAlertsAction(IntegrationAction):
    """Pull alerts from Cortex XDR.

    Uses the Alerts API:
    POST /public_api/v1/alerts/get_alerts_multi_events with time filter.

    Project Symi: AlertSource archetype requires this action.
    """

    def _get_auth_headers(self) -> dict[str, str]:
        """Generate authentication headers."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        advanced = self.settings.get(SETTINGS_ADVANCED, False)

        if advanced:
            nonce = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
            )
            timestamp = int(datetime.now(UTC).timestamp()) * 1000
            auth_key = f"{api_key}{nonce}{timestamp}"
            api_key_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

            return {
                HEADER_TIMESTAMP: str(timestamp),
                HEADER_NONCE: nonce,
                HEADER_AUTH_ID: str(api_key_id),
                HEADER_AUTHORIZATION: api_key_hash,
            }
        return {HEADER_AUTH_ID: str(api_key_id), HEADER_AUTHORIZATION: api_key}

    async def execute(self, **params) -> dict[str, Any]:
        """Pull alerts from Cortex XDR within a time range.

        Args:
            start_time: Start of time range (datetime or ISO string, optional)
            end_time: End of time range (datetime or ISO string, optional)
            max_results: Maximum number of alerts to return (default: 1000)

        Returns:
            dict: Alerts pulled with count and data

        Note:
            If start_time is not provided, uses the integration's
            default_lookback_minutes setting to determine how far back
            to search (default: 5 minutes).
        """
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_key_id = self.credentials.get(CREDENTIAL_API_KEY_ID)
        fqdn = self.settings.get(SETTINGS_FQDN)

        if not api_key or not api_key_id or not fqdn:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "error": MSG_MISSING_CREDENTIALS,
            }

        # Determine time range
        now = datetime.now(UTC)
        end_time = params.get("end_time")
        start_time = params.get("start_time")

        if end_time and isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        if not end_time:
            end_time = now

        if start_time and isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if not start_time:
            lookback = self.settings.get(
                SETTINGS_DEFAULT_LOOKBACK, DEFAULT_LOOKBACK_MINUTES
            )
            start_time = end_time - timedelta(minutes=lookback)

        max_results = params.get("max_results", DEFAULT_MAX_ALERTS)

        # Cortex XDR uses epoch milliseconds for time filters
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        base_url = f"https://api-{fqdn}/public_api/v1"

        try:
            headers = self._get_auth_headers()

            request_data: dict[str, Any] = {
                "filters": [
                    {
                        "field": "creation_time",
                        "operator": "gte",
                        "value": start_ms,
                    },
                    {
                        "field": "creation_time",
                        "operator": "lte",
                        "value": end_ms,
                    },
                ],
                "sort": {
                    "field": "creation_time",
                    "keyword": "asc",
                },
            }

            # Cortex XDR uses search_from/search_to for pagination
            all_alerts: list[dict[str, Any]] = []
            search_from = 0

            while len(all_alerts) < max_results:
                page_size = min(100, max_results - len(all_alerts))
                request_data["search_from"] = search_from
                request_data["search_to"] = search_from + page_size

                payload = {"request_data": request_data}

                response = await self.http_request(
                    f"{base_url}{ENDPOINT_GET_ALERTS}",
                    method="POST",
                    headers=headers,
                    json_data=payload,
                    timeout=timeout,
                )
                data = response.json()

                reply = data.get("reply", {})
                alerts = reply.get("alerts", [])
                all_alerts.extend(alerts)

                # Stop if fewer results than page size (last page)
                if len(alerts) < page_size:
                    break

                search_from += len(alerts)

            return {
                "status": STATUS_SUCCESS,
                "alerts_count": len(all_alerts),
                "alerts": all_alerts,
                "message": f"Retrieved {len(all_alerts)} alerts",
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class AlertsToOcsfAction(IntegrationAction):
    """Normalize raw Cortex XDR alerts to OCSF Detection Finding v1.8.0.

    Delegates to CortexXDROCSFNormalizer which produces full OCSF Detection
    Findings with metadata, evidences, observables, device, actor,
    and MITRE ATT&CK mapping.

    Project Symi: AlertSource archetype requires this action.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Normalize raw Cortex XDR alerts to OCSF format.

        Args:
            raw_alerts: List of raw Cortex XDR alert documents.

        Returns:
            dict with status, normalized_alerts (OCSF dicts), count, and errors.
        """
        from alert_normalizer.cortex_xdr_ocsf import CortexXDROCSFNormalizer

        raw_alerts = params.get("raw_alerts", [])
        logger.info("cortex_xdr_alerts_to_ocsf_called", count=len(raw_alerts))

        normalizer = CortexXDROCSFNormalizer()
        normalized = []
        errors = 0

        for alert in raw_alerts:
            try:
                ocsf_finding = normalizer.to_ocsf(alert)
                normalized.append(ocsf_finding)
            except Exception:
                logger.exception(
                    "cortex_xdr_alert_to_ocsf_failed",
                    alert_id=alert.get("alert_id"),
                    alert_name=alert.get("alert_name"),
                )
                errors += 1

        return {
            "status": "success" if errors == 0 else "partial",
            "normalized_alerts": normalized,
            "count": len(normalized),
            "errors": errors,
        }

"""
Carbon Black Cloud EDR integration actions.
Uses REST API directly (not cbc-sdk) with API Key + API ID authentication.

Auth header format: X-Auth-Token: {api_key}/{api_id}
"""

import asyncio
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.carbonblack.constants import (
    ALERT_GET_ENDPOINT,
    ALERT_SEARCH_ENDPOINT,
    CREDENTIAL_API_ID,
    CREDENTIAL_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_SEARCH_ROWS,
    DEFAULT_TIMEOUT,
    DEVICE_ACTIONS_ENDPOINT,
    DEVICE_SEARCH_ENDPOINT,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_VALIDATION,
    MAX_SEARCH_ROWS,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAMETER,
    OVERRIDE_LIST_BLACK,
    OVERRIDE_TYPE_SHA256,
    PROCESS_MAX_POLLS,
    PROCESS_POLL_INTERVAL,
    PROCESS_RESULTS_ENDPOINT,
    PROCESS_SEARCH_ENDPOINT,
    QUARANTINE_ACTION,
    REPUTATION_OVERRIDE_ENDPOINT,
    REPUTATION_OVERRIDE_SEARCH_ENDPOINT,
    SETTINGS_BASE_URL,
    SETTINGS_ORG_KEY,
    SETTINGS_TIMEOUT,
    UBS_METADATA_ENDPOINT,
    UNQUARANTINE_ACTION,
)

logger = get_logger(__name__)

# ============================================================================
# Auth Mixin
# ============================================================================

class CarbonBlackAuthMixin:
    """Mixin providing Carbon Black Cloud API authentication and request helper.

    Auth uses the ``X-Auth-Token`` header with the combined
    ``{api_key}/{api_id}`` token format.
    """

    def _get_auth_token(self) -> str:
        """Build CBC auth token from credentials.

        Returns:
            Token string in ``{api_key}/{api_id}`` format.

        Raises:
            ValueError: If credentials are incomplete.
        """
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_id = self.credentials.get(CREDENTIAL_API_ID)

        if not api_key or not api_id:
            raise ValueError(MSG_MISSING_CREDENTIALS)

        return f"{api_key}/{api_id}"

    def _get_org_key(self) -> str:
        """Get org_key from credentials.

        Returns:
            Org key string.

        Raises:
            ValueError: If org_key is missing.
        """
        org_key = self.settings.get(SETTINGS_ORG_KEY)
        if not org_key:
            raise ValueError(MSG_MISSING_CREDENTIALS)
        return org_key

    def _get_base_url(self) -> str:
        """Get base URL from settings, with trailing slash stripped."""
        return self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL).rstrip("/")

    def _build_url(self, endpoint_template: str, **path_params) -> str:
        """Build full URL from endpoint template and path parameters.

        Args:
            endpoint_template: URL path with ``{placeholder}`` tokens.
            **path_params: Values to substitute into the template.

        Returns:
            Fully-qualified URL.
        """
        path_params.setdefault("org_key", self._get_org_key())
        endpoint = endpoint_template.format(**path_params)
        return f"{self._get_base_url()}{endpoint}"

    async def _cbc_request(
        self,
        endpoint_template: str,
        *,
        method: str = "GET",
        params: dict | None = None,
        json_data: dict | None = None,
        path_params: dict | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to Carbon Black Cloud API.

        Args:
            endpoint_template: Endpoint path template with ``{org_key}`` etc.
            method: HTTP method.
            params: Query parameters.
            json_data: JSON request body.
            path_params: Extra path substitution values.

        Returns:
            Parsed JSON response body.
        """
        url = self._build_url(endpoint_template, **(path_params or {}))
        token = self._get_auth_token()
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        headers = {
            "X-Auth-Token": token,
            "Content-Type": "application/json",
        }

        response = await self.http_request(
            url,
            method=method,
            headers=headers,
            params=params,
            json_data=json_data,
            timeout=timeout,
        )
        return response.json()

# ============================================================================
# Validation helpers
# ============================================================================

def _validate_sha256(hash_value: str) -> tuple[bool, str]:
    """Validate a SHA-256 hash string.

    Returns:
        ``(is_valid, error_message)`` tuple.
    """
    if not hash_value or not isinstance(hash_value, str):
        return False, "SHA-256 hash must be a non-empty string"
    if len(hash_value) != 64:
        return False, "SHA-256 hash must be exactly 64 characters"
    if not all(c in "0123456789abcdefABCDEF" for c in hash_value):
        return False, "SHA-256 hash must contain only hexadecimal characters"
    return True, ""

# ============================================================================
# Health Check
# ============================================================================

class HealthCheckAction(CarbonBlackAuthMixin, IntegrationAction):
    """Verify connectivity and authentication with Carbon Black Cloud."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test CBC API connectivity by querying devices.

        Returns:
            Success result with connectivity status.
        """
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        api_id = self.credentials.get(CREDENTIAL_API_ID)
        org_key = self.settings.get(SETTINGS_ORG_KEY)

        if not all([api_key, api_id, org_key]):
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
                healthy=False,
            )

        try:
            result = await self._cbc_request(
                DEVICE_SEARCH_ENDPOINT,
                method="POST",
                json_data={"rows": 1},
            )

            return self.success_result(
                data={
                    "healthy": True,
                    "num_found": result.get("num_found", 0),
                },
                healthy=True,
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                return self.error_result(
                    "Authentication failed. Check API key, API ID, and Org Key.",
                    error_type=ERROR_TYPE_AUTHENTICATION,
                    healthy=False,
                )
            return self.error_result(e, healthy=False)
        except Exception as e:
            return self.error_result(e, healthy=False)

# ============================================================================
# Device Actions
# ============================================================================

class GetDeviceAction(CarbonBlackAuthMixin, IntegrationAction):
    """Get device/endpoint details by device ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve device details from CBC.

        Args:
            **kwargs: Must contain ``device_id``.
        """
        device_id = kwargs.get("device_id")
        if not device_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("device_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            # Use device search with device_id criteria
            result = await self._cbc_request(
                DEVICE_SEARCH_ENDPOINT,
                method="POST",
                json_data={
                    "criteria": {"id": [str(device_id)]},
                    "rows": 1,
                },
            )

            devices = result.get("results", [])
            if not devices:
                self.log_info("carbonblack_device_not_found", device_id=device_id)
                return self.success_result(
                    not_found=True,
                    data={"device_id": device_id},
                )

            return self.success_result(data=devices[0])

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"device_id": device_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class SearchDevicesAction(CarbonBlackAuthMixin, IntegrationAction):
    """Search for devices/endpoints by query criteria."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search devices using CBC search API.

        Args:
            **kwargs: May contain ``query``, ``criteria``, ``rows``, ``start``.
        """
        query = kwargs.get("query", "")
        criteria = kwargs.get("criteria", {})
        rows = min(int(kwargs.get("rows", DEFAULT_SEARCH_ROWS)), MAX_SEARCH_ROWS)
        start = int(kwargs.get("start", 0))

        try:
            body: dict[str, Any] = {"rows": rows, "start": start}
            if query:
                body["query"] = query
            if criteria:
                body["criteria"] = criteria

            result = await self._cbc_request(
                DEVICE_SEARCH_ENDPOINT,
                method="POST",
                json_data=body,
            )

            return self.success_result(
                data={
                    "devices": result.get("results", []),
                    "num_found": result.get("num_found", 0),
                    "rows": rows,
                    "start": start,
                },
            )
        except Exception as e:
            return self.error_result(e)

class QuarantineDeviceAction(CarbonBlackAuthMixin, IntegrationAction):
    """Isolate/quarantine a device to prevent lateral movement."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Quarantine a device.

        Args:
            **kwargs: Must contain ``device_id``.
        """
        device_id = kwargs.get("device_id")
        if not device_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("device_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            await self._cbc_request(
                DEVICE_ACTIONS_ENDPOINT,
                method="POST",
                json_data={
                    "action_type": QUARANTINE_ACTION,
                    "device_id": [str(device_id)],
                },
            )

            self.log_info("carbonblack_device_quarantined", device_id=device_id)
            return self.success_result(
                data={
                    "device_id": device_id,
                    "action": "quarantine",
                    "message": "Device quarantine initiated successfully",
                },
            )
        except Exception as e:
            return self.error_result(e)

class UnquarantineDeviceAction(CarbonBlackAuthMixin, IntegrationAction):
    """Release a device from quarantine/isolation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Remove quarantine from a device.

        Args:
            **kwargs: Must contain ``device_id``.
        """
        device_id = kwargs.get("device_id")
        if not device_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("device_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            await self._cbc_request(
                DEVICE_ACTIONS_ENDPOINT,
                method="POST",
                json_data={
                    "action_type": UNQUARANTINE_ACTION,
                    "device_id": [str(device_id)],
                },
            )

            self.log_info("carbonblack_device_unquarantined", device_id=device_id)
            return self.success_result(
                data={
                    "device_id": device_id,
                    "action": "unquarantine",
                    "message": "Device unquarantine initiated successfully",
                },
            )
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# Alert Actions
# ============================================================================

class GetAlertAction(CarbonBlackAuthMixin, IntegrationAction):
    """Get alert details by alert ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve alert details from CBC.

        Args:
            **kwargs: Must contain ``alert_id``.
        """
        alert_id = kwargs.get("alert_id")
        if not alert_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("alert_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            result = await self._cbc_request(
                ALERT_GET_ENDPOINT,
                method="GET",
                path_params={"alert_id": alert_id},
            )

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("carbonblack_alert_not_found", alert_id=alert_id)
                return self.success_result(
                    not_found=True,
                    data={"alert_id": alert_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class SearchAlertsAction(CarbonBlackAuthMixin, IntegrationAction):
    """Search alerts by query criteria."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search alerts using CBC alert search API.

        Args:
            **kwargs: May contain ``query``, ``criteria``, ``rows``,
                ``start``, ``sort``.
        """
        query = kwargs.get("query", "")
        criteria = kwargs.get("criteria", {})
        rows = min(int(kwargs.get("rows", DEFAULT_SEARCH_ROWS)), MAX_SEARCH_ROWS)
        start = int(kwargs.get("start", 0))
        sort = kwargs.get("sort")

        try:
            body: dict[str, Any] = {"rows": rows, "start": start}
            if query:
                body["query"] = query
            if criteria:
                body["criteria"] = criteria
            if sort:
                body["sort"] = sort if isinstance(sort, list) else [sort]

            result = await self._cbc_request(
                ALERT_SEARCH_ENDPOINT,
                method="POST",
                json_data=body,
            )

            return self.success_result(
                data={
                    "alerts": result.get("results", []),
                    "num_found": result.get("num_found", 0),
                    "rows": rows,
                    "start": start,
                },
            )
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# Process Search
# ============================================================================

class SearchProcessesAction(CarbonBlackAuthMixin, IntegrationAction):
    """Search process events across endpoints."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search processes via CBC Enterprise EDR process search API.

        This is a two-step operation: first create a search job, then
        fetch results.

        Args:
            **kwargs: May contain ``query``, ``criteria``, ``rows``,
                ``start``, ``time_range``.
        """
        query = kwargs.get("query", "")
        criteria = kwargs.get("criteria", {})
        rows = min(int(kwargs.get("rows", DEFAULT_SEARCH_ROWS)), MAX_SEARCH_ROWS)
        start = int(kwargs.get("start", 0))
        time_range = kwargs.get("time_range")

        if not query and not criteria:
            return self.error_result(
                "At least one of 'query' or 'criteria' is required",
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            # Step 1: Create the search job
            body: dict[str, Any] = {"rows": rows, "start": start}
            if query:
                body["query"] = query
            if criteria:
                body["criteria"] = criteria
            if time_range:
                body["time_range"] = time_range

            job_result = await self._cbc_request(
                PROCESS_SEARCH_ENDPOINT,
                method="POST",
                json_data=body,
            )

            job_id = job_result.get("job_id")
            if not job_id:
                return self.error_result(
                    "Failed to create process search job",
                    error_type=ERROR_TYPE_HTTP,
                )

            # Step 2: Poll for results until job completes
            results: dict[str, Any] = {}
            for _poll in range(PROCESS_MAX_POLLS):
                results = await self._cbc_request(
                    PROCESS_RESULTS_ENDPOINT,
                    method="GET",
                    params={"start": start, "rows": rows},
                    path_params={"job_id": job_id},
                )
                contacted = results.get("contacted", 0)
                completed = results.get("completed", 0)
                if contacted > 0 and contacted == completed:
                    break
                await asyncio.sleep(PROCESS_POLL_INTERVAL)

            return self.success_result(
                data={
                    "processes": results.get("results", []),
                    "num_found": results.get("num_found", 0),
                    "num_available": results.get("num_available", 0),
                    "job_id": job_id,
                    "rows": rows,
                    "start": start,
                },
            )
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# Hash Banning (Reputation Overrides)
# ============================================================================

class BanHashAction(CarbonBlackAuthMixin, IntegrationAction):
    """Ban a SHA-256 hash by adding it to the organization's banned list."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create a reputation override to ban a hash.

        Args:
            **kwargs: Must contain ``sha256_hash``. Optional: ``description``,
                ``filename``.
        """
        sha256_hash = kwargs.get("sha256_hash")
        if not sha256_hash:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("sha256_hash"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        is_valid, error_msg = _validate_sha256(sha256_hash)
        if not is_valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_VALIDATION)

        description = kwargs.get("description", "Banned via Analysi")
        filename = kwargs.get("filename", "Unknown")

        try:
            result = await self._cbc_request(
                REPUTATION_OVERRIDE_ENDPOINT,
                method="POST",
                json_data={
                    "sha256_hash": sha256_hash.upper(),
                    "override_type": OVERRIDE_TYPE_SHA256,
                    "override_list": OVERRIDE_LIST_BLACK,
                    "filename": filename,
                    "description": description,
                },
            )

            self.log_info("carbonblack_hash_banned", sha256_hash=sha256_hash)
            return self.success_result(
                data={
                    "sha256_hash": sha256_hash,
                    "action": "ban",
                    "message": f"Hash {sha256_hash} banned successfully",
                    "override": result,
                },
            )
        except Exception as e:
            return self.error_result(e)

class UnbanHashAction(CarbonBlackAuthMixin, IntegrationAction):
    """Remove a SHA-256 hash from the banned list."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Remove reputation override for a banned hash.

        First searches for the override by hash, then deletes it.

        Args:
            **kwargs: Must contain ``sha256_hash``.
        """
        sha256_hash = kwargs.get("sha256_hash")
        if not sha256_hash:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("sha256_hash"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        is_valid, error_msg = _validate_sha256(sha256_hash)
        if not is_valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_VALIDATION)

        try:
            # Search for existing override
            search_result = await self._cbc_request(
                REPUTATION_OVERRIDE_SEARCH_ENDPOINT,
                method="POST",
                json_data={
                    "query": sha256_hash.upper(),
                    "criteria": {
                        "override_list": OVERRIDE_LIST_BLACK,
                        "override_type": OVERRIDE_TYPE_SHA256,
                    },
                },
            )

            overrides = search_result.get("results", [])
            if not overrides:
                self.log_info("carbonblack_hash_not_banned", sha256_hash=sha256_hash)
                return self.success_result(
                    data={
                        "sha256_hash": sha256_hash,
                        "action": "unban",
                        "message": f"Hash {sha256_hash} was not in the banned list",
                        "already_unbanned": True,
                    },
                )

            # Delete the override
            override_id = overrides[0].get("id")
            url = self._build_url(
                "/appservices/v6/orgs/{org_key}/reputations/overrides/{override_id}",
                override_id=override_id,
            )
            token = self._get_auth_token()
            timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

            await self.http_request(
                url,
                method="DELETE",
                headers={
                    "X-Auth-Token": token,
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )

            self.log_info("carbonblack_hash_unbanned", sha256_hash=sha256_hash)
            return self.success_result(
                data={
                    "sha256_hash": sha256_hash,
                    "action": "unban",
                    "message": f"Hash {sha256_hash} unbanned successfully",
                },
            )
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# Binary / File Metadata
# ============================================================================

class GetBinaryAction(CarbonBlackAuthMixin, IntegrationAction):
    """Get binary/file metadata by SHA-256 hash from the Unified Binary Store."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve binary metadata from UBS.

        Args:
            **kwargs: Must contain ``sha256_hash``.
        """
        sha256_hash = kwargs.get("sha256_hash")
        if not sha256_hash:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("sha256_hash"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        is_valid, error_msg = _validate_sha256(sha256_hash)
        if not is_valid:
            return self.error_result(error_msg, error_type=ERROR_TYPE_VALIDATION)

        try:
            result = await self._cbc_request(
                UBS_METADATA_ENDPOINT,
                method="GET",
                path_params={"sha256": sha256_hash.upper()},
            )

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("carbonblack_binary_not_found", sha256_hash=sha256_hash)
                return self.success_result(
                    not_found=True,
                    data={"sha256_hash": sha256_hash},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

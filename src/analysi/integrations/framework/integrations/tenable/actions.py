"""Tenable.io integration actions for vulnerability management."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
from dateutil.parser import ParserError
from dateutil.parser import parse as dateutil_parse

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_ACCESS_KEY,
    CREDENTIAL_SECRET_KEY,
    DEFAULT_SCAN_NAME,
    DEFAULT_SCAN_POLLING_INTERVAL,
    DEFAULT_SCAN_TIMEOUT,
    DEFAULT_TIMEOUT,
    ENDPOINT_POLICIES_LIST,
    ENDPOINT_SCANNERS_LIST,
    ENDPOINT_SCANS_CREATE,
    ENDPOINT_SCANS_DELETE,
    ENDPOINT_SCANS_DETAILS,
    ENDPOINT_SCANS_LAUNCH,
    ENDPOINT_SCANS_LIST,
    ENDPOINT_SCANS_STATUS,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    MAX_SCAN_TIMEOUT,
    MIN_SCAN_TIMEOUT,
    MSG_INVALID_DATETIME,
    MSG_INVALID_SCAN_TIMEOUT,
    MSG_MISSING_ACCESS_KEY,
    MSG_MISSING_POLICY_ID,
    MSG_MISSING_SCAN_ID,
    MSG_MISSING_SECRET_KEY,
    MSG_MISSING_TARGET,
    MSG_SCAN_NOT_COMPLETE,
    MSG_SCAN_RESPONSE_EMPTY,
    MSG_SERVER_CONNECTION,
    OUTPUT_DELETE_STATUS,
    OUTPUT_POLICY_COUNT,
    OUTPUT_SCAN_COUNT,
    OUTPUT_SCAN_ID,
    OUTPUT_SCANNER_COUNT,
    OUTPUT_TOTAL_VULNS,
    SCAN_STATUS_COMPLETED,
    SETTINGS_TIMEOUT,
    STATUS_ERROR,
    STATUS_SUCCESS,
    TENABLE_BASE_URL,
    TERMINAL_SCAN_STATUSES,
    VULNERABILITY_SEVERITIES,
)

logger = get_logger(__name__)

# ============================================================================
# VALIDATION UTILITIES
# ============================================================================

def _parse_datetime(value: str) -> datetime:
    """Parse datetime string or Unix timestamp.

    Args:
        value: Datetime string or Unix timestamp

    Returns:
        Parsed datetime object

    Raises:
        ValueError: If datetime format is invalid
    """
    if value.isdigit():
        return datetime.fromtimestamp(int(value), UTC)
    return dateutil_parse(value)

def _validate_scan_timeout(timeout: int) -> tuple[bool, str]:
    """Validate scan timeout parameter.

    Args:
        timeout: Scan timeout in seconds

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(timeout, (int, float)):
        return False, MSG_INVALID_SCAN_TIMEOUT.format(
            MIN_SCAN_TIMEOUT, MAX_SCAN_TIMEOUT
        )

    if timeout < MIN_SCAN_TIMEOUT or timeout > MAX_SCAN_TIMEOUT:
        return False, MSG_INVALID_SCAN_TIMEOUT.format(
            MIN_SCAN_TIMEOUT, MAX_SCAN_TIMEOUT
        )

    return True, ""

# ============================================================================
# API CLIENT HELPER
# ============================================================================

async def _make_tenable_request(
    action: IntegrationAction,
    endpoint: str,
    access_key: str,
    secret_key: str,
    method: str = "GET",
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any] | list[Any]:
    """Make HTTP request to Tenable.io API.

    Args:
        endpoint: API endpoint (with leading slash)
        access_key: Tenable access key
        secret_key: Tenable secret key
        method: HTTP method (GET, POST, DELETE)
        json_data: JSON request body
        params: Query parameters
        timeout: Request timeout in seconds

    Returns:
        API response data

    Raises:
        Exception: On API errors
    """
    url = f"{TENABLE_BASE_URL}{endpoint}"
    headers = {
        "X-ApiKeys": f"accessKey={access_key}; secretKey={secret_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        response = await action.http_request(
            url,
            method=method,
            headers=headers,
            json_data=json_data,
            params=params,
            timeout=timeout,
        )

        # Some endpoints return empty response (e.g., DELETE)
        if not response.content:
            return {}

        return response.json()

    except httpx.TimeoutException as e:
        logger.error("tenable_api_timeout_for", endpoint=endpoint, error=str(e))
        raise Exception(f"Request timed out after {timeout} seconds")
    except httpx.HTTPStatusError as e:
        logger.error(
            "tenable_api_http_error_for",
            endpoint=endpoint,
            status_code=e.response.status_code,
        )
        if e.response.status_code == 401:
            raise Exception("Invalid API credentials")
        if e.response.status_code == 403:
            raise Exception("Access forbidden - check API key permissions")
        if e.response.status_code == 404:
            raise Exception("Resource not found")
        if e.response.status_code == 429:
            raise Exception("Rate limit exceeded")
        error_text = e.response.text[:200] if e.response.text else ""
        raise Exception(f"HTTP {e.response.status_code}: {error_text}")
    except httpx.RequestError as e:
        logger.error(
            "tenable_api_connection_error_for", endpoint=endpoint, error=str(e)
        )
        raise Exception(MSG_SERVER_CONNECTION)
    except Exception as e:
        if "timed out" in str(e).lower() or "timeout" in str(e).lower():
            raise Exception(f"Request timed out: {e}")
        raise

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Tenable.io API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Tenable.io API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        access_key = self.credentials.get(CREDENTIAL_ACCESS_KEY)
        secret_key = self.credentials.get(CREDENTIAL_SECRET_KEY)

        if not access_key:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        if not secret_key:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_SECRET_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Test connectivity by listing scans
            result = await _make_tenable_request(
                self,
                ENDPOINT_SCANS_LIST,
                access_key=access_key,
                secret_key=secret_key,
                timeout=timeout,
            )

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Tenable.io API is accessible",
                "data": {
                    "healthy": True,
                    "scan_count": len(result.get("scans", []))
                    if isinstance(result, dict)
                    else 0,
                },
            }

        except Exception as e:
            logger.error("tenable_health_check_failed", error=str(e))
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

class ListScansAction(IntegrationAction):
    """Retrieve list of configured scans."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List scans in Tenable.io.

        Args:
            **kwargs: Optional parameters:
                - folder_id: Filter scans by folder ID
                - last_modified: Filter scans modified since timestamp/datetime

        Returns:
            Result with scan list or error
        """
        access_key = self.credentials.get(CREDENTIAL_ACCESS_KEY)
        secret_key = self.credentials.get(CREDENTIAL_SECRET_KEY)

        if not access_key or not secret_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_KEY
                if not access_key
                else MSG_MISSING_SECRET_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Parse optional parameters
        folder_id = kwargs.get("folder_id")
        last_modified = kwargs.get("last_modified")

        params = {}
        if folder_id is not None:
            params["folder_id"] = folder_id

        if last_modified:
            try:
                # Parse datetime and convert to Unix timestamp
                dt = _parse_datetime(last_modified)
                params["last_modification_date"] = int(dt.timestamp())
            except (ValueError, OverflowError, ParserError) as e:
                logger.error("invalid_datetime_format", error=str(e))
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_DATETIME,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

        try:
            result = await _make_tenable_request(
                self,
                ENDPOINT_SCANS_LIST,
                access_key=access_key,
                secret_key=secret_key,
                params=params if params else None,
                timeout=timeout,
            )

            scans = result.get("scans", []) if isinstance(result, dict) else []

            return {
                "status": STATUS_SUCCESS,
                "summary": {OUTPUT_SCAN_COUNT: len(scans)},
                "scans": scans,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("tenable_scans_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "scans": [],
                }
            logger.error("list_scans_failed", error=str(e))
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

class ListScannersAction(IntegrationAction):
    """Retrieve list of available scanners."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List scanners available to the user.

        Returns:
            Result with scanner list or error
        """
        access_key = self.credentials.get(CREDENTIAL_ACCESS_KEY)
        secret_key = self.credentials.get(CREDENTIAL_SECRET_KEY)

        if not access_key or not secret_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_KEY
                if not access_key
                else MSG_MISSING_SECRET_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            result = await _make_tenable_request(
                self,
                ENDPOINT_SCANNERS_LIST,
                access_key=access_key,
                secret_key=secret_key,
                timeout=timeout,
            )

            scanners = result.get("scanners", []) if isinstance(result, dict) else []

            return {
                "status": STATUS_SUCCESS,
                "summary": {OUTPUT_SCANNER_COUNT: len(scanners)},
                "scanners": scanners,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("tenable_scanners_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "scanners": [],
                }
            logger.error("list_scanners_failed", error=str(e))
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

class ListPoliciesAction(IntegrationAction):
    """Retrieve list of scan policies."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List scan policies in Tenable.io.

        Returns:
            Result with policy list or error
        """
        access_key = self.credentials.get(CREDENTIAL_ACCESS_KEY)
        secret_key = self.credentials.get(CREDENTIAL_SECRET_KEY)

        if not access_key or not secret_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_KEY
                if not access_key
                else MSG_MISSING_SECRET_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            result = await _make_tenable_request(
                self,
                ENDPOINT_POLICIES_LIST,
                access_key=access_key,
                secret_key=secret_key,
                timeout=timeout,
            )

            policies = result.get("policies", []) if isinstance(result, dict) else []

            return {
                "status": STATUS_SUCCESS,
                "summary": {OUTPUT_POLICY_COUNT: len(policies)},
                "policies": policies,
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("tenable_policies_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "policies": [],
                }
            logger.error("list_policies_failed", error=str(e))
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

class ScanHostAction(IntegrationAction):
    """Scan a host using specified policy."""

    async def execute(self, **kwargs) -> dict[str, Any]:  # noqa: C901
        """Scan a host and wait for results.

        Args:
            **kwargs: Required parameters:
                - target_to_scan: IP or hostname to scan
                - policy_id: ID of scan policy to use
                Optional parameters:
                - scan_name: Name for the scan
                - scanner_id: ID of scanner to use
                - scan_timeout: Max time to wait for scan completion (seconds)

        Returns:
            Result with scan results or error
        """
        access_key = self.credentials.get(CREDENTIAL_ACCESS_KEY)
        secret_key = self.credentials.get(CREDENTIAL_SECRET_KEY)

        if not access_key or not secret_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_KEY
                if not access_key
                else MSG_MISSING_SECRET_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Validate required parameters
        target_to_scan = kwargs.get("target_to_scan")
        if not target_to_scan:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_TARGET,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        policy_id = kwargs.get("policy_id")
        if not policy_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_POLICY_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Convert policy_id to int if it's a numeric string
        if isinstance(policy_id, str) and policy_id.isdigit():
            policy_id = int(policy_id)

        # Optional parameters
        scan_name = kwargs.get("scan_name", DEFAULT_SCAN_NAME)
        scanner_id = kwargs.get("scanner_id")
        scan_timeout = kwargs.get("scan_timeout", DEFAULT_SCAN_TIMEOUT)

        # Validate scan timeout
        is_valid, error_msg = _validate_scan_timeout(scan_timeout)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Step 1: Create scan
            logger.info("creating_scan_for_target", target_to_scan=target_to_scan)
            scan_config = {
                "uuid": policy_id if isinstance(policy_id, str) else None,
                "settings": {
                    "name": scan_name,
                    "text_targets": target_to_scan,
                },
            }

            # Add policy_id if numeric
            if isinstance(policy_id, int):
                scan_config["settings"]["policy_id"] = policy_id

            # Add scanner_id if provided
            if scanner_id:
                scan_config["settings"]["scanner_id"] = scanner_id

            create_result = await _make_tenable_request(
                self,
                ENDPOINT_SCANS_CREATE,
                access_key=access_key,
                secret_key=secret_key,
                method="POST",
                json_data=scan_config,
                timeout=timeout,
            )

            scan_id = create_result.get("scan", {}).get("id")
            if not scan_id:
                return {
                    "status": STATUS_ERROR,
                    "error": "Failed to create scan - no scan ID returned",
                    "error_type": ERROR_TYPE_HTTP,
                }

            # Step 2: Launch scan
            logger.info("launching_scan_id", scan_id=scan_id)
            launch_endpoint = ENDPOINT_SCANS_LAUNCH.format(scan_id=scan_id)
            await _make_tenable_request(
                self,
                launch_endpoint,
                access_key=access_key,
                secret_key=secret_key,
                method="POST",
                timeout=timeout,
            )

            # Step 3: Poll for scan completion
            logger.info("polling_scan_status_timeout_s", scan_timeout=scan_timeout)
            status_endpoint = ENDPOINT_SCANS_STATUS.format(scan_id=scan_id)
            scan_status = None
            elapsed = 0

            while elapsed < scan_timeout:
                status_result = await _make_tenable_request(
                    self,
                    status_endpoint,
                    access_key=access_key,
                    secret_key=secret_key,
                    timeout=timeout,
                )

                scan_status = status_result.get("info", {}).get("status")
                logger.info(
                    "scan_status_elapsed_s", scan_status=scan_status, elapsed=elapsed
                )

                if scan_status in TERMINAL_SCAN_STATUSES:
                    break

                await asyncio.sleep(DEFAULT_SCAN_POLLING_INTERVAL)
                elapsed += DEFAULT_SCAN_POLLING_INTERVAL

            # Step 4: Get scan details
            details_endpoint = ENDPOINT_SCANS_DETAILS.format(scan_id=scan_id)
            scan_details = await _make_tenable_request(
                self,
                details_endpoint,
                access_key=access_key,
                secret_key=secret_key,
                timeout=timeout,
            )

            hosts = scan_details.get("hosts", [])

            # Calculate total vulnerabilities
            total_vulns = 0
            if hosts:
                last_host = hosts[-1]
                total_vulns = sum(
                    last_host.get(sev, 0) for sev in VULNERABILITY_SEVERITIES
                )

            # Check if scan completed successfully
            error_messages = []
            if scan_status != SCAN_STATUS_COMPLETED:
                error_messages.append(
                    MSG_SCAN_NOT_COMPLETE.format(scan_timeout, scan_status)
                )

            if not hosts:
                error_messages.append(MSG_SCAN_RESPONSE_EMPTY)

            if error_messages:
                return {
                    "status": STATUS_ERROR,
                    "error": " ".join(error_messages),
                    "error_type": ERROR_TYPE_HTTP,
                    "summary": {
                        OUTPUT_SCAN_ID: scan_id,
                        OUTPUT_TOTAL_VULNS: total_vulns,
                    },
                    "hosts": hosts,
                }

            return {
                "status": STATUS_SUCCESS,
                "summary": {
                    OUTPUT_SCAN_ID: scan_id,
                    OUTPUT_TOTAL_VULNS: total_vulns,
                },
                "hosts": hosts,
                "full_data": scan_details,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("tenable_scan_target_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                }
            logger.error("scan_host_failed", error=str(e))
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

class DeleteScanAction(IntegrationAction):
    """Delete a scan."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Delete a scan from Tenable.io.

        Args:
            **kwargs: Required parameters:
                - scan_id: ID of scan to delete

        Returns:
            Result with deletion status or error
        """
        access_key = self.credentials.get(CREDENTIAL_ACCESS_KEY)
        secret_key = self.credentials.get(CREDENTIAL_SECRET_KEY)

        if not access_key or not secret_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_KEY
                if not access_key
                else MSG_MISSING_SECRET_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Validate required parameters
        scan_id = kwargs.get("scan_id")
        if not scan_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_SCAN_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            delete_endpoint = ENDPOINT_SCANS_DELETE.format(scan_id=scan_id)
            await _make_tenable_request(
                self,
                delete_endpoint,
                access_key=access_key,
                secret_key=secret_key,
                method="DELETE",
                timeout=timeout,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Delete scan completed",
                "summary": {OUTPUT_DELETE_STATUS: True},
                "data": {
                    OUTPUT_SCAN_ID: scan_id,
                    OUTPUT_DELETE_STATUS: True,
                },
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("tenable_scan_not_found", scan_id=scan_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "scan_id": scan_id,
                }
            logger.error("delete_scan_failed_for_scanid", scan_id=scan_id, error=str(e))
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

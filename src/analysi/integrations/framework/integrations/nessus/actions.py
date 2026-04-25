"""Nessus vulnerability scanner integration actions."""

import asyncio
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.nessus.constants import (
    ADVANCED_SCAN_TEMPLATE_UUID,
    CREDENTIAL_ACCESS_KEY,
    CREDENTIAL_SECRET_KEY,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    ENDPOINT_POLICIES,
    ENDPOINT_SCANS,
    ENDPOINT_USERS,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MSG_INVALID_RESPONSE,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_KEYS,
    MSG_MISSING_POLICY_ID,
    MSG_MISSING_SERVER,
    MSG_MISSING_TARGET,
    MSG_SCAN_FAILED,
    PARAM_POLICY_ID,
    PARAM_TARGET_TO_SCAN,
    SCAN_CHECK_INTERVAL,
    SCAN_STATUS_COMPLETED,
    SETTINGS_PORT,
    SETTINGS_SERVER,
    SETTINGS_TIMEOUT,
    SETTINGS_VERIFY_CERT,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# ============================================================================
# API CLIENT HELPER
# ============================================================================

async def _make_nessus_request(
    action: IntegrationAction,
    server: str,
    port: int,
    access_key: str,
    secret_key: str,
    endpoint: str,
    method: str = "GET",
    data: dict | None = None,
    verify_cert: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Make HTTP request to Nessus API.

    Args:
        server: Nessus server hostname/IP
        port: Nessus server port
        access_key: API access key
        secret_key: API secret key
        endpoint: API endpoint (without base URL)
        method: HTTP method (GET or POST)
        data: Request body data
        verify_cert: Whether to verify SSL certificate
        timeout: Request timeout in seconds

    Returns:
        API response data

    Raises:
        Exception: On API errors
    """
    url = f"https://{server}:{port}/{endpoint}"
    headers = {
        "X-ApiKeys": f"accessKey={access_key}; secretKey={secret_key};",
        "Content-Type": "application/json",
    }

    try:
        response = await action.http_request(
            url,
            method=method,
            headers=headers,
            json_data=data,
            verify_ssl=verify_cert,
            timeout=timeout,
        )

        # Handle empty response
        if not response.text:
            return {}

        return response.json()

    except httpx.TimeoutException as e:
        logger.error("nessus_api_timeout_for", endpoint=endpoint, error=str(e))
        raise Exception(f"Request timed out after {timeout} seconds")
    except httpx.HTTPStatusError as e:
        logger.error(
            "nessus_api_http_error_for",
            endpoint=endpoint,
            status_code=e.response.status_code,
        )
        raise Exception(f"HTTP {e.response.status_code}: {e.response.text}")
    except Exception as e:
        logger.error("nessus_api_error_for", endpoint=endpoint, error=str(e))
        raise

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Nessus API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Nessus API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        # Validate credentials
        server = self.settings.get(SETTINGS_SERVER)
        access_key = self.credentials.get(CREDENTIAL_ACCESS_KEY)
        secret_key = self.credentials.get(CREDENTIAL_SECRET_KEY)
        port = self.settings.get(SETTINGS_PORT, DEFAULT_PORT)
        verify_cert = self.settings.get(SETTINGS_VERIFY_CERT, False)

        if not server:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_SERVER,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        if not access_key or not secret_key:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_KEYS,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Try to get users list as health check
            await _make_nessus_request(
                self,
                server=server,
                port=port,
                access_key=access_key,
                secret_key=secret_key,
                endpoint=ENDPOINT_USERS,
                verify_cert=verify_cert,
                timeout=timeout,
            )

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Nessus API is accessible",
                "data": {
                    "healthy": True,
                    "server": server,
                    "port": port,
                },
            }

        except Exception as e:
            logger.error("nessus_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class ListPoliciesAction(IntegrationAction):
    """List available scan policies."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get list of available scan policies from Nessus.

        Returns:
            Result with list of policies or error
        """
        # Validate credentials
        server = self.settings.get(SETTINGS_SERVER)
        access_key = self.credentials.get(CREDENTIAL_ACCESS_KEY)
        secret_key = self.credentials.get(CREDENTIAL_SECRET_KEY)
        port = self.settings.get(SETTINGS_PORT, DEFAULT_PORT)
        verify_cert = self.settings.get(SETTINGS_VERIFY_CERT, False)

        if not server or not access_key or not secret_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            result = await _make_nessus_request(
                self,
                server=server,
                port=port,
                access_key=access_key,
                secret_key=secret_key,
                endpoint=ENDPOINT_POLICIES,
                verify_cert=verify_cert,
                timeout=timeout,
            )

            policies = result.get("policies", [])
            if not isinstance(policies, list):
                policies = [policies] if policies else []

            return {
                "status": STATUS_SUCCESS,
                "policies": policies,
                "policy_count": len(policies),
                "data": result,
            }

        except Exception as e:
            logger.error("nessus_list_policies_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ScanHostAction(IntegrationAction):
    """Scan a host using a selected scan policy."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Scan a host with specified policy.

        Args:
            **kwargs: Must contain 'target_to_scan' and 'policy_id'

        Returns:
            Result with scan results or error
        """
        # Validate inputs
        target = kwargs.get(PARAM_TARGET_TO_SCAN)
        if not target:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_TARGET,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        policy_id = kwargs.get(PARAM_POLICY_ID)
        if not policy_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_POLICY_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        server = self.settings.get(SETTINGS_SERVER)
        access_key = self.credentials.get(CREDENTIAL_ACCESS_KEY)
        secret_key = self.credentials.get(CREDENTIAL_SECRET_KEY)
        port = self.settings.get(SETTINGS_PORT, DEFAULT_PORT)
        verify_cert = self.settings.get(SETTINGS_VERIFY_CERT, False)

        if not server or not access_key or not secret_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Create scan options
            scan_options = {
                "uuid": ADVANCED_SCAN_TEMPLATE_UUID,
                "settings": {
                    "name": "Scan Launched from Naxos",
                    "enabled": "true",
                    "scanner_id": "1",
                    "policy_id": str(policy_id),
                    "text_targets": str(target),
                    "launch_now": "true",
                },
            }

            # Launch scan
            scan_result = await _make_nessus_request(
                self,
                server=server,
                port=port,
                access_key=access_key,
                secret_key=secret_key,
                endpoint=ENDPOINT_SCANS,
                method="POST",
                data=scan_options,
                verify_cert=verify_cert,
                timeout=timeout,
            )

            scan_id = scan_result.get("scan", {}).get("id")
            if not scan_id:
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_RESPONSE,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            # Poll scan status until completed
            scan_completed = False
            hosts_data = []

            while not scan_completed:
                await asyncio.sleep(SCAN_CHECK_INTERVAL)

                scan_status = await _make_nessus_request(
                    self,
                    server=server,
                    port=port,
                    access_key=access_key,
                    secret_key=secret_key,
                    endpoint=f"{ENDPOINT_SCANS}/{scan_id}",
                    verify_cert=verify_cert,
                    timeout=timeout,
                )

                info = scan_status.get("info", {})
                status = info.get("status", "")

                if status == SCAN_STATUS_COMPLETED:
                    scan_completed = True
                    hosts_data = scan_status.get("hosts", [])
                    if not isinstance(hosts_data, list):
                        hosts_data = [hosts_data] if hosts_data else []

            # Process scan results
            if not hosts_data:
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_SCAN_FAILED,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            # Calculate total vulnerabilities
            total_vulns = 0
            if hosts_data:
                last_host = hosts_data[-1]
                total_vulns = (
                    last_host.get("low", 0)
                    + last_host.get("medium", 0)
                    + last_host.get("high", 0)
                    + last_host.get("critical", 0)
                )

            return {
                "status": STATUS_SUCCESS,
                "target": target,
                "policy_id": policy_id,
                "scan_id": scan_id,
                "hosts": hosts_data,
                "total_vulnerabilities": total_vulns,
                "summary": {
                    "critical": sum(h.get("critical", 0) for h in hosts_data),
                    "high": sum(h.get("high", 0) for h in hosts_data),
                    "medium": sum(h.get("medium", 0) for h in hosts_data),
                    "low": sum(h.get("low", 0) for h in hosts_data),
                    "info": sum(h.get("info", 0) for h in hosts_data),
                },
            }

        except Exception as e:
            logger.error("nessus_scan_host_failed_for", target=target, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetHostVulnerabilitiesAction(IntegrationAction):
    """Get vulnerabilities for a specific host from a scan."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get host vulnerabilities from scan results.

        This action retrieves detailed vulnerability information for a specific host.
        It maps to the VulnerabilityManagement archetype's get_asset_vulnerabilities.

        Args:
            **kwargs: Must contain 'scan_id' and 'host_id'

        Returns:
            Result with host vulnerability details or error
        """
        # Validate inputs
        scan_id = kwargs.get("scan_id")
        host_id = kwargs.get("host_id")

        if not scan_id:
            return {
                "status": STATUS_ERROR,
                "error": "Missing scan_id parameter",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not host_id:
            return {
                "status": STATUS_ERROR,
                "error": "Missing host_id parameter",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        server = self.settings.get(SETTINGS_SERVER)
        access_key = self.credentials.get(CREDENTIAL_ACCESS_KEY)
        secret_key = self.credentials.get(CREDENTIAL_SECRET_KEY)
        port = self.settings.get(SETTINGS_PORT, DEFAULT_PORT)
        verify_cert = self.settings.get(SETTINGS_VERIFY_CERT, False)

        if not server or not access_key or not secret_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Get host details from scan
            result = await _make_nessus_request(
                self,
                server=server,
                port=port,
                access_key=access_key,
                secret_key=secret_key,
                endpoint=f"{ENDPOINT_SCANS}/{scan_id}/hosts/{host_id}",
                verify_cert=verify_cert,
                timeout=timeout,
            )

            vulnerabilities = result.get("vulnerabilities", [])
            if not isinstance(vulnerabilities, list):
                vulnerabilities = [vulnerabilities] if vulnerabilities else []

            return {
                "status": STATUS_SUCCESS,
                "scan_id": scan_id,
                "host_id": host_id,
                "vulnerabilities": vulnerabilities,
                "vulnerability_count": len(vulnerabilities),
                "data": result,
            }

        except Exception as e:
            logger.error(
                "nessus_get_host_vulnerabilities_failed",
                scan_id=scan_id,
                host_id=host_id,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

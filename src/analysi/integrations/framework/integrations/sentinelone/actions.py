"""SentinelOne integration actions for EDR/XDR operations."""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ANALYST_VERDICTS,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP_ERROR,
    ERROR_TYPE_REQUEST_ERROR,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    INCIDENT_STATUSES,
    MITIGATION_ACTIONS,
    MSG_ENDPOINT_NOT_FOUND,
    MSG_HASH_ALREADY_EXISTS,
    MSG_HASH_NOT_FOUND,
    MSG_MISSING_CREDENTIALS,
    MSG_MULTIPLE_ENDPOINTS_FOUND,
    MSG_THREAT_NOT_FOUND,
    OS_TYPES,
    SENTINELONE_BASE_URL_SUFFIX,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# Type alias for the request function passed to helpers
_RequestFn = Callable[..., Coroutine[Any, Any, httpx.Response]]

async def _get_agent_id(
    ip_hostname: str,
    base_url: str,
    headers: dict[str, str],
    request_fn: _RequestFn,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[str, str | None]:
    """Get agent ID from IP or hostname.

    Args:
        ip_hostname: IP address or hostname to search
        base_url: SentinelOne API base URL
        headers: Auth headers
        request_fn: Bound ``self.http_request`` from the calling action
        timeout: Request timeout

    Returns:
        Tuple of (status, agent_id or error_message)
        status can be: "success", "not_found", "multiple", "error"
    """
    try:
        response = await request_fn(
            f"{base_url}/agents",
            headers=headers,
            params={"query": ip_hostname},
            timeout=timeout,
        )
        result = response.json()

        endpoints_found = len(result.get("data", []))
        if endpoints_found == 0:
            return "not_found", None
        if endpoints_found > 1:
            return "multiple", None
        return "success", result["data"][0]["id"]
    except Exception as e:
        return "error", str(e)

async def _get_site_ids(
    base_url: str,
    headers: dict[str, str],
    request_fn: _RequestFn,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[str, list[str] | None]:
    """Get all site IDs.

    Args:
        base_url: SentinelOne API base URL
        headers: Auth headers
        request_fn: Bound ``self.http_request`` from the calling action
        timeout: Request timeout

    Returns:
        Tuple of (status, list of site IDs or None)
    """
    try:
        response = await request_fn(
            f"{base_url}/sites",
            headers=headers,
            timeout=timeout,
        )
        result = response.json()

        sites = result.get("data", {}).get("sites", [])
        site_ids = [site["id"] for site in sites if site and site.get("id")]
        return "success", site_ids if site_ids else None
    except Exception:
        return "error", None

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for SentinelOne API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check SentinelOne API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            # Test connectivity by getting accounts
            response = await self.http_request(
                f"{base_url}/accounts",
                headers=headers,
                timeout=timeout,
            )
            result = response.json()

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "SentinelOne API is accessible",
                "data": {
                    "healthy": True,
                    "api_version": "v2.1",
                    "accounts_count": len(result.get("data", [])),
                },
            }

        except Exception as e:
            logger.error("sentinelone_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class BlockHashAction(IntegrationAction):
    """Add a file hash to the global blocklist."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block a file hash globally.

        Args:
            **kwargs: Must contain 'hash', 'description', 'os_family'

        Returns:
            Result with status
        """
        # Validate inputs
        file_hash = kwargs.get("hash")
        description = kwargs.get("description", "Added via Naxos")
        os_family = kwargs.get("os_family", "windows")

        if not file_hash:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'hash'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if os_family not in OS_TYPES:
            return {
                "status": STATUS_ERROR,
                "error": f"Invalid os_family. Must be one of: {', '.join(OS_TYPES)}",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            # Get site IDs
            site_status, site_ids = await _get_site_ids(
                base_url,
                headers,
                self.http_request,
                timeout,
            )
            if site_status != "success" or not site_ids:
                return {
                    "status": STATUS_ERROR,
                    "error": "Failed to retrieve site IDs",
                    "error_type": ERROR_TYPE_CONFIGURATION,
                }

            # Check if hash already exists
            check_resp = await self.http_request(
                f"{base_url}/restrictions",
                headers=headers,
                params={"value": file_hash, "type": "black_hash"},
                timeout=timeout,
            )
            check_response = check_resp.json()

            if check_response.get("pagination", {}).get("totalItems", 0) > 0:
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_HASH_ALREADY_EXISTS,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            # Add hash to blocklist for each site
            results = []
            for site_id in site_ids:
                body = {
                    "data": {
                        "description": description,
                        "osType": os_family,
                        "type": "black_hash",
                        "value": file_hash,
                        "source": "naxos",
                    },
                    "filter": {"siteIds": [site_id], "tenant": "true"},
                }

                resp = await self.http_request(
                    f"{base_url}/restrictions",
                    method="POST",
                    headers=headers,
                    json_data=body,
                    timeout=timeout,
                )
                result = resp.json()
                results.append({"site_id": site_id, "result": result})

            return {
                "status": STATUS_SUCCESS,
                "message": f"Successfully added hash to blocklist for {len(site_ids)} site(s)",
                "hash": file_hash,
                "sites_updated": len(site_ids),
                "results": results,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("sentinelone_block_hash_not_found", hash=file_hash)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "hash": file_hash,
                }
            logger.error("block_hash_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("block_hash_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class UnblockHashAction(IntegrationAction):
    """Remove a file hash from the global blocklist."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock a file hash.

        Args:
            **kwargs: Must contain 'hash'

        Returns:
            Result with status
        """
        file_hash = kwargs.get("hash")

        if not file_hash:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'hash'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            # Find hash ID
            resp = await self.http_request(
                f"{base_url}/restrictions",
                headers=headers,
                params={"value": file_hash, "type": "black_hash"},
                timeout=timeout,
            )
            find_result = resp.json()

            total_items = find_result.get("pagination", {}).get("totalItems", 0)
            if total_items == 0:
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_HASH_NOT_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if total_items > 1:
                return {
                    "status": STATUS_ERROR,
                    "error": f"Multiple IDs found for hash {file_hash}: {total_items}",
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            hash_id = find_result["data"][0]["id"]

            # Delete hash
            delete_body = {"data": {"ids": [hash_id], "type": "black_hash"}}

            await self.http_request(
                f"{base_url}/restrictions",
                method="DELETE",
                headers=headers,
                json_data=delete_body,
                params={"value": file_hash, "type": "black_hash"},
                timeout=timeout,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully removed hash from blocklist",
                "hash": file_hash,
                "hash_id": hash_id,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("sentinelone_unblock_hash_not_found", hash=file_hash)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "hash": file_hash,
                }
            logger.error("unblock_hash_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("unblock_hash_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class IsolateHostAction(IntegrationAction):
    """Isolate/quarantine a device from the network."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Quarantine a device.

        Args:
            **kwargs: Must contain 'ip_hostname'

        Returns:
            Result with status
        """
        ip_hostname = kwargs.get("ip_hostname")

        if not ip_hostname:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'ip_hostname'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            # Get agent ID
            status, agent_id_or_error = await _get_agent_id(
                ip_hostname,
                base_url,
                headers,
                self.http_request,
                timeout,
            )

            if status == "not_found":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_ENDPOINT_NOT_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "multiple":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_MULTIPLE_ENDPOINTS_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "error":
                return {
                    "status": STATUS_ERROR,
                    "error": agent_id_or_error,
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            agent_id = agent_id_or_error

            # Disconnect agent (quarantine)
            body = {
                "data": {},
                "filter": {"isActive": "true", "ids": [agent_id]},
            }

            resp = await self.http_request(
                f"{base_url}/agents/actions/disconnect",
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )
            result = resp.json()

            affected = result.get("data", {}).get("affected", 0)
            if affected == 0:
                return {
                    "status": STATUS_ERROR,
                    "error": "Could not quarantine device",
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully quarantined device",
                "ip_hostname": ip_hostname,
                "agent_id": agent_id,
                "affected": affected,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "sentinelone_isolate_host_not_found", ip_hostname=ip_hostname
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                }
            logger.error("isolate_host_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("isolate_host_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ReleaseHostAction(IntegrationAction):
    """Release a device from isolation/quarantine."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unquarantine a device.

        Args:
            **kwargs: Must contain 'ip_hostname'

        Returns:
            Result with status
        """
        ip_hostname = kwargs.get("ip_hostname")

        if not ip_hostname:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'ip_hostname'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            # Get agent ID
            status, agent_id_or_error = await _get_agent_id(
                ip_hostname,
                base_url,
                headers,
                self.http_request,
                timeout,
            )

            if status == "not_found":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_ENDPOINT_NOT_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "multiple":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_MULTIPLE_ENDPOINTS_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "error":
                return {
                    "status": STATUS_ERROR,
                    "error": agent_id_or_error,
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            agent_id = agent_id_or_error

            # Connect agent (unquarantine)
            body = {
                "data": {},
                "filter": {"isActive": "true", "ids": [agent_id]},
            }

            resp = await self.http_request(
                f"{base_url}/agents/actions/connect",
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )
            result = resp.json()

            affected = result.get("data", {}).get("affected", 0)
            if affected == 0:
                return {
                    "status": STATUS_ERROR,
                    "error": "Could not unquarantine device",
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully unquarantined device",
                "ip_hostname": ip_hostname,
                "agent_id": agent_id,
                "affected": affected,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "sentinelone_release_host_not_found", ip_hostname=ip_hostname
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                }
            logger.error("release_host_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("release_host_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ScanHostAction(IntegrationAction):
    """Initiate a scan on an endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Scan an endpoint.

        Args:
            **kwargs: Must contain 'ip_hostname'

        Returns:
            Result with status
        """
        ip_hostname = kwargs.get("ip_hostname")

        if not ip_hostname:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'ip_hostname'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            # Get agent ID
            status, agent_id_or_error = await _get_agent_id(
                ip_hostname,
                base_url,
                headers,
                self.http_request,
                timeout,
            )

            if status == "not_found":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_ENDPOINT_NOT_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "multiple":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_MULTIPLE_ENDPOINTS_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "error":
                return {
                    "status": STATUS_ERROR,
                    "error": agent_id_or_error,
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            agent_id = agent_id_or_error

            # Initiate scan
            body = {"data": {}, "filter": {"ids": agent_id}}

            resp = await self.http_request(
                f"{base_url}/agents/actions/initiate-scan",
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )
            result = resp.json()

            affected = result.get("data", {}).get("affected", 0)
            if affected == 0:
                return {
                    "status": STATUS_ERROR,
                    "error": "Could not start scanning",
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully initiated scan",
                "ip_hostname": ip_hostname,
                "agent_id": agent_id,
                "affected": affected,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("sentinelone_scan_host_not_found", ip_hostname=ip_hostname)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                }
            logger.error("scan_host_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("scan_host_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetHostDetailsAction(IntegrationAction):
    """Get endpoint/host information."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get endpoint information.

        Args:
            **kwargs: Must contain 'ip_hostname'

        Returns:
            Result with endpoint data
        """
        ip_hostname = kwargs.get("ip_hostname")

        if not ip_hostname:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'ip_hostname'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            # Get agent ID
            status, agent_id_or_error = await _get_agent_id(
                ip_hostname,
                base_url,
                headers,
                self.http_request,
                timeout,
            )

            if status == "not_found":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_ENDPOINT_NOT_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "multiple":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_MULTIPLE_ENDPOINTS_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "error":
                return {
                    "status": STATUS_ERROR,
                    "error": agent_id_or_error,
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            agent_id = agent_id_or_error

            # Get agent details
            resp = await self.http_request(
                f"{base_url}/agents",
                headers=headers,
                params={"ids": [agent_id]},
                timeout=timeout,
            )
            result = resp.json()

            return {
                "status": STATUS_SUCCESS,
                "ip_hostname": ip_hostname,
                "agent_id": agent_id,
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "sentinelone_get_host_details_not_found", ip_hostname=ip_hostname
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                }
            logger.error("get_host_details_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("get_host_details_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class MitigateThreatAction(IntegrationAction):
    """Mitigate a threat (kill, quarantine, remediate, etc.)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Mitigate a threat.

        Args:
            **kwargs: Must contain 's1_threat_id' and 'action'

        Returns:
            Result with status
        """
        s1_threat_id = kwargs.get("s1_threat_id")
        action = kwargs.get("action")

        if not s1_threat_id:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 's1_threat_id'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not action:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'action'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if action not in MITIGATION_ACTIONS:
            return {
                "status": STATUS_ERROR,
                "error": f"Invalid action. Must be one of: {', '.join(MITIGATION_ACTIONS)}",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            body = {
                "data": {},
                "filter": {"ids": [s1_threat_id]},
            }

            resp = await self.http_request(
                f"{base_url}/threats/mitigate/{action}",
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )
            result = resp.json()

            affected = result.get("data", {}).get("affected", 0)
            if affected == 0:
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_THREAT_NOT_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            return {
                "status": STATUS_SUCCESS,
                "message": f"Successfully mitigated threat with action '{action}'",
                "s1_threat_id": s1_threat_id,
                "action": action,
                "affected": affected,
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "sentinelone_mitigate_threat_not_found", s1_threat_id=s1_threat_id
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "threat_id": s1_threat_id,
                }
            logger.error("mitigate_threat_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("mitigate_threat_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class AbortScanAction(IntegrationAction):
    """Abort a running scan on an endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Abort scan on endpoint.

        Args:
            **kwargs: Must contain 'ip_hostname'

        Returns:
            Result with status
        """
        ip_hostname = kwargs.get("ip_hostname")

        if not ip_hostname:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'ip_hostname'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            status, agent_id_or_error = await _get_agent_id(
                ip_hostname,
                base_url,
                headers,
                self.http_request,
                timeout,
            )

            if status == "not_found":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_ENDPOINT_NOT_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "multiple":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_MULTIPLE_ENDPOINTS_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "error":
                return {
                    "status": STATUS_ERROR,
                    "error": agent_id_or_error,
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            agent_id = agent_id_or_error

            body = {"data": {}, "filter": {"ids": agent_id}}

            resp = await self.http_request(
                f"{base_url}/agents/actions/abort-scan",
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )
            result = resp.json()

            affected = result.get("data", {}).get("affected", 0)
            if affected == 0:
                return {
                    "status": STATUS_ERROR,
                    "error": "Could not abort scanning",
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully aborted scan",
                "ip_hostname": ip_hostname,
                "agent_id": agent_id,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("sentinelone_abort_scan_not_found", ip_hostname=ip_hostname)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                }
            logger.error("abort_scan_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("abort_scan_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ShutdownEndpointAction(IntegrationAction):
    """Shutdown an endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Shutdown endpoint.

        Args:
            **kwargs: Must contain 'ip_hostname'

        Returns:
            Result with status
        """
        ip_hostname = kwargs.get("ip_hostname")

        if not ip_hostname:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'ip_hostname'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            status, agent_id_or_error = await _get_agent_id(
                ip_hostname,
                base_url,
                headers,
                self.http_request,
                timeout,
            )

            if status == "not_found":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_ENDPOINT_NOT_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "multiple":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_MULTIPLE_ENDPOINTS_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "error":
                return {
                    "status": STATUS_ERROR,
                    "error": agent_id_or_error,
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            agent_id = agent_id_or_error

            body = {"data": {}, "filter": {"ids": agent_id}}

            resp = await self.http_request(
                f"{base_url}/agents/actions/shutdown",
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )
            result = resp.json()

            affected = result.get("data", {}).get("affected", 0)
            if affected == 0:
                return {
                    "status": STATUS_ERROR,
                    "error": "Could not shutdown endpoint",
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully shutdown endpoint",
                "ip_hostname": ip_hostname,
                "agent_id": agent_id,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "sentinelone_shutdown_endpoint_not_found", ip_hostname=ip_hostname
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                }
            logger.error("shutdown_endpoint_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("shutdown_endpoint_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class BroadcastMessageAction(IntegrationAction):
    """Broadcast a message to an endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Broadcast message to endpoint.

        Args:
            **kwargs: Must contain 'ip_hostname' and 'message'

        Returns:
            Result with status
        """
        ip_hostname = kwargs.get("ip_hostname")
        message = kwargs.get("message")

        if not ip_hostname:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'ip_hostname'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not message:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'message'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            status, agent_id_or_error = await _get_agent_id(
                ip_hostname,
                base_url,
                headers,
                self.http_request,
                timeout,
            )

            if status == "not_found":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_ENDPOINT_NOT_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "multiple":
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_MULTIPLE_ENDPOINTS_FOUND,
                    "error_type": ERROR_TYPE_VALIDATION,
                }
            if status == "error":
                return {
                    "status": STATUS_ERROR,
                    "error": agent_id_or_error,
                    "error_type": ERROR_TYPE_REQUEST_ERROR,
                }

            agent_id = agent_id_or_error

            body = {"data": {"message": message}, "filter": {"ids": agent_id}}

            await self.http_request(
                f"{base_url}/agents/actions/broadcast",
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully broadcast message",
                "ip_hostname": ip_hostname,
                "agent_id": agent_id,
                "broadcast_message": message,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "sentinelone_broadcast_message_not_found", ip_hostname=ip_hostname
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                }
            logger.error("broadcast_message_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("broadcast_message_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetThreatInfoAction(IntegrationAction):
    """Get threat information."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get threat details.

        Args:
            **kwargs: Must contain 's1_threat_id'

        Returns:
            Result with threat data
        """
        s1_threat_id = kwargs.get("s1_threat_id")

        if not s1_threat_id:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 's1_threat_id'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = await self.http_request(
                f"{base_url}/threats",
                headers=headers,
                params={"ids": [s1_threat_id]},
                timeout=timeout,
            )
            result = resp.json()

            return {
                "status": STATUS_SUCCESS,
                "s1_threat_id": s1_threat_id,
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "sentinelone_get_threat_info_not_found", s1_threat_id=s1_threat_id
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "threat_id": s1_threat_id,
                }
            logger.error("get_threat_info_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("get_threat_info_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class HashReputationAction(IntegrationAction):
    """Get hash reputation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get hash reputation.

        Args:
            **kwargs: Must contain 'hash'

        Returns:
            Result with reputation data
        """
        file_hash = kwargs.get("hash")

        if not file_hash:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'hash'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = await self.http_request(
                f"{base_url}/hashes/{file_hash}/reputation",
                headers=headers,
                timeout=timeout,
            )
            result = resp.json()

            return {
                "status": STATUS_SUCCESS,
                "hash": file_hash,
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("sentinelone_hash_reputation_not_found", hash=file_hash)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "hash": file_hash,
                    "reputation": "unknown",
                }
            logger.error("hash_reputation_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("hash_reputation_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetThreatNotesAction(IntegrationAction):
    """Get notes for a threat."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get threat notes.

        Args:
            **kwargs: Must contain 's1_threat_id'

        Returns:
            Result with threat notes
        """
        s1_threat_id = kwargs.get("s1_threat_id")

        if not s1_threat_id:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 's1_threat_id'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = await self.http_request(
                f"{base_url}/threats/{s1_threat_id}/notes",
                headers=headers,
                timeout=timeout,
            )
            result = resp.json()

            return {
                "status": STATUS_SUCCESS,
                "s1_threat_id": s1_threat_id,
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "sentinelone_get_threat_notes_not_found", s1_threat_id=s1_threat_id
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "threat_id": s1_threat_id,
                }
            logger.error("get_threat_notes_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("get_threat_notes_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class AddThreatNoteAction(IntegrationAction):
    """Add a note to one or more threats."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add note to threats.

        Args:
            **kwargs: Must contain 's1_threat_ids' (comma-separated) and 'note'

        Returns:
            Result with status
        """
        s1_threat_ids_str = kwargs.get("s1_threat_ids")
        note = kwargs.get("note")

        if not s1_threat_ids_str:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 's1_threat_ids'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not note:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'note'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Parse comma-separated IDs
        s1_threat_ids = [
            tid.strip() for tid in s1_threat_ids_str.split(",") if tid.strip()
        ]
        if not s1_threat_ids:
            return {
                "status": STATUS_ERROR,
                "error": "Invalid s1_threat_ids - must be comma-separated list",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            body = {
                "data": {"text": note},
                "filter": {"ids": s1_threat_ids, "tenant": "true"},
            }

            resp = await self.http_request(
                f"{base_url}/threats/notes",
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )
            result = resp.json()

            return {
                "status": STATUS_SUCCESS,
                "message": f"Successfully added note to {len(s1_threat_ids)} threat(s)",
                "threat_ids": s1_threat_ids,
                "note": note,
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "sentinelone_add_threat_note_not_found", s1_threat_ids=s1_threat_ids
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                }
            logger.error("add_threat_note_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("add_threat_note_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class UpdateThreatAnalystVerdictAction(IntegrationAction):
    """Update threat analyst verdict."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update analyst verdict.

        Args:
            **kwargs: Must contain 's1_threat_id' and 'analyst_verdict'

        Returns:
            Result with status
        """
        s1_threat_id = kwargs.get("s1_threat_id")
        analyst_verdict = kwargs.get("analyst_verdict")

        if not s1_threat_id:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 's1_threat_id'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not analyst_verdict:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'analyst_verdict'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if analyst_verdict not in ANALYST_VERDICTS:
            return {
                "status": STATUS_ERROR,
                "error": f"Invalid analyst_verdict. Must be one of: {', '.join(ANALYST_VERDICTS)}",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            body = {
                "data": {"analystVerdict": analyst_verdict},
                "filter": {"ids": s1_threat_id, "tenant": "true"},
            }

            resp = await self.http_request(
                f"{base_url}/threats/analyst-verdict",
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )
            result = resp.json()

            affected = result.get("data", {}).get("affected", 0)
            if affected == 0:
                return {
                    "status": STATUS_ERROR,
                    "error": "Given analyst verdict is already present",
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully updated threat analyst verdict",
                "s1_threat_id": s1_threat_id,
                "analyst_verdict": analyst_verdict,
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "sentinelone_update_analyst_verdict_not_found",
                    s1_threat_id=s1_threat_id,
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "threat_id": s1_threat_id,
                }
            logger.error("update_threat_analyst_verdict_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("update_threat_analyst_verdict_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class UpdateThreatIncidentAction(IntegrationAction):
    """Update threat incident status."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update threat incident.

        Args:
            **kwargs: Must contain 's1_threat_id', 'analyst_verdict', 'incident_status'

        Returns:
            Result with status
        """
        s1_threat_id = kwargs.get("s1_threat_id")
        analyst_verdict = kwargs.get("analyst_verdict")
        incident_status = kwargs.get("incident_status")

        if not s1_threat_id:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 's1_threat_id'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not analyst_verdict:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'analyst_verdict'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not incident_status:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'incident_status'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if analyst_verdict not in ANALYST_VERDICTS:
            return {
                "status": STATUS_ERROR,
                "error": f"Invalid analyst_verdict. Must be one of: {', '.join(ANALYST_VERDICTS)}",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if incident_status not in INCIDENT_STATUSES:
            return {
                "status": STATUS_ERROR,
                "error": f"Invalid incident_status. Must be one of: {', '.join(INCIDENT_STATUSES)}",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        try:
            body = {
                "data": {
                    "analystVerdict": analyst_verdict,
                    "incidentStatus": incident_status,
                },
                "filter": {"ids": s1_threat_id, "tenant": "true"},
            }

            resp = await self.http_request(
                f"{base_url}/threats/incident",
                method="POST",
                headers=headers,
                json_data=body,
                timeout=timeout,
            )
            result = resp.json()

            affected = result.get("data", {}).get("affected", 0)
            if affected == 0:
                return {
                    "status": STATUS_ERROR,
                    "error": "Given threat incident status is already present",
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully updated threat incident status",
                "s1_threat_id": s1_threat_id,
                "analyst_verdict": analyst_verdict,
                "incident_status": incident_status,
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "sentinelone_update_incident_not_found", s1_threat_id=s1_threat_id
                )
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "threat_id": s1_threat_id,
                }
            logger.error("update_threat_incident_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("update_threat_incident_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

# ============================================================================
# ALERT SOURCE ACTIONS
# ============================================================================

class PullAlertsAction(IntegrationAction):
    """Pull threats from SentinelOne as alerts.

    Project Symi: AlertSource archetype requires this action.
    Queries GET /web/api/v2.1/threats with cursor-based pagination.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Pull threats from SentinelOne.

        Args:
            start_time: Start of time range (datetime or ISO string, optional)
            end_time: End of time range (datetime or ISO string, optional)
            max_results: Maximum number of threats to return (default: 1000)

        Returns:
            dict: Alerts pulled with count and data

        Note:
            If start_time is not provided, uses the integration's
            default_lookback_minutes setting to determine how far back
            to search (default: 5 minutes).
        """
        console_url = self.settings.get("console_url")
        api_token = self.credentials.get("api_token")

        if not console_url or not api_token:
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
            lookback_minutes = self.settings.get("default_lookback_minutes", 5)
            start_time = end_time - timedelta(minutes=lookback_minutes)

        max_results = params.get("max_results", 1000)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        base_url = console_url.rstrip("/") + SENTINELONE_BASE_URL_SUFFIX
        headers = {
            "Authorization": f"APIToken {api_token}",
            "Content-Type": "application/json",
        }

        all_threats: list[dict[str, Any]] = []
        cursor: str | None = None
        page_size = min(100, max_results)

        try:
            while len(all_threats) < max_results:
                query_params: dict[str, Any] = {
                    "createdAt__gte": start_time.isoformat(),
                    "limit": page_size,
                    "sortBy": "createdAt",
                    "sortOrder": "desc",
                }
                if cursor:
                    query_params["cursor"] = cursor

                response = await self.http_request(
                    f"{base_url}/threats",
                    headers=headers,
                    params=query_params,
                    timeout=timeout,
                )
                result = response.json()

                threats = result.get("data", [])
                if not threats:
                    break

                all_threats.extend(threats)

                # Check for next cursor
                pagination = result.get("pagination", {})
                next_cursor = pagination.get("nextCursor")
                if not next_cursor:
                    break
                cursor = next_cursor

            return {
                "status": STATUS_SUCCESS,
                "alerts_count": len(all_threats),
                "alerts": all_threats,
                "message": f"Retrieved {len(all_threats)} threats",
            }

        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_TIMEOUT,
                "error": f"Threat query timeout: {e!s}",
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_HTTP_ERROR,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error_type": ERROR_TYPE_REQUEST_ERROR,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

class AlertsToOcsfAction(IntegrationAction):
    """Normalize raw SentinelOne threats to OCSF Detection Finding v1.8.0.

    Delegates to SentinelOneOCSFNormalizer which produces full OCSF
    Detection Findings with metadata, evidences, observables, device,
    actor, and disposition mapping.

    Project Symi: AlertSource archetype requires this action.
    """

    async def execute(self, **params) -> dict[str, Any]:
        """Normalize raw SentinelOne threats to OCSF format.

        Args:
            raw_alerts: List of raw SentinelOne threat objects.

        Returns:
            dict with status, normalized_alerts (OCSF dicts), count, and errors.
        """
        from alert_normalizer.sentinelone_ocsf import SentinelOneOCSFNormalizer

        raw_alerts = params.get("raw_alerts", [])
        logger.info("sentinelone_alerts_to_ocsf_called", count=len(raw_alerts))

        normalizer = SentinelOneOCSFNormalizer()
        normalized = []
        errors = 0

        for alert in raw_alerts:
            try:
                ocsf_finding = normalizer.to_ocsf(alert)
                normalized.append(ocsf_finding)
            except Exception:
                threat_id = alert.get("id") if isinstance(alert, dict) else None
                threat_name = (
                    alert.get("threatInfo", {}).get("threatName")
                    if isinstance(alert, dict)
                    else None
                )
                logger.exception(
                    "sentinelone_threat_to_ocsf_failed",
                    threat_id=threat_id,
                    threat_name=threat_name,
                )
                errors += 1

        return {
            "status": "success" if errors == 0 else "partial",
            "normalized_alerts": normalized,
            "count": len(normalized),
            "errors": errors,
        }

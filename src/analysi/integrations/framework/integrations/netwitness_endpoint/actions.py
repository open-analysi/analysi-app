"""
NetWitness Endpoint integration actions.
RSA NetWitness Endpoint is an EDR platform for threat detection and response.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    BLOCKLIST_DOMAIN_ENDPOINT,
    BLOCKLIST_IP_ENDPOINT,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_IOC_LEVEL,
    DEFAULT_IOC_SCORE_GTE,
    DEFAULT_IOC_SCORE_LTE,
    DEFAULT_LIMIT,
    DEFAULT_MAX_CPU_VALUE,
    DEFAULT_MAX_CPU_VM_VALUE,
    DEFAULT_MIN_CPU_VALUE,
    DEFAULT_MIN_MACHINE_COUNT,
    DEFAULT_MIN_MODULE_COUNT,
    DEFAULT_SCAN_CATEGORY,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_NOT_FOUND,
    ERROR_TYPE_VALIDATION,
    GET_SCAN_DATA_ENDPOINT,
    GET_SYSTEM_INFO_ENDPOINT,
    HTTP_OK,
    INSTANTIOC_ENDPOINT,
    LIST_MACHINES_ENDPOINT,
    MSG_ENDPOINT_NOT_FOUND,
    MSG_IOC_NOT_FOUND,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAMETER,
    SCAN_CATEGORY_MAPPING,
    SCAN_DATA_CATEGORIES,
    SCAN_ENDPOINT,
    SETTINGS_TIMEOUT,
    SETTINGS_URL,
    SETTINGS_VERIFY_SSL,
    STATUS_ERROR,
    STATUS_SUCCESS,
    TEST_CONNECTIVITY_ENDPOINT,
)

logger = get_logger(__name__)

# ============================================================================
# API CLIENT HELPER
# ============================================================================

async def _make_netwitness_request(
    action: IntegrationAction,
    endpoint: str,
    base_url: str,
    username: str,
    password: str,
    method: str = "GET",
    params: dict | None = None,
    data: dict | None = None,
    verify_ssl: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Make HTTP request to NetWitness Endpoint API.

    Args:
        endpoint: API endpoint path
        base_url: NetWitness base URL
        username: Username for HTTP Basic Auth
        password: Password for HTTP Basic Auth
        method: HTTP method
        params: Query parameters
        data: Request body data (JSON)
        verify_ssl: Whether to verify SSL certificates
        timeout: Request timeout

    Returns:
        API response data

    Raises:
        Exception: On API errors
    """
    url = f"{base_url.rstrip('/')}{endpoint}"

    try:
        response = await action.http_request(
            url,
            method=method.upper(),
            params=params,
            json_data=data,
            auth=(username, password),
            verify_ssl=verify_ssl,
            timeout=timeout,
        )

        # NetWitness returns 200 for successful operations
        if response.status_code == HTTP_OK:
            # Check content type
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                return response.json()
            return {"text": response.text}
        # For other 2xx codes, return empty
        return {}

    except httpx.TimeoutException as e:
        logger.error("netwitness_api_timeout_for", endpoint=endpoint, error=str(e))
        raise Exception(f"Request timed out after {timeout} seconds")
    except httpx.HTTPStatusError as e:
        logger.error(
            "netwitness_api_http_error_for",
            endpoint=endpoint,
            status_code=e.response.status_code,
        )
        if e.response.status_code == 401:
            raise Exception("Invalid username or password")
        if e.response.status_code == 403:
            raise Exception("Invalid permission")
        if e.response.status_code == 404:
            raise Exception("Resource not found")
        raise Exception(f"HTTP {e.response.status_code}: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(
            "netwitness_api_connection_error_for", endpoint=endpoint, error=str(e)
        )
        raise Exception(f"Connection failed: {e!s}")
    except Exception as e:
        logger.error("netwitness_api_error_for", endpoint=endpoint, error=str(e))
        raise

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for NetWitness Endpoint API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check NetWitness Endpoint API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "healthy": False,
            }

        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Test connectivity by calling health endpoint
            result = await _make_netwitness_request(
                self,
                endpoint=TEST_CONNECTIVITY_ENDPOINT,
                base_url=url,
                username=username,
                password=password,
                method="GET",
                verify_ssl=verify_ssl,
                timeout=timeout,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "NetWitness Endpoint API is accessible",
                "healthy": True,
                "data": result,
            }

        except Exception as e:
            logger.error("netwitness_health_check_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
                "healthy": False,
            }

class BlocklistDomainAction(IntegrationAction):
    """Blocklist a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Blocklist a domain.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with status
        """
        domain = kwargs.get("domain")

        if not domain:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("domain"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            payload = {"Domains": [domain]}

            result = await _make_netwitness_request(
                self,
                endpoint=BLOCKLIST_DOMAIN_ENDPOINT,
                base_url=url,
                username=username,
                password=password,
                method="POST",
                data=payload,
                verify_ssl=verify_ssl,
                timeout=timeout,
            )

            blocked_domain = (
                result.get("Domains", [domain])[0] if result.get("Domains") else domain
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Domain blocklisted successfully",
                "domain": blocked_domain,
            }

        except Exception as e:
            logger.error("blocklist_domain_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class BlocklistIpAction(IntegrationAction):
    """Blocklist an IP address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Blocklist an IP address.

        Args:
            **kwargs: Must contain 'ip'

        Returns:
            Result with status
        """
        ip = kwargs.get("ip")

        if not ip:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("ip"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            payload = {"Ips": [ip]}

            result = await _make_netwitness_request(
                self,
                endpoint=BLOCKLIST_IP_ENDPOINT,
                base_url=url,
                username=username,
                password=password,
                method="POST",
                data=payload,
                verify_ssl=verify_ssl,
                timeout=timeout,
            )

            blocked_ip = result.get("Ips", [ip])[0] if result.get("Ips") else ip

            return {
                "status": STATUS_SUCCESS,
                "message": "IP blocklisted successfully",
                "ip": blocked_ip,
            }

        except Exception as e:
            logger.error("blocklist_ip_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ListEndpointsAction(IntegrationAction):
    """List all Windows endpoints configured on NetWitness Endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List endpoints.

        Args:
            **kwargs: Optional 'limit', 'ioc_score_gte', 'ioc_score_lte'

        Returns:
            Result with endpoints list
        """
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Extract parameters with defaults
        ioc_score_gte = kwargs.get("ioc_score_gte", DEFAULT_IOC_SCORE_GTE)
        ioc_score_lte = kwargs.get("ioc_score_lte", DEFAULT_IOC_SCORE_LTE)
        limit = kwargs.get("limit", DEFAULT_LIMIT)

        # Validate parameters
        if ioc_score_lte > DEFAULT_IOC_SCORE_LTE:
            return {
                "status": STATUS_ERROR,
                "error": "ioc_score_lte must be <= 1024",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if ioc_score_lte < ioc_score_gte:
            return {
                "status": STATUS_ERROR,
                "error": "ioc_score_lte must be >= ioc_score_gte",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        try:
            params = {
                "iocscore_gte": ioc_score_gte,
                "iocscore_lte": ioc_score_lte,
            }

            result = await _make_netwitness_request(
                self,
                endpoint=LIST_MACHINES_ENDPOINT,
                base_url=url,
                username=username,
                password=password,
                method="GET",
                params=params,
                verify_ssl=verify_ssl,
                timeout=timeout,
            )

            machines = result.get("Items", [])

            # Filter Windows machines only
            windows_machines = []
            for machine in machines[:limit]:
                # Get machine details to check OS
                try:
                    machine_detail = await _make_netwitness_request(
                        self,
                        endpoint=GET_SYSTEM_INFO_ENDPOINT.format(machine["Id"]),
                        base_url=url,
                        username=username,
                        password=password,
                        method="GET",
                        verify_ssl=verify_ssl,
                        timeout=timeout,
                    )

                    os = machine_detail.get("Machine", {}).get("OperatingSystem", "")
                    if "Windows" in os:
                        windows_machines.append(machine)

                except Exception as e:
                    logger.warning(
                        "failed_to_get_details_for_machine",
                        Id=machine.get("Id"),
                        error=str(e),
                    )
                    continue

            return {
                "status": STATUS_SUCCESS,
                "endpoints": windows_machines,
                "total_endpoints": len(windows_machines),
            }

        except Exception as e:
            logger.error("list_endpoints_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetSystemInfoAction(IntegrationAction):
    """Get endpoint's information from GUID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get system information.

        Args:
            **kwargs: Must contain 'guid'

        Returns:
            Result with system info
        """
        guid = kwargs.get("guid")

        if not guid:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("guid"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            result = await _make_netwitness_request(
                self,
                endpoint=GET_SYSTEM_INFO_ENDPOINT.format(guid),
                base_url=url,
                username=username,
                password=password,
                method="GET",
                verify_ssl=verify_ssl,
                timeout=timeout,
            )

            machine_info = result.get("Machine", {})

            return {
                "status": STATUS_SUCCESS,
                "guid": guid,
                "machine_name": machine_info.get("MachineName"),
                "iiocscore": machine_info.get("IIOCScore"),
                "data": result,
            }

        except Exception as e:
            logger.error("get_system_info_failed", error=str(e))
            if "not found" in str(e).lower() or "404" in str(e):
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_ENDPOINT_NOT_FOUND,
                    "error_type": ERROR_TYPE_NOT_FOUND,
                }
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ScanEndpointAction(IntegrationAction):
    """Request scan of an endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Scan an endpoint.

        Args:
            **kwargs: Must contain 'guid', optional scan parameters

        Returns:
            Result with scan status
        """
        guid = kwargs.get("guid")

        if not guid:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("guid"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Extract scan parameters with defaults
        cpu_max = kwargs.get("cpu_max", DEFAULT_MAX_CPU_VALUE)
        cpu_max_vm = kwargs.get("cpu_max_vm", DEFAULT_MAX_CPU_VM_VALUE)
        cpu_min = kwargs.get("cpu_min", DEFAULT_MIN_CPU_VALUE)
        scan_category = kwargs.get("scan_category", DEFAULT_SCAN_CATEGORY)

        # Validate CPU parameters
        if cpu_max > 100 or cpu_max_vm > 100 or cpu_min > 100:
            return {
                "status": STATUS_ERROR,
                "error": "CPU values must not exceed 100",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if cpu_max < cpu_min:
            return {
                "status": STATUS_ERROR,
                "error": "cpu_max must be >= cpu_min",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        try:
            payload = {
                "Guid": guid,
                "CpuMax": cpu_max,
                "CpuMaxVm": cpu_max_vm,
                "CpuMin": cpu_min,
                "ScanCategory": SCAN_CATEGORY_MAPPING.get(
                    scan_category, SCAN_CATEGORY_MAPPING["All"]
                ),
            }

            # Add optional parameters
            filter_hooks = kwargs.get("filter_hooks")
            if filter_hooks == "Signed Modules":
                payload["FilterSigned"] = True
            elif filter_hooks == "Whitelisted Certificates":
                payload["FilterTrustedRoot"] = True

            for key, param in [
                ("CaptureFloatingCode", "capture_floating_code"),
                ("AllNetworkConnections", "all_network_connections"),
                ("ResetAgentNetworkCache", "reset_agent_network_cache"),
                ("RetrieveMasterBootRecord", "retrieve_master_boot_record"),
                ("Notify", "notify"),
            ]:
                value = kwargs.get(param)
                if value is not None:
                    payload[key] = value

            result = await _make_netwitness_request(
                self,
                endpoint=SCAN_ENDPOINT.format(guid),
                base_url=url,
                username=username,
                password=password,
                method="POST",
                data=payload,
                verify_ssl=verify_ssl,
                timeout=timeout,
            )

            return {
                "status": STATUS_SUCCESS,
                "message": "Scan initiated successfully",
                "guid": guid,
                "data": result,
            }

        except Exception as e:
            logger.error("scan_endpoint_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetScanDataAction(IntegrationAction):
    """Get scan data of an endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get endpoint scan data.

        Args:
            **kwargs: Must contain 'guid', optional 'limit'

        Returns:
            Result with scan data
        """
        guid = kwargs.get("guid")

        if not guid:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("guid"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        limit = kwargs.get("limit", DEFAULT_LIMIT)

        try:
            scan_data = {}

            # Fetch data for each scan category
            for category in SCAN_DATA_CATEGORIES:
                try:
                    result = await _make_netwitness_request(
                        self,
                        endpoint=GET_SCAN_DATA_ENDPOINT.format(guid, category.lower()),
                        base_url=url,
                        username=username,
                        password=password,
                        method="GET",
                        verify_ssl=verify_ssl,
                        timeout=timeout,
                    )

                    category_data = result.get(category, [])
                    scan_data[category] = category_data[:limit]

                except Exception as e:
                    logger.warning(
                        "failed_to_get_data", category=category, error=str(e)
                    )
                    scan_data[category] = []

            # Calculate summary
            summary = {
                category.lower(): len(data) for category, data in scan_data.items()
            }

            return {
                "status": STATUS_SUCCESS,
                "guid": guid,
                "scan_data": scan_data,
                "summary": summary,
            }

        except Exception as e:
            logger.error("get_scan_data_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ListIocAction(IntegrationAction):
    """List available IOCs."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List IOCs.

        Args:
            **kwargs: Optional filtering parameters

        Returns:
            Result with IOC list
        """
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Extract filter parameters
        machine_count = kwargs.get("machine_count", DEFAULT_MIN_MACHINE_COUNT)
        module_count = kwargs.get("module_count", DEFAULT_MIN_MODULE_COUNT)
        ioc_level = kwargs.get("ioc_level", DEFAULT_IOC_LEVEL)
        limit = kwargs.get("limit", DEFAULT_LIMIT)

        try:
            result = await _make_netwitness_request(
                self,
                endpoint=INSTANTIOC_ENDPOINT,
                base_url=url,
                username=username,
                password=password,
                method="GET",
                verify_ssl=verify_ssl,
                timeout=timeout,
            )

            ioc_list = result.get("iocQueries", [])

            # Filter IOCs
            filtered_iocs = []
            for ioc in ioc_list:
                if (
                    int(ioc.get("IOCLevel", 99)) <= ioc_level
                    and int(ioc.get("MachineCount", 0)) >= machine_count
                    and int(ioc.get("ModuleCount", 0)) >= module_count
                    and ioc.get("Type") == "Windows"
                ):
                    filtered_iocs.append(ioc)

                if limit and len(filtered_iocs) >= limit:
                    break

            return {
                "status": STATUS_SUCCESS,
                "iocs": filtered_iocs,
                "available_iocs": len(filtered_iocs),
            }

        except Exception as e:
            logger.error("list_ioc_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetIocAction(IntegrationAction):
    """Get IOC details."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get IOC details.

        Args:
            **kwargs: Must contain 'name'

        Returns:
            Result with IOC details
        """
        name = kwargs.get("name")

        if not name:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PARAMETER.format("name"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        verify_ssl = self.settings.get(SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            result = await _make_netwitness_request(
                self,
                endpoint=INSTANTIOC_ENDPOINT,
                base_url=url,
                username=username,
                password=password,
                method="GET",
                verify_ssl=verify_ssl,
                timeout=timeout,
            )

            ioc_list = result.get("iocQueries", [])

            # Find matching IOC
            ioc_query = None
            for ioc in ioc_list:
                if (
                    ioc.get("Name", "").lower() == name.lower()
                    and ioc.get("Type", "").lower() == "windows"
                ):
                    ioc_query = ioc
                    break

            if not ioc_query:
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_IOC_NOT_FOUND,
                    "error_type": ERROR_TYPE_NOT_FOUND,
                }

            return {
                "status": STATUS_SUCCESS,
                "name": name,
                "ioc_level": ioc_query.get("IOCLevel"),
                "machine_count": ioc_query.get("MachineCount"),
                "module_count": ioc_query.get("ModuleCount"),
                "ioc_query": ioc_query,
            }

        except Exception as e:
            logger.error("get_ioc_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

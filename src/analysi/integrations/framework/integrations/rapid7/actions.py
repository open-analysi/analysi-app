"""Rapid7 InsightVM vulnerability management integration actions.

Uses ``self.http_request()`` with API key authentication (``X-Api-Key``
header) against the Rapid7 InsightVM REST API v3.

Actions:
    - health_check: Verify API connectivity
    - get_asset: Get asset details by ID
    - search_assets: Search assets by IP, hostname, or filters
    - get_vulnerabilities: Get vulnerabilities for an asset
    - get_vulnerability: Get details for a specific vulnerability by ID
    - list_scans: List recent vulnerability scans
    - get_scan: Get scan details/results
"""

import json
from typing import Any

import httpx

from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.rapid7.constants import (
    CREDENTIAL_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT,
    ENDPOINT_ADMINISTRATION_INFO,
    ENDPOINT_ASSET_VULNERABILITIES,
    ENDPOINT_ASSETS,
    ENDPOINT_ASSETS_SEARCH,
    ENDPOINT_SCAN,
    ENDPOINT_SCANS,
    ENDPOINT_VULNERABILITIES,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MSG_MISSING_API_KEY,
    MSG_MISSING_ASSET_ID,
    MSG_MISSING_QUERY,
    MSG_MISSING_SCAN_ID,
    MSG_MISSING_VULNERABILITY_ID,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
    VALID_MATCH_OPERATORS,
)

# ============================================================================
# VALIDATION UTILITIES
# ============================================================================

def _validate_positive_integer(
    value: Any, field_name: str
) -> tuple[bool, int | None, str]:
    """Validate that a value is a positive integer.

    Args:
        value: Value to validate
        field_name: Name of the field for error messages

    Returns:
        Tuple of (is_valid, parsed_int, error_message)
    """
    if value is None:
        return False, None, f"Missing required parameter: {field_name}"

    try:
        int_value = int(value)
    except (ValueError, TypeError):
        return False, None, f"{field_name} must be a positive integer"

    if int_value <= 0:
        return False, None, f"{field_name} must be a positive integer"

    return True, int_value, ""

# ============================================================================
# PAGINATION HELPER
# ============================================================================

async def _paginate_rapid7(
    action: IntegrationAction,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
    method: str = "GET",
    json_data: dict | None = None,
    max_results: int | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """Paginate through Rapid7 API results.

    The Rapid7 API uses page-based pagination with 'page' and 'size' params.
    Results are in the 'resources' key of the response.

    Args:
        action: IntegrationAction instance (for self.http_request)
        url: Full URL to request
        headers: Request headers
        params: Query parameters
        method: HTTP method
        json_data: JSON request body (for POST search)
        max_results: Maximum number of results to return
        timeout: Request timeout

    Returns:
        List of all resources across pages
    """
    all_resources: list[dict] = []
    page = 0
    params = dict(params) if params else {}
    params["size"] = DEFAULT_PAGE_SIZE
    params["page"] = page

    while True:
        if method.upper() == "POST":
            response = await action.http_request(
                url,
                method="POST",
                headers=headers,
                params=params,
                json_data=json_data,
                timeout=timeout,
            )
        else:
            response = await action.http_request(
                url,
                method="GET",
                headers=headers,
                params=params,
                timeout=timeout,
            )

        data = response.json()
        resources = data.get("resources", [])
        all_resources.extend(resources)

        # Check if we have enough results
        if max_results and len(all_resources) >= max_results:
            return all_resources[:max_results]

        # Check if there are more pages
        if len(resources) < DEFAULT_PAGE_SIZE:
            break

        page_info = data.get("page", {})
        total_resources = page_info.get("totalResources", 0)
        if len(all_resources) >= total_resources:
            break

        page += 1
        params["page"] = page

    return all_resources

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Rapid7 InsightVM API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Rapid7 InsightVM API connectivity.

        Calls the administration/info endpoint to verify credentials and
        connectivity, matching the upstream test_connectivity action.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY,
                error_type=ERROR_TYPE_CONFIGURATION,
                healthy=False,
                data={"healthy": False},
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        url = f"{base_url}{ENDPOINT_ADMINISTRATION_INFO}"

        try:
            response = await self.http_request(
                url,
                headers={"X-Api-Key": api_key},
                timeout=timeout,
            )
            result = response.json()

            version = result.get("version", {}).get("semantic", "Unknown")

            return self.success_result(
                data={
                    "healthy": True,
                    "version": version,
                    "base_url": base_url,
                },
                healthy=True,
                message=f"Rapid7 InsightVM API is accessible (version {version})",
            )

        except Exception as e:
            self.log_error("rapid7_health_check_failed", error=e)
            return self.error_result(e, healthy=False, data={"healthy": False})

class GetAssetAction(IntegrationAction):
    """Get asset details by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get asset details from Rapid7 InsightVM by asset ID.

        Args:
            **kwargs: Must contain 'asset_id' (integer)

        Returns:
            Result with asset data or error
        """
        # Validate asset_id
        is_valid, asset_id, error_msg = _validate_positive_integer(
            kwargs.get("asset_id"), "asset_id"
        )
        if not is_valid:
            return self.error_result(
                error_msg or MSG_MISSING_ASSET_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        url = f"{base_url}{ENDPOINT_ASSETS}/{asset_id}"

        try:
            response = await self.http_request(
                url,
                headers={"X-Api-Key": api_key},
                timeout=timeout,
            )
            asset_data = response.json()

            return self.success_result(data={"asset_id": asset_id, **asset_data})

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("rapid7_asset_not_found", asset_id=asset_id)
                return self.success_result(
                    not_found=True,
                    data={"asset_id": asset_id},
                )
            self.log_error("rapid7_get_asset_failed", error=e, asset_id=asset_id)
            return self.error_result(e)
        except Exception as e:
            self.log_error("rapid7_get_asset_failed", error=e, asset_id=asset_id)
            return self.error_result(e)

class SearchAssetsAction(IntegrationAction):
    """Search assets by IP, hostname, or custom filters."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search for assets in Rapid7 InsightVM.

        Supports searching by IP address, hostname, or custom filters JSON.
        When ip or hostname is provided, constructs the appropriate filter.
        When filters is provided, it is used directly (must be a JSON array).

        Mirrors the upstream find_assets action which uses POST /assets/search.

        Args:
            **kwargs: At least one of:
                - ip: IP address to search for
                - hostname: Hostname to search for
                - filters: JSON string of filter objects
                - match: Filter match operator ('all' or 'any', default 'all')

        Returns:
            Result with matched assets or error
        """
        ip = kwargs.get("ip")
        hostname = kwargs.get("hostname")
        filters_raw = kwargs.get("filters")
        match = kwargs.get("match", "all")

        # Build filters from convenience parameters
        filters = []
        if ip:
            filters.append({"field": "ip-address", "operator": "is", "value": ip})
        if hostname:
            filters.append(
                {"field": "host-name", "operator": "contains", "value": hostname}
            )

        # Parse custom filters JSON if provided
        if filters_raw:
            if isinstance(filters_raw, str):
                try:
                    parsed = json.loads(filters_raw)
                    if isinstance(parsed, list):
                        filters.extend(parsed)
                    else:
                        return self.error_result(
                            "filters must be a JSON array of filter objects",
                            error_type=ERROR_TYPE_VALIDATION,
                        )
                except json.JSONDecodeError as e:
                    return self.error_result(
                        f"Invalid filters JSON: {e}",
                        error_type=ERROR_TYPE_VALIDATION,
                    )
            elif isinstance(filters_raw, list):
                filters.extend(filters_raw)

        if not filters:
            return self.error_result(
                MSG_MISSING_QUERY,
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Validate match operator
        if match not in VALID_MATCH_OPERATORS:
            return self.error_result(
                f"match must be one of {VALID_MATCH_OPERATORS}",
                error_type=ERROR_TYPE_VALIDATION,
            )

        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        url = f"{base_url}{ENDPOINT_ASSETS_SEARCH}"
        payload = {"filters": filters, "match": match}

        try:
            assets = await _paginate_rapid7(
                action=self,
                url=url,
                headers={"X-Api-Key": api_key},
                method="POST",
                json_data=payload,
                timeout=timeout,
            )

            return self.success_result(
                data={"assets": assets, "num_assets": len(assets)},
            )

        except Exception as e:
            self.log_error("rapid7_search_assets_failed", error=e)
            return self.error_result(e)

class GetVulnerabilitiesAction(IntegrationAction):
    """Get vulnerabilities for an asset."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve all vulnerability findings on an asset.

        Mirrors the upstream get_asset_vulnerabilities action which calls
        GET /assets/{id}/vulnerabilities with pagination.

        Args:
            **kwargs: Must contain 'asset_id' (integer)

        Returns:
            Result with vulnerability list or error
        """
        is_valid, asset_id, error_msg = _validate_positive_integer(
            kwargs.get("asset_id"), "asset_id"
        )
        if not is_valid:
            return self.error_result(
                error_msg or MSG_MISSING_ASSET_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        url = f"{base_url}{ENDPOINT_ASSET_VULNERABILITIES.format(asset_id=asset_id)}"

        try:
            vulnerabilities = await _paginate_rapid7(
                action=self,
                url=url,
                headers={"X-Api-Key": api_key},
                timeout=timeout,
            )

            return self.success_result(
                data={
                    "asset_id": asset_id,
                    "vulnerabilities": vulnerabilities,
                    "num_vulnerabilities": len(vulnerabilities),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "rapid7_asset_not_found_for_vulnerabilities",
                    asset_id=asset_id,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "asset_id": asset_id,
                        "vulnerabilities": [],
                        "num_vulnerabilities": 0,
                    },
                )
            self.log_error(
                "rapid7_get_vulnerabilities_failed", error=e, asset_id=asset_id
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error(
                "rapid7_get_vulnerabilities_failed", error=e, asset_id=asset_id
            )
            return self.error_result(e)

class GetVulnerabilityAction(IntegrationAction):
    """Get details for a specific vulnerability by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get detailed information about a specific vulnerability.

        Calls GET /vulnerabilities/{id} for a single vulnerability record.

        Args:
            **kwargs: Must contain 'vulnerability_id' (string, e.g. 'CVE-2021-44228')

        Returns:
            Result with vulnerability details or error
        """
        vulnerability_id = kwargs.get("vulnerability_id")
        if not vulnerability_id:
            return self.error_result(
                MSG_MISSING_VULNERABILITY_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        url = f"{base_url}{ENDPOINT_VULNERABILITIES.format(vulnerability_id=vulnerability_id)}"

        try:
            response = await self.http_request(
                url,
                headers={"X-Api-Key": api_key},
                timeout=timeout,
            )
            vuln_data = response.json()

            return self.success_result(
                data={"vulnerability_id": vulnerability_id, **vuln_data},
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "rapid7_vulnerability_not_found",
                    vulnerability_id=vulnerability_id,
                )
                return self.success_result(
                    not_found=True,
                    data={"vulnerability_id": vulnerability_id},
                )
            self.log_error(
                "rapid7_get_vulnerability_failed",
                error=e,
                vulnerability_id=vulnerability_id,
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error(
                "rapid7_get_vulnerability_failed",
                error=e,
                vulnerability_id=vulnerability_id,
            )
            return self.error_result(e)

class ListScansAction(IntegrationAction):
    """List recent vulnerability scans."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List vulnerability scans from Rapid7 InsightVM.

        Returns paginated list of scans. Optionally filter by status.

        Args:
            **kwargs: Optional:
                - status: Filter scans by status (e.g. 'finished', 'running')
                - limit: Maximum number of scans to return

        Returns:
            Result with list of scans or error
        """
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        url = f"{base_url}{ENDPOINT_SCANS}"

        status_filter = kwargs.get("status")
        limit = kwargs.get("limit")

        # Validate limit if provided
        if limit is not None:
            is_valid, limit, error_msg = _validate_positive_integer(limit, "limit")
            if not is_valid:
                return self.error_result(
                    error_msg,
                    error_type=ERROR_TYPE_VALIDATION,
                )

        params: dict[str, Any] = {}
        if status_filter:
            params["active"] = str(status_filter == "running").lower()

        try:
            scans = await _paginate_rapid7(
                action=self,
                url=url,
                headers={"X-Api-Key": api_key},
                params=params,
                max_results=limit,
                timeout=timeout,
            )

            return self.success_result(
                data={"scans": scans, "num_scans": len(scans)},
            )

        except Exception as e:
            self.log_error("rapid7_list_scans_failed", error=e)
            return self.error_result(e)

class GetScanAction(IntegrationAction):
    """Get scan details/results by scan ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get details for a specific scan.

        Args:
            **kwargs: Must contain 'scan_id' (integer)

        Returns:
            Result with scan details or error
        """
        is_valid, scan_id, error_msg = _validate_positive_integer(
            kwargs.get("scan_id"), "scan_id"
        )
        if not is_valid:
            return self.error_result(
                error_msg or MSG_MISSING_SCAN_ID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        url = f"{base_url}{ENDPOINT_SCAN.format(scan_id=scan_id)}"

        try:
            response = await self.http_request(
                url,
                headers={"X-Api-Key": api_key},
                timeout=timeout,
            )
            scan_data = response.json()

            return self.success_result(
                data={"scan_id": scan_id, **scan_data},
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("rapid7_scan_not_found", scan_id=scan_id)
                return self.success_result(
                    not_found=True,
                    data={"scan_id": scan_id},
                )
            self.log_error("rapid7_get_scan_failed", error=e, scan_id=scan_id)
            return self.error_result(e)
        except Exception as e:
            self.log_error("rapid7_get_scan_failed", error=e, scan_id=scan_id)
            return self.error_result(e)

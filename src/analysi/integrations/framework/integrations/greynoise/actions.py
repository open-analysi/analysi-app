"""GreyNoise integration actions for IP noise and threat intelligence.
Library type: REST API (the upstream connector uses the ``greynoise`` Python SDK via ``requests``;
Naxos uses ``self.http_request()`` for direct REST API calls).

GreyNoise tells analysts whether an IP is mass-scanning the internet (noise)
versus a targeted attack. The API requires an API key via the ``key`` header.

Endpoints used (GreyNoise API v3):
- GET  /v3/community/{ip}         -- quick community lookup (single IP)
- POST /v3/noise/multi/quick      -- multi-IP quick check
- GET  /v3/noise/context/{ip}     -- full IP context / reputation
- POST /v3/queries/scroll         -- GNQL paginated query
- GET  /v3/noise/ips/{ip}/timeline/{field} -- IP timeline
- GET  /v3/cve/{cve_id}           -- CVE details
- GET  /ping                      -- connectivity test
"""

import ipaddress
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    AUTH_HEADER,
    DEFAULT_BASE_URL,
    DEFAULT_GNQL_QUERY_SIZE,
    DEFAULT_TIMEOUT,
    MAX_GNQL_PAGE_SIZE,
    MSG_INTERNAL_IP,
    MSG_INVALID_FIELD,
    MSG_INVALID_INTEGER,
    MSG_INVALID_IP,
    MSG_MISSING_API_KEY,
    MSG_MISSING_PARAM,
    TIMELINE_FIELD_VALUES,
    TRUST_LEVELS,
    VISUALIZATION_URL,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_ip(ip: str) -> tuple[bool, str | None]:
    """Validate an IP address string. Returns (is_valid, error_message)."""
    ip_input = ip.split("%")[0] if "%" in ip else ip
    try:
        addr = ipaddress.ip_address(ip_input)
    except ValueError:
        return False, MSG_INVALID_IP.format(ip=ip)
    if addr.is_private:
        return False, MSG_INTERNAL_IP
    return True, None

def _enrich_trust_level(data: dict[str, Any]) -> None:
    """Add human-readable trust_level to a result dict (mutates in place)."""
    bsi = data.get("business_service_intelligence", {})
    raw_level = bsi.get("trust_level", "")
    if raw_level:
        data["trust_level"] = TRUST_LEVELS.get(str(raw_level), str(raw_level))

def _add_visualization(data: dict[str, Any]) -> None:
    """Add viz.greynoise.io link for the IP (mutates in place)."""
    ip = data.get("ip")
    if ip:
        data["visualization"] = VISUALIZATION_URL.format(ip=ip)

# ---------------------------------------------------------------------------
# Base class with shared auth / URL helpers
# ---------------------------------------------------------------------------

class _GreyNoiseBase(IntegrationAction):
    """Shared helpers for all GreyNoise actions."""

    def get_http_headers(self) -> dict[str, str]:
        """Inject the API key into every outbound request."""
        api_key = self.credentials.get("api_key", "")
        return {AUTH_HEADER: api_key} if api_key else {}

    def get_timeout(self) -> int | float:
        """Return timeout, defaulting to GreyNoise-specific value."""
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        return self.settings.get("base_url", DEFAULT_BASE_URL).rstrip("/")

    def _require_api_key(self) -> dict[str, Any] | None:
        """Return an error_result if api_key is missing, else None."""
        if not self.credentials.get("api_key"):
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )
        return None

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(_GreyNoiseBase):
    """Verify connectivity to GreyNoise API and validate API key."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_key():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/ping",
            )
            ping_data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Connectivity and credentials test passed",
                    "ping": ping_data,
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("greynoise_health_check_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("greynoise_health_check_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LOOKUP IP (Quick Check - single IP)
# ============================================================================

class LookupIpAction(_GreyNoiseBase):
    """Quick check a single IP via the multi quick-check endpoint.

    Uses the same multi-quick endpoint as the upstream ``lookup_ip`` action,
    which calls ``GreyNoise.quick(ip)`` under the hood.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ip"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        valid, error_msg = _validate_ip(ip)
        if not valid:
            return self.error_result(error_msg, error_type="ValidationError")

        try:
            response = await self.http_request(
                url=f"{self.base_url}/v3/noise/multi/quick",
                method="POST",
                json_data={"ips": [ip]},
            )
            results = response.json()

            # Enrich each result
            if isinstance(results, list):
                for item in results:
                    _enrich_trust_level(item)
                    _add_visualization(item)

            return self.success_result(data=results)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("greynoise_lookup_ip_not_found", ip=ip)
                return self.success_result(
                    not_found=True,
                    data={"ip": ip},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("greynoise_lookup_ip_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LOOKUP IPS (Multi Quick Check - comma-separated)
# ============================================================================

class LookupIpsAction(_GreyNoiseBase):
    """Quick check multiple IPs (comma-separated, limit 500 per request)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ips_raw = kwargs.get("ips")
        if not ips_raw:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ips"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        # Parse and validate comma-separated IPs
        ip_list = [ip.strip() for ip in str(ips_raw).split(",") if ip.strip()]
        if not ip_list:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ips"),
                error_type="ValidationError",
            )

        for ip in ip_list:
            valid, error_msg = _validate_ip(ip)
            if not valid:
                return self.error_result(error_msg, error_type="ValidationError")

        try:
            response = await self.http_request(
                url=f"{self.base_url}/v3/noise/multi/quick",
                method="POST",
                json_data={"ips": ip_list},
            )
            results = response.json()

            if isinstance(results, list):
                for item in results:
                    _enrich_trust_level(item)
                    _add_visualization(item)

            return self.success_result(data=results)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("greynoise_lookup_ips_failed", error=e)
            return self.error_result(e)

# ============================================================================
# IP REPUTATION (Full Context)
# ============================================================================

class IpReputationAction(_GreyNoiseBase):
    """Get full GreyNoise reputation and context for a specific IP.

    Returns time ranges, IP metadata (network owner, ASN, rDNS, country),
    associated actors, activity tags, raw port scan, and web request information.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ip"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        valid, error_msg = _validate_ip(ip)
        if not valid:
            return self.error_result(error_msg, error_type="ValidationError")

        try:
            response = await self.http_request(
                url=f"{self.base_url}/v3/noise/context/{ip}",
            )
            result_data = response.json()

            # Enrich result (matching upstream logic)
            _add_visualization(result_data)
            _enrich_trust_level(result_data)

            # Determine if IP is unseen (neither BSI nor ISI found)
            bsi_found = result_data.get("business_service_intelligence", {}).get(
                "found", False
            )
            isi_found = result_data.get("internet_scanner_intelligence", {}).get(
                "found", False
            )
            result_data["unseen_rep"] = not (bsi_found or isi_found)

            return self.success_result(data=result_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("greynoise_ip_reputation_not_found", ip=ip)
                return self.success_result(
                    not_found=True,
                    data={
                        "ip": ip,
                        "unseen_rep": True,
                        "business_service_intelligence": {"found": False},
                        "internet_scanner_intelligence": {"found": False},
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("greynoise_ip_reputation_failed", error=e)
            return self.error_result(e)

# ============================================================================
# GNQL QUERY
# ============================================================================

class GnqlQueryAction(_GreyNoiseBase):
    """Run a GreyNoise Query Language (GNQL) query with pagination."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="query"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        # Validate size parameter
        size = kwargs.get("size", DEFAULT_GNQL_QUERY_SIZE)
        try:
            size = int(size)
            if size < 1:
                raise ValueError
        except (ValueError, TypeError):
            return self.error_result(
                MSG_INVALID_INTEGER.format(key="size"),
                error_type="ValidationError",
            )

        exclude_raw = kwargs.get("exclude_raw", False)
        quick = kwargs.get("quick", False)

        try:
            result = await self._paginated_query(query, size, exclude_raw, quick)

            # Enrich results
            for ip_info in result.get("data", []):
                _enrich_trust_level(ip_info)
                _add_visualization(ip_info)

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("greynoise_gnql_query_failed", error=e)
            return self.error_result(e)

    async def _paginated_query(
        self,
        query: str,
        size: int,
        exclude_raw: bool = False,
        quick: bool = False,
    ) -> dict[str, Any]:
        """Fetch paginated GNQL query results."""
        all_data: list[dict[str, Any]] = []
        remaining = size
        scroll: str | None = None

        while remaining > 0:
            page_size = min(MAX_GNQL_PAGE_SIZE, remaining)

            payload: dict[str, Any] = {
                "query": query,
                "size": page_size,
            }
            if exclude_raw:
                payload["exclude_raw"] = True
            if quick:
                payload["quick"] = True
            if scroll:
                payload["scroll"] = scroll

            response = await self.http_request(
                url=f"{self.base_url}/v3/queries/scroll",
                method="POST",
                json_data=payload,
            )
            api_response = response.json()

            current_data = api_response.get("data", [])
            request_metadata = api_response.get("request_metadata", {})

            if request_metadata.get("count", 0) == 0:
                break

            all_data.extend(current_data)
            remaining -= len(current_data)

            scroll = request_metadata.get("scroll")
            if not scroll:
                break

        return {"data": all_data}

# ============================================================================
# IP TIMELINE
# ============================================================================

class LookupIpTimelineAction(_GreyNoiseBase):
    """Get historical timeline data for an IP filtered by a specific field."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ip"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        field = kwargs.get("field", "classification")
        if field not in TIMELINE_FIELD_VALUES:
            return self.error_result(
                MSG_INVALID_FIELD.format(valid=", ".join(TIMELINE_FIELD_VALUES)),
                error_type="ValidationError",
            )

        days = kwargs.get("days", 30)
        try:
            days = int(days)
            if days < 0:
                raise ValueError
        except (ValueError, TypeError):
            return self.error_result(
                MSG_INVALID_INTEGER.format(key="days"),
                error_type="ValidationError",
            )

        granularity = kwargs.get("granularity", "1d")

        try:
            response = await self.http_request(
                url=f"{self.base_url}/v3/noise/ips/{ip}/timeline/{field}",
                params={"days": days, "granularity": granularity},
            )
            result_data = response.json()

            return self.success_result(data=result_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("greynoise_ip_timeline_not_found", ip=ip)
                return self.success_result(
                    not_found=True,
                    data={"ip": ip, "field": field, "results": []},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("greynoise_ip_timeline_failed", error=e)
            return self.error_result(e)

# ============================================================================
# CVE DETAILS
# ============================================================================

class GetCveDetailsAction(_GreyNoiseBase):
    """Retrieve details about a specific CVE from GreyNoise."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        cve_id = kwargs.get("cve_id")
        if not cve_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="cve_id"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/v3/cve/{cve_id}",
            )
            result_data = response.json()

            return self.success_result(data=result_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("greynoise_cve_not_found", cve_id=cve_id)
                return self.success_result(
                    not_found=True,
                    data={"id": cve_id},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("greynoise_cve_details_failed", error=e)
            return self.error_result(e)

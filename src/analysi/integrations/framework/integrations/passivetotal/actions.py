"""PassiveTotal (RiskIQ) integration actions for infrastructure intelligence.
Library type: REST API (the upstream connector uses ``requests``; Naxos uses ``self.http_request()``).

PassiveTotal v2 API uses HTTP Basic Auth with username (email) and API key.
All endpoints are under ``https://api.riskiq.net/pt/v2``.
"""

import asyncio
import ipaddress
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    DEFAULT_BASE_URL,
    DEFAULT_PASSIVE_LOOKBACK_DAYS,
    DEFAULT_TIMEOUT,
    HOST_PAIR_DIRECTIONS,
    MSG_DATE_RANGE,
    MSG_INVALID_DATE,
    MSG_INVALID_DIRECTION,
    MSG_INVALID_FIELD,
    MSG_INVALID_IP,
    MSG_INVALID_PAGE,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAM,
    SSL_CERTIFICATE_SEARCH_FIELDS,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_ip(ip_str: str) -> bool:
    """Return True if the string is a valid IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False

def _is_valid_date(date_str: str) -> bool:
    """Return True if date_str is in YYYY-MM-DD format."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        return True
    except ValueError:
        return False

def _validate_date_range(from_date: str | None, to_date: str | None) -> str | None:
    """Validate optional from/to date parameters.

    Returns an error message string if invalid, or None if valid.
    """
    if from_date and not _is_valid_date(from_date):
        return MSG_INVALID_DATE.format(param="from")
    if to_date and not _is_valid_date(to_date):
        return MSG_INVALID_DATE.format(param="to")
    if from_date and to_date:
        f = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=UTC)
        t = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=UTC)
        if f > t:
            return MSG_DATE_RANGE
    return None

# ---------------------------------------------------------------------------
# Base class with shared auth
# ---------------------------------------------------------------------------

class _PassiveTotalBase(IntegrationAction):
    """Shared helpers for all PassiveTotal actions.

    PassiveTotal authenticates via HTTP Basic Auth (username, api_key).
    """

    def get_timeout(self) -> int | float:
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        return self.settings.get("base_url", DEFAULT_BASE_URL).rstrip("/")

    @property
    def _auth(self) -> tuple[str, str] | None:
        """Return (username, api_key) tuple for HTTP Basic Auth, or None."""
        username = self.credentials.get("username")
        api_key = self.credentials.get("api_key")
        if username and api_key:
            return (username, api_key)
        return None

    def _require_credentials(self) -> dict[str, Any] | None:
        """Return an error_result if credentials are missing, else None."""
        if not self._auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )
        return None

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(_PassiveTotalBase):
    """Verify connectivity to the PassiveTotal API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_credentials():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/enrichment",
                params={"query": "passivetotal.org"},
                auth=self._auth,
            )
            data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Connectivity test passed",
                    "query_value": data.get("queryValue", ""),
                },
            )
        except Exception as e:
            self.log_error("passivetotal_health_check_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# LOOKUP DOMAIN
# ============================================================================

class LookupDomainAction(_PassiveTotalBase):
    """Get domain enrichment: metadata, passive DNS, classification, tags."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="domain"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        from_date = kwargs.get("from")
        to_date = kwargs.get("to")
        if date_err := _validate_date_range(from_date, to_date):
            return self.error_result(date_err, error_type="ValidationError")

        try:
            result = await self._gather_enrichment(domain, from_date, to_date)
            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("passivetotal_lookup_domain_not_found", domain=domain)
                return self.success_result(not_found=True, data={"domain": domain})
            return self.error_result(e)
        except Exception as e:
            self.log_error("passivetotal_lookup_domain_failed", error=str(e))
            return self.error_result(e)

    async def _gather_enrichment(
        self, query: str, from_date: str | None, to_date: str | None
    ) -> dict[str, Any]:
        """Gather multiple enrichment data points for a domain."""
        result: dict[str, Any] = {"query": query}

        # Build passive DNS params
        passive_params: dict[str, str] = {"query": query}
        if from_date:
            passive_params["start"] = from_date
        else:
            lookback = datetime.now(tz=UTC) - timedelta(
                days=DEFAULT_PASSIVE_LOOKBACK_DAYS
            )
            passive_params["start"] = lookback.strftime("%Y-%m-%d")
        if to_date:
            passive_params["end"] = to_date

        # All three calls are independent — run in parallel
        meta_resp, passive_resp, class_resp = await asyncio.gather(
            self.http_request(
                url=f"{self.base_url}/enrichment",
                params={"query": query},
                auth=self._auth,
            ),
            self.http_request(
                url=f"{self.base_url}/dns/passive",
                params=passive_params,
                auth=self._auth,
            ),
            self.http_request(
                url=f"{self.base_url}/actions/classification",
                params={"query": query},
                auth=self._auth,
            ),
        )

        result["metadata"] = meta_resp.json()
        result["passive"] = passive_resp.json()
        result["classification"] = class_resp.json()
        return result

# ============================================================================
# LOOKUP IP
# ============================================================================

class LookupIpAction(_PassiveTotalBase):
    """Get IP enrichment: metadata, passive DNS, classification, SSL certs."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ip"),
                error_type="ValidationError",
            )
        if not _is_valid_ip(ip):
            return self.error_result(MSG_INVALID_IP, error_type="ValidationError")
        if err := self._require_credentials():
            return err

        from_date = kwargs.get("from")
        to_date = kwargs.get("to")
        if date_err := _validate_date_range(from_date, to_date):
            return self.error_result(date_err, error_type="ValidationError")

        try:
            result = await self._gather_ip_enrichment(ip, from_date, to_date)
            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("passivetotal_lookup_ip_not_found", ip=ip)
                return self.success_result(not_found=True, data={"ip": ip})
            return self.error_result(e)
        except Exception as e:
            self.log_error("passivetotal_lookup_ip_failed", error=str(e))
            return self.error_result(e)

    async def _gather_ip_enrichment(
        self, ip: str, from_date: str | None, to_date: str | None
    ) -> dict[str, Any]:
        """Gather enrichment data for an IP address."""
        result: dict[str, Any] = {"query": ip}

        # Build passive DNS params
        passive_params: dict[str, str] = {"query": ip}
        if from_date:
            passive_params["start"] = from_date
        else:
            lookback = datetime.now(tz=UTC) - timedelta(
                days=DEFAULT_PASSIVE_LOOKBACK_DAYS
            )
            passive_params["start"] = lookback.strftime("%Y-%m-%d")
        if to_date:
            passive_params["end"] = to_date

        # All four calls are independent — run in parallel
        meta_resp, passive_resp, class_resp, ssl_resp = await asyncio.gather(
            self.http_request(
                url=f"{self.base_url}/enrichment",
                params={"query": ip},
                auth=self._auth,
            ),
            self.http_request(
                url=f"{self.base_url}/dns/passive",
                params=passive_params,
                auth=self._auth,
            ),
            self.http_request(
                url=f"{self.base_url}/actions/classification",
                params={"query": ip},
                auth=self._auth,
            ),
            self.http_request(
                url=f"{self.base_url}/ssl-certificate/history",
                params={"query": ip},
                auth=self._auth,
            ),
        )

        result["metadata"] = meta_resp.json()
        result["passive"] = passive_resp.json()
        result["classification"] = class_resp.json()

        ssl_data = ssl_resp.json()
        ssl_results = ssl_data.get("results", [])
        if ssl_results:
            result["ssl_certificates"] = ssl_results

        return result

# ============================================================================
# WHOIS IP
# ============================================================================

class WhoisIpAction(_PassiveTotalBase):
    """Get WHOIS registration data for an IP address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ip"),
                error_type="ValidationError",
            )
        if not _is_valid_ip(ip):
            return self.error_result(MSG_INVALID_IP, error_type="ValidationError")
        if err := self._require_credentials():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/whois",
                params={"query": ip},
                auth=self._auth,
            )
            data = response.json()

            if not data:
                return self.success_result(
                    data={"ip": ip, "message": "No registrant info found"},
                )

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("passivetotal_whois_ip_not_found", ip=ip)
                return self.success_result(not_found=True, data={"ip": ip})
            return self.error_result(e)
        except Exception as e:
            self.log_error("passivetotal_whois_ip_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# WHOIS DOMAIN
# ============================================================================

class WhoisDomainAction(_PassiveTotalBase):
    """Get WHOIS registration data for a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="domain"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/whois",
                params={"query": domain},
                auth=self._auth,
            )
            data = response.json()

            if not data:
                return self.success_result(
                    data={"domain": domain, "message": "No registrant info found"},
                )

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("passivetotal_whois_domain_not_found", domain=domain)
                return self.success_result(not_found=True, data={"domain": domain})
            return self.error_result(e)
        except Exception as e:
            self.log_error("passivetotal_whois_domain_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# LOOKUP CERTIFICATE HASH
# ============================================================================

class LookupCertificateHashAction(_PassiveTotalBase):
    """Look up SSL certificate details and history by SHA-1 hash."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="query"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            result: dict[str, Any] = {"query": query}

            # Both calls are independent — run in parallel
            cert_resp, hist_resp = await asyncio.gather(
                self.http_request(
                    url=f"{self.base_url}/ssl-certificate",
                    params={"query": query},
                    auth=self._auth,
                ),
                self.http_request(
                    url=f"{self.base_url}/ssl-certificate/history",
                    params={"query": query},
                    auth=self._auth,
                ),
            )

            cert_data = cert_resp.json()
            cert_results = cert_data.get("results", [])
            result["ssl_certificate"] = cert_results

            hist_data = hist_resp.json()
            hist_results = hist_data.get("results", [])
            result["ssl_certificate_history"] = hist_results

            result["total_records"] = len(cert_results)

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("passivetotal_lookup_cert_hash_not_found", query=query)
                return self.success_result(not_found=True, data={"query": query})
            return self.error_result(e)
        except Exception as e:
            self.log_error("passivetotal_lookup_cert_hash_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# LOOKUP CERTIFICATE (SEARCH)
# ============================================================================

class LookupCertificateAction(_PassiveTotalBase):
    """Search SSL certificates by a specific field value."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="query"),
                error_type="ValidationError",
            )
        field = kwargs.get("field")
        if not field:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="field"),
                error_type="ValidationError",
            )
        if field not in SSL_CERTIFICATE_SEARCH_FIELDS:
            return self.error_result(
                MSG_INVALID_FIELD.format(
                    fields=", ".join(SSL_CERTIFICATE_SEARCH_FIELDS[:5]) + ", ..."
                ),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/ssl-certificate/search",
                params={"query": query, "field": field},
                auth=self._auth,
            )
            data = response.json()
            results = data.get("results", [])

            return self.success_result(
                data={
                    "query": query,
                    "field": field,
                    "ssl_certificates": results,
                    "total_records": len(results),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("passivetotal_lookup_cert_not_found", query=query)
                return self.success_result(
                    not_found=True, data={"query": query, "field": field}
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("passivetotal_lookup_cert_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# GET HOST COMPONENTS
# ============================================================================

class GetHostComponentsAction(_PassiveTotalBase):
    """Retrieve host attribute components (web frameworks, servers, etc.)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="query"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        from_date = kwargs.get("from")
        to_date = kwargs.get("to")
        if date_err := _validate_date_range(from_date, to_date):
            return self.error_result(date_err, error_type="ValidationError")

        # Validate page parameter
        raw_page = kwargs.get("page", 0)
        try:
            page = int(raw_page)
            if page < 0:
                return self.error_result(MSG_INVALID_PAGE, error_type="ValidationError")
        except (ValueError, TypeError):
            return self.error_result(MSG_INVALID_PAGE, error_type="ValidationError")

        try:
            params: dict[str, Any] = {"query": query, "page": page}
            if from_date:
                params["start"] = from_date
            if to_date:
                params["end"] = to_date

            response = await self.http_request(
                url=f"{self.base_url}/host-attributes/components",
                params=params,
                auth=self._auth,
            )
            data = response.json()

            return self.success_result(
                data={
                    "query": query,
                    "components": data.get("results", []),
                    "total_records": data.get("totalRecords", 0),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("passivetotal_host_components_not_found", query=query)
                return self.success_result(not_found=True, data={"query": query})
            return self.error_result(e)
        except Exception as e:
            self.log_error("passivetotal_host_components_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# GET HOST PAIRS
# ============================================================================

class GetHostPairsAction(_PassiveTotalBase):
    """Retrieve host attribute pairs (parent/child relationships)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="query"),
                error_type="ValidationError",
            )
        direction = kwargs.get("direction")
        if not direction:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="direction"),
                error_type="ValidationError",
            )
        if direction not in HOST_PAIR_DIRECTIONS:
            return self.error_result(
                MSG_INVALID_DIRECTION, error_type="ValidationError"
            )
        if err := self._require_credentials():
            return err

        from_date = kwargs.get("from")
        to_date = kwargs.get("to")
        if date_err := _validate_date_range(from_date, to_date):
            return self.error_result(date_err, error_type="ValidationError")

        raw_page = kwargs.get("page", 0)
        try:
            page = int(raw_page)
            if page < 0:
                return self.error_result(MSG_INVALID_PAGE, error_type="ValidationError")
        except (ValueError, TypeError):
            return self.error_result(MSG_INVALID_PAGE, error_type="ValidationError")

        try:
            params: dict[str, Any] = {
                "query": query,
                "direction": direction,
                "page": page,
            }
            if from_date:
                params["start"] = from_date
            if to_date:
                params["end"] = to_date

            response = await self.http_request(
                url=f"{self.base_url}/host-attributes/pairs",
                params=params,
                auth=self._auth,
            )
            data = response.json()

            return self.success_result(
                data={
                    "query": query,
                    "direction": direction,
                    "pairs": data.get("results", []),
                    "total_records": data.get("totalRecords", 0),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("passivetotal_host_pairs_not_found", query=query)
                return self.success_result(not_found=True, data={"query": query})
            return self.error_result(e)
        except Exception as e:
            self.log_error("passivetotal_host_pairs_failed", error=str(e))
            return self.error_result(e)

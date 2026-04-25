"""SecurityTrails integration actions for passive DNS, WHOIS, and domain infrastructure.
Library type: REST API (the upstream connector uses ``requests``; Naxos uses ``self.http_request()``).

SecurityTrails provides passive DNS records, historical WHOIS, subdomain
enumeration, domain tags/categories, DNS history, and a domain search API.
All calls are authenticated with the ``APIKEY`` header.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    AUTH_HEADER,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    MSG_INVALID_FILTER,
    MSG_INVALID_RECORD_TYPE,
    MSG_MISSING_API_KEY,
    MSG_MISSING_PARAM,
    VALID_DNS_RECORD_TYPES,
    VALID_SEARCH_FILTERS,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Base class with shared auth / URL helpers
# ---------------------------------------------------------------------------

class _SecurityTrailsBase(IntegrationAction):
    """Shared helpers for all SecurityTrails actions."""

    def get_http_headers(self) -> dict[str, str]:
        """Inject the API key into every outbound request."""
        api_key = self.credentials.get("api_key", "")
        return {AUTH_HEADER: api_key} if api_key else {}

    def get_timeout(self) -> int | float:
        """Return timeout, defaulting to SecurityTrails-specific value."""
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        url = self.settings.get("base_url", DEFAULT_BASE_URL)
        return url.rstrip("/")

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

class HealthCheckAction(_SecurityTrailsBase):
    """Verify connectivity to SecurityTrails API and validate API key."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_key():
            return err

        try:
            response = await self.http_request(url=f"{self.base_url}/ping/")
            data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Connectivity and credentials test passed",
                    "ping_response": data,
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("securitytrails_health_check_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("securitytrails_health_check_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LOOKUP DOMAIN
# ============================================================================

class LookupDomainAction(_SecurityTrailsBase):
    """Get current DNS records and domain information.

    Returns A/AAAA records, Alexa rank, and hostname from SecurityTrails.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="domain"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/domain/{domain}",
            )
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("securitytrails_domain_not_found", domain=domain)
                return self.success_result(
                    not_found=True,
                    data={"domain": domain},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("securitytrails_lookup_domain_failed", error=e)
            return self.error_result(e)

# ============================================================================
# WHOIS DOMAIN
# ============================================================================

class WhoisDomainAction(_SecurityTrailsBase):
    """Get current WHOIS data for a domain.

    Returns registrant contacts, dates, and nameserver info.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="domain"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/domain/{domain}/whois",
            )
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("securitytrails_whois_not_found", domain=domain)
                return self.success_result(
                    not_found=True,
                    data={"domain": domain},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("securitytrails_whois_domain_failed", error=e)
            return self.error_result(e)

# ============================================================================
# WHOIS HISTORY
# ============================================================================

class WhoisHistoryAction(_SecurityTrailsBase):
    """Get historical WHOIS records for a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="domain"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/history/{domain}/whois",
                params={"page": 1},
            )
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("securitytrails_whois_history_not_found", domain=domain)
                return self.success_result(
                    not_found=True,
                    data={"domain": domain},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("securitytrails_whois_history_failed", error=e)
            return self.error_result(e)

# ============================================================================
# DOMAIN SEARCHER
# ============================================================================

class DomainSearcherAction(_SecurityTrailsBase):
    """Search domains by filter criteria (e.g. IP, MX, NS, WHOIS fields).

    Uses the SecurityTrails ``/search/list`` POST endpoint with a filter DSL.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        filter_type = kwargs.get("filter")
        if not filter_type:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="filter"),
                error_type="ValidationError",
            )
        filter_string = kwargs.get("filterstring")
        if not filter_string:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="filterstring"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        # Validate filter type
        if filter_type not in VALID_SEARCH_FILTERS:
            return self.error_result(
                MSG_INVALID_FILTER.format(
                    value=filter_type,
                    valid=", ".join(VALID_SEARCH_FILTERS),
                ),
                error_type="ValidationError",
            )

        # Build filter payload
        filter_payload: dict[str, str] = {filter_type: filter_string}
        keyword = kwargs.get("keyword")
        if keyword:
            filter_payload["keyword"] = keyword

        try:
            response = await self.http_request(
                url=f"{self.base_url}/search/list",
                method="POST",
                json_data={"filter": filter_payload},
                headers={"Content-Type": "application/json"},
            )
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("securitytrails_domain_searcher_failed", error=e)
            return self.error_result(e)

# ============================================================================
# DOMAIN CATEGORY (TAGS)
# ============================================================================

class DomainCategoryAction(_SecurityTrailsBase):
    """Get category tags for a domain (e.g. gambling, sports, news)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="domain"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/domain/{domain}/tags",
            )
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("securitytrails_domain_category_not_found", domain=domain)
                return self.success_result(
                    not_found=True,
                    data={"domain": domain, "tags": []},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("securitytrails_domain_category_failed", error=e)
            return self.error_result(e)

# ============================================================================
# DOMAIN SUBDOMAIN
# ============================================================================

class DomainSubdomainAction(_SecurityTrailsBase):
    """Enumerate subdomains for a given domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="domain"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/domain/{domain}/subdomains",
            )
            data = response.json()

            # Expand subdomain prefixes into fully-qualified names
            subdomains = data.get("subdomains", [])
            expanded = [{"domain": f"{sub}.{domain}"} for sub in subdomains]

            return self.success_result(
                data={
                    "domain": domain,
                    "subdomains": expanded,
                    "subdomain_count": len(expanded),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("securitytrails_subdomains_not_found", domain=domain)
                return self.success_result(
                    not_found=True,
                    data={
                        "domain": domain,
                        "subdomains": [],
                        "subdomain_count": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("securitytrails_domain_subdomain_failed", error=e)
            return self.error_result(e)

# ============================================================================
# DOMAIN HISTORY (DNS)
# ============================================================================

class DomainHistoryAction(_SecurityTrailsBase):
    """Get historical DNS records for a domain by record type.

    Fetches the first page of results from ``/history/{domain}/dns/{type}``.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="domain"),
                error_type="ValidationError",
            )
        record_type = kwargs.get("record_type", "a")
        if not record_type:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="record_type"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        record_type = record_type.lower()
        if record_type not in VALID_DNS_RECORD_TYPES:
            return self.error_result(
                MSG_INVALID_RECORD_TYPE.format(
                    value=record_type,
                    valid=", ".join(VALID_DNS_RECORD_TYPES),
                ),
                error_type="ValidationError",
            )

        try:
            response = await self.http_request(
                url=f"{self.base_url}/history/{domain}/dns/{record_type}",
                params={"page": 1},
            )
            data = response.json()

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "securitytrails_domain_history_not_found",
                    domain=domain,
                    record_type=record_type,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "domain": domain,
                        "record_type": record_type,
                        "records": [],
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("securitytrails_domain_history_failed", error=e)
            return self.error_result(e)

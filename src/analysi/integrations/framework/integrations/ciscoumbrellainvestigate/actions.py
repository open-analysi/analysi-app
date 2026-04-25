"""Cisco Umbrella Investigate integration actions.

This module provides ThreatIntel actions for domain and IP reputation lookups
via the Cisco Umbrella Investigate REST API:
- Health check (test connectivity by categorizing a known domain)
- Lookup domain (comprehensive domain reputation: category, security, risk, tags)
- Lookup IP (latest domains hosted on an IP)
- Domain WHOIS (registrant and administrative contact information)
- Domain security info (security scores and threat indicators)
- DNS history (domain timeline/tagging history)

Authentication uses a Bearer token passed via the Authorization header.
"""

from typing import Any
from urllib.parse import quote

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    BASE_URL,
    CREDENTIAL_ACCESS_TOKEN,
    DEFAULT_TIMEOUT,
    ERR_MISSING_ACCESS_TOKEN,
    ERR_MISSING_DOMAIN,
    ERR_MISSING_IP,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MSG_HEALTH_CHECK_PASSED,
    SETTINGS_TIMEOUT,
    STATUS_DESC,
)

logger = get_logger(__name__)

# ============================================================================
# BASE CLASS
# ============================================================================

class _CiscoUmbrellaInvestigateBase(IntegrationAction):
    """Shared base for all Cisco Umbrella Investigate actions.

    Provides the Bearer token auth header injection and common request helper.
    """

    def _get_access_token(self) -> str | None:
        """Extract the API access token from credentials."""
        return self.credentials.get(CREDENTIAL_ACCESS_TOKEN)

    def get_timeout(self) -> int | float:
        """Return configured timeout."""
        return self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

    def get_http_headers(self) -> dict[str, str]:
        """Return authorization headers with Bearer token."""
        token = self._get_access_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def _investigate_request(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make a GET request to the Cisco Umbrella Investigate API.

        Args:
            endpoint: API endpoint path (appended to BASE_URL).
            params: Optional query parameters.

        Returns:
            httpx.Response object.
        """
        url = f"{BASE_URL}{endpoint}"

        return await self.http_request(
            url=url,
            params=params,
        )

# ============================================================================
# ACTIONS
# ============================================================================

class HealthCheckAction(_CiscoUmbrellaInvestigateBase):
    """Test connectivity to Cisco Umbrella Investigate by categorizing a known domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check API connectivity by querying a known domain."""
        token = self._get_access_token()
        if not token:
            return self.error_result(
                ERR_MISSING_ACCESS_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            response = await self._investigate_request(
                "/domains/categorization/phantomcyber.com?showLabels"
            )
            resp_data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "message": MSG_HEALTH_CHECK_PASSED,
                    "test_domain": "phantomcyber.com",
                    "categorization": resp_data.get("phantomcyber.com", {}),
                }
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class LookupDomainAction(_CiscoUmbrellaInvestigateBase):
    """Comprehensive domain reputation lookup.

    Aggregates multiple Investigate API calls to build a complete picture:
    - Domain categorization (status, content categories, security categories)
    - Co-occurrences / recommendations
    - Related domains
    - Security scores (DGA, pagerank, entropy, etc.)
    - Timeline / tagging info
    - Risk score and indicators

    This mirrors the upstream connector's _domain_reputation method which
    calls all six sub-endpoints.
    """

    async def _fetch_co_occurrences(
        self, safe_domain: str, data: dict[str, Any], summary: dict[str, Any]
    ) -> None:
        """Fetch co-occurrence / recommendation data for a domain."""
        try:
            rec_resp = await self._investigate_request(
                f"/recommendations/name/{safe_domain}.json"
            )
            co_occurances = rec_resp.json().get("pfs2")
            if co_occurances:
                data["co_occurances"] = co_occurances
                summary["total_co_occurances"] = len(co_occurances)
            else:
                summary["total_co_occurances"] = 0
        except httpx.HTTPStatusError:
            summary["total_co_occurances"] = 0

    async def _fetch_related_domains(
        self, safe_domain: str, data: dict[str, Any], summary: dict[str, Any]
    ) -> None:
        """Fetch related domain links."""
        try:
            rel_resp = await self._investigate_request(
                f"/links/name/{safe_domain}.json"
            )
            links = rel_resp.json().get("tb1")
            if links:
                data["relative_links"] = links
                summary["total_relative_links"] = len(links)
            else:
                summary["total_relative_links"] = 0
        except httpx.HTTPStatusError:
            summary["total_relative_links"] = 0

    async def _fetch_security_info(
        self, safe_domain: str, data: dict[str, Any]
    ) -> None:
        """Fetch security scores for a domain."""
        try:
            sec_resp = await self._investigate_request(
                f"/security/name/{safe_domain}.json"
            )
            if sec_resp.status_code != 204:
                data["security_info"] = sec_resp.json()
        except httpx.HTTPStatusError:
            pass

    async def _fetch_tagging_info(
        self, safe_domain: str, data: dict[str, Any], summary: dict[str, Any]
    ) -> None:
        """Fetch timeline / tagging history for a domain."""
        try:
            tag_resp = await self._investigate_request(f"/timeline/{safe_domain}")
            tag_json = tag_resp.json()
            if tag_json:
                data["tag_info"] = tag_json
                summary["total_tag_info"] = len(tag_json)
            else:
                summary["total_tag_info"] = 0
        except httpx.HTTPStatusError:
            summary["total_tag_info"] = 0

    async def _fetch_risk_score(
        self, safe_domain: str, data: dict[str, Any], summary: dict[str, Any]
    ) -> None:
        """Fetch risk score and indicators for a domain."""
        try:
            risk_resp = await self._investigate_request(
                f"/domains/risk-score/{safe_domain}"
            )
            risk_json = risk_resp.json()
            if risk_json:
                data["indicators"] = risk_json.get("indicators", [])
                risk_score = risk_json.get("risk_score", "Not Found")
                data["risk_score"] = risk_score
                summary["risk_score"] = risk_score
        except httpx.HTTPStatusError:
            pass

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up comprehensive domain reputation.

        Args:
            **kwargs: Must contain:
                - domain (str): Domain to look up

        Returns:
            Aggregated domain reputation data or error.
        """
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                ERR_MISSING_DOMAIN, error_type=ERROR_TYPE_VALIDATION
            )

        token = self._get_access_token()
        if not token:
            return self.error_result(
                ERR_MISSING_ACCESS_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        safe_domain = quote(domain, safe="")
        data: dict[str, Any] = {}
        summary: dict[str, Any] = {}

        try:
            # 1. Category info (primary -- failure here fails the action)
            cat_resp = await self._investigate_request(
                f"/domains/categorization/{safe_domain}?showLabels"
            )
            cat_json = cat_resp.json()
            domain_cat_info = cat_json.get(domain, {})

            status_code = domain_cat_info.get("status", 0)
            status_desc = STATUS_DESC.get(str(status_code), "UNKNOWN")

            content_cats = domain_cat_info.get("content_categories", []) or []
            security_cats = domain_cat_info.get("security_categories", []) or []
            categories = ", ".join(content_cats + security_cats)

            data["status_desc"] = status_desc
            data["category"] = categories
            data["category_info"] = domain_cat_info
            summary["domain_status"] = status_desc

            # 2-6. Secondary enrichment calls (failures are non-fatal)
            await self._fetch_co_occurrences(safe_domain, data, summary)
            await self._fetch_related_domains(safe_domain, data, summary)
            await self._fetch_security_info(safe_domain, data)
            await self._fetch_tagging_info(safe_domain, data, summary)
            await self._fetch_risk_score(safe_domain, data, summary)

            data["summary"] = summary

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "ciscoumbrellainvestigate_domain_not_found", domain=domain
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "domain": domain,
                        "status_desc": "UNKNOWN",
                        "category": "",
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class LookupIpAction(_CiscoUmbrellaInvestigateBase):
    """Look up IP reputation by finding latest domains hosted on the IP.

    The Investigate API returns a list of domains recently seen on the IP.
    If domains are found, the IP is considered potentially malicious.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up latest domains associated with an IP.

        Args:
            **kwargs: Must contain:
                - ip (str): IP address to look up

        Returns:
            IP reputation data with associated domains.
        """
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(ERR_MISSING_IP, error_type=ERROR_TYPE_VALIDATION)

        token = self._get_access_token()
        if not token:
            return self.error_result(
                ERR_MISSING_ACCESS_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            response = await self._investigate_request(f"/ips/{ip}/latest_domains")

            if response.status_code == 204:
                return self.success_result(
                    data={
                        "ip": ip,
                        "ip_status": STATUS_DESC["0"],
                        "domains": [],
                        "total_blocked_domains": 0,
                    },
                )

            domains = response.json()

            if not domains:
                status_desc = STATUS_DESC["1"]  # NON MALICIOUS
                total = 0
            else:
                total = len(domains)
                status_desc = STATUS_DESC["1"] if total == 0 else STATUS_DESC["-1"]

            return self.success_result(
                data={
                    "ip": ip,
                    "ip_status": status_desc,
                    "domains": domains,
                    "total_blocked_domains": total,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("ciscoumbrellainvestigate_ip_not_found", ip=ip)
                return self.success_result(
                    not_found=True,
                    data={
                        "ip": ip,
                        "ip_status": STATUS_DESC["0"],
                        "domains": [],
                        "total_blocked_domains": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class DomainWhoisAction(_CiscoUmbrellaInvestigateBase):
    """Run a WHOIS query for a domain via Cisco Umbrella Investigate.

    Returns registrant, administrative, and technical contact information.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get WHOIS information for a domain.

        Args:
            **kwargs: Must contain:
                - domain (str): Domain (or URL) to query

        Returns:
            WHOIS data including registrant information.
        """
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                ERR_MISSING_DOMAIN, error_type=ERROR_TYPE_VALIDATION
            )

        token = self._get_access_token()
        if not token:
            return self.error_result(
                ERR_MISSING_ACCESS_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        # Clean domain: extract hostname from URL if needed, strip trailing path
        cleaned = domain
        if "://" in cleaned:
            cleaned = cleaned.split("://", 1)[1]
        slash_pos = cleaned.find("/")
        if slash_pos != -1:
            cleaned = cleaned[:slash_pos]

        safe_domain = quote(cleaned, safe="")

        try:
            response = await self._investigate_request(f"/whois/{safe_domain}")
            whois_data = response.json()

            summary = {
                "organization": whois_data.get("registrantOrganization", ""),
                "city": whois_data.get("registrantCity", ""),
                "country": whois_data.get("registrantCountry", ""),
            }

            return self.success_result(
                data={
                    "whois": whois_data,
                    "summary": summary,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "ciscoumbrellainvestigate_whois_not_found", domain=cleaned
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "domain": cleaned,
                        "whois": {},
                        "summary": {
                            "organization": "",
                            "city": "",
                            "country": "",
                        },
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class DomainSecurityInfoAction(_CiscoUmbrellaInvestigateBase):
    """Get security-specific scores for a domain.

    Returns threat scores including DGA score, ASN score, perplexity,
    entropy, pagerank, geodiversity, and other security indicators from
    the /security/name/{domain}.json endpoint.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get security scores and threat indicators for a domain.

        Args:
            **kwargs: Must contain:
                - domain (str): Domain to query

        Returns:
            Security information data.
        """
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                ERR_MISSING_DOMAIN, error_type=ERROR_TYPE_VALIDATION
            )

        token = self._get_access_token()
        if not token:
            return self.error_result(
                ERR_MISSING_ACCESS_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        safe_domain = quote(domain, safe="")

        try:
            response = await self._investigate_request(
                f"/security/name/{safe_domain}.json"
            )

            if response.status_code == 204:
                return self.success_result(
                    data={
                        "domain": domain,
                        "security_info": {},
                        "message": "No security data available",
                    },
                )

            security_data = response.json()

            return self.success_result(
                data={
                    "domain": domain,
                    "security_info": security_data,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "ciscoumbrellainvestigate_security_not_found", domain=domain
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "domain": domain,
                        "security_info": {},
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class DnsHistoryAction(_CiscoUmbrellaInvestigateBase):
    """Get DNS timeline and tagging history for a domain.

    Returns the domain's historical threat categorization timeline from
    the /timeline/{domain} endpoint, including threat types, attack
    categories, and time periods.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get DNS timeline/tagging history for a domain.

        Args:
            **kwargs: Must contain:
                - domain (str): Domain to query

        Returns:
            Timeline data with historical threat tagging.
        """
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                ERR_MISSING_DOMAIN, error_type=ERROR_TYPE_VALIDATION
            )

        token = self._get_access_token()
        if not token:
            return self.error_result(
                ERR_MISSING_ACCESS_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        safe_domain = quote(domain, safe="")

        try:
            response = await self._investigate_request(f"/timeline/{safe_domain}")
            timeline_data = response.json()

            total_entries = len(timeline_data) if timeline_data else 0

            return self.success_result(
                data={
                    "domain": domain,
                    "timeline": timeline_data or [],
                    "total_entries": total_entries,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "ciscoumbrellainvestigate_timeline_not_found", domain=domain
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "domain": domain,
                        "timeline": [],
                        "total_entries": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

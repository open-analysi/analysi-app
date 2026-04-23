"""Kaspersky Threat Intelligence Portal integration actions.

Provides ThreatIntel actions for domain, IP, file hash, and URL reputation
lookups against the Kaspersky TIP API, plus APT report retrieval.

Authentication: HTTP Basic Auth (username + password).
Note: The upstream connector also uses a PEM client certificate for mTLS.
The Naxos framework's http_request() does not currently support client
certificates. If mTLS is required, the pem_certificate credential field
is available but unused until framework support is added.
"""

import re
from typing import Any
from urllib.parse import quote

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    BASE_URL,
    DEFAULT_RECORDS_COUNT,
    ENDPOINT_DOMAIN,
    ENDPOINT_HASH,
    ENDPOINT_IP,
    ENDPOINT_PUBLICATIONS,
    ENDPOINT_URL,
    MSG_ACCESS_DENIED,
    MSG_MISSING_APT_ID,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_DOMAIN,
    MSG_MISSING_HASH,
    MSG_MISSING_INDICATOR,
    MSG_MISSING_IP,
    MSG_MISSING_URL,
    SECTIONS_DOMAIN_REPUTATION,
    SECTIONS_FILE_REPUTATION,
    SECTIONS_HEALTH_CHECK,
    SECTIONS_IP_REPUTATION,
    SECTIONS_URL_REPUTATION,
    ZONE_GREY,
)

logger = get_logger(__name__)

# ============================================================================
# HELPER UTILITIES
# ============================================================================

def _prepare_url_indicator(url_input: str) -> str:
    """Prepare a URL indicator for the Kaspersky TIP API.

    Strips protocol, www prefix, credentials, ports, trailing slashes,
    fragments, and URL-encodes special characters. Mirrors the upstream
    connector's _prepare_url() logic.

    Args:
        url_input: Raw URL string to normalize.

    Returns:
        URL-encoded indicator string suitable for the API path.
    """
    url_input = url_input.lower()
    url_input = url_input.replace("..", ".")
    url_input = url_input.replace("./", "/")

    # Strip embedded credentials (user:pass@)
    creds = re.search(r"^\S+://(\S+(?::\S+)?@).*?", url_input)
    if creds:
        url_input = url_input.replace(creds.group(1), "")

    # Strip port numbers
    port = re.search(r"^\S+://\S+(:\d+)(?:/|$)", url_input)
    if port:
        url_input = url_input.replace(port.group(1), "")

    # Strip trailing dot before slash
    dot = re.search(r"^\S+://\S+(\.)/$", url_input)
    if dot:
        url_input = url_input[:-2]

    # Strip protocol
    protocol = re.search(r"^(\S+://).*?", url_input)
    if protocol:
        url_input = url_input.replace(protocol.group(1), "")

    # Strip www. prefix
    www = re.search(r"^(www\.).*?", url_input)
    if www:
        url_input = url_input.replace(www.group(1), "")

    # Strip trailing slash
    endslash = re.search(r"^.*?(/)$", url_input)
    if endslash:
        url_input = url_input[:-1]

    # Strip fragment identifiers
    endfragment = re.search(r"^.*?(#\w+)$", url_input)
    if endfragment:
        url_input = url_input.replace(endfragment.group(1), "")

    # Collapse double slashes
    while "//" in url_input:
        url_input = url_input.replace("//", "/")

    # URL-encode the indicator for use in the API path
    return quote(url_input, safe="")

def _detect_indicator_type(indicator: str) -> str:
    """Detect the type of indicator and return the appropriate API endpoint.

    Mirrors the upstream connector's type_of_indicator() logic.

    Args:
        indicator: An IP, hash, URL, or domain string.

    Returns:
        API endpoint template path.
    """
    # Check for IP address pattern
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", indicator):
        return ENDPOINT_IP

    # Check for hash pattern (32-64 hex characters)
    if re.match(r"^[\da-fA-F]{32,64}$", indicator):
        return ENDPOINT_HASH

    # Check for URL pattern (contains protocol)
    if re.match(r"^\S+://.*", indicator):
        return ENDPOINT_URL

    # Default: treat as domain
    return ENDPOINT_DOMAIN

def _extract_apt_info(info_block: dict[str, Any], summary: dict[str, Any]) -> None:
    """Extract APT association data from a general-info block into summary.

    Shared helper for domain, IP, file, and URL info sections which all
    share the same HasApt / RelatedAptReports structure.

    Args:
        info_block: A *GeneralInfo dict from the API response.
        summary: The summary dict to update in place.
    """
    if info_block.get("HasApt"):
        summary["apt_related"] = True
        apt_reports = info_block.get("RelatedAptReports", [])
        if apt_reports:
            summary["apt_report"] = apt_reports[0].get("Title")
            summary["apt_report_id"] = apt_reports[0].get("Id", "")

def _extract_summary(response: dict[str, Any]) -> dict[str, Any]:
    """Extract a structured summary from a Kaspersky TIP API response.

    Mirrors the upstream connector's _extract_kaspersky_summary() logic,
    producing a flat summary dict with zone, categories, APT info,
    threat score, and license quota data.

    Args:
        response: Raw JSON response from the Kaspersky TIP API.

    Returns:
        Flat summary dictionary.
    """
    summary: dict[str, Any] = {
        "found": False,
        "zone": ZONE_GREY,
        "categories": [],
        "threat_score": 0,
        "hits_count": 0,
        "apt_related": False,
        "apt_report": None,
        "apt_report_id": "",
    }

    # Zone info
    zone = response.get("Zone", ZONE_GREY)
    if zone != ZONE_GREY:
        summary["found"] = True
        summary["zone"] = zone

    # Domain info
    domain_info = response.get("DomainGeneralInfo")
    if domain_info:
        summary["hits_count"] = domain_info.get("HitsCount", 0)
        categories = domain_info.get("Categories", [])
        if categories:
            summary["categories"] = categories
        _extract_apt_info(domain_info, summary)

    # IP info
    ip_info = response.get("IpGeneralInfo")
    if ip_info:
        summary["hits_count"] = ip_info.get("HitsCount", 0)
        categories = ip_info.get("Categories", [])
        if categories:
            summary["categories"] = categories
        _extract_apt_info(ip_info, summary)
        if ip_info.get("ThreatScore"):
            summary["threat_score"] = ip_info["ThreatScore"]

    # File info
    file_info = response.get("FileGeneralInfo")
    if file_info:
        summary["hits_count"] = file_info.get("HitsCount", 0)
        summary["hash"] = file_info.get("Md5", "")
        summary["sha1"] = file_info.get("Sha1", "")
        summary["sha256"] = file_info.get("Sha256", "")
        detections = response.get("DetectionsInfo", [])
        if detections:
            summary["categories"] = [d.get("DetectionName", "") for d in detections]
        _extract_apt_info(file_info, summary)

    # URL info
    url_info = response.get("UrlGeneralInfo")
    if url_info:
        categories = url_info.get("Categories", [])
        if categories:
            summary["categories"] = categories
        _extract_apt_info(url_info, summary)

    # License info
    license_info = response.get("LicenseInfo")
    if license_info:
        summary["day_requests"] = license_info.get("DayRequests", 0)
        summary["day_quota"] = license_info.get("DayQuota", 0)

    # APT publication info (from get_reports)
    return_data = response.get("return_data")
    if return_data:
        summary["apt_report"] = return_data.get("name")
        summary["apt_report_url"] = (
            f"https://tip.kaspersky.com/reporting?id={return_data.get('id', '')}"
        )
        summary["apt_report_desc"] = return_data.get("desc", "")
        summary["apt_report_geo"] = return_data.get("tags_geo", "")
        summary["apt_report_industry"] = return_data.get("tags_industry", "")
        summary["apt_report_actors"] = return_data.get("tags_actors", "")

    return summary

def _get_auth(credentials: dict[str, Any]) -> tuple[str, str] | None:
    """Extract Basic Auth credentials tuple.

    Args:
        credentials: Credentials dict with username and password.

    Returns:
        Tuple of (username, password) or None if missing.
    """
    username = credentials.get("username")
    password = credentials.get("password")
    if username and password:
        return (username, password)
    return None

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Check Kaspersky TIP API connectivity and license quota."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity by querying example.com with Zone and LicenseInfo sections.

        Returns:
            Result with license quota info if healthy, error otherwise.
        """
        auth = _get_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        base_url = self.settings.get("base_url", BASE_URL)
        url = f"{base_url}/api/domain/example.com?sections={SECTIONS_HEALTH_CHECK}"

        try:
            response = await self.http_request(url=url, auth=auth)
            data = response.json()
            summary = _extract_summary(data)

            return self.success_result(
                data={
                    "healthy": True,
                    "day_quota": summary.get("day_quota", 0),
                    "day_requests": summary.get("day_requests", 0),
                    "zone": summary.get("zone", ZONE_GREY),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                return self.error_result(
                    MSG_ACCESS_DENIED, error_type="AuthenticationError"
                )
            if e.response.status_code == 401:
                return self.error_result(
                    "Invalid credentials or terms not accepted",
                    error_type="AuthenticationError",
                )
            return self.error_result(e)
        except Exception as e:
            logger.error("kasperskyti_health_check_failed", error=str(e))
            return self.error_result(e)

class DomainReputationAction(IntegrationAction):
    """Look up domain reputation in Kaspersky TIP."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get domain reputation including zone, categories, and APT association.

        Args:
            **kwargs: Must contain 'domain'.

        Returns:
            Result with domain reputation data or error.
        """
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(MSG_MISSING_DOMAIN, error_type="ValidationError")

        auth = _get_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        base_url = self.settings.get("base_url", BASE_URL)
        url = f"{base_url}/api/domain/{domain}?sections={SECTIONS_DOMAIN_REPUTATION}"

        try:
            response = await self.http_request(url=url, auth=auth)
            data = response.json()
            summary = _extract_summary(data)

            return self.success_result(
                data={
                    "domain": domain,
                    "zone": summary["zone"],
                    "found": summary["found"],
                    "categories": summary["categories"],
                    "hits_count": summary["hits_count"],
                    "apt_related": summary["apt_related"],
                    "apt_report": summary["apt_report"],
                    "apt_report_id": summary["apt_report_id"],
                    "tip_url": f"https://tip.kaspersky.com/search?searchString={domain}",
                    "full_data": data,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):
                logger.info("kasperskyti_domain_not_found", domain=domain)
                return self.success_result(
                    not_found=True,
                    data={
                        "domain": domain,
                        "zone": ZONE_GREY,
                        "found": False,
                        "categories": [],
                        "hits_count": 0,
                        "apt_related": False,
                    },
                )
            if e.response.status_code == 403:
                return self.error_result(
                    MSG_ACCESS_DENIED, error_type="AuthenticationError"
                )
            return self.error_result(e)
        except Exception as e:
            logger.error(
                "kasperskyti_domain_reputation_failed", domain=domain, error=str(e)
            )
            return self.error_result(e)

class IpReputationAction(IntegrationAction):
    """Look up IP address reputation in Kaspersky TIP."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get IP reputation including zone, threat score, categories, and APT association.

        Args:
            **kwargs: Must contain 'ip'.

        Returns:
            Result with IP reputation data or error.
        """
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(MSG_MISSING_IP, error_type="ValidationError")

        auth = _get_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        base_url = self.settings.get("base_url", BASE_URL)
        url = f"{base_url}/api/ip/{ip}?sections={SECTIONS_IP_REPUTATION}"

        try:
            response = await self.http_request(url=url, auth=auth)
            data = response.json()
            summary = _extract_summary(data)

            return self.success_result(
                data={
                    "ip": ip,
                    "zone": summary["zone"],
                    "found": summary["found"],
                    "threat_score": summary["threat_score"],
                    "categories": summary["categories"],
                    "hits_count": summary["hits_count"],
                    "apt_related": summary["apt_related"],
                    "apt_report": summary["apt_report"],
                    "apt_report_id": summary["apt_report_id"],
                    "tip_url": f"https://tip.kaspersky.com/search?searchString={ip}",
                    "full_data": data,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):
                logger.info("kasperskyti_ip_not_found", ip=ip)
                return self.success_result(
                    not_found=True,
                    data={
                        "ip": ip,
                        "zone": ZONE_GREY,
                        "found": False,
                        "threat_score": 0,
                        "categories": [],
                        "hits_count": 0,
                        "apt_related": False,
                    },
                )
            if e.response.status_code == 403:
                return self.error_result(
                    MSG_ACCESS_DENIED, error_type="AuthenticationError"
                )
            return self.error_result(e)
        except Exception as e:
            logger.error("kasperskyti_ip_reputation_failed", ip=ip, error=str(e))
            return self.error_result(e)

class FileReputationAction(IntegrationAction):
    """Look up file hash reputation in Kaspersky TIP."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get file hash reputation including zone, detections, and APT association.

        Args:
            **kwargs: Must contain 'hash' (MD5, SHA1, or SHA256).

        Returns:
            Result with file reputation data or error.
        """
        file_hash = kwargs.get("hash")
        if not file_hash:
            return self.error_result(MSG_MISSING_HASH, error_type="ValidationError")

        auth = _get_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        base_url = self.settings.get("base_url", BASE_URL)
        url = f"{base_url}/api/hash/{file_hash}?sections={SECTIONS_FILE_REPUTATION}"

        try:
            response = await self.http_request(url=url, auth=auth)
            data = response.json()
            summary = _extract_summary(data)

            return self.success_result(
                data={
                    "hash": file_hash,
                    "zone": summary["zone"],
                    "found": summary["found"],
                    "categories": summary["categories"],
                    "hits_count": summary["hits_count"],
                    "md5": summary.get("hash", ""),
                    "sha1": summary.get("sha1", ""),
                    "sha256": summary.get("sha256", ""),
                    "apt_related": summary["apt_related"],
                    "apt_report": summary["apt_report"],
                    "apt_report_id": summary["apt_report_id"],
                    "tip_url": f"https://tip.kaspersky.com/search?searchString={file_hash}",
                    "full_data": data,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):
                logger.info("kasperskyti_file_not_found", file_hash=file_hash)
                return self.success_result(
                    not_found=True,
                    data={
                        "hash": file_hash,
                        "zone": ZONE_GREY,
                        "found": False,
                        "categories": [],
                        "hits_count": 0,
                        "apt_related": False,
                    },
                )
            if e.response.status_code == 403:
                return self.error_result(
                    MSG_ACCESS_DENIED, error_type="AuthenticationError"
                )
            return self.error_result(e)
        except Exception as e:
            logger.error(
                "kasperskyti_file_reputation_failed", file_hash=file_hash, error=str(e)
            )
            return self.error_result(e)

class UrlReputationAction(IntegrationAction):
    """Look up URL reputation in Kaspersky TIP."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get URL reputation including zone, categories, and APT association.

        Args:
            **kwargs: Must contain 'url'.

        Returns:
            Result with URL reputation data or error.
        """
        url_input = kwargs.get("url")
        if not url_input:
            return self.error_result(MSG_MISSING_URL, error_type="ValidationError")

        auth = _get_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        base_url = self.settings.get("base_url", BASE_URL)
        prepared_url = _prepare_url_indicator(url_input)
        url = f"{base_url}/api/url/{prepared_url}?sections={SECTIONS_URL_REPUTATION}"

        try:
            response = await self.http_request(url=url, auth=auth)
            data = response.json()
            summary = _extract_summary(data)

            return self.success_result(
                data={
                    "url": url_input,
                    "zone": summary["zone"],
                    "found": summary["found"],
                    "categories": summary["categories"],
                    "apt_related": summary["apt_related"],
                    "apt_report": summary["apt_report"],
                    "apt_report_id": summary["apt_report_id"],
                    "tip_url": f"https://tip.kaspersky.com/search?searchString={url_input}",
                    "full_data": data,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):
                logger.info("kasperskyti_url_not_found", url=url_input)
                return self.success_result(
                    not_found=True,
                    data={
                        "url": url_input,
                        "zone": ZONE_GREY,
                        "found": False,
                        "categories": [],
                        "apt_related": False,
                    },
                )
            if e.response.status_code == 403:
                return self.error_result(
                    MSG_ACCESS_DENIED, error_type="AuthenticationError"
                )
            return self.error_result(e)
        except Exception as e:
            logger.error(
                "kasperskyti_url_reputation_failed", url=url_input, error=str(e)
            )
            return self.error_result(e)

class GetIndicatorDetailsAction(IntegrationAction):
    """Get detailed information about any indicator (IP, domain, hash, URL)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Query detailed indicator information with configurable sections.

        Auto-detects the indicator type (IP, hash, URL, or domain) and
        queries the appropriate Kaspersky TIP API endpoint. Optionally
        accepts a comma-separated list of API sections.

        Args:
            **kwargs: Must contain 'indicator'. Optionally 'sections'.

        Returns:
            Result with detailed indicator data or error.
        """
        indicator = kwargs.get("indicator")
        if not indicator:
            return self.error_result(
                MSG_MISSING_INDICATOR, error_type="ValidationError"
            )

        sections = kwargs.get("sections")

        auth = _get_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        base_url = self.settings.get("base_url", BASE_URL)
        records_count = self.settings.get("records_count", DEFAULT_RECORDS_COUNT)

        # Detect indicator type and build endpoint
        endpoint_template = _detect_indicator_type(indicator)
        if endpoint_template == ENDPOINT_URL:
            prepared_indicator = _prepare_url_indicator(indicator)
        else:
            prepared_indicator = indicator

        url = f"{base_url}{endpoint_template.format(indicator=prepared_indicator)}?count={records_count}"
        if sections:
            url += f"&sections={sections}"

        try:
            response = await self.http_request(url=url, auth=auth)
            data = response.json()
            summary = _extract_summary(data)

            return self.success_result(
                data={
                    "indicator": indicator,
                    "indicator_type": endpoint_template.split("/")[2],
                    "zone": summary["zone"],
                    "found": summary["found"],
                    "categories": summary["categories"],
                    "hits_count": summary["hits_count"],
                    "threat_score": summary["threat_score"],
                    "apt_related": summary["apt_related"],
                    "apt_report": summary["apt_report"],
                    "apt_report_id": summary["apt_report_id"],
                    "tip_url": f"https://tip.kaspersky.com/search?searchString={indicator}",
                    "full_data": data,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):
                logger.info("kasperskyti_indicator_not_found", indicator=indicator)
                return self.success_result(
                    not_found=True,
                    data={
                        "indicator": indicator,
                        "zone": ZONE_GREY,
                        "found": False,
                        "categories": [],
                        "hits_count": 0,
                        "apt_related": False,
                    },
                )
            if e.response.status_code == 403:
                return self.error_result(
                    MSG_ACCESS_DENIED, error_type="AuthenticationError"
                )
            return self.error_result(e)
        except Exception as e:
            logger.error(
                "kasperskyti_indicator_details_failed",
                indicator=indicator,
                error=str(e),
            )
            return self.error_result(e)

class GetAptReportsAction(IntegrationAction):
    """Retrieve APT campaign reports from Kaspersky TIP."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get an APT report by publication ID.

        Args:
            **kwargs: Must contain 'apt_id' (publication ID).

        Returns:
            Result with APT report data or error.
        """
        apt_id = kwargs.get("apt_id")
        if not apt_id:
            return self.error_result(MSG_MISSING_APT_ID, error_type="ValidationError")

        auth = _get_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )

        base_url = self.settings.get("base_url", BASE_URL)
        url = f"{base_url}{ENDPOINT_PUBLICATIONS}"

        try:
            response = await self.http_request(
                url=url,
                auth=auth,
                params={
                    "publication_id": apt_id,
                    "include_info": "all",
                },
            )
            data = response.json()
            summary = _extract_summary(data)

            return self.success_result(
                data={
                    "apt_id": apt_id,
                    "apt_report": summary.get("apt_report"),
                    "apt_report_url": summary.get("apt_report_url", ""),
                    "apt_report_desc": summary.get("apt_report_desc", ""),
                    "apt_report_geo": summary.get("apt_report_geo", ""),
                    "apt_report_industry": summary.get("apt_report_industry", ""),
                    "apt_report_actors": summary.get("apt_report_actors", ""),
                    "full_data": data,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):
                logger.info("kasperskyti_apt_report_not_found", apt_id=apt_id)
                return self.success_result(
                    not_found=True,
                    data={
                        "apt_id": apt_id,
                        "apt_report": None,
                    },
                )
            if e.response.status_code == 403:
                return self.error_result(
                    MSG_ACCESS_DENIED, error_type="AuthenticationError"
                )
            return self.error_result(e)
        except Exception as e:
            logger.error("kasperskyti_apt_report_failed", apt_id=apt_id, error=str(e))
            return self.error_result(e)

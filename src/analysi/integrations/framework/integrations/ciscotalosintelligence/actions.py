"""Cisco Talos Intelligence integration actions.

Provides ThreatIntel actions for IP, domain, and URL reputation lookups
using the Cisco Talos reputation API with mTLS certificate authentication.
"""

import contextlib
import ipaddress
import os
import re
import tempfile
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    APP_INFO_PRODUCT_FAMILY,
    APP_INFO_PRODUCT_ID,
    APP_INFO_PRODUCT_VERSION,
    DEFAULT_BASE_URL,
    DEFAULT_CATALOG_ID,
    DEFAULT_TIMEOUT,
    ENDPOINT_QUERY_REPUTATION_V3,
    ENDPOINT_QUERY_TAXONOMIES,
    MSG_INVALID_DOMAIN,
    MSG_INVALID_IP,
    MSG_INVALID_URL,
    MSG_MISSING_CREDENTIALS,
    TAXONOMY_AUP_CATEGORIES,
    TAXONOMY_THREAT_CATEGORIES,
    TAXONOMY_THREAT_LEVELS,
)

logger = get_logger(__name__)

# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def _validate_ip(ip: str | None) -> tuple[bool, str]:
    """Validate IPv4 or IPv6 address.

    Args:
        ip: IP address string to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not ip or not isinstance(ip, str) or not ip.strip():
        return False, "IP address is required"
    try:
        ipaddress.ip_address(ip.strip())
        return True, ""
    except ValueError:
        return False, f"{MSG_INVALID_IP}: {ip}"

def _validate_domain(domain: str | None) -> tuple[bool, str]:
    """Validate domain name format.

    Uses the same regex pattern as the upstream connector.

    Args:
        domain: Domain name to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not domain or not isinstance(domain, str) or not domain.strip():
        return False, "Domain is required"
    regex = r"^(?!-)([A-Za-z0-9-]{1,63}(?<!-)\.)+[A-Za-z]{2,}$"
    if not re.match(regex, domain.strip()):
        return False, f"{MSG_INVALID_DOMAIN}: {domain}"
    return True, ""

def _validate_url(url: str | None) -> tuple[bool, str]:
    """Validate URL format (must have scheme and netloc).

    Args:
        url: URL string to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not url or not isinstance(url, str) or not url.strip():
        return False, "URL is required"
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return False, f"{MSG_INVALID_URL}: {url}"
    return True, ""

def _format_ip_for_request(ip_str: str) -> dict[str, Any]:
    """Format an IP address into the Talos API request structure.

    IPv4 is sent as an integer, IPv6 as a hex string of packed bytes.
    Matches the upstream connector's format_ip_type method.

    Args:
        ip_str: Validated IP address string.

    Returns:
        Dict with either 'ipv4_addr' (int) or 'ipv6_addr' (hex string).
    """
    addr = ipaddress.ip_address(ip_str.strip())
    if isinstance(addr, ipaddress.IPv4Address):
        return {"ipv4_addr": int(addr)}
    return {"ipv6_addr": addr.packed.hex()}

def _build_app_info() -> dict[str, Any]:
    """Build the app_info payload required by the Talos API.

    Returns:
        Dict with product identification fields.
    """
    return {
        "product_family": APP_INFO_PRODUCT_FAMILY,
        "product_id": APP_INFO_PRODUCT_ID,
        "product_version": APP_INFO_PRODUCT_VERSION,
        "perf_testing": False,
    }

def _parse_reputation_response(
    response: dict[str, Any],
    taxonomy: dict[str, Any],
    observable: str,
) -> dict[str, Any]:
    """Parse the Talos reputation API response using taxonomy data.

    Extracts threat level, threat categories, and AUP categories from
    the taxonomy-tagged results.

    Args:
        response: Raw API response from QueryReputationV3.
        taxonomy: Taxonomy catalog data from QueryTaxonomyCatalogs.
        observable: The queried IP/domain/URL for labeling.

    Returns:
        Dict with Observable, Threat_Level, Threat_Categories, and AUP fields.
    """
    threat_level = ""
    threat_categories: dict[str, str] = {}
    aup_categories: dict[str, str] = {}

    for result in response.get("results", []):
        for url_result in result.get("results", []):
            for tag in url_result.get("context_tags", []):
                tax_id = str(tag.get("taxonomy_id", ""))
                entry_id = str(tag.get("taxonomy_entry_id", ""))

                if tax_id not in taxonomy.get("taxonomies", {}):
                    continue

                tax_entry = taxonomy["taxonomies"][tax_id]
                if not tax_entry.get("is_avail", False):
                    continue

                category = tax_entry.get("name", {}).get("en-us", {}).get("text", "")
                entries = tax_entry.get("entries", {})
                entry = entries.get(entry_id, {})
                name = entry.get("name", {}).get("en-us", {}).get("text", "")
                description = (
                    entry.get("description", {}).get("en-us", {}).get("text", "")
                )

                if category == TAXONOMY_THREAT_LEVELS:
                    threat_level = name
                elif category == TAXONOMY_THREAT_CATEGORIES:
                    threat_categories[name] = description
                elif category == TAXONOMY_AUP_CATEGORIES:
                    aup_categories[name] = description

    return {
        "observable": observable,
        "threat_level": threat_level,
        "threat_categories": ", ".join(threat_categories.keys()),
        "threat_category_details": threat_categories,
        "aup_categories": ", ".join(aup_categories.keys()),
        "aup_category_details": aup_categories,
    }

# ============================================================================
# CREDENTIAL VALIDATION
# ============================================================================

def _validate_credentials(credentials: dict[str, Any]) -> tuple[bool, str]:
    """Validate that required mTLS credentials are present.

    Args:
        credentials: Credentials dict from Vault.

    Returns:
        Tuple of (is_valid, error_message).
    """
    certificate = credentials.get("certificate")
    key = credentials.get("key")
    if not certificate or not key:
        return False, MSG_MISSING_CREDENTIALS
    return True, ""

@contextmanager
def _mtls_cert_files(certificate: str, key: str):
    """Write PEM strings from Vault to temp files for httpx mTLS.

    Yields:
        Tuple of (cert_path, key_path) for use with ``http_request(cert=...)``.
    """
    cert_path = key_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".pem", mode="w"
        ) as cert_fd:
            cert_fd.write(certificate)
            cert_path = cert_fd.name

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".pem", mode="w"
        ) as key_fd:
            key_fd.write(key)
            key_path = key_fd.name

        yield (cert_path, key_path)
    finally:
        for path in (cert_path, key_path):
            if path:
                with contextlib.suppress(OSError):
                    os.unlink(path)

async def _fetch_taxonomy(
    http_request_fn,
    base_url: str,
    app_info: dict[str, Any],
    timeout: int | float,
    cert: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch taxonomy catalog from the Talos API.

    Args:
        http_request_fn: Bound ``self.http_request`` method.
        base_url: Talos API base URL.
        app_info: App identification payload.
        timeout: Request timeout in seconds.
        cert: Optional mTLS cert pair ``(cert_path, key_path)``.

    Returns:
        Taxonomy catalog dict for the default catalog ID.
    """
    payload = {"app_info": app_info}
    response = await http_request_fn(
        url=f"{base_url}{ENDPOINT_QUERY_TAXONOMIES}",
        method="POST",
        json_data=payload,
        timeout=timeout,
        cert=cert,
    )
    result = response.json()
    return result.get("catalogs", {}).get(str(DEFAULT_CATALOG_ID), {})

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Cisco Talos Intelligence API connectivity.

    Tests connectivity by querying the reputation of cisco.com (a safe,
    known-good domain). Uses the same approach as the upstream connector's
    test_connectivity handler.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Talos API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy.
        """
        is_valid, error_msg = _validate_credentials(self.credentials)
        if not is_valid:
            return self.error_result(error_msg, error_type="ConfigurationError")

        base_url = self.settings.get("base_url", DEFAULT_BASE_URL)
        app_info = _build_app_info()
        app_info["perf_testing"] = True  # Match upstream test_connectivity behavior

        payload = {
            "urls": [{"raw_url": "cisco.com"}],
            "app_info": app_info,
        }

        try:
            with _mtls_cert_files(
                self.credentials["certificate"], self.credentials["key"]
            ) as cert:
                response = await self.http_request(
                    url=f"{base_url}{ENDPOINT_QUERY_REPUTATION_V3}",
                    method="POST",
                    json_data=payload,
                    timeout=self.settings.get("timeout", DEFAULT_TIMEOUT),
                    cert=cert,
                )
            response.json()  # Verify response is valid JSON
            return self.success_result(
                data={"healthy": True, "message": "Talos API is accessible"}
            )

        except Exception as e:
            self.log_error("talos_health_check_failed", error=e)
            return self.error_result(e)

class IpReputationAction(IntegrationAction):
    """Look up IP address reputation in Cisco Talos Intelligence.

    Queries the Talos reputation API for threat level, threat categories,
    and acceptable use policy categories associated with an IP address.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get IP reputation from Talos.

        Args:
            **kwargs: Must contain:
                - ip (str): IPv4 or IPv6 address to look up.

        Returns:
            Result with threat level, categories, and AUP data.
        """
        ip = kwargs.get("ip")
        is_valid, error_msg = _validate_ip(ip)
        if not is_valid:
            return self.error_result(error_msg, error_type="ValidationError")

        is_valid, error_msg = _validate_credentials(self.credentials)
        if not is_valid:
            return self.error_result(error_msg, error_type="ConfigurationError")

        base_url = self.settings.get("base_url", DEFAULT_BASE_URL)
        app_info = _build_app_info()

        try:
            ip_request = _format_ip_for_request(ip)
        except Exception:
            return self.error_result(
                f"{MSG_INVALID_IP}: {ip}", error_type="ValidationError"
            )

        payload = {
            "urls": {"endpoint": [ip_request]},
            "app_info": app_info,
        }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            with _mtls_cert_files(
                self.credentials["certificate"], self.credentials["key"]
            ) as cert:
                # Fetch taxonomy first (required to interpret results)
                taxonomy = await _fetch_taxonomy(
                    self.http_request, base_url, app_info, timeout, cert=cert
                )

                # Query reputation
                response = await self.http_request(
                    url=f"{base_url}{ENDPOINT_QUERY_REPUTATION_V3}",
                    method="POST",
                    json_data=payload,
                    timeout=timeout,
                    cert=cert,
                )
            result = response.json()

            # Parse response using taxonomy
            reputation = _parse_reputation_response(result, taxonomy, ip)

            return self.success_result(
                data=reputation,
                message=f"{ip} has a {reputation['threat_level']} threat level",
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("talos_ip_not_found", ip=ip)
                return self.success_result(
                    not_found=True,
                    data={
                        "observable": ip,
                        "threat_level": "",
                        "threat_categories": "",
                        "aup_categories": "",
                    },
                )
            self.log_error("talos_ip_reputation_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("talos_ip_reputation_failed", error=e)
            return self.error_result(e)

class DomainReputationAction(IntegrationAction):
    """Look up domain reputation in Cisco Talos Intelligence.

    Queries the Talos reputation API for threat level, threat categories,
    and acceptable use policy categories associated with a domain.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get domain reputation from Talos.

        Args:
            **kwargs: Must contain:
                - domain (str): Domain name to look up.

        Returns:
            Result with threat level, categories, and AUP data.
        """
        domain = kwargs.get("domain")
        is_valid, error_msg = _validate_domain(domain)
        if not is_valid:
            return self.error_result(error_msg, error_type="ValidationError")

        is_valid, error_msg = _validate_credentials(self.credentials)
        if not is_valid:
            return self.error_result(error_msg, error_type="ConfigurationError")

        base_url = self.settings.get("base_url", DEFAULT_BASE_URL)
        app_info = _build_app_info()
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        payload = {
            "urls": [{"raw_url": domain}],
            "app_info": app_info,
        }

        try:
            with _mtls_cert_files(
                self.credentials["certificate"], self.credentials["key"]
            ) as cert:
                # Fetch taxonomy first
                taxonomy = await _fetch_taxonomy(
                    self.http_request, base_url, app_info, timeout, cert=cert
                )

                # Query reputation
                response = await self.http_request(
                    url=f"{base_url}{ENDPOINT_QUERY_REPUTATION_V3}",
                    method="POST",
                    json_data=payload,
                    timeout=timeout,
                    cert=cert,
                )
            result = response.json()

            reputation = _parse_reputation_response(result, taxonomy, domain)

            return self.success_result(
                data=reputation,
                message=f"{domain} has a {reputation['threat_level']} threat level",
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("talos_domain_not_found", domain=domain)
                return self.success_result(
                    not_found=True,
                    data={
                        "observable": domain,
                        "threat_level": "",
                        "threat_categories": "",
                        "aup_categories": "",
                    },
                )
            self.log_error("talos_domain_reputation_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("talos_domain_reputation_failed", error=e)
            return self.error_result(e)

class UrlReputationAction(IntegrationAction):
    """Look up URL reputation in Cisco Talos Intelligence.

    Queries the Talos reputation API for threat level, threat categories,
    and acceptable use policy categories associated with a URL.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get URL reputation from Talos.

        Args:
            **kwargs: Must contain:
                - url (str): URL to look up (must have scheme and netloc).

        Returns:
            Result with threat level, categories, and AUP data.
        """
        url = kwargs.get("url")
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return self.error_result(error_msg, error_type="ValidationError")

        is_valid, error_msg = _validate_credentials(self.credentials)
        if not is_valid:
            return self.error_result(error_msg, error_type="ConfigurationError")

        base_url = self.settings.get("base_url", DEFAULT_BASE_URL)
        app_info = _build_app_info()
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        payload = {
            "urls": [{"raw_url": url}],
            "app_info": app_info,
        }

        try:
            with _mtls_cert_files(
                self.credentials["certificate"], self.credentials["key"]
            ) as cert:
                # Fetch taxonomy first
                taxonomy = await _fetch_taxonomy(
                    self.http_request, base_url, app_info, timeout, cert=cert
                )

                # Query reputation
                response = await self.http_request(
                    url=f"{base_url}{ENDPOINT_QUERY_REPUTATION_V3}",
                    method="POST",
                    json_data=payload,
                    timeout=timeout,
                    cert=cert,
                )
            result = response.json()

            reputation = _parse_reputation_response(result, taxonomy, url)

            return self.success_result(
                data=reputation,
                message=f"{url} has a {reputation['threat_level']} threat level",
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("talos_url_not_found", url=url)
                return self.success_result(
                    not_found=True,
                    data={
                        "observable": url,
                        "threat_level": "",
                        "threat_categories": "",
                        "aup_categories": "",
                    },
                )
            self.log_error("talos_url_reputation_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("talos_url_reputation_failed", error=e)
            return self.error_result(e)

"""VirusTotal integration actions for threat intelligence lookups."""

import base64
from typing import Any

import httpx
import validators

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

logger = get_logger(__name__)

VIRUSTOTAL_BASE_URL = "https://www.virustotal.com/api/v3/"
DEFAULT_TIMEOUT = 30

# ============================================================================
# VALIDATION UTILITIES
# ============================================================================

def _validate_ip_safe(ip_address: str) -> tuple[bool, str]:
    """Validate IP address format.

    Args:
        ip_address: IP address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not ip_address or not isinstance(ip_address, str):
        return False, "IP address must be a non-empty string"
    if validators.ipv4(ip_address) or validators.ipv6(ip_address):
        return True, ""
    return False, "Invalid IP address format"

def _validate_domain_safe(domain: str) -> tuple[bool, str]:
    """Validate domain format.

    Args:
        domain: Domain to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not domain or not isinstance(domain, str):
        return False, "Domain must be a non-empty string"
    if validators.domain(domain):
        return True, ""
    return False, "Invalid domain format"

def _validate_url_safe(url: str) -> tuple[bool, str]:
    """Validate URL format.

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string"
    if validators.url(url):
        return True, ""
    return False, "Invalid URL format"

def _validate_hash_safe(file_hash: str) -> tuple[bool, str]:
    """Validate file hash format (MD5, SHA1, or SHA256).

    Args:
        file_hash: File hash to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not file_hash or not isinstance(file_hash, str):
        return False, "File hash must be a non-empty string"

    hash_length = len(file_hash)
    if hash_length == 32:  # MD5
        hash_type = "MD5"
    elif hash_length == 40:  # SHA1
        hash_type = "SHA1"
    elif hash_length == 64:  # SHA256
        hash_type = "SHA256"
    else:
        return (
            False,
            "File hash must be MD5 (32 chars), SHA1 (40 chars), or SHA256 (64 chars)",
        )

    # Verify all characters are hexadecimal
    if not all(c in "0123456789abcdefABCDEF" for c in file_hash):
        return (
            False,
            f"Invalid {hash_type} hash format - must contain only hexadecimal characters",
        )

    return True, ""

def _url_to_base64_id(url: str) -> str:
    """Convert URL to base64 identifier for VirusTotal API.

    Args:
        url: URL to convert

    Returns:
        Base64-encoded URL identifier (without padding)
    """
    # Remove padding as per VirusTotal API requirements
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for VirusTotal API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check VirusTotal API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "healthy": False,
                "status": "error",
                "error": "Missing API key in credentials",
                "error_type": "ConfigurationError",
                "data": {"healthy": False},
            }

        try:
            response = await self.http_request(
                f"{VIRUSTOTAL_BASE_URL}users/current",
                headers={"x-apikey": api_key},
            )
            result = response.json()

            return {
                "healthy": True,
                "status": "success",
                "message": "VirusTotal API is accessible",
                "data": {
                    "healthy": True,
                    "api_version": "v3",
                    "quota": result.get("data", {})
                    .get("attributes", {})
                    .get("quotas", {}),
                },
            }

        except Exception as e:
            logger.error("virustotal_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class IpReputationAction(IntegrationAction):
    """Look up IP address reputation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get IP address reputation from VirusTotal.

        Args:
            **kwargs: Must contain 'ip_address' or 'ip'

        Returns:
            Result with IP reputation data or error
        """
        # Validate inputs - accept both 'ip' and 'ip_address' parameter names
        ip_address = kwargs.get("ip_address") or kwargs.get("ip")
        is_valid, error_msg = _validate_ip_safe(ip_address)
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "status": "error",
                "error": "Missing API key in credentials",
                "error_type": "ConfigurationError",
            }

        try:
            response = await self.http_request(
                f"{VIRUSTOTAL_BASE_URL}ip_addresses/{ip_address}",
                headers={"x-apikey": api_key},
            )
            result = response.json()

            # Extract key security information
            attributes = result.get("data", {}).get("attributes", {})
            last_analysis_stats = attributes.get("last_analysis_stats", {})

            return {
                "status": "success",
                "ip_address": ip_address,
                "reputation_summary": {
                    "malicious": last_analysis_stats.get("malicious", 0),
                    "suspicious": last_analysis_stats.get("suspicious", 0),
                    "harmless": last_analysis_stats.get("harmless", 0),
                    "undetected": last_analysis_stats.get("undetected", 0),
                },
                "network_info": {
                    "asn": attributes.get("asn"),
                    "as_owner": attributes.get("as_owner"),
                    "country": attributes.get("country"),
                },
                "last_analysis_date": attributes.get("last_analysis_date"),
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "virustotal_ip_not_found",
                    ip_address=ip_address,
                )
                return {
                    "status": "success",
                    "not_found": True,
                    "ip_address": ip_address,
                    "reputation_summary": {
                        "malicious": 0,
                        "suspicious": 0,
                        "harmless": 0,
                        "undetected": 0,
                    },
                    "network_info": {},
                }
            logger.error(
                "virustotal_ip_reputation_lookup_failed_for",
                ip_address=ip_address,
                error=str(e),
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}
        except Exception as e:
            logger.error(
                "virustotal_ip_reputation_lookup_failed_for",
                ip_address=ip_address,
                error=str(e),
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}

class DomainReputationAction(IntegrationAction):
    """Look up domain reputation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get domain reputation from VirusTotal.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with domain reputation data or error
        """
        # Validate inputs
        domain = kwargs.get("domain")
        is_valid, error_msg = _validate_domain_safe(domain)
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "status": "error",
                "error": "Missing API key in credentials",
                "error_type": "ConfigurationError",
            }

        try:
            response = await self.http_request(
                f"{VIRUSTOTAL_BASE_URL}domains/{domain}",
                headers={"x-apikey": api_key},
            )
            result = response.json()

            # Extract key security information
            attributes = result.get("data", {}).get("attributes", {})
            last_analysis_stats = attributes.get("last_analysis_stats", {})

            return {
                "status": "success",
                "domain": domain,
                "reputation_summary": {
                    "malicious": last_analysis_stats.get("malicious", 0),
                    "suspicious": last_analysis_stats.get("suspicious", 0),
                    "harmless": last_analysis_stats.get("harmless", 0),
                    "undetected": last_analysis_stats.get("undetected", 0),
                },
                "categories": attributes.get("categories", {}),
                "creation_date": attributes.get("creation_date"),
                "last_analysis_date": attributes.get("last_analysis_date"),
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "virustotal_domain_not_found",
                    domain=domain,
                )
                return {
                    "status": "success",
                    "not_found": True,
                    "domain": domain,
                    "reputation_summary": {
                        "malicious": 0,
                        "suspicious": 0,
                        "harmless": 0,
                        "undetected": 0,
                    },
                    "categories": {},
                }
            logger.error(
                "virustotal_domain_reputation_lookup_failed_for",
                domain=domain,
                error=str(e),
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}
        except Exception as e:
            logger.error(
                "virustotal_domain_reputation_lookup_failed_for",
                domain=domain,
                error=str(e),
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}

class UrlReputationAction(IntegrationAction):
    """Look up URL reputation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get URL reputation from VirusTotal.

        Args:
            **kwargs: Must contain 'url'

        Returns:
            Result with URL reputation data or error
        """
        # Validate inputs
        url = kwargs.get("url")
        is_valid, error_msg = _validate_url_safe(url)
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "status": "error",
                "error": "Missing API key in credentials",
                "error_type": "ConfigurationError",
            }

        try:
            # Convert URL to base64 identifier
            url_id = _url_to_base64_id(url)

            response = await self.http_request(
                f"{VIRUSTOTAL_BASE_URL}urls/{url_id}",
                headers={"x-apikey": api_key},
            )
            result = response.json()

            # Extract key security information
            attributes = result.get("data", {}).get("attributes", {})
            last_analysis_stats = attributes.get("last_analysis_stats", {})

            return {
                "status": "success",
                "url": url,
                "reputation_summary": {
                    "malicious": last_analysis_stats.get("malicious", 0),
                    "suspicious": last_analysis_stats.get("suspicious", 0),
                    "harmless": last_analysis_stats.get("harmless", 0),
                    "undetected": last_analysis_stats.get("undetected", 0),
                },
                "categories": attributes.get("categories", {}),
                "last_analysis_date": attributes.get("last_analysis_date"),
                "first_submission_date": attributes.get("first_submission_date"),
                "times_submitted": attributes.get("times_submitted", 0),
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "virustotal_url_not_found",
                    url=url,
                )
                return {
                    "status": "success",
                    "not_found": True,
                    "url": url,
                    "reputation_summary": {
                        "malicious": 0,
                        "suspicious": 0,
                        "harmless": 0,
                        "undetected": 0,
                    },
                    "categories": {},
                }
            logger.error(
                "virustotal_url_reputation_lookup_failed_for", url=url, error=str(e)
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}
        except Exception as e:
            logger.error(
                "virustotal_url_reputation_lookup_failed_for", url=url, error=str(e)
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}

class FileReputationAction(IntegrationAction):
    """Look up file hash reputation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get file hash reputation from VirusTotal.

        Args:
            **kwargs: Must contain 'file_hash' (MD5, SHA1, or SHA256)

        Returns:
            Result with file reputation data or error
        """
        # Validate inputs
        file_hash = kwargs.get("file_hash")
        is_valid, error_msg = _validate_hash_safe(file_hash)
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "status": "error",
                "error": "Missing API key in credentials",
                "error_type": "ConfigurationError",
            }

        try:
            response = await self.http_request(
                f"{VIRUSTOTAL_BASE_URL}files/{file_hash}",
                headers={"x-apikey": api_key},
            )
            result = response.json()

            # Extract key security information
            attributes = result.get("data", {}).get("attributes", {})
            last_analysis_stats = attributes.get("last_analysis_stats", {})

            return {
                "status": "success",
                "file_hash": file_hash,
                "reputation_summary": {
                    "malicious": last_analysis_stats.get("malicious", 0),
                    "suspicious": last_analysis_stats.get("suspicious", 0),
                    "harmless": last_analysis_stats.get("harmless", 0),
                    "undetected": last_analysis_stats.get("undetected", 0),
                },
                "file_info": {
                    "size": attributes.get("size"),
                    "type_description": attributes.get("type_description"),
                    "type_tag": attributes.get("type_tag"),
                    "creation_date": attributes.get("creation_date"),
                    "first_submission_date": attributes.get("first_submission_date"),
                },
                "last_analysis_date": attributes.get("last_analysis_date"),
                "times_submitted": attributes.get("times_submitted", 0),
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "virustotal_file_not_found",
                    file_hash=file_hash,
                )
                return {
                    "status": "success",
                    "not_found": True,
                    "file_hash": file_hash,
                    "reputation_summary": {
                        "malicious": 0,
                        "suspicious": 0,
                        "harmless": 0,
                        "undetected": 0,
                    },
                    "file_info": {},
                }
            logger.error(
                "virustotal_file_reputation_lookup_failed_for",
                file_hash=file_hash,
                error=str(e),
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}
        except Exception as e:
            logger.error(
                "virustotal_file_reputation_lookup_failed_for",
                file_hash=file_hash,
                error=str(e),
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}

class SubmitUrlAnalysisAction(IntegrationAction):
    """Submit URL for analysis."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Submit URL for analysis to VirusTotal.

        Args:
            **kwargs: Must contain 'url'

        Returns:
            Result with analysis ID or error
        """
        # Validate inputs
        url = kwargs.get("url")
        is_valid, error_msg = _validate_url_safe(url)
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "status": "error",
                "error": "Missing API key in credentials",
                "error_type": "ConfigurationError",
            }

        try:
            # VT's POST /urls requires application/x-www-form-urlencoded, not JSON
            response = await self.http_request(
                f"{VIRUSTOTAL_BASE_URL}urls",
                method="POST",
                headers={"x-apikey": api_key},
                data={"url": url},
            )
            result = response.json()

            # Extract analysis ID for later retrieval
            analysis_id = result.get("data", {}).get("id")

            return {
                "status": "success",
                "url": url,
                "analysis_id": analysis_id,
                "message": "URL submitted for analysis. Use get_analysis_report with the analysis_id to get results.",
                "full_data": result,
            }

        except Exception as e:
            logger.error("virustotal_url_submission_failed_for", url=url, error=str(e))
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}

class GetAnalysisReportAction(IntegrationAction):
    """Get analysis report for submitted URL."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get analysis report from VirusTotal.

        Args:
            **kwargs: Must contain 'analysis_id'

        Returns:
            Result with analysis report or error
        """
        # Validate inputs
        analysis_id = kwargs.get("analysis_id")
        if not analysis_id or not isinstance(analysis_id, str):
            return {
                "status": "error",
                "error": "analysis_id must be a non-empty string",
                "error_type": "ValidationError",
            }

        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "status": "error",
                "error": "Missing API key in credentials",
                "error_type": "ConfigurationError",
            }

        try:
            response = await self.http_request(
                f"{VIRUSTOTAL_BASE_URL}analyses/{analysis_id}",
                headers={"x-apikey": api_key},
            )
            result = response.json()

            # Extract key analysis information
            attributes = result.get("data", {}).get("attributes", {})
            stats = attributes.get("stats", {})

            return {
                "status": "success",
                "analysis_id": analysis_id,
                "analysis_status": attributes.get("status"),
                "analysis_stats": {
                    "malicious": stats.get("malicious", 0),
                    "suspicious": stats.get("suspicious", 0),
                    "harmless": stats.get("harmless", 0),
                    "undetected": stats.get("undetected", 0),
                },
                "analysis_date": attributes.get("date"),
                "full_data": result,
            }

        except Exception as e:
            logger.error(
                "virustotal_analysis_report_retrieval_failed_for",
                analysis_id=analysis_id,
                error=str(e),
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}

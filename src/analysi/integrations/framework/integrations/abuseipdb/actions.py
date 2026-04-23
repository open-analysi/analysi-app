"""AbuseIPDB integration actions.

This module provides ThreatIntel actions for IP reputation lookups and abuse reporting.
"""

import ipaddress
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

logger = get_logger(__name__)

# Constants
ABUSEIPDB_BASE_URL = "https://api.abuseipdb.com/api/v2"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_AGE_DAYS = 30

# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def _validate_ip_safe(ip: str | None) -> tuple[bool, str]:
    """Validate IP address (IPv4 or IPv6).

    Args:
        ip: IP address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not ip or not isinstance(ip, str) or not ip.strip():
        return False, "IP address is required"

    try:
        ipaddress.ip_address(ip.strip())
        return True, ""
    except ValueError:
        return False, f"Invalid IP address format: {ip}"

def _validate_categories(categories: str | None) -> tuple[bool, str]:
    """Validate category IDs format.

    Args:
        categories: Comma-separated category IDs

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not categories or not isinstance(categories, str) or not categories.strip():
        return False, "Categories are required"

    # Split by comma and validate each part
    parts = [p.strip() for p in categories.split(",")]

    # Check for empty parts (like "4,,18" or "," or "4,")
    if not all(parts):
        return False, f"Invalid categories format: {categories}"

    # Check that all parts are numeric
    if not all(p.isdigit() for p in parts):
        return False, f"Invalid categories format: {categories}"

    return True, ""

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for AbuseIPDB API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check AbuseIPDB API connectivity.

        Tests connectivity by checking 127.0.0.1 (localhost).
        Uses GET /check instead of POST /report to avoid consuming rate limit quota.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "status": "error",
                "error": "Missing API key in credentials",
                "error_type": "ConfigurationError",
                "healthy": False,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            # Test connectivity by checking 127.0.0.1 (localhost - safe and doesn't pollute reports)
            # Uses GET /check instead of POST /report to conserve rate limit quota
            response = await self.http_request(
                f"{ABUSEIPDB_BASE_URL}/check",
                headers={
                    "Key": api_key,
                    "Accept": "application/json",
                },
                params={
                    "ipAddress": "127.0.0.1",
                    "maxAgeInDays": 1,  # Minimal lookback to reduce response size
                },
                timeout=timeout,
            )
            result = response.json()

            return {
                "status": "success",
                "message": "AbuseIPDB API is accessible",
                "healthy": True,
                "data": result,
            }

        except Exception as e:
            logger.error("AbuseIPDB health check failed", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "healthy": False,
            }

class LookupIpAction(IntegrationAction):
    """Look up IP address reputation and abuse reports."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get IP address reputation from AbuseIPDB.

        Args:
            **kwargs: Must contain:
                - ip (str): IPv4 or IPv6 address
                - days (int, optional): Lookback period (default: 10)

        Returns:
            Result with IP reputation data or error
        """
        # Extract IP address - support both 'ip' and 'ip_address' parameter names
        ip = kwargs.get("ip") or kwargs.get("ip_address")

        # Validate IP address
        is_valid, error_msg = _validate_ip_safe(ip)
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        # Extract other parameters
        days = kwargs.get("days", 10)  # Default to 10 days lookback
        api_key = self.credentials.get("api_key")

        if not api_key:
            return {
                "status": "error",
                "error": "Missing API key in credentials",
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            # Call AbuseIPDB check endpoint
            response = await self.http_request(
                f"{ABUSEIPDB_BASE_URL}/check",
                headers={
                    "Key": api_key,
                    "Accept": "application/json",
                },
                params={
                    "ipAddress": ip,
                    "maxAgeInDays": days,
                },
                timeout=timeout,
            )
            result = response.json()

            # Extract data from response
            data = result.get("data", {})

            return {
                "status": "success",
                "ip_address": data.get("ipAddress", ip),
                "abuse_confidence_score": data.get("abuseConfidenceScore", 0),
                "total_reports": data.get("totalReports", 0),
                "num_distinct_users": data.get("numDistinctUsers", 0),
                "is_public": data.get("isPublic"),
                "is_whitelisted": data.get("isWhitelisted"),
                "country_code": data.get("countryCode"),
                "usage_type": data.get("usageType"),
                "isp": data.get("isp"),
                "domain": data.get("domain"),
                "hostnames": data.get("hostnames", []),
                "last_reported_at": data.get("lastReportedAt"),
                "full_data": result,  # Include full response for advanced users
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("abuseipdb_ip_not_found", ip=ip)
                return {
                    "status": "success",
                    "not_found": True,
                    "ip_address": ip,
                    "abuse_confidence_score": 0,
                    "total_reports": 0,
                    "num_distinct_users": 0,
                }
            logger.error("AbuseIPDB IP lookup failed", ip=ip, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("AbuseIPDB IP lookup failed", ip=ip, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ReportIpAction(IntegrationAction):
    """Report an IP address for abusive behavior."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Report an IP address to AbuseIPDB.

        Args:
            **kwargs: Must contain:
                - ip (str): IP address to report
                - categories (str): Comma-separated category IDs
                - comment (str, optional): Description of abuse

        Returns:
            Result with report confirmation or error
        """
        # Extract parameters
        ip = kwargs.get("ip")
        categories = kwargs.get("categories")
        comment = kwargs.get("comment", "")  # Comment is optional

        # Validate IP address
        is_valid, error_msg = _validate_ip_safe(ip)
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        # Validate categories
        is_valid, error_msg = _validate_categories(categories)
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        # Extract API key
        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "status": "error",
                "error": "Missing API key in credentials",
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            # Call AbuseIPDB report endpoint
            # AbuseIPDB expects form-encoded data, not JSON
            response = await self.http_request(
                f"{ABUSEIPDB_BASE_URL}/report",
                method="POST",
                headers={
                    "Key": api_key,
                    "Accept": "application/json",
                },
                data={
                    "ip": ip,
                    "categories": categories,
                    "comment": comment,
                },
                timeout=timeout,
            )
            result = response.json()

            # Extract data from response
            data = result.get("data", {})

            return {
                "status": "success",
                "ip_address": data.get("ipAddress", ip),
                "abuse_confidence_score": data.get("abuseConfidenceScore", 0),
                "message": "IP successfully reported to AbuseIPDB",
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("abuseipdb_report_not_found", ip=ip)
                return {
                    "status": "success",
                    "not_found": True,
                    "ip_address": ip,
                    "abuse_confidence_score": 0,
                    "message": "Resource not found",
                    "data": {},
                }
            logger.error("AbuseIPDB IP report failed", ip=ip, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("AbuseIPDB IP report failed", ip=ip, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

# ============================================================================
# STUB ACTIONS (ThreatIntel Archetype Compliance)
# ============================================================================
# AbuseIPDB only supports IP lookups, not domain/file/URL.
# These stubs satisfy archetype requirements while providing clear error messages.

class LookupDomainAction(IntegrationAction):
    """Stub action - AbuseIPDB does not support domain lookups."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Return not supported error for domain lookups.

        Args:
            **kwargs: Ignored

        Returns:
            Error dict indicating feature not supported
        """
        return {
            "status": "error",
            "error": "Domain lookups are not supported by AbuseIPDB. Use lookup_ip instead.",
            "error_type": "NotSupportedError",
            "supported_lookups": ["ip"],
        }

class LookupFileHashAction(IntegrationAction):
    """Stub action - AbuseIPDB does not support file hash lookups."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Return not supported error for file hash lookups.

        Args:
            **kwargs: Ignored

        Returns:
            Error dict indicating feature not supported
        """
        return {
            "status": "error",
            "error": "File hash lookups are not supported by AbuseIPDB. Use lookup_ip instead.",
            "error_type": "NotSupportedError",
            "supported_lookups": ["ip"],
        }

class LookupUrlAction(IntegrationAction):
    """Stub action - AbuseIPDB does not support URL lookups."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Return not supported error for URL lookups.

        Args:
            **kwargs: Ignored

        Returns:
            Error dict indicating feature not supported
        """
        return {
            "status": "error",
            "error": "URL lookups are not supported by AbuseIPDB. Use lookup_ip instead.",
            "error_type": "NotSupportedError",
            "supported_lookups": ["ip"],
        }

"""MaxMind integration actions.

This module provides Geolocation actions for IP address geolocation using MaxMind GeoIP2 Web Services API.
"""

import ipaddress
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    DEFAULT_HEALTH_CHECK_IP,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    FIELD_AS_NUMBER,
    FIELD_AS_ORG,
    FIELD_CITY_NAME,
    FIELD_CONTINENT_NAME,
    FIELD_COUNTRY_ISO_CODE,
    FIELD_COUNTRY_NAME,
    FIELD_LATITUDE,
    FIELD_LONGITUDE,
    FIELD_POSTAL_CODE,
    FIELD_STATE_ISO_CODE,
    FIELD_STATE_NAME,
    FIELD_TIME_ZONE,
    MSG_INVALID_IP,
    MSG_MISSING_LICENSE_KEY,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# MaxMind GeoIP2 Precision Web Services API base URL
GEOIP2_BASE_URL = "https://geoip.maxmind.com/geoip/v2.1"

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
        return False, MSG_INVALID_IP

    try:
        ipaddress.ip_address(ip.strip())
        return True, ""
    except ValueError:
        return False, f"{MSG_INVALID_IP}: {ip}"

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for MaxMind API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check MaxMind API connectivity.

        Tests connectivity by geolocating a known IP address (8.8.8.8 by default).

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        account_id = self.settings.get("account_id")
        license_key = self.credentials.get("license_key")

        if not account_id or not license_key:
            return {
                "status": STATUS_ERROR,
                "error": "Missing account_id in settings or license_key in credentials",
                "error_type": ERROR_TYPE_CONFIGURATION,
                "healthy": False,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        test_ip = self.settings.get("test_ip", DEFAULT_HEALTH_CHECK_IP)

        try:
            # Test connectivity by geolocating a known IP (8.8.8.8)
            response = await self.http_request(
                f"{GEOIP2_BASE_URL}/city/{test_ip}",
                auth=(account_id, license_key),
                timeout=timeout,
            )
            result = response.json()

            return {
                "status": STATUS_SUCCESS,
                "message": "MaxMind API is accessible",
                "healthy": True,
                "data": result,
            }

        except Exception as e:
            logger.error("MaxMind health check failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
                "healthy": False,
            }

class GeolocateIpAction(IntegrationAction):
    """Geolocate IP address using MaxMind GeoIP2 API."""

    async def execute(self, **kwargs) -> dict[str, Any]:  # noqa: C901
        """Get IP address geolocation from MaxMind.

        Args:
            **kwargs: Must contain:
                - ip (str): IPv4 or IPv6 address

        Returns:
            Result with geolocation data or error
        """
        # Extract IP address
        ip = kwargs.get("ip")

        # Validate IP address
        is_valid, error_msg = _validate_ip_safe(ip)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Extract credentials
        account_id = self.settings.get("account_id")
        license_key = self.credentials.get("license_key")

        if not account_id or not license_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_LICENSE_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            # Call MaxMind GeoIP2 City endpoint
            response = await self.http_request(
                f"{GEOIP2_BASE_URL}/city/{ip}",
                auth=(account_id, license_key),
                timeout=timeout,
            )
            result = response.json()

            # Extract data from response (following MaxMind GeoIP2 response structure)
            city = result.get("city", {})
            subdivisions = result.get("subdivisions", [])
            country = result.get("country", {})
            continent = result.get("continent", {})
            location = result.get("location", {})
            postal = result.get("postal", {})
            traits = result.get("traits", {})

            # Get most specific subdivision (state/province)
            subdivision = subdivisions[0] if subdivisions else {}

            # Build response matching upstream format
            response_data = {
                "status": STATUS_SUCCESS,
                "ip_address": ip,
            }

            # Add geolocation fields
            if city.get("names", {}).get("en"):
                response_data[FIELD_CITY_NAME] = city["names"]["en"]

            if subdivision.get("names", {}).get("en"):
                response_data[FIELD_STATE_NAME] = subdivision["names"]["en"]
            if subdivision.get("iso_code"):
                response_data[FIELD_STATE_ISO_CODE] = subdivision["iso_code"]

            if country.get("names", {}).get("en"):
                response_data[FIELD_COUNTRY_NAME] = country["names"]["en"]
            if country.get("iso_code"):
                response_data[FIELD_COUNTRY_ISO_CODE] = country["iso_code"]

            if continent.get("names", {}).get("en"):
                response_data[FIELD_CONTINENT_NAME] = continent["names"]["en"]

            if location.get("latitude") is not None:
                response_data[FIELD_LATITUDE] = location["latitude"]
            if location.get("longitude") is not None:
                response_data[FIELD_LONGITUDE] = location["longitude"]
            if location.get("time_zone"):
                response_data[FIELD_TIME_ZONE] = location["time_zone"]

            if postal.get("code"):
                response_data[FIELD_POSTAL_CODE] = postal["code"]

            if traits.get("autonomous_system_number"):
                response_data[FIELD_AS_NUMBER] = traits["autonomous_system_number"]
            if traits.get("autonomous_system_organization"):
                response_data[FIELD_AS_ORG] = traits["autonomous_system_organization"]
            if traits.get("domain"):
                response_data["domain"] = traits["domain"]

            # Include full response for advanced users
            response_data["full_data"] = result

            return response_data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("maxmind_ip_not_found", ip=ip)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ip_address": ip,
                }
            logger.error("MaxMind IP geolocation failed", ip=ip, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("MaxMind IP geolocation failed", ip=ip, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

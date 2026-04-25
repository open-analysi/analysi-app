"""MAC Vendors integration actions.

This module provides MAC address OUI lookup actions using the macvendors.com
API. Works without authentication (free tier: 1000 req/day). An optional API
key unlocks higher rate limits.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.mac_vendors.constants import (
    DEFAULT_REQUEST_TIMEOUT,
    HEALTH_CHECK_MAC,
    MAC_VENDORS_BASE_URL,
    VENDOR_NOT_FOUND_TEXT,
)

logger = get_logger(__name__)

class HealthCheckAction(IntegrationAction):
    """Health check for MAC Vendors API connectivity."""

    def get_http_headers(self) -> dict[str, str]:
        """Add Bearer auth header when API key is configured."""
        api_key = self.credentials.get("api_key")
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity to the MAC Vendors API.

        Queries a well-known VMware MAC address to verify the API is reachable.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        timeout = self.settings.get("timeout", DEFAULT_REQUEST_TIMEOUT)

        try:
            response = await self.http_request(
                f"{MAC_VENDORS_BASE_URL}/{HEALTH_CHECK_MAC}",
                timeout=timeout,
            )
            # The API returns plain text (vendor name or "vendor not found")
            vendor_text = response.text.strip()

            return {
                "status": "success",
                "healthy": True,
                "message": "MAC Vendors API is accessible",
                "data": {"vendor": vendor_text},
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "mac_vendors_health_check_http_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            return {
                "status": "error",
                "healthy": False,
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "error_type": "HTTPStatusError",
            }
        except Exception as e:
            logger.error("mac_vendors_health_check_failed", error=str(e))
            return {
                "status": "error",
                "healthy": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class LookupMacAction(IntegrationAction):
    """Look up the vendor/manufacturer for a MAC address OUI."""

    def get_http_headers(self) -> dict[str, str]:
        """Add Bearer auth header when API key is configured."""
        api_key = self.credentials.get("api_key")
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Query the MAC vendor based on the OUI portion of the MAC address.

        The macvendors.com API accepts full MAC addresses or just the OUI prefix.
        It returns the vendor name as plain text, or "vendor not found" if unknown.

        Args:
            **kwargs: Must contain:
                - mac (str): MAC address to look up (e.g. "d0:a6:37:aa:bb:cc")

        Returns:
            Result with vendor name if found, or not_found=True if unknown.
            A missing vendor is NOT an error — callers can check not_found.
        """
        mac = kwargs.get("mac")
        if not mac:
            return {
                "status": "error",
                "error": "Missing required parameter: mac",
                "error_type": "ValidationError",
            }

        mac = mac.strip()
        timeout = self.settings.get("timeout", DEFAULT_REQUEST_TIMEOUT)

        try:
            response = await self.http_request(
                f"{MAC_VENDORS_BASE_URL}/{mac}",
                timeout=timeout,
            )
            # The API returns plain text
            vendor_text = response.text.strip()

            if VENDOR_NOT_FOUND_TEXT in vendor_text.lower():
                logger.info("mac_vendors_vendor_not_found", mac=mac)
                return {
                    "status": "success",
                    "not_found": True,
                    "vendor_found": False,
                    "mac": mac,
                    "vendor": None,
                }

            return {
                "status": "success",
                "vendor_found": True,
                "mac": mac,
                "vendor": vendor_text,
            }

        except httpx.HTTPStatusError as e:
            # 404 from the API means vendor not found (some API versions return 404)
            if e.response.status_code == 404:
                logger.info("mac_vendors_vendor_not_found_404", mac=mac)
                return {
                    "status": "success",
                    "not_found": True,
                    "vendor_found": False,
                    "mac": mac,
                    "vendor": None,
                }
            # 429 = rate limit exceeded
            if e.response.status_code == 429:
                logger.warning("mac_vendors_rate_limit_exceeded", mac=mac)
                return {
                    "status": "error",
                    "error": "Rate limit exceeded. The free tier allows 1000 requests/day.",
                    "error_type": "RateLimitError",
                    "mac": mac,
                }
            logger.error(
                "mac_vendors_lookup_http_error",
                mac=mac,
                status_code=e.response.status_code,
                error=str(e),
            )
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "error_type": "HTTPStatusError",
                "mac": mac,
            }
        except Exception as e:
            logger.error("mac_vendors_lookup_failed", mac=mac, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "mac": mac,
            }

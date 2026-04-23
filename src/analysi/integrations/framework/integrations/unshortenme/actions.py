"""unshorten.me integration actions.

This module expands shortened URLs to their final destination using the
unshorten.me public API. No authentication is required.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

logger = get_logger(__name__)

# Constants
UNSHORTEN_ME_BASE_URL = "https://unshorten.me/json/"
DEFAULT_TIMEOUT = 30

# Known URL used for connectivity testing (resolves to https://unshorten.me/)
HEALTH_CHECK_SHORT_URL = "goo.gl/IGL1lE"

def _strip_scheme(url: str) -> str:
    """Remove the http:// or https:// scheme prefix from a URL.

    The unshorten.me API accepts URLs without scheme — the scheme is part of
    the path appended to the base URL.

    Args:
        url: URL string, may or may not contain a scheme prefix.

    Returns:
        URL string with any leading http:// or https:// removed.
    """
    if url.startswith("https://"):
        return url[8:]
    if url.startswith("http://"):
        return url[7:]
    return url

class HealthCheckAction(IntegrationAction):
    """Health check for unshorten.me API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity to the unshorten.me API.

        Expands a known short URL (goo.gl/IGL1lE) and verifies that the
        resolved URL matches the expected value (https://unshorten.me/).

        Returns:
            Result with status=success if healthy, status=error if unhealthy.
        """
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        url = UNSHORTEN_ME_BASE_URL + HEALTH_CHECK_SHORT_URL

        try:
            response = await self.http_request(url, timeout=timeout)
            data = response.json()

            if "error" in data:
                return {
                    "status": "error",
                    "error": f"API returned error: {data['error']}",
                    "error_type": "APIError",
                    "healthy": False,
                }

            resolved = data.get("resolved_url", "")
            if resolved != "https://unshorten.me/":
                return {
                    "status": "error",
                    "error": f"Unexpected resolved URL from health check: {resolved!r}",
                    "error_type": "UnexpectedResponse",
                    "healthy": False,
                }

            return {
                "status": "success",
                "message": "unshorten.me API is accessible",
                "healthy": True,
                "resolved_url": resolved,
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "unshortenme_health_check_http_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e}",
                "error_type": "HTTPStatusError",
                "healthy": False,
            }
        except httpx.RequestError as e:
            logger.error("unshortenme_health_check_request_error", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": "RequestError",
                "healthy": False,
            }
        except Exception as e:
            logger.error("unshortenme_health_check_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "healthy": False,
            }

class UnshortenUrlAction(IntegrationAction):
    """Expand a shortened URL to its final destination."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Resolve a shortened URL to its final destination.

        Args:
            **kwargs: Must contain:
                - url (str): The shortened URL to expand.

        Returns:
            Result dict with:
                - status: "success" or "error"
                - resolved_url: The final destination URL
                - requested_url: The original short URL as echoed by the API
                - success: Boolean from the API indicating resolution success
                - usage_count: Number of times this short URL has been looked up
                - remaining_calls: API rate-limit remaining calls
        """
        url = kwargs.get("url")
        if not url or not isinstance(url, str) or not url.strip():
            return {
                "status": "error",
                "error": "Missing required parameter: url",
                "error_type": "ValidationError",
            }

        url = url.strip()
        path = _strip_scheme(url)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)
        api_url = UNSHORTEN_ME_BASE_URL + path

        try:
            response = await self.http_request(api_url, timeout=timeout)
            data = response.json()

            if "error" in data:
                logger.error("unshortenme_api_error", url=url, error=data["error"])
                return {
                    "status": "error",
                    "error": f"API returned error: {data['error']}",
                    "error_type": "APIError",
                    "url": url,
                }

            return {
                "status": "success",
                "url": url,
                "resolved_url": data.get("resolved_url", ""),
                "requested_url": data.get("requested_url", ""),
                "success": data.get("success", False),
                "usage_count": data.get("usage_count"),
                "remaining_calls": data.get("remaining_calls"),
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "unshortenme_unshorten_http_error",
                url=url,
                status_code=e.response.status_code,
                error=str(e),
            )
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e}",
                "error_type": "HTTPStatusError",
                "url": url,
            }
        except httpx.RequestError as e:
            logger.error("unshortenme_unshorten_request_error", url=url, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": "RequestError",
                "url": url,
            }
        except Exception as e:
            logger.error("unshortenme_unshorten_failed", url=url, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "url": url,
            }

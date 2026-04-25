"""Have I Been Pwned integration actions for data breach lookups.
Library type: REST API (the upstream connector uses ``requests``; Naxos uses ``self.http_request()``).

HIBP provides breach data for email addresses and domains via its v3 API.
All calls are authenticated with the ``hibp-api-key`` header.
"""

from typing import Any
from urllib.parse import urlparse

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    AUTH_HEADER,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    ENDPOINT_BREACHED_ACCOUNT,
    ENDPOINT_BREACHES,
    HEALTH_CHECK_EMAIL,
    MSG_MISSING_API_KEY,
    MSG_MISSING_PARAM,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Base class with shared auth / URL helpers
# ---------------------------------------------------------------------------

class _HIBPBase(IntegrationAction):
    """Shared helpers for all Have I Been Pwned actions."""

    def get_http_headers(self) -> dict[str, str]:
        """Inject the API key into every outbound request."""
        api_key = self.credentials.get("api_key", "")
        return {AUTH_HEADER: api_key} if api_key else {}

    def get_timeout(self) -> int | float:
        """Return timeout, defaulting to HIBP-specific value."""
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        return self.settings.get("base_url", DEFAULT_BASE_URL).rstrip("/")

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

class HealthCheckAction(_HIBPBase):
    """Verify connectivity to the HIBP API and validate the API key.

    Mirrors the upstream ``_handle_test_connectivity``: looks up a known email
    with truncated response to confirm credentials work.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_api_key():
            return err

        try:
            url = f"{self.base_url}{ENDPOINT_BREACHED_ACCOUNT.format(email=HEALTH_CHECK_EMAIL)}"
            await self.http_request(
                url=url,
                params={"truncateResponse": "true"},
            )

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Connectivity and credentials test passed",
                },
            )
        except httpx.HTTPStatusError as e:
            # 404 means the test email has no breaches -- API is reachable and
            # credentials are valid, so this is still a successful health check.
            if e.response.status_code == 404:
                return self.success_result(
                    data={
                        "healthy": True,
                        "message": "Connectivity and credentials test passed (no breaches for test email)",
                    },
                )
            self.log_error("haveibeenpwned_health_check_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("haveibeenpwned_health_check_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LOOKUP EMAIL
# ============================================================================

class LookupEmailAction(_HIBPBase):
    """Search for breaches associated with an email address.

    Mirrors the upstream ``_lookup_email``.  A 404 from the API means the email
    has not appeared in any known breach -- returned as success with
    ``not_found=True`` so Cy scripts are not interrupted.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        email = kwargs.get("email")
        if not email:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="email"),
                error_type="ValidationError",
            )
        if err := self._require_api_key():
            return err

        truncate = kwargs.get("truncate", False)

        try:
            url = f"{self.base_url}{ENDPOINT_BREACHED_ACCOUNT.format(email=email)}"
            params: dict[str, str] = {}
            if not truncate:
                params["truncateResponse"] = "false"

            response = await self.http_request(url=url, params=params)
            breaches = response.json()

            return self.success_result(
                data={
                    "email": email,
                    "total_breaches": len(breaches),
                    "breaches": breaches,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("haveibeenpwned_email_not_found", email=email)
                return self.success_result(
                    not_found=True,
                    data={
                        "email": email,
                        "total_breaches": 0,
                        "breaches": [],
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("haveibeenpwned_lookup_email_failed", error=e)
            return self.error_result(e)

# ============================================================================
# LOOKUP DOMAIN
# ============================================================================

class LookupDomainAction(_HIBPBase):
    """Search for breaches associated with a domain.

    Mirrors the upstream ``_lookup_domain``.  Accepts either a bare domain or a
    full URL (the host is extracted and ``www.`` stripped automatically).
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

        # Normalise: extract host from URL if needed, strip www.
        domain = self._normalise_domain(domain)

        try:
            url = f"{self.base_url}{ENDPOINT_BREACHES}"
            response = await self.http_request(
                url=url,
                params={"domain": domain},
            )
            breaches = response.json()

            return self.success_result(
                data={
                    "domain": domain,
                    "total_breaches": len(breaches),
                    "breaches": breaches,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("haveibeenpwned_domain_not_found", domain=domain)
                return self.success_result(
                    not_found=True,
                    data={
                        "domain": domain,
                        "total_breaches": 0,
                        "breaches": [],
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("haveibeenpwned_lookup_domain_failed", error=e)
            return self.error_result(e)

    @staticmethod
    def _normalise_domain(domain: str) -> str:
        """Extract bare domain from a URL or domain string.

        Mirrors the upstream logic: if input looks like a URL, extract the host
        component; then strip any leading ``www.`` prefix.
        """
        if "://" in domain:
            parsed = urlparse(domain)
            domain = parsed.hostname or domain

        return domain.removeprefix("www.")

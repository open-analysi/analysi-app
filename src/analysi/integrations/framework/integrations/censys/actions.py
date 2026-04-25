"""Censys integration actions for internet-wide scanning and host/certificate lookup.
Library type: REST API (the upstream connector uses ``requests``; Naxos uses ``self.http_request()``).

Censys v2 API uses HTTP Basic Auth with API ID and Secret.
All endpoints are under ``https://search.censys.io/api/v2/``.
"""

import ipaddress
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    DATASET_CERTIFICATES,
    DATASET_HOSTS,
    DEFAULT_BASE_URL,
    DEFAULT_QUERY_LIMIT,
    DEFAULT_TIMEOUT,
    MSG_INVALID_IP,
    MSG_INVALID_LIMIT,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAM,
    MSG_NO_INFO,
    QUERY_CERTIFICATE_PER_PAGE,
    QUERY_IP_PER_PAGE,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_ip(ip_str: str) -> bool:
    """Return True if the string is a valid IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False

# ---------------------------------------------------------------------------
# Base class with shared auth
# ---------------------------------------------------------------------------

class _CensysAction(IntegrationAction):
    """Shared helpers for all Censys actions.

    Censys authenticates via HTTP Basic Auth using api_id / secret.
    """

    def get_timeout(self) -> int | float:
        """Return timeout, defaulting to Censys-specific value."""
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        return self.settings.get("base_url", DEFAULT_BASE_URL).rstrip("/")

    async def _paginated_search(
        self,
        dataset: str,
        query: str,
        per_page: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        """Fetch results page by page until limit is reached or no more pages.

        Returns (hits, total_available).
        """
        params: dict[str, Any] = {
            "q": query,
            "per_page": min(limit, per_page),
        }

        response = await self.http_request(
            url=f"{self.base_url}/api/v2/{dataset}/search",
            params=params,
            auth=self._auth,
        )
        body = response.json()

        result_block = body.get("result", {})
        hits = result_block.get("hits", [])
        total = result_block.get("total", 0)
        cursor = result_block.get("links", {}).get("next", "")

        data_left = limit - len(hits)
        while cursor and data_left > 0:
            next_params: dict[str, Any] = {
                "q": query,
                "per_page": min(data_left, per_page),
                "cursor": cursor,
            }
            next_response = await self.http_request(
                url=f"{self.base_url}/api/v2/{dataset}/search",
                params=next_params,
                auth=self._auth,
            )
            next_body = next_response.json()
            next_result = next_body.get("result", {})
            next_hits = next_result.get("hits", [])
            hits.extend(next_hits)
            cursor = next_result.get("links", {}).get("next", "")
            data_left -= len(next_hits)

        return hits, total

    @property
    def _auth(self) -> tuple[str, str] | None:
        """Return (api_id, secret) tuple for HTTP Basic Auth, or None."""
        api_id = self.credentials.get("api_id")
        secret = self.credentials.get("secret")
        if api_id and secret:
            return (api_id, secret)
        return None

    def _require_credentials(self) -> dict[str, Any] | None:
        """Return an error_result if credentials are missing, else None."""
        if not self._auth:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )
        return None

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(_CensysAction):
    """Verify connectivity to the Censys API using the /account endpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_credentials():
            return err

        try:
            # Uses v1 /account endpoint intentionally — the account/quota
            # endpoint only exists in the v1 API; other actions use v2.
            response = await self.http_request(
                url=f"{self.base_url}/api/v1/account",
                auth=self._auth,
            )
            account_data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Connectivity test passed",
                    "account": account_data,
                },
            )
        except Exception as e:
            self.log_error("censys_health_check_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# LOOKUP IP
# ============================================================================

class LookupIpAction(_CensysAction):
    """Look up host information for an IP address via the Censys v2 hosts API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ip"),
                error_type="ValidationError",
            )
        if not _is_valid_ip(ip):
            return self.error_result(MSG_INVALID_IP, error_type="ValidationError")
        if err := self._require_credentials():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/v2/{DATASET_HOSTS}/{ip}",
                auth=self._auth,
            )
            result = response.json()

            # Check if host has any services (matches the upstream summary logic)
            services = result.get("result", {}).get("services", [])
            if not services:
                self.log_info("censys_lookup_ip_no_services", ip=ip)
                return self.success_result(
                    data=result,
                    message=MSG_NO_INFO,
                )

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("censys_lookup_ip_not_found", ip=ip)
                return self.success_result(
                    not_found=True,
                    data={"ip": ip, "result": {"services": []}},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("censys_lookup_ip_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# LOOKUP CERTIFICATE
# ============================================================================

class LookupCertificateAction(_CensysAction):
    """Look up certificate details by SHA-256 fingerprint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        sha256 = kwargs.get("sha256")
        if not sha256:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="sha256"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            response = await self.http_request(
                url=f"{self.base_url}/api/v2/{DATASET_CERTIFICATES}/{sha256}",
                auth=self._auth,
            )
            result = response.json()

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("censys_lookup_certificate_not_found", sha256=sha256)
                return self.success_result(
                    not_found=True,
                    data={"sha256": sha256},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("censys_lookup_certificate_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# QUERY IP
# ============================================================================

class QueryIpAction(_CensysAction):
    """Search the Censys hosts dataset using the Censys query language.

    Supports pagination via cursor-based iteration.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="query"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        # Validate and parse limit
        raw_limit = kwargs.get("limit", DEFAULT_QUERY_LIMIT)
        try:
            limit = int(raw_limit)
            if limit <= 0:
                return self.error_result(
                    MSG_INVALID_LIMIT, error_type="ValidationError"
                )
        except (ValueError, TypeError):
            return self.error_result(MSG_INVALID_LIMIT, error_type="ValidationError")

        try:
            hits, total = await self._paginated_search(
                dataset=DATASET_HOSTS,
                query=query,
                per_page=QUERY_IP_PER_PAGE,
                limit=limit,
            )

            return self.success_result(
                data={
                    "hits": hits,
                    "total_records_fetched": len(hits),
                    "total_available_records": total,
                },
            )
        except Exception as e:
            self.log_error("censys_query_ip_failed", error=str(e))
            return self.error_result(e)

# ============================================================================
# QUERY CERTIFICATE
# ============================================================================

class QueryCertificateAction(_CensysAction):
    """Search the Censys certificates dataset using the Censys query language.

    Supports pagination via cursor-based iteration.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="query"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        # Validate and parse limit
        raw_limit = kwargs.get("limit", DEFAULT_QUERY_LIMIT)
        try:
            limit = int(raw_limit)
            if limit <= 0:
                return self.error_result(
                    MSG_INVALID_LIMIT, error_type="ValidationError"
                )
        except (ValueError, TypeError):
            return self.error_result(MSG_INVALID_LIMIT, error_type="ValidationError")

        try:
            hits, total = await self._paginated_search(
                dataset=DATASET_CERTIFICATES,
                query=query,
                per_page=QUERY_CERTIFICATE_PER_PAGE,
                limit=limit,
            )

            return self.success_result(
                data={
                    "hits": hits,
                    "total_records_fetched": len(hits),
                    "total_available_records": total,
                },
            )
        except Exception as e:
            self.log_error("censys_query_certificate_failed", error=str(e))
            return self.error_result(e)

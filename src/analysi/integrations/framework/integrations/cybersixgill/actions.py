"""Cybersixgill dark web threat intelligence integration actions.
Library type: REST API (upstream used proprietary ``sixgill`` SDK wrapping
OAuth2 REST calls; Naxos uses ``self.http_request()``).

Cybersixgill provides dark web intelligence including IOC enrichment
(IP, domain, URL, hash), post ID enrichment, threat actor enrichment,
and alert management.  All calls use OAuth2 client_credentials for auth.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CHANNEL_ID,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    GRANT_TYPE,
    IOC_TYPE_DOMAIN,
    IOC_TYPE_HASH,
    IOC_TYPE_IP,
    IOC_TYPE_URL,
    MSG_AUTH_FAILED,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAM,
    TOKEN_ENDPOINT,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Base class with shared auth helpers
# ---------------------------------------------------------------------------

class _CybersixgillAction(IntegrationAction):
    """Shared helpers for all Cybersixgill actions."""

    def get_timeout(self) -> int | float:
        """Return timeout, defaulting to Cybersixgill-specific value."""
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        return self.settings.get("base_url", DEFAULT_BASE_URL).rstrip("/")

    def _require_credentials(self) -> dict[str, Any] | None:
        """Return an error_result if credentials are missing, else None."""
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")
        if not client_id or not client_secret:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )
        return None

    async def _get_access_token(self) -> str:
        """Obtain an OAuth2 access token using client credentials.

        Returns:
            The access token string.

        Raises:
            httpx.HTTPStatusError: If the token request fails.
            ValueError: If the response does not contain a token.
        """
        client_id = self.credentials.get("client_id", "")
        client_secret = self.credentials.get("client_secret", "")

        response = await self.http_request(
            url=f"{self.base_url}{TOKEN_ENDPOINT}",
            method="POST",
            data={
                "grant_type": GRANT_TYPE,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError(MSG_AUTH_FAILED)
        return access_token

    async def _authenticated_request(
        self,
        url: str,
        method: str = "GET",
        params: dict | None = None,
        json_data: dict | None = None,
    ) -> httpx.Response:
        """Make an authenticated request with an OAuth2 bearer token.

        Obtains a fresh token for each request (stateless, multi-tenant safe).
        """
        access_token = await self._get_access_token()
        return await self.http_request(
            url=url,
            method=method,
            params=params,
            json_data=json_data,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(_CybersixgillAction):
    """Verify API connectivity and credential validity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_credentials():
            return err

        try:
            # Validate credentials by obtaining a token
            access_token = await self._get_access_token()

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Connectivity and credentials test passed",
                    "has_valid_token": bool(access_token),
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("cybersixgill_health_check_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("cybersixgill_health_check_failed", error=e)
            return self.error_result(e)

# ============================================================================
# IOC ENRICHMENT ACTIONS
# ============================================================================

class LookupIpAction(_CybersixgillAction):
    """Query Cybersixgill Darkfeed for IOCs matching an IP address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="ip"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            response = await self._authenticated_request(
                url=f"{self.base_url}{_enrich_ioc_path()}",
                method="POST",
                json_data={
                    "ioc_type": IOC_TYPE_IP,
                    "ioc_value": ip,
                    "channel_id": CHANNEL_ID,
                },
            )
            result = response.json()
            indicators = result if isinstance(result, list) else result.get("items", [])

            return self.success_result(
                data={
                    "ip": ip,
                    "indicators_found": len(indicators),
                    "indicators": indicators,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("cybersixgill_ip_not_found", ip=ip)
                return self.success_result(
                    not_found=True,
                    data={
                        "ip": ip,
                        "indicators_found": 0,
                        "indicators": [],
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("cybersixgill_lookup_ip_failed", error=e)
            return self.error_result(e)

class LookupDomainAction(_CybersixgillAction):
    """Query Cybersixgill Darkfeed for IOCs matching a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="domain"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            response = await self._authenticated_request(
                url=f"{self.base_url}{_enrich_ioc_path()}",
                method="POST",
                json_data={
                    "ioc_type": IOC_TYPE_DOMAIN,
                    "ioc_value": domain,
                    "channel_id": CHANNEL_ID,
                },
            )
            result = response.json()
            indicators = result if isinstance(result, list) else result.get("items", [])

            return self.success_result(
                data={
                    "domain": domain,
                    "indicators_found": len(indicators),
                    "indicators": indicators,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("cybersixgill_domain_not_found", domain=domain)
                return self.success_result(
                    not_found=True,
                    data={
                        "domain": domain,
                        "indicators_found": 0,
                        "indicators": [],
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("cybersixgill_lookup_domain_failed", error=e)
            return self.error_result(e)

class LookupHashAction(_CybersixgillAction):
    """Query Cybersixgill Darkfeed for IOCs matching a file hash."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        file_hash = kwargs.get("hash")
        if not file_hash:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="hash"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            response = await self._authenticated_request(
                url=f"{self.base_url}{_enrich_ioc_path()}",
                method="POST",
                json_data={
                    "ioc_type": IOC_TYPE_HASH,
                    "ioc_value": file_hash,
                    "channel_id": CHANNEL_ID,
                },
            )
            result = response.json()
            indicators = result if isinstance(result, list) else result.get("items", [])

            return self.success_result(
                data={
                    "hash": file_hash,
                    "indicators_found": len(indicators),
                    "indicators": indicators,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("cybersixgill_hash_not_found", file_hash=file_hash)
                return self.success_result(
                    not_found=True,
                    data={
                        "hash": file_hash,
                        "indicators_found": 0,
                        "indicators": [],
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("cybersixgill_lookup_hash_failed", error=e)
            return self.error_result(e)

class LookupUrlAction(_CybersixgillAction):
    """Query Cybersixgill Darkfeed for IOCs matching a URL."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        url = kwargs.get("url")
        if not url:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="url"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            response = await self._authenticated_request(
                url=f"{self.base_url}{_enrich_ioc_path()}",
                method="POST",
                json_data={
                    "ioc_type": IOC_TYPE_URL,
                    "ioc_value": url,
                    "channel_id": CHANNEL_ID,
                },
            )
            result = response.json()
            indicators = result if isinstance(result, list) else result.get("items", [])

            return self.success_result(
                data={
                    "url": url,
                    "indicators_found": len(indicators),
                    "indicators": indicators,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("cybersixgill_url_not_found", url=url)
                return self.success_result(
                    not_found=True,
                    data={
                        "url": url,
                        "indicators_found": 0,
                        "indicators": [],
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("cybersixgill_lookup_url_failed", error=e)
            return self.error_result(e)

# ============================================================================
# SEARCH & ALERTS
# ============================================================================

class SearchThreatsAction(_CybersixgillAction):
    """Search for threats/mentions on the dark web.

    Accepts a free-text query and optional parameters for filtering results.
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

        limit = kwargs.get("limit", 10)
        from_date = kwargs.get("from_date")

        try:
            request_body: dict[str, Any] = {
                "query": query,
                "channel_id": CHANNEL_ID,
                "results_size": limit,
            }
            if from_date:
                request_body["from_date"] = from_date

            response = await self._authenticated_request(
                url=f"{self.base_url}/darkfeed/search",
                method="POST",
                json_data=request_body,
            )
            result = response.json()
            items = result if isinstance(result, list) else result.get("items", [])

            return self.success_result(
                data={
                    "query": query,
                    "total_results": len(items),
                    "items": items,
                },
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("cybersixgill_search_threats_failed", error=e)
            return self.error_result(e)

class GetAlertAction(_CybersixgillAction):
    """Get a Cybersixgill alert by its ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        alert_id = kwargs.get("alert_id")
        if not alert_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="alert_id"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            response = await self._authenticated_request(
                url=f"{self.base_url}/alerts/{alert_id}",
            )
            result = response.json()

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("cybersixgill_alert_not_found", alert_id=alert_id)
                return self.success_result(
                    not_found=True,
                    data={
                        "alert_id": alert_id,
                        "message": "Alert not found",
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("cybersixgill_get_alert_failed", error=e)
            return self.error_result(e)

class ListAlertsAction(_CybersixgillAction):
    """List Cybersixgill alerts with optional filters."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_credentials():
            return err

        limit = kwargs.get("limit", 25)
        offset = kwargs.get("offset", 0)
        severity = kwargs.get("severity")
        status = kwargs.get("status")

        try:
            params: dict[str, Any] = {
                "limit": limit,
                "offset": offset,
            }
            if severity:
                params["severity"] = severity
            if status:
                params["status"] = status

            response = await self._authenticated_request(
                url=f"{self.base_url}/alerts",
                params=params,
            )
            result = response.json()
            alerts = result if isinstance(result, list) else result.get("items", [])
            total = (
                result.get("total", len(alerts))
                if isinstance(result, dict)
                else len(alerts)
            )

            return self.success_result(
                data={
                    "total_alerts": total,
                    "alerts_returned": len(alerts),
                    "offset": offset,
                    "limit": limit,
                    "alerts": alerts,
                },
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("cybersixgill_list_alerts_failed", error=e)
            return self.error_result(e)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enrich_ioc_path() -> str:
    """Return the enrichment IOC endpoint path."""
    return "/darkfeed/enrich/ioc"

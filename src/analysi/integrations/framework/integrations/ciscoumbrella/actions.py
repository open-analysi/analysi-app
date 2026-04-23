"""Cisco Umbrella integration actions.

This module provides actions for managing DNS-layer domain blocking via the
Cisco Umbrella (formerly OpenDNS) S-Platform API:
- Health check (test connectivity by fetching a single domain entry)
- Block domain (submit a block event to the enforcement API)
- Unblock domain (delete a domain from the block list)
- List blocked domains (paginate through the blocked domain list)

Authentication uses a customer key passed as a query parameter on every
request. The base class handles injecting the key automatically.
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_VERSION,
    BASE_URL,
    CREDENTIAL_CUSTOMER_KEY,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_TIMEOUT,
    ENDPOINT_DOMAINS,
    ENDPOINT_EVENTS,
    ERR_INVALID_LIMIT,
    ERR_MISSING_CUSTOMER_KEY,
    ERR_MISSING_DOMAIN,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MAX_PAGES,
    MSG_DOMAIN_BLOCKED,
    MSG_DOMAIN_UNBLOCKED,
    MSG_HEALTH_CHECK_PASSED,
    SETTINGS_TIMEOUT,
)

logger = get_logger(__name__)

# ============================================================================
# BASE CLASS
# ============================================================================

class _CiscoUmbrellaBase(IntegrationAction):
    """Shared base for all Cisco Umbrella actions.

    Provides the API base URL construction and customer key injection
    into every request as a query parameter.
    """

    def _get_base_api_url(self) -> str:
        """Build the versioned base API URL."""
        return f"{BASE_URL}/{API_VERSION}"

    def _get_customer_key(self) -> str | None:
        """Extract the customer key from credentials."""
        return self.credentials.get(CREDENTIAL_CUSTOMER_KEY)

    def get_timeout(self) -> int | float:
        """Return configured timeout."""
        return self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

    async def _umbrella_request(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
    ) -> httpx.Response:
        """Make a request to the Cisco Umbrella S-Platform API.

        Automatically injects the customerKey query parameter for auth.
        """
        url = f"{self._get_base_api_url()}{endpoint}"
        customer_key = self._get_customer_key()

        if params is None:
            params = {}
        params["customerKey"] = customer_key

        kwargs: dict[str, Any] = {
            "url": url,
            "params": params,
            "headers": {
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        }
        if method != "GET":
            kwargs["method"] = method
        if json_data is not None:
            kwargs["json_data"] = json_data

        return await self.http_request(**kwargs)

    async def _paginate_domains(
        self,
        *,
        limit: int = 0,
    ) -> list[dict[str, Any]]:
        """Paginate through the blocked domain list.

        Args:
            limit: Maximum number of domains to return. 0 means all.

        Returns:
            List of domain dicts from the API.
        """
        all_domains: list[dict[str, Any]] = []

        for page in range(1, MAX_PAGES + 1):
            response = await self._umbrella_request(
                ENDPOINT_DOMAINS,
                params={"limit": DEFAULT_PAGE_LIMIT, "page": page},
            )
            resp_json = response.json()
            data = resp_json.get("data", [])
            all_domains.extend(data)

            if limit and len(all_domains) >= limit:
                return all_domains[:limit]

            if not resp_json.get("meta", {}).get("next"):
                break
        else:
            logger.warning(
                "ciscoumbrella_list_truncated",
                max_pages=MAX_PAGES,
                total_fetched=len(all_domains),
            )

        return all_domains

# ============================================================================
# ACTIONS
# ============================================================================

class HealthCheckAction(_CiscoUmbrellaBase):
    """Test connectivity to Cisco Umbrella by fetching a single domain entry."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        customer_key = self._get_customer_key()
        if not customer_key:
            return self.error_result(
                ERR_MISSING_CUSTOMER_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            await self._umbrella_request(
                ENDPOINT_DOMAINS,
                params={"page": 1, "limit": 1},
            )
            return self.success_result(
                data={"healthy": True, "message": MSG_HEALTH_CHECK_PASSED}
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class BlockDomainAction(_CiscoUmbrellaBase):
    """Block a domain by submitting an enforcement event to Cisco Umbrella.

    The S-Platform events API accepts a list of event objects. The domain
    is blocked at the DNS layer once the event is processed.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                ERR_MISSING_DOMAIN, error_type=ERROR_TYPE_VALIDATION
            )

        customer_key = self._get_customer_key()
        if not customer_key:
            return self.error_result(
                ERR_MISSING_CUSTOMER_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        disable_safeguards = kwargs.get("disable_safeguards", False)

        now_str = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.0Z")

        event = {
            "alertTime": now_str,
            "deviceId": "analysi-platform",
            "deviceVersion": "1.0.0",
            "dstDomain": domain,
            "dstUrl": f"http://{domain}/",
            "eventTime": now_str,
            "protocolVersion": "1.0a",
            "providerName": "Security Platform",
            "disableDstSafeguards": disable_safeguards,
        }

        try:
            response = await self._umbrella_request(
                ENDPOINT_EVENTS,
                method="POST",
                json_data=[event],
            )

            resp_data = response.json() if response.text else {}
            event_id = resp_data.get("id", "") if isinstance(resp_data, dict) else ""

            return self.success_result(
                data={
                    "domain": domain,
                    "message": MSG_DOMAIN_BLOCKED,
                    "event_id": event_id,
                },
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class UnblockDomainAction(_CiscoUmbrellaBase):
    """Unblock a domain by removing it from the Cisco Umbrella block list.

    Uses a DELETE request to the domains endpoint with a domain name filter.
    A 204 response indicates success (no body).
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                ERR_MISSING_DOMAIN, error_type=ERROR_TYPE_VALIDATION
            )

        customer_key = self._get_customer_key()
        if not customer_key:
            return self.error_result(
                ERR_MISSING_CUSTOMER_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            await self._umbrella_request(
                ENDPOINT_DOMAINS,
                method="DELETE",
                params={"where[name]": domain},
            )

            return self.success_result(
                data={
                    "domain": domain,
                    "message": MSG_DOMAIN_UNBLOCKED,
                },
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={
                        "domain": domain,
                        "message": "Domain not found in block list",
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListBlockedDomainsAction(_CiscoUmbrellaBase):
    """List domains currently on the Cisco Umbrella block list.

    Supports an optional limit parameter. Paginates through all results
    using the meta.next field from the API response.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        customer_key = self._get_customer_key()
        if not customer_key:
            return self.error_result(
                ERR_MISSING_CUSTOMER_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        limit = kwargs.get("limit", 0)
        if limit is not None:
            try:
                limit = int(limit)
                if limit < 0:
                    return self.error_result(
                        ERR_INVALID_LIMIT, error_type=ERROR_TYPE_VALIDATION
                    )
            except (TypeError, ValueError):
                return self.error_result(
                    ERR_INVALID_LIMIT, error_type=ERROR_TYPE_VALIDATION
                )

        try:
            domains = await self._paginate_domains(limit=limit)

            return self.success_result(
                data={
                    "domains": domains,
                    "total_domains": len(domains),
                },
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

"""Mandiant Advantage Threat Intelligence integration actions.
Library type: REST API (the upstream connector uses ``requests``; Naxos uses ``self.http_request()``).

Mandiant TI uses OAuth2 client-credentials flow: POST to ``/token`` with
basic-auth (api_key, secret_key) to get a bearer token, then include
``Authorization: Bearer <token>`` on subsequent API calls.

All lookup actions treat 404 as not-found (success with empty data) so that
Cy scripts are not interrupted by missing entities.
"""

import datetime
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_V4_PREFIX,
    APP_NAME_HEADER,
    APP_NAME_VALUE,
    DEFAULT_BASE_URL,
    DEFAULT_REPORT_DAYS,
    DEFAULT_TIMEOUT,
    ENTITLEMENTS_ENDPOINT,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAM,
    MSG_TOKEN_FAILED,
    OAUTH2_GRANT_TYPE,
    REPORT_PAGE_SIZE,
    SEARCH_PAGE_SIZE,
    TOKEN_ENDPOINT,
)

logger = get_logger(__name__)

# Safety limit for paginated endpoints — prevents runaway loops if the API
# keeps returning full pages (e.g., due to a cursor bug).
MAX_PAGES = 100

# ---------------------------------------------------------------------------
# Base class with shared OAuth2 bearer-token auth
# ---------------------------------------------------------------------------

class _MandiantBase(IntegrationAction):
    """Shared helpers for all Mandiant TI actions.

    Handles OAuth2 client-credentials flow and common URL/timeout helpers.
    The bearer token is obtained per-execution (stateless); we do not cache
    tokens across action invocations because integrations must remain
    stateless for multi-tenancy.
    """

    def get_http_headers(self) -> dict[str, str]:
        """Add the Mandiant app-name header to every request.

        The Authorization header is set per-call after obtaining a token,
        so it is NOT injected here.
        """
        return {APP_NAME_HEADER: APP_NAME_VALUE}

    def get_timeout(self) -> int | float:
        return self.settings.get("timeout", DEFAULT_TIMEOUT)

    @property
    def base_url(self) -> str:
        url = self.settings.get("base_url", DEFAULT_BASE_URL)
        return url.rstrip("/")

    def _require_credentials(self) -> dict[str, Any] | None:
        """Return an error_result if api_key or secret_key are missing."""
        api_key = self.credentials.get("api_key")
        secret_key = self.credentials.get("secret_key")
        if not api_key or not secret_key:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type="ConfigurationError"
            )
        return None

    async def _get_bearer_token(self) -> str:
        """Obtain an OAuth2 bearer token using client credentials.

        Raises:
            httpx.HTTPStatusError: On auth failure.
            RuntimeError: If the token response is malformed.
        """
        api_key = self.credentials.get("api_key", "")
        secret_key = self.credentials.get("secret_key", "")

        response = await self.http_request(
            url=f"{self.base_url}/{TOKEN_ENDPOINT}",
            method="POST",
            data={"grant_type": OAUTH2_GRANT_TYPE, "scope": ""},
            auth=(api_key, secret_key),
            headers={"Accept": "application/json"},
        )

        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise RuntimeError(MSG_TOKEN_FAILED)
        return access_token

    def _auth_headers(self, token: str) -> dict[str, str]:
        """Build Authorization header dict from a bearer token."""
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def _api_request(
        self,
        token: str,
        endpoint: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
        data: Any | None = None,
        accept: str = "application/json",
    ) -> httpx.Response:
        """Make an authenticated v4 API call."""
        headers = self._auth_headers(token)
        headers["Accept"] = accept
        return await self.http_request(
            url=f"{self.base_url}/{endpoint}",
            method=method,
            headers=headers,
            params=params,
            json_data=json_data,
            data=data,
        )

# ============================================================================
# HEALTH CHECK
# ============================================================================

class HealthCheckAction(_MandiantBase):
    """Verify connectivity to Mandiant TI API and validate credentials."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_credentials():
            return err

        try:
            token = await self._get_bearer_token()

            response = await self._api_request(
                token, ENTITLEMENTS_ENDPOINT, method="GET"
            )
            entitlements = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Connectivity and credentials test passed",
                    "entitlements": entitlements,
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("mandiantti_health_check_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("mandiantti_health_check_failed", error=e)
            return self.error_result(e)

# ============================================================================
# INDICATOR LOOKUP
# ============================================================================

class IndicatorLookupAction(_MandiantBase):
    """Retrieve indicator information (IP, domain, hash, URL).

    Mirrors the upstream ``_handle_indicator_lookup``: first POSTs to ``v4/indicator``
    to identify the indicator, then GETs full details and associated reports.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        indicator = kwargs.get("indicator")
        if not indicator:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="indicator"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            token = await self._get_bearer_token()

            # Step 1: identify the indicator
            search_data = {"requests": [{"values": [indicator]}]}
            search_resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/indicator",
                method="POST",
                json_data=search_data,
                params={"include_campaigns": True},
            )
            search_result = search_resp.json()

            indicators = search_result.get("indicators")
            if not isinstance(indicators, list) or len(indicators) == 0:
                self.log_info("mandiantti_indicator_not_found", indicator=indicator)
                return self.success_result(
                    not_found=True,
                    data={"indicator": indicator, "status": "no results"},
                )

            ind = indicators[0]

            # Step 2: get full indicator details
            detail_resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/indicator/{ind['type']}/{ind['value']}",
                method="GET",
                params={"include_campaigns": True},
            )
            indicator_detail = detail_resp.json()

            # Extract categories from sources
            categories: set[str] = set()
            for source in indicator_detail.get("sources", []):
                for category in source.get("category", []):
                    categories.add(category)

            # Step 3: get associated reports
            report_resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/indicator/{indicator_detail['id']}/reports",
                method="GET",
                params={"include_campaigns": True},
            )
            report_data = report_resp.json()

            output: dict[str, Any] = {
                "value": indicator_detail.get("value"),
                "type": indicator_detail.get("type"),
                "confidence": indicator_detail.get("mscore"),
                "categories": sorted(categories),
                "attributed_associations": [
                    {"name": a["name"], "type": a["type"]}
                    for a in indicator_detail.get("attributed_associations", [])
                ],
                "first_seen": indicator_detail.get("first_seen"),
                "last_seen": indicator_detail.get("last_seen"),
                "reports": report_data.get("reports", []),
                "campaigns": indicator_detail.get("campaigns", []),
            }

            # Include associated hashes for hash-type indicators
            if indicator_detail.get("type") == "md5":
                for h in indicator_detail.get("associated_hashes", []):
                    output[f"associated_{h['type']}"] = h["value"]

            return self.success_result(data=output)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("mandiantti_indicator_not_found", indicator=indicator)
                return self.success_result(
                    not_found=True,
                    data={"indicator": indicator, "status": "not found"},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("mandiantti_indicator_lookup_failed", error=e)
            return self.error_result(e)

# ============================================================================
# THREAT ACTOR LOOKUP
# ============================================================================

class ThreatActorLookupAction(_MandiantBase):
    """Retrieve threat actor information, reports, and campaigns."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        threat_actor = kwargs.get("threat_actor")
        if not threat_actor:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="threat_actor"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            token = await self._get_bearer_token()

            # Get actor details
            actor_resp = await self._api_request(
                token, f"{API_V4_PREFIX}/actor/{threat_actor}", method="GET"
            )
            output = actor_resp.json()

            # Get associated reports
            report_resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/actor/{threat_actor}/reports",
                method="GET",
            )
            output["reports"] = report_resp.json().get("reports", [])

            # Get associated campaigns
            campaign_resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/actor/{threat_actor}/campaigns",
                method="GET",
            )
            output["campaigns"] = campaign_resp.json().get("campaigns", [])

            return self.success_result(data=output)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "mandiantti_threat_actor_not_found",
                    threat_actor=threat_actor,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "threat_actor": threat_actor,
                        "status": "not found",
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("mandiantti_threat_actor_lookup_failed", error=e)
            return self.error_result(e)

# ============================================================================
# VULNERABILITY LOOKUP
# ============================================================================

class VulnerabilityLookupAction(_MandiantBase):
    """Retrieve vulnerability (CVE) information from Mandiant TI."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        vulnerability = kwargs.get("vulnerability")
        if not vulnerability:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="vulnerability"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            token = await self._get_bearer_token()

            resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/vulnerability/{vulnerability}",
                method="GET",
            )
            output = resp.json()

            # Capitalize risk_rating as upstream does
            if "risk_rating" in output:
                output["risk_rating"] = str(output["risk_rating"]).capitalize()

            return self.success_result(data=output)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "mandiantti_vulnerability_not_found",
                    vulnerability=vulnerability,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "vulnerability": vulnerability,
                        "status": "not found",
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("mandiantti_vulnerability_lookup_failed", error=e)
            return self.error_result(e)

# ============================================================================
# MALWARE FAMILY LOOKUP
# ============================================================================

class MalwareFamilyLookupAction(_MandiantBase):
    """Retrieve malware family information, reports, and campaigns."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        malware_family = kwargs.get("malware_family")
        if not malware_family:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="malware_family"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            token = await self._get_bearer_token()

            # Get malware family details
            malware_resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/malware/{malware_family}",
                method="GET",
            )
            output = malware_resp.json()

            # Get associated reports
            report_resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/malware/{malware_family}/reports",
                method="GET",
            )
            output["reports"] = report_resp.json().get("reports", [])

            # Get associated campaigns
            campaign_resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/malware/{malware_family}/campaigns",
                method="GET",
            )
            output["campaigns"] = campaign_resp.json().get("campaigns", [])

            return self.success_result(data=output)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "mandiantti_malware_family_not_found",
                    malware_family=malware_family,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "malware_family": malware_family,
                        "status": "not found",
                    },
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("mandiantti_malware_family_lookup_failed", error=e)
            return self.error_result(e)

# ============================================================================
# CAMPAIGN LOOKUP
# ============================================================================

class CampaignLookupAction(_MandiantBase):
    """Retrieve campaign information and associated reports."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        campaign = kwargs.get("campaign")
        if not campaign:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="campaign"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            token = await self._get_bearer_token()

            # Get campaign details
            campaign_resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/campaign/{campaign}",
                method="GET",
            )
            output = campaign_resp.json()

            # Get associated reports
            report_resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/campaign/{campaign}/reports",
                method="GET",
            )
            output["reports"] = report_resp.json().get("reports", [])

            return self.success_result(data=output)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "mandiantti_campaign_not_found",
                    campaign=campaign,
                )
                return self.success_result(
                    not_found=True,
                    data={"campaign": campaign, "status": "not found"},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("mandiantti_campaign_lookup_failed", error=e)
            return self.error_result(e)

# ============================================================================
# SEARCH
# ============================================================================

class SearchAction(_MandiantBase):
    """Search Mandiant TI for a given query string with automatic pagination."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="query"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            token = await self._get_bearer_token()

            search_data: dict[str, Any] = {"search": query}
            all_objects: list[dict[str, Any]] = []

            for _page in range(MAX_PAGES):
                resp = await self._api_request(
                    token,
                    f"{API_V4_PREFIX}/search",
                    method="POST",
                    json_data=search_data,
                )
                result = resp.json()

                objects = result.get("objects", [])
                if not objects:
                    break

                all_objects.extend(objects)

                # Mandiant returns pages of SEARCH_PAGE_SIZE; stop if short page
                if len(objects) < SEARCH_PAGE_SIZE:
                    break

                search_data["next"] = result.get("next")
            else:
                # Loop exhausted MAX_PAGES without a short/empty page — warn caller
                self.log_warning(
                    "mandiantti_search_truncated",
                    max_pages=MAX_PAGES,
                    total_objects=len(all_objects),
                )
                return self.success_result(
                    data={"objects": all_objects, "truncated": True}
                )

            return self.success_result(data={"objects": all_objects})

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("mandiantti_search_failed", error=e)
            return self.error_result(e)

# ============================================================================
# REPORT LOOKUP (single report, HTML)
# ============================================================================

class ReportLookupAction(_MandiantBase):
    """Retrieve a single report by ID from Mandiant TI (returns HTML)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        report_id = kwargs.get("report_id")
        if not report_id:
            return self.error_result(
                MSG_MISSING_PARAM.format(param="report_id"),
                error_type="ValidationError",
            )
        if err := self._require_credentials():
            return err

        try:
            token = await self._get_bearer_token()

            resp = await self._api_request(
                token,
                f"{API_V4_PREFIX}/report/{report_id}",
                method="GET",
                accept="text/html",
            )

            return self.success_result(
                data={"report_id": report_id, "report": resp.text},
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("mandiantti_report_not_found", report_id=report_id)
                return self.success_result(
                    not_found=True,
                    data={"report_id": report_id, "status": "not found"},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("mandiantti_report_lookup_failed", error=e)
            return self.error_result(e)

# ============================================================================
# REPORT LIST
# ============================================================================

class ReportListAction(_MandiantBase):
    """Retrieve a list of reports from Mandiant TI, optionally filtered by type."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        if err := self._require_credentials():
            return err

        days_raw = kwargs.get("days", DEFAULT_REPORT_DAYS)
        try:
            days = int(days_raw)
            if days <= 0:
                return self.error_result(
                    "days must be a positive integer",
                    error_type="ValidationError",
                )
        except (ValueError, TypeError):
            return self.error_result(
                f"Invalid days value: {days_raw}",
                error_type="ValidationError",
            )

        report_type = kwargs.get("report_type")

        try:
            token = await self._get_bearer_token()

            now = datetime.datetime.now(tz=datetime.UTC)
            start_epoch = int((now - datetime.timedelta(days=days)).timestamp())

            query_params: dict[str, Any] = {"start_epoch": start_epoch}
            all_objects: list[dict[str, Any]] = []

            for _page in range(MAX_PAGES):
                resp = await self._api_request(
                    token,
                    f"{API_V4_PREFIX}/reports",
                    method="GET",
                    params=query_params,
                )
                result = resp.json()

                objects = result.get("objects", [])
                all_objects.extend(objects)

                # Mandiant returns pages of REPORT_PAGE_SIZE; stop if short
                if len(objects) < REPORT_PAGE_SIZE:
                    break

                query_params = {"next": result.get("next")}
            else:
                # Loop exhausted MAX_PAGES without a short/empty page — warn caller
                self.log_warning(
                    "mandiantti_report_list_truncated",
                    max_pages=MAX_PAGES,
                    total_objects=len(all_objects),
                )

                if report_type:
                    all_objects = [
                        r
                        for r in all_objects
                        if r.get("report_type", "").upper() == report_type.upper()
                    ]

                return self.success_result(
                    data={"objects": all_objects, "truncated": True}
                )

            # Optional filter by report_type
            if report_type:
                all_objects = [
                    r
                    for r in all_objects
                    if r.get("report_type", "").upper() == report_type.upper()
                ]

            return self.success_result(data={"objects": all_objects})

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            self.log_error("mandiantti_report_list_failed", error=e)
            return self.error_result(e)

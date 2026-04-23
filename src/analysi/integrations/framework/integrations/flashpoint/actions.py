"""Flashpoint integration actions for deep/dark web threat intelligence.

Covers intelligence reports, technical indicators (IoCs), compromised
credentials, and universal search across deep and dark web data.
"""

import contextlib
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ALL_SEARCH_ENDPOINT,
    ALL_SEARCH_SCROLL_ENDPOINT,
    CREDENTIAL_API_TOKEN,
    DEFAULT_SESSION_TIMEOUT_MINUTES,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    FLASHPOINT_DEFAULT_BASE_URL,
    GET_REPORT_ENDPOINT,
    INDICATORS_ENDPOINT,
    INDICATORS_SCROLL_ENDPOINT,
    LIST_RELATED_REPORTS_ENDPOINT,
    LIST_REPORTS_ENDPOINT,
    MSG_INVALID_COMMA_SEPARATED,
    MSG_INVALID_LIMIT,
    MSG_MISSING_API_TOKEN,
    MSG_MISSING_ATTRIBUTE_TYPE,
    MSG_MISSING_ATTRIBUTE_VALUE,
    MSG_MISSING_QUERY,
    MSG_MISSING_REPORT_ID,
    MSG_SERVER_CONNECTION,
    PER_PAGE_DEFAULT_LIMIT,
    SETTINGS_BASE_URL,
    SETTINGS_SESSION_TIMEOUT,
    SETTINGS_TIMEOUT,
    X_FP_INTEGRATION_PLATFORM,
)

logger = get_logger(__name__)

# ============================================================================
# VALIDATION UTILITIES
# ============================================================================

def _validate_limit(limit: Any) -> tuple[bool, int | None, str]:
    """Validate and convert limit parameter.

    Args:
        limit: Limit value to validate

    Returns:
        Tuple of (is_valid, parsed_value, error_message)
    """
    if limit is None:
        return True, PER_PAGE_DEFAULT_LIMIT, ""
    try:
        limit_int = int(limit)
        if limit_int <= 0:
            return False, None, MSG_INVALID_LIMIT
        return True, limit_int, ""
    except (ValueError, TypeError):
        return False, None, MSG_INVALID_LIMIT

def _strip_html(text: str | None) -> str | None:
    """Strip HTML tags from text for processed_body / processed_summary.

    Simplified version of the upstream BeautifulSoup processing.
    We avoid importing bs4 as a hard dependency and use a simple approach.
    """
    if not text:
        return text

    # Strip HTML tags using regex (no external dependency)
    import re

    clean = re.sub(r"<[^>]+>", "", text)
    lines = [x.strip() for x in clean.split("\n") if x.strip()]
    return "\n".join(lines)

def _process_report(report: dict[str, Any]) -> dict[str, Any]:
    """Add processed_body and processed_summary fields to a report.

    Mirrors the upstream ``_process_report_data`` method.
    """
    body = report.get("body")
    report["processed_body"] = _strip_html(body) if body else body

    summary = report.get("summary")
    report["processed_summary"] = _strip_html(summary) if summary else summary

    return report

# ============================================================================
# BASE HELPER FOR ALL FLASHPOINT ACTIONS
# ============================================================================

class _FlashpointBase(IntegrationAction):
    """Shared helpers for all Flashpoint actions."""

    def get_http_headers(self) -> dict[str, str]:
        """Return authorization and integration-identifier headers."""
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN, "")
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-FP-IntegrationPlatform": X_FP_INTEGRATION_PLATFORM,
        }
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        return headers

    @property
    def _base_url(self) -> str:
        return self.settings.get(SETTINGS_BASE_URL, FLASHPOINT_DEFAULT_BASE_URL).rstrip(
            "/"
        )

    @property
    def _timeout(self) -> int:
        return self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

    @property
    def _session_timeout(self) -> int:
        """Session scroll timeout in minutes (1-60)."""
        return self.settings.get(
            SETTINGS_SESSION_TIMEOUT, DEFAULT_SESSION_TIMEOUT_MINUTES
        )

    def _validate_api_token(self) -> str | None:
        """Validate and return API token, or None if missing."""
        return self.credentials.get(CREDENTIAL_API_TOKEN)

    # ------------------------------------------------------------------
    # Pagination helpers
    # ------------------------------------------------------------------

    async def _paginate_with_skip(
        self,
        endpoint: str,
        limit: int = PER_PAGE_DEFAULT_LIMIT,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Paginate using skip/offset strategy (reports endpoints).

        Returns:
            List of result items.

        Raises:
            httpx.HTTPStatusError: On HTTP errors.
        """
        all_items: list[dict[str, Any]] = []
        skip = 0
        page_limit = min(limit, PER_PAGE_DEFAULT_LIMIT)
        request_params = dict(params or {})

        while True:
            request_params["limit"] = page_limit
            request_params["skip"] = skip

            response = await self.http_request(
                url=f"{self._base_url}{endpoint}",
                params=request_params,
                timeout=self._timeout,
            )
            body = response.json()

            items = body.get("data", [])
            if items is None:
                break

            all_items.extend(items)

            if len(all_items) >= limit:
                return all_items[:limit]

            total = body.get("total", 0)
            if len(all_items) >= total:
                break

            skip += PER_PAGE_DEFAULT_LIMIT

        return all_items

    async def _paginate_with_scroll(
        self,
        limit: int = PER_PAGE_DEFAULT_LIMIT,
        params: dict[str, Any] | None = None,
        is_indicators: bool = False,
    ) -> list[dict[str, Any]]:
        """Paginate using session-scroll strategy (indicators / search).

        Args:
            limit: Maximum results to fetch.
            params: Extra query parameters.
            is_indicators: True for indicator APIs, False for search APIs.

        Returns:
            List of result items.

        Raises:
            httpx.HTTPStatusError: On HTTP errors.
        """
        all_items: list[dict[str, Any]] = []
        page_limit = min(limit, PER_PAGE_DEFAULT_LIMIT)
        request_params = dict(params or {})
        request_params["limit"] = page_limit

        # Choose endpoint and scroll param based on API type
        if is_indicators:
            endpoint = INDICATORS_ENDPOINT
            scroll_endpoint = INDICATORS_SCROLL_ENDPOINT
            request_params["scroll"] = True
        else:
            endpoint = ALL_SEARCH_ENDPOINT
            scroll_endpoint = ALL_SEARCH_SCROLL_ENDPOINT
            request_params["scroll"] = f"{self._session_timeout}m"

        # Initial request
        response = await self.http_request(
            url=f"{self._base_url}{endpoint}",
            params=request_params,
            timeout=self._timeout,
        )
        body = response.json()

        items, scroll_id = self._extract_scroll_items(body, is_indicators)
        if not items:
            await self._disable_scroll(scroll_id, is_indicators)
            return all_items

        all_items.extend(items)

        if len(all_items) >= limit:
            await self._disable_scroll(scroll_id, is_indicators)
            return all_items[:limit]

        # Further pagination
        if scroll_id:
            scroll_url = f"{self._base_url}{scroll_endpoint}"
            if not is_indicators:
                scroll_url = f"{scroll_url}?scroll={self._session_timeout}m"

            while True:
                response = await self.http_request(
                    url=scroll_url,
                    method="POST",
                    json_data={"scroll_id": scroll_id},
                    timeout=self._timeout,
                )
                body = response.json()

                items, _ = self._extract_scroll_items(body, is_indicators)

                if not items:
                    break

                all_items.extend(items)

                if len(all_items) >= limit:
                    break

            await self._disable_scroll(scroll_id, is_indicators)

        return all_items[:limit]

    @staticmethod
    def _extract_scroll_items(
        body: dict[str, Any], is_indicators: bool
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Extract items and scroll_id from paginated response."""
        if is_indicators:
            items = body.get("results", [])
            scroll_id = body.get("scroll_id")
        else:
            items = body.get("hits", {}).get("hits", [])
            scroll_id = body.get("_scroll_id")
        return items or [], scroll_id

    async def _disable_scroll(self, scroll_id: str | None, is_indicators: bool) -> None:
        """Disable a scroll session (best-effort, errors logged not raised)."""
        if not scroll_id:
            return

        endpoint = (
            INDICATORS_SCROLL_ENDPOINT if is_indicators else ALL_SEARCH_SCROLL_ENDPOINT
        )

        try:
            await self.http_request(
                url=f"{self._base_url}{endpoint}",
                method="DELETE",
                json_data={"scroll_id": scroll_id},
                timeout=self._timeout,
            )
        except Exception:
            # Session may already be expired/disabled -- log and move on
            logger.debug("flashpoint_scroll_disable_ignored", scroll_id=scroll_id)

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(_FlashpointBase):
    """Test connectivity to the Flashpoint API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Fetch a single indicator to validate API connectivity.

        Returns:
            Success result if API responds, error result otherwise.
        """
        api_token = self._validate_api_token()
        if not api_token:
            return self.error_result(
                MSG_MISSING_API_TOKEN,
                error_type=ERROR_TYPE_CONFIGURATION,
                data={"healthy": False},
            )

        try:
            await self.http_request(
                url=f"{self._base_url}{INDICATORS_ENDPOINT}",
                params={"limit": 1},
                timeout=self._timeout,
            )
            return self.success_result(data={"healthy": True})
        except httpx.TimeoutException as e:
            logger.error("flashpoint_health_check_timeout", error=str(e))
            return self.error_result(
                e, error_type=ERROR_TYPE_TIMEOUT, data={"healthy": False}
            )
        except httpx.RequestError as e:
            logger.error("flashpoint_health_check_connection_error", error=str(e))
            return self.error_result(
                MSG_SERVER_CONNECTION,
                error_type=ERROR_TYPE_HTTP,
                data={"healthy": False},
            )
        except httpx.HTTPStatusError as e:
            error_detail = str(e)
            with contextlib.suppress(Exception):
                error_detail = e.response.json().get("detail", str(e))
            logger.error("flashpoint_health_check_failed", error=error_detail)
            return self.error_result(
                error_detail, error_type=ERROR_TYPE_HTTP, data={"healthy": False}
            )
        except Exception as e:
            logger.error("flashpoint_health_check_failed", error=str(e))
            return self.error_result(e, data={"healthy": False})

class ListIntelligenceReportsAction(_FlashpointBase):
    """Fetch a list of intelligence reports from Flashpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List intelligence reports with skip-based pagination.

        Keyword Args:
            limit: Maximum number of reports (default 500).

        Returns:
            Success result with list of report data.
        """
        api_token = self._validate_api_token()
        if not api_token:
            return self.error_result(
                MSG_MISSING_API_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        is_valid, limit, err = _validate_limit(kwargs.get("limit"))
        if not is_valid:
            return self.error_result(err, error_type=ERROR_TYPE_VALIDATION)

        try:
            reports = await self._paginate_with_skip(LIST_REPORTS_ENDPOINT, limit=limit)
            reports = [_process_report(r) for r in reports]

            return self.success_result(
                data=reports,
                summary={"total_reports": len(reports)},
            )
        except httpx.TimeoutException as e:
            return self.error_result(e, error_type=ERROR_TYPE_TIMEOUT)
        except httpx.RequestError:
            return self.error_result(MSG_SERVER_CONNECTION, error_type=ERROR_TYPE_HTTP)
        except httpx.HTTPStatusError as e:
            return self.error_result(e, error_type=ERROR_TYPE_HTTP)
        except Exception as e:
            return self.error_result(e)

class GetIntelligenceReportAction(_FlashpointBase):
    """Fetch a specific intelligence report by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get a single intelligence report.

        Keyword Args:
            report_id: Flashpoint report ID (required).

        Returns:
            Success result with report data, or not_found for 404.
        """
        api_token = self._validate_api_token()
        if not api_token:
            return self.error_result(
                MSG_MISSING_API_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        report_id = kwargs.get("report_id")
        if not report_id or not isinstance(report_id, str):
            return self.error_result(
                MSG_MISSING_REPORT_ID, error_type=ERROR_TYPE_VALIDATION
            )

        try:
            url = f"{self._base_url}{GET_REPORT_ENDPOINT.format(report_id=report_id)}"
            response = await self.http_request(url=url, timeout=self._timeout)
            report = response.json()
            report = _process_report(report)

            return self.success_result(data=report)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("flashpoint_report_not_found", report_id=report_id)
                return self.success_result(
                    data={"report_id": report_id}, not_found=True
                )
            return self.error_result(e, error_type=ERROR_TYPE_HTTP)
        except httpx.TimeoutException as e:
            return self.error_result(e, error_type=ERROR_TYPE_TIMEOUT)
        except httpx.RequestError:
            return self.error_result(MSG_SERVER_CONNECTION, error_type=ERROR_TYPE_HTTP)
        except Exception as e:
            return self.error_result(e)

class ListRelatedReportsAction(_FlashpointBase):
    """Fetch related intelligence reports for a given report ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List reports related to a specific report.

        Keyword Args:
            report_id: Flashpoint report ID (required).
            limit: Maximum number of related reports (default 500).

        Returns:
            Success result with list of related reports.
        """
        api_token = self._validate_api_token()
        if not api_token:
            return self.error_result(
                MSG_MISSING_API_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        report_id = kwargs.get("report_id")
        if not report_id or not isinstance(report_id, str):
            return self.error_result(
                MSG_MISSING_REPORT_ID, error_type=ERROR_TYPE_VALIDATION
            )

        is_valid, limit, err = _validate_limit(kwargs.get("limit"))
        if not is_valid:
            return self.error_result(err, error_type=ERROR_TYPE_VALIDATION)

        try:
            endpoint = LIST_RELATED_REPORTS_ENDPOINT.format(report_id=report_id)
            reports = await self._paginate_with_skip(endpoint, limit=limit)
            reports = [_process_report(r) for r in reports]

            return self.success_result(
                data=reports,
                summary={"total_related_reports": len(reports)},
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("flashpoint_related_reports_not_found", report_id=report_id)
                return self.success_result(
                    data={"report_id": report_id}, not_found=True
                )
            return self.error_result(e, error_type=ERROR_TYPE_HTTP)
        except httpx.TimeoutException as e:
            return self.error_result(e, error_type=ERROR_TYPE_TIMEOUT)
        except httpx.RequestError:
            return self.error_result(MSG_SERVER_CONNECTION, error_type=ERROR_TYPE_HTTP)
        except Exception as e:
            return self.error_result(e)

class GetCompromisedCredentialsAction(_FlashpointBase):
    """Fetch compromised credential sightings from Flashpoint."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search for compromised credential sightings.

        Keyword Args:
            filter: Additional query filter (e.g. ``+is_fresh:true``).
            limit: Maximum number of results (default 500).

        Returns:
            Success result with credential sighting data.
        """
        api_token = self._validate_api_token()
        if not api_token:
            return self.error_result(
                MSG_MISSING_API_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        is_valid, limit, err = _validate_limit(kwargs.get("limit"))
        if not is_valid:
            return self.error_result(err, error_type=ERROR_TYPE_VALIDATION)

        # Build credential-sighting query (matches the upstream logic)
        query_filter = kwargs.get("filter", "")
        query = f"+basetypes:credential-sighting{query_filter}"

        try:
            results = await self._paginate_with_scroll(
                limit=limit,
                params={"query": query},
                is_indicators=False,
            )

            return self.success_result(
                data=results,
                summary={"total_results": len(results)},
            )
        except httpx.TimeoutException as e:
            return self.error_result(e, error_type=ERROR_TYPE_TIMEOUT)
        except httpx.RequestError:
            return self.error_result(MSG_SERVER_CONNECTION, error_type=ERROR_TYPE_HTTP)
        except httpx.HTTPStatusError as e:
            return self.error_result(e, error_type=ERROR_TYPE_HTTP)
        except Exception as e:
            return self.error_result(e)

class RunQueryAction(_FlashpointBase):
    """Perform a universal search across all Flashpoint data sources."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute a free-text or basetype search.

        Keyword Args:
            query: Search query string (required).
            limit: Maximum number of results (default 500).

        Returns:
            Success result with search results.
        """
        api_token = self._validate_api_token()
        if not api_token:
            return self.error_result(
                MSG_MISSING_API_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        query = kwargs.get("query")
        if not query or not isinstance(query, str):
            return self.error_result(
                MSG_MISSING_QUERY, error_type=ERROR_TYPE_VALIDATION
            )

        is_valid, limit, err = _validate_limit(kwargs.get("limit"))
        if not is_valid:
            return self.error_result(err, error_type=ERROR_TYPE_VALIDATION)

        try:
            results = await self._paginate_with_scroll(
                limit=limit,
                params={"query": query},
                is_indicators=False,
            )

            return self.success_result(
                data=results,
                summary={"total_results": len(results)},
            )
        except httpx.TimeoutException as e:
            return self.error_result(e, error_type=ERROR_TYPE_TIMEOUT)
        except httpx.RequestError:
            return self.error_result(MSG_SERVER_CONNECTION, error_type=ERROR_TYPE_HTTP)
        except httpx.HTTPStatusError as e:
            return self.error_result(e, error_type=ERROR_TYPE_HTTP)
        except Exception as e:
            return self.error_result(e)

class ListIndicatorsAction(_FlashpointBase):
    """List IoC indicators from Flashpoint technical intelligence."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Fetch IoCs with optional attribute-type and query filtering.

        Keyword Args:
            attributes_types: Comma-separated IoC types (e.g. ``ip-src,domain``).
            query: Free-text filter.
            limit: Maximum indicators (default 500).

        Returns:
            Success result with indicator data (Attribute-level objects).
        """
        api_token = self._validate_api_token()
        if not api_token:
            return self.error_result(
                MSG_MISSING_API_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        is_valid, limit, err = _validate_limit(kwargs.get("limit"))
        if not is_valid:
            return self.error_result(err, error_type=ERROR_TYPE_VALIDATION)

        params: dict[str, Any] = {}

        # Validate and normalize attribute types
        attributes_types = kwargs.get("attributes_types")
        if attributes_types:
            types = [t.strip() for t in attributes_types.split(",")]
            types = [t for t in types if t]
            if not types:
                return self.error_result(
                    MSG_INVALID_COMMA_SEPARATED, error_type=ERROR_TYPE_VALIDATION
                )
            params["types"] = ",".join(t.lower() for t in types)

        query = kwargs.get("query")
        if query:
            params["query"] = query

        try:
            results = await self._paginate_with_scroll(
                limit=limit,
                params=params,
                is_indicators=True,
            )

            # Unwrap Attribute wrapper if present (matches the upstream behaviour)
            unwrapped = []
            for item in results:
                if "Attribute" in item:
                    unwrapped.append(item["Attribute"])
                else:
                    unwrapped.append(item)

            return self.success_result(
                data=unwrapped,
                summary={"total_iocs": len(unwrapped)},
            )
        except httpx.TimeoutException as e:
            return self.error_result(e, error_type=ERROR_TYPE_TIMEOUT)
        except httpx.RequestError:
            return self.error_result(MSG_SERVER_CONNECTION, error_type=ERROR_TYPE_HTTP)
        except httpx.HTTPStatusError as e:
            return self.error_result(e, error_type=ERROR_TYPE_HTTP)
        except Exception as e:
            return self.error_result(e)

class SearchIndicatorsAction(_FlashpointBase):
    """Search for a specific IoC value by attribute type."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search indicators by exact type + value.

        Keyword Args:
            attribute_type: IoC attribute type (e.g. ``ip-src``, ``domain``).
            attribute_value: The value to search for.
            limit: Maximum indicators (default 500).

        Returns:
            Success result with matching indicator data.
        """
        api_token = self._validate_api_token()
        if not api_token:
            return self.error_result(
                MSG_MISSING_API_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        attribute_type = kwargs.get("attribute_type")
        if not attribute_type or not isinstance(attribute_type, str):
            return self.error_result(
                MSG_MISSING_ATTRIBUTE_TYPE, error_type=ERROR_TYPE_VALIDATION
            )

        attribute_value = kwargs.get("attribute_value")
        if not attribute_value or not isinstance(attribute_value, str):
            return self.error_result(
                MSG_MISSING_ATTRIBUTE_VALUE, error_type=ERROR_TYPE_VALIDATION
            )

        is_valid, limit, err = _validate_limit(kwargs.get("limit"))
        if not is_valid:
            return self.error_result(err, error_type=ERROR_TYPE_VALIDATION)

        attribute_type = attribute_type.strip().lower()

        # URL values need quoting to avoid 500 errors
        if attribute_type == "url":
            search_fields = f'{attribute_type}=="{attribute_value}"'
        else:
            search_fields = f"{attribute_type}=={attribute_value}"

        try:
            results = await self._paginate_with_scroll(
                limit=limit,
                params={"search_fields": search_fields},
                is_indicators=True,
            )

            # Unwrap Attribute wrapper if present (matches the upstream behaviour)
            unwrapped = []
            for item in results:
                if "Attribute" in item:
                    unwrapped.append(item["Attribute"])
                else:
                    unwrapped.append(item)

            return self.success_result(
                data=unwrapped,
                summary={"total_iocs": len(unwrapped)},
            )
        except httpx.TimeoutException as e:
            return self.error_result(e, error_type=ERROR_TYPE_TIMEOUT)
        except httpx.RequestError:
            return self.error_result(MSG_SERVER_CONNECTION, error_type=ERROR_TYPE_HTTP)
        except httpx.HTTPStatusError as e:
            return self.error_result(e, error_type=ERROR_TYPE_HTTP)
        except Exception as e:
            return self.error_result(e)

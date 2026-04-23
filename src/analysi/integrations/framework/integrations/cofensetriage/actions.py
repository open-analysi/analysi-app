"""Cofense Triage integration actions for phishing report triage and response.
Uses Cofense Triage v2 API with OAuth2 client_credentials authentication.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ACCEPT_HEADER,
    CATEGORIES_ENDPOINT,
    CATEGORIZE_REPORT_ENDPOINT,
    CATEGORY_BY_NAME_ENDPOINT,
    CATEGORY_REPORTS_ENDPOINT,
    CONTENT_TYPE_HEADER,
    DEFAULT_MAX_RESULTS,
    DEFAULT_PAGE_SIZE,
    DEFAULT_THREAT_SOURCE,
    LEVEL_VALUES,
    OPERATORS,
    REPORT_ENDPOINT,
    REPORT_FILTER_MAPPING,
    REPORT_LOCATIONS,
    REPORTER_REPORTS_ENDPOINT,
    REPORTERS_ENDPOINT,
    REPORTS_ENDPOINT,
    SORT_VALUES,
    STATUS_ENDPOINT,
    THREAT_FILTER_MAPPING,
    THREAT_INDICATORS_ENDPOINT,
    THREAT_LEVELS,
    THREAT_TYPES,
    TOKEN_ENDPOINT,
    TYPE_VALUES,
    URLS_ENDPOINT,
)

logger = get_logger(__name__)

# ============================================================================
# OAUTH2 TOKEN HELPER
# ============================================================================

async def _get_access_token(action: IntegrationAction) -> str | None:
    """Obtain OAuth2 access token using client_credentials grant.

    Args:
        action: IntegrationAction instance with credentials and settings

    Returns:
        Access token string, or None on failure
    """
    base_url = action.settings.get("base_url", "").rstrip("/")
    client_id = action.credentials.get("client_id")
    client_secret = action.credentials.get("client_secret")

    if not base_url or not client_id or not client_secret:
        return None

    token_url = f"{base_url}{TOKEN_ENDPOINT}"

    response = await action.http_request(
        url=token_url,
        method="POST",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
    )

    token_data = response.json()
    return token_data.get("access_token")

def _get_auth_headers(access_token: str) -> dict[str, str]:
    """Build authorization headers for Cofense Triage API calls.

    Args:
        access_token: OAuth2 bearer token

    Returns:
        Headers dict with Accept and Authorization
    """
    return {
        "Accept": ACCEPT_HEADER,
        "Authorization": f"Bearer {access_token}",
    }

# ============================================================================
# PAGINATION HELPER
# ============================================================================

async def _paginate(
    action: IntegrationAction,
    endpoint: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
    max_results: int = 0,
) -> list[dict[str, Any]]:
    """Fetch paginated results from a Cofense Triage v2 API endpoint.

    Args:
        action: IntegrationAction instance for HTTP calls
        endpoint: Full URL of the API endpoint
        headers: Auth headers
        params: Query parameters
        max_results: Maximum number of results (0 = unlimited)

    Returns:
        List of data objects from paginated responses
    """
    if params is None:
        params = {}

    data: list[dict[str, Any]] = []
    page = 1
    page_size = DEFAULT_PAGE_SIZE

    if max_results and max_results < DEFAULT_PAGE_SIZE:
        page_size = max_results

    while True:
        params["page[number]"] = page
        params["page[size]"] = page_size

        response = await action.http_request(
            url=endpoint,
            headers=headers,
            params=params,
        )
        resp_json = response.json()

        data.extend(resp_json.get("data", []))

        total_data = len(data)
        if max_results and total_data >= max_results:
            return data[:max_results]

        if not resp_json.get("links", {}).get("next"):
            break

        page += 1
        if max_results:
            page_size = min(max_results - total_data, DEFAULT_PAGE_SIZE)

    return data

# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def _validate_positive_integer(
    value: Any, param_name: str
) -> tuple[bool, str, int | None]:
    """Validate that a value is a positive integer.

    Args:
        value: Value to validate
        param_name: Parameter name for error messages

    Returns:
        Tuple of (is_valid, error_message, parsed_value)
    """
    if value is None:
        return True, "", None

    try:
        parsed = int(value)
    except (ValueError, TypeError):
        return False, f"Please provide a valid integer value for '{param_name}'", None

    if parsed < 0:
        return (
            False,
            f"Please provide a non-negative integer value for '{param_name}'",
            None,
        )

    if parsed == 0:
        return (
            False,
            f"Please provide a non-zero integer value for '{param_name}'",
            None,
        )

    return True, "", parsed

def _clean_comma_list(value: str) -> str:
    """Clean a comma-separated list string by stripping whitespace and empty items.

    Args:
        value: Comma-separated string

    Returns:
        Cleaned comma-separated string
    """
    if not value:
        return ""
    items = [x.strip() for x in value.split(",")]
    return ",".join(item for item in items if item)

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Test connectivity to Cofense Triage by obtaining an OAuth2 token and checking system status."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Cofense Triage API connectivity.

        Returns:
            Success result if OAuth2 token and status endpoint are reachable.
        """
        base_url = self.settings.get("base_url", "").rstrip("/")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")

        if not base_url:
            return self.error_result(
                "Missing required setting: base_url", error_type="ConfigurationError"
            )

        if not client_id or not client_secret:
            return self.error_result(
                "Missing required credentials: client_id and client_secret",
                error_type="ConfigurationError",
            )

        try:
            access_token = await _get_access_token(self)
            if not access_token:
                return self.error_result(
                    "Failed to obtain OAuth2 access token",
                    error_type="AuthenticationError",
                )

            headers = _get_auth_headers(access_token)
            status_url = f"{base_url}{STATUS_ENDPOINT}"

            await self.http_request(url=status_url, headers=headers)

            return self.success_result(
                data={"healthy": True, "api_version": "v2"},
                healthy=True,
                message="Cofense Triage API is accessible",
            )

        except httpx.HTTPStatusError as e:
            self.log_error("cofensetriage_health_check_failed", error=e)
            return self.error_result(e, data={"healthy": False})
        except Exception as e:
            self.log_error("cofensetriage_health_check_failed", error=e)
            return self.error_result(e, data={"healthy": False})

def _build_report_query_params(kwargs: dict[str, Any], sort: str) -> dict[str, Any]:
    """Build query parameters for the reports endpoint from action kwargs.

    Args:
        kwargs: Action keyword arguments
        sort: Validated sort value (oldest_first or latest_first)

    Returns:
        Query parameters dict for the Cofense Triage v2 API
    """
    params: dict[str, Any] = {}

    location = kwargs.get("location")
    if location and location.lower() != "all":
        params[REPORT_FILTER_MAPPING["location"]] = location

    for key in ("from_address", "subject"):
        value = kwargs.get(key)
        if value:
            params[REPORT_FILTER_MAPPING[key]] = value

    match_priority = kwargs.get("match_priority")
    if match_priority is not None:
        params[REPORT_FILTER_MAPPING["match_priority"]] = match_priority

    for key in ("start_date", "end_date"):
        value = kwargs.get(key)
        if value:
            params[REPORT_FILTER_MAPPING[key]] = value

    tags = _clean_comma_list(kwargs.get("tags", ""))
    if tags:
        params[REPORT_FILTER_MAPPING["tags"]] = tags

    categorization_tags = _clean_comma_list(kwargs.get("categorization_tags", ""))
    if categorization_tags:
        params[REPORT_FILTER_MAPPING["categorization_tags"]] = categorization_tags

    params["sort"] = "updated_at" if sort == "oldest_first" else "-updated_at"

    return params

class GetReportsAction(IntegrationAction):
    """Retrieve phishing reports from Cofense Triage filtered by various parameters."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get reports from Cofense Triage.

        Keyword Args:
            location: Filter by report location (inbox, reconnaissance, processed, all)
            from_address: Filter by sender email address
            subject: Filter by email subject (contains match)
            match_priority: Filter by highest matching rule priority
            category_id: Filter by category ID
            reporter_email: Filter by reporter email (resolved to reporter_id)
            start_date: Filter reports updated on or after this date
            end_date: Filter reports updated before this date
            tags: Comma-separated list of tags
            categorization_tags: Comma-separated categorization tags
            sort: Sort order (oldest_first or latest_first)
            max_results: Maximum number of results to return

        Returns:
            Success result with list of report objects.
        """
        base_url = self.settings.get("base_url", "").rstrip("/")
        if not base_url:
            return self.error_result(
                "Missing required setting: base_url", error_type="ConfigurationError"
            )

        # Validate parameters before making any network calls
        location = kwargs.get("location")
        if location and location.lower() not in REPORT_LOCATIONS:
            return self.error_result(
                f"Invalid location: '{location}'. Must be one of: {REPORT_LOCATIONS}",
                error_type="ValidationError",
            )

        sort = kwargs.get("sort", "oldest_first")
        if sort not in SORT_VALUES:
            return self.error_result(
                f"Invalid sort: '{sort}'. Must be one of: {SORT_VALUES}",
                error_type="ValidationError",
            )

        max_results = kwargs.get("max_results", DEFAULT_MAX_RESULTS)
        is_valid, err_msg, max_results_int = _validate_positive_integer(
            max_results, "max_results"
        )
        if not is_valid:
            return self.error_result(err_msg, error_type="ValidationError")

        try:
            access_token = await _get_access_token(self)
            if not access_token:
                return self.error_result(
                    "Failed to obtain OAuth2 access token",
                    error_type="AuthenticationError",
                )

            headers = _get_auth_headers(access_token)
            params = _build_report_query_params(kwargs, sort)

            # Determine endpoint based on reporter_email or category_id
            category_id = kwargs.get("category_id")
            reporter_email = kwargs.get("reporter_email")
            endpoint = f"{base_url}{REPORTS_ENDPOINT}"

            if reporter_email:
                # Look up reporter_id from email
                reporter_params = {"filter[email]": reporter_email}
                reporter_resp = await self.http_request(
                    url=f"{base_url}{REPORTERS_ENDPOINT}",
                    headers=headers,
                    params=reporter_params,
                )
                reporters = reporter_resp.json().get("data", [])
                if not reporters:
                    return self.error_result(
                        f"Reporter with email '{reporter_email}' not found",
                        error_type="ValidationError",
                    )
                reporter_id = reporters[0]["id"]
                endpoint = f"{base_url}{REPORTER_REPORTS_ENDPOINT.format(reporter_id=reporter_id)}"

            if category_id is not None:
                endpoint = f"{base_url}{CATEGORY_REPORTS_ENDPOINT.format(category_id=category_id)}"

            reports = await _paginate(
                self, endpoint, headers, params, max_results_int or 0
            )

            return self.success_result(
                data=reports,
                summary={"total_reports_retrieved": len(reports)},
            )

        except httpx.HTTPStatusError as e:
            self.log_error("cofensetriage_get_reports_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("cofensetriage_get_reports_failed", error=e)
            return self.error_result(e)

class GetReportAction(IntegrationAction):
    """Retrieve a single phishing report by ID from Cofense Triage."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get a specific report by ID.

        Keyword Args:
            report_id: The report ID to retrieve (required)

        Returns:
            Success result with report data, or not_found if report doesn't exist.
        """
        report_id = kwargs.get("report_id")
        if not report_id:
            return self.error_result(
                "Missing required parameter: report_id", error_type="ValidationError"
            )

        is_valid, err_msg, report_id_int = _validate_positive_integer(
            report_id, "report_id"
        )
        if not is_valid:
            return self.error_result(err_msg, error_type="ValidationError")

        base_url = self.settings.get("base_url", "").rstrip("/")
        if not base_url:
            return self.error_result(
                "Missing required setting: base_url", error_type="ConfigurationError"
            )

        try:
            access_token = await _get_access_token(self)
            if not access_token:
                return self.error_result(
                    "Failed to obtain OAuth2 access token",
                    error_type="AuthenticationError",
                )

            headers = _get_auth_headers(access_token)
            url = f"{base_url}{REPORT_ENDPOINT.format(report_id=report_id_int)}"

            response = await self.http_request(url=url, headers=headers)
            resp_json = response.json()

            report = resp_json.get("data", {})
            if not report:
                return self.success_result(
                    not_found=True,
                    data={"report_id": report_id_int},
                    message="No report found",
                )

            return self.success_result(
                data=report, message="Successfully retrieved the report"
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("cofensetriage_report_not_found", report_id=report_id_int)
                return self.success_result(
                    not_found=True,
                    data={"report_id": report_id_int},
                )
            self.log_error("cofensetriage_get_report_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("cofensetriage_get_report_failed", error=e)
            return self.error_result(e)

class CategorizeReportAction(IntegrationAction):
    """Categorize a phishing report in Cofense Triage."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Categorize a report.

        Keyword Args:
            report_id: The report ID to categorize (required)
            category_id: Category ID to assign (one of category_id or category_name required)
            category_name: Category name to assign (resolved to category_id)
            categorization_tags: Comma-separated categorization tags
            response_id: Optional response ID to associate

        Returns:
            Success result on categorization, error on failure.
        """
        report_id = kwargs.get("report_id")
        if not report_id:
            return self.error_result(
                "Missing required parameter: report_id", error_type="ValidationError"
            )

        is_valid, err_msg, report_id_int = _validate_positive_integer(
            report_id, "report_id"
        )
        if not is_valid:
            return self.error_result(err_msg, error_type="ValidationError")

        category_id = kwargs.get("category_id")
        category_name = kwargs.get("category_name")

        if category_id is None and not category_name:
            return self.error_result(
                "Please provide either category_id or category_name",
                error_type="ValidationError",
            )

        # Validate category_id if provided
        if category_id is not None:
            try:
                category_id = int(category_id)
            except (ValueError, TypeError):
                return self.error_result(
                    "category_id must be an integer",
                    error_type="ValidationError",
                )

        base_url = self.settings.get("base_url", "").rstrip("/")
        if not base_url:
            return self.error_result(
                "Missing required setting: base_url", error_type="ConfigurationError"
            )

        try:
            access_token = await _get_access_token(self)
            if not access_token:
                return self.error_result(
                    "Failed to obtain OAuth2 access token",
                    error_type="AuthenticationError",
                )

            headers = {
                "Accept": ACCEPT_HEADER,
                "Content-Type": CONTENT_TYPE_HEADER,
                "Authorization": f"Bearer {access_token}",
            }

            # Resolve category_name to category_id if needed
            if category_name and category_id is None:
                cat_url = f"{base_url}{CATEGORY_BY_NAME_ENDPOINT.format(category_name=category_name)}"
                cat_response = await self.http_request(url=cat_url, headers=headers)
                cat_data = cat_response.json().get("data", [])
                if not cat_data:
                    return self.error_result(
                        f"Category with name '{category_name}' not found",
                        error_type="ValidationError",
                    )
                category_id = int(cat_data[0]["id"])

            # Build categorization tags
            categorization_tags_str = kwargs.get("categorization_tags", "")
            categorization_tags = [
                x.strip() for x in categorization_tags_str.split(",") if x.strip()
            ]

            response_id = kwargs.get("response_id")
            if response_id is not None:
                try:
                    response_id = int(response_id)
                except (ValueError, TypeError):
                    return self.error_result(
                        "response_id must be an integer",
                        error_type="ValidationError",
                    )

            payload = {
                "data": {
                    "category_id": category_id,
                    "categorization_tags": categorization_tags,
                    "response_id": response_id,
                }
            }

            url = f"{base_url}{CATEGORIZE_REPORT_ENDPOINT.format(report_id=report_id_int)}"
            await self.http_request(
                url=url, method="POST", headers=headers, json_data=payload
            )

            return self.success_result(
                data={"report_id": report_id_int, "category_id": category_id},
                message="Successfully categorized the report",
            )

        except httpx.HTTPStatusError as e:
            self.log_error("cofensetriage_categorize_report_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("cofensetriage_categorize_report_failed", error=e)
            return self.error_result(e)

class GetThreatIndicatorsAction(IntegrationAction):
    """Retrieve threat indicators from Cofense Triage."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get threat indicators matching filter criteria.

        Keyword Args:
            level: Threat level filter (malicious, suspicious, benign, all)
            type: Threat type filter (hostname, url, md5, sha256, header, all)
            source: Threat source filter
            value: Threat value filter
            start_date: Filter indicators updated on or after this date
            end_date: Filter indicators updated before this date
            sort: Sort order (oldest_first or latest_first)
            max_results: Maximum number of results to return

        Returns:
            Success result with list of threat indicator objects.
        """
        base_url = self.settings.get("base_url", "").rstrip("/")
        if not base_url:
            return self.error_result(
                "Missing required setting: base_url", error_type="ConfigurationError"
            )

        # Validate parameters before making any network calls
        level = kwargs.get("level")
        if level and level.lower() not in LEVEL_VALUES:
            return self.error_result(
                f"Invalid level: '{level}'. Must be one of: {LEVEL_VALUES}",
                error_type="ValidationError",
            )

        threat_type = kwargs.get("type")
        if threat_type and threat_type.lower() not in TYPE_VALUES:
            return self.error_result(
                f"Invalid type: '{threat_type}'. Must be one of: {TYPE_VALUES}",
                error_type="ValidationError",
            )

        sort = kwargs.get("sort", "oldest_first")
        if sort not in SORT_VALUES:
            return self.error_result(
                f"Invalid sort: '{sort}'. Must be one of: {SORT_VALUES}",
                error_type="ValidationError",
            )

        max_results = kwargs.get("max_results", DEFAULT_MAX_RESULTS)
        is_valid, err_msg, max_results_int = _validate_positive_integer(
            max_results, "max_results"
        )
        if not is_valid:
            return self.error_result(err_msg, error_type="ValidationError")

        try:
            access_token = await _get_access_token(self)
            if not access_token:
                return self.error_result(
                    "Failed to obtain OAuth2 access token",
                    error_type="AuthenticationError",
                )

            headers = _get_auth_headers(access_token)

            # Build query params
            params: dict[str, Any] = {}

            if level and level.lower() != "all":
                params[THREAT_FILTER_MAPPING["level"]] = level

            if threat_type and threat_type.lower() != "all":
                params[THREAT_FILTER_MAPPING["type"]] = threat_type

            source = kwargs.get("source")
            if source:
                params[THREAT_FILTER_MAPPING["source"]] = source

            value = kwargs.get("value")
            if value:
                params[THREAT_FILTER_MAPPING["value"]] = value

            start_date = kwargs.get("start_date")
            if start_date:
                params[THREAT_FILTER_MAPPING["start_date"]] = start_date

            end_date = kwargs.get("end_date")
            if end_date:
                params[THREAT_FILTER_MAPPING["end_date"]] = end_date

            params["sort"] = "updated_at" if sort == "oldest_first" else "-updated_at"

            endpoint = f"{base_url}{THREAT_INDICATORS_ENDPOINT}"
            indicators = await _paginate(
                self, endpoint, headers, params, max_results_int or 0
            )

            return self.success_result(
                data=indicators,
                summary={"total_threat_indicators_retrieved": len(indicators)},
            )

        except httpx.HTTPStatusError as e:
            self.log_error("cofensetriage_get_threat_indicators_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("cofensetriage_get_threat_indicators_failed", error=e)
            return self.error_result(e)

class CreateThreatIndicatorAction(IntegrationAction):
    """Create a new threat indicator in Cofense Triage."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create a threat indicator.

        Keyword Args:
            level: Threat level (malicious, suspicious, benign) - required
            type: Threat type (hostname, header, url, md5, sha256) - required
            value: Threat value (the actual indicator) - required
            source: Threat source (defaults to 'Analysi-UI')

        Returns:
            Success result with created threat indicator data.
        """
        threat_level = kwargs.get("level")
        if not threat_level:
            return self.error_result(
                "Missing required parameter: level", error_type="ValidationError"
            )
        if threat_level.lower() not in THREAT_LEVELS:
            return self.error_result(
                f"Invalid level: '{threat_level}'. Must be one of: {THREAT_LEVELS}",
                error_type="ValidationError",
            )

        threat_type = kwargs.get("type")
        if not threat_type:
            return self.error_result(
                "Missing required parameter: type", error_type="ValidationError"
            )
        if threat_type.lower() not in THREAT_TYPES:
            return self.error_result(
                f"Invalid type: '{threat_type}'. Must be one of: {THREAT_TYPES}",
                error_type="ValidationError",
            )

        threat_value = kwargs.get("value")
        if not threat_value:
            return self.error_result(
                "Missing required parameter: value", error_type="ValidationError"
            )

        threat_source = kwargs.get("source", DEFAULT_THREAT_SOURCE)

        base_url = self.settings.get("base_url", "").rstrip("/")
        if not base_url:
            return self.error_result(
                "Missing required setting: base_url", error_type="ConfigurationError"
            )

        try:
            access_token = await _get_access_token(self)
            if not access_token:
                return self.error_result(
                    "Failed to obtain OAuth2 access token",
                    error_type="AuthenticationError",
                )

            headers = {
                "Accept": ACCEPT_HEADER,
                "Content-Type": CONTENT_TYPE_HEADER,
                "Authorization": f"Bearer {access_token}",
            }

            payload = {
                "data": {
                    "type": "threat_indicators",
                    "attributes": {
                        "threat_level": threat_level,
                        "threat_type": threat_type,
                        "threat_value": threat_value,
                        "threat_source": threat_source,
                    },
                }
            }

            endpoint = f"{base_url}{THREAT_INDICATORS_ENDPOINT}"
            response = await self.http_request(
                url=endpoint,
                method="POST",
                headers=headers,
                json_data=payload,
            )
            resp_json = response.json()
            indicator = resp_json.get("data", {})

            return self.success_result(
                data=indicator,
                summary={"threat_indicator_id": indicator.get("id")},
                message="Successfully created the threat indicator",
            )

        except httpx.HTTPStatusError as e:
            self.log_error("cofensetriage_create_threat_indicator_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("cofensetriage_create_threat_indicator_failed", error=e)
            return self.error_result(e)

class GetReportersAction(IntegrationAction):
    """Retrieve reporters from Cofense Triage."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get reporters matching filter criteria.

        Keyword Args:
            vip: Filter by VIP status (boolean)
            email: Filter by reporter email
            reputation_score: Comma-separated reputation scores to filter on
            sort: Sort order (oldest_first or latest_first)
            max_results: Maximum number of results to return

        Returns:
            Success result with list of reporter objects.
        """
        base_url = self.settings.get("base_url", "").rstrip("/")
        if not base_url:
            return self.error_result(
                "Missing required setting: base_url", error_type="ConfigurationError"
            )

        # Validate parameters before making any network calls
        sort = kwargs.get("sort", "oldest_first")
        if sort not in SORT_VALUES:
            return self.error_result(
                f"Invalid sort: '{sort}'. Must be one of: {SORT_VALUES}",
                error_type="ValidationError",
            )

        max_results = kwargs.get("max_results", DEFAULT_MAX_RESULTS)
        is_valid, err_msg, max_results_int = _validate_positive_integer(
            max_results, "max_results"
        )
        if not is_valid:
            return self.error_result(err_msg, error_type="ValidationError")

        try:
            access_token = await _get_access_token(self)
            if not access_token:
                return self.error_result(
                    "Failed to obtain OAuth2 access token",
                    error_type="AuthenticationError",
                )

            headers = _get_auth_headers(access_token)

            params: dict[str, Any] = {
                "sort": "id" if sort == "oldest_first" else "-id",
            }

            vip = kwargs.get("vip")
            if vip is not None:
                params["filter[vip]"] = vip

            email = kwargs.get("email")
            if email:
                params["filter[email]"] = email

            reputation_score = kwargs.get("reputation_score")
            if reputation_score:
                params["filter[reputation_score]"] = reputation_score

            endpoint = f"{base_url}{REPORTERS_ENDPOINT}"
            reporters = await _paginate(
                self, endpoint, headers, params, max_results_int or 0
            )

            return self.success_result(
                data=reporters,
                summary={"total_reporters_retrieved": len(reporters)},
            )

        except httpx.HTTPStatusError as e:
            self.log_error("cofensetriage_get_reporters_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("cofensetriage_get_reporters_failed", error=e)
            return self.error_result(e)

class GetUrlsAction(IntegrationAction):
    """Retrieve URLs from Cofense Triage."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get URLs matching filter criteria.

        Keyword Args:
            url_value: Filter by URL value
            risk_score: Filter by risk score
            risk_score_operator: Operator for risk score filter (eq, not_eq, lt, lteq, gt, gteq)
            start_date: Filter URLs updated on or after this date
            end_date: Filter URLs updated before this date
            sort: Sort order (oldest_first or latest_first)
            max_results: Maximum number of results to return

        Returns:
            Success result with list of URL objects.
        """
        base_url = self.settings.get("base_url", "").rstrip("/")
        if not base_url:
            return self.error_result(
                "Missing required setting: base_url", error_type="ConfigurationError"
            )

        # Validate parameters before making any network calls
        sort = kwargs.get("sort", "oldest_first")
        if sort not in SORT_VALUES:
            return self.error_result(
                f"Invalid sort: '{sort}'. Must be one of: {SORT_VALUES}",
                error_type="ValidationError",
            )

        risk_score_operator = kwargs.get("risk_score_operator", "eq")
        if risk_score_operator not in OPERATORS:
            return self.error_result(
                f"Invalid risk_score_operator: '{risk_score_operator}'. Must be one of: {OPERATORS}",
                error_type="ValidationError",
            )

        risk_score = kwargs.get("risk_score")
        if risk_score is not None:
            is_valid, err_msg, risk_score_int = _validate_positive_integer(
                risk_score, "risk_score"
            )
            if not is_valid:
                return self.error_result(err_msg, error_type="ValidationError")
        else:
            risk_score_int = None

        max_results = kwargs.get("max_results", DEFAULT_MAX_RESULTS)
        is_valid, err_msg, max_results_int = _validate_positive_integer(
            max_results, "max_results"
        )
        if not is_valid:
            return self.error_result(err_msg, error_type="ValidationError")

        try:
            access_token = await _get_access_token(self)
            if not access_token:
                return self.error_result(
                    "Failed to obtain OAuth2 access token",
                    error_type="AuthenticationError",
                )

            headers = _get_auth_headers(access_token)

            params: dict[str, Any] = {
                "sort": "updated_at" if sort == "oldest_first" else "-updated_at",
            }

            url_value = kwargs.get("url_value")
            if url_value:
                params["filter[url]"] = url_value

            if risk_score_int is not None:
                params[f"filter[risk_score_{risk_score_operator}]"] = risk_score_int

            start_date = kwargs.get("start_date")
            if start_date:
                params["filter[updated_at_gteq]"] = start_date

            end_date = kwargs.get("end_date")
            if end_date:
                params["filter[updated_at_lt]"] = end_date

            endpoint = f"{base_url}{URLS_ENDPOINT}"
            urls = await _paginate(
                self, endpoint, headers, params, max_results_int or 0
            )

            return self.success_result(
                data=urls,
                summary={"total_urls_retrieved": len(urls)},
            )

        except httpx.HTTPStatusError as e:
            self.log_error("cofensetriage_get_urls_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("cofensetriage_get_urls_failed", error=e)
            return self.error_result(e)

class GetCategoriesAction(IntegrationAction):
    """Retrieve report categories from Cofense Triage."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get categories from Cofense Triage.

        Keyword Args:
            name: Filter by category name (contains match)
            malicious: Filter by malicious flag (boolean)
            max_results: Maximum number of results to return

        Returns:
            Success result with list of category objects.
        """
        base_url = self.settings.get("base_url", "").rstrip("/")
        if not base_url:
            return self.error_result(
                "Missing required setting: base_url", error_type="ConfigurationError"
            )

        try:
            access_token = await _get_access_token(self)
            if not access_token:
                return self.error_result(
                    "Failed to obtain OAuth2 access token",
                    error_type="AuthenticationError",
                )

            headers = _get_auth_headers(access_token)

            max_results = kwargs.get("max_results", DEFAULT_MAX_RESULTS)
            is_valid, err_msg, max_results_int = _validate_positive_integer(
                max_results, "max_results"
            )
            if not is_valid:
                return self.error_result(err_msg, error_type="ValidationError")

            params: dict[str, Any] = {}

            name = kwargs.get("name")
            if name:
                params["filter[name_cont]"] = name

            malicious = kwargs.get("malicious")
            if malicious:
                params["filter[malicious]"] = True

            endpoint = f"{base_url}{CATEGORIES_ENDPOINT}"
            categories = await _paginate(
                self, endpoint, headers, params, max_results_int or 0
            )

            return self.success_result(
                data=categories,
                summary={"total_categories_retrieved": len(categories)},
            )

        except httpx.HTTPStatusError as e:
            self.log_error("cofensetriage_get_categories_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("cofensetriage_get_categories_failed", error=e)
            return self.error_result(e)

"""Unit tests for Flashpoint integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.flashpoint.actions import (
    GetCompromisedCredentialsAction,
    GetIntelligenceReportAction,
    HealthCheckAction,
    ListIndicatorsAction,
    ListIntelligenceReportsAction,
    ListRelatedReportsAction,
    RunQueryAction,
    SearchIndicatorsAction,
)
from analysi.integrations.framework.integrations.flashpoint.constants import (
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    MSG_INVALID_COMMA_SEPARATED,
    MSG_INVALID_LIMIT,
    MSG_MISSING_API_TOKEN,
    MSG_MISSING_ATTRIBUTE_TYPE,
    MSG_MISSING_ATTRIBUTE_VALUE,
    MSG_MISSING_QUERY,
    MSG_MISSING_REPORT_ID,
    MSG_SERVER_CONNECTION,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

# ============================================================================
# FIXTURES
# ============================================================================

DEFAULT_SETTINGS = {
    "base_url": "https://api.flashpoint.io",
    "timeout": 30,
    "session_timeout": 2,
}
DEFAULT_CREDENTIALS = {"api_token": "test-fp-token-123"}


def _make_action(cls, credentials=None, settings=None, action_id="test"):
    return cls(
        integration_id="flashpoint",
        action_id=action_id,
        settings=settings or DEFAULT_SETTINGS,
        credentials=credentials if credentials is not None else DEFAULT_CREDENTIALS,
    )


@pytest.fixture
def health_check():
    return _make_action(HealthCheckAction, action_id="health_check")


@pytest.fixture
def list_reports():
    return _make_action(
        ListIntelligenceReportsAction, action_id="list_intelligence_reports"
    )


@pytest.fixture
def get_report():
    return _make_action(
        GetIntelligenceReportAction, action_id="get_intelligence_report"
    )


@pytest.fixture
def list_related():
    return _make_action(ListRelatedReportsAction, action_id="list_related_reports")


@pytest.fixture
def compromised_creds():
    return _make_action(
        GetCompromisedCredentialsAction, action_id="get_compromised_credentials"
    )


@pytest.fixture
def run_query():
    return _make_action(RunQueryAction, action_id="run_query")


@pytest.fixture
def list_indicators():
    return _make_action(ListIndicatorsAction, action_id="list_indicators")


@pytest.fixture
def search_indicators():
    return _make_action(SearchIndicatorsAction, action_id="search_indicators")


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.text = str(json_data)
    return resp


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check):
    """Test successful health check."""
    mock_resp = _mock_response({"results": [{"type": "ip-dst"}]})

    health_check.http_request = AsyncMock(return_value=mock_resp)
    result = await health_check.execute()

    assert result["status"] == STATUS_SUCCESS
    assert result["data"]["healthy"] is True
    assert result["integration_id"] == "flashpoint"
    assert result["action_id"] == "health_check"
    health_check.http_request.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_missing_api_token():
    """Test health check without API token."""
    action = _make_action(HealthCheckAction, credentials={}, action_id="health_check")
    result = await action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_API_TOKEN
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION
    assert result["data"]["healthy"] is False
    assert result["integration_id"] == "flashpoint"
    assert result["action_id"] == "health_check"


@pytest.mark.asyncio
async def test_health_check_timeout(health_check):
    """Test health check timeout."""
    health_check.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("Request timed out")
    )
    result = await health_check.execute()

    assert result["status"] == STATUS_ERROR
    assert "timed out" in result["error"].lower()
    assert result["error_type"] == ERROR_TYPE_TIMEOUT
    assert result["data"]["healthy"] is False
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_health_check_connection_error(health_check):
    """Test health check connection error."""
    health_check.http_request = AsyncMock(
        side_effect=httpx.RequestError("Connection failed")
    )
    result = await health_check.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_SERVER_CONNECTION
    assert result["error_type"] == ERROR_TYPE_HTTP
    assert result["data"]["healthy"] is False
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_health_check_http_401(health_check):
    """Test health check with unauthorized response."""
    mock_resp = _mock_response({"detail": "Invalid API key"}, status_code=401)
    health_check.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_resp
        )
    )
    result = await health_check.execute()

    assert result["status"] == STATUS_ERROR
    assert "Invalid API key" in result["error"]
    assert result["data"]["healthy"] is False
    assert result["integration_id"] == "flashpoint"


# ============================================================================
# LIST INTELLIGENCE REPORTS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_reports_success(list_reports):
    """Test successful list reports with pagination."""
    mock_resp = _mock_response(
        {
            "data": [
                {"id": "rpt-1", "title": "Report 1", "body": "<p>Hello</p>"},
                {"id": "rpt-2", "title": "Report 2", "summary": "<b>Summary</b>"},
            ],
            "total": 2,
        }
    )
    list_reports.http_request = AsyncMock(return_value=mock_resp)

    result = await list_reports.execute(limit=10)

    assert result["status"] == STATUS_SUCCESS
    assert len(result["data"]) == 2
    assert result["summary"]["total_reports"] == 2
    assert result["integration_id"] == "flashpoint"
    assert result["action_id"] == "list_intelligence_reports"
    # Verify processed fields were added
    assert "processed_body" in result["data"][0]
    assert "processed_summary" in result["data"][1]


@pytest.mark.asyncio
async def test_list_reports_missing_token():
    """Test list reports without API token."""
    action = _make_action(ListIntelligenceReportsAction, credentials={})
    result = await action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_API_TOKEN
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_list_reports_invalid_limit(list_reports):
    """Test list reports with invalid limit."""
    result = await list_reports.execute(limit=-5)

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_INVALID_LIMIT
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_list_reports_timeout(list_reports):
    """Test list reports timeout."""
    list_reports.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("timed out")
    )
    result = await list_reports.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error_type"] == ERROR_TYPE_TIMEOUT
    assert result["integration_id"] == "flashpoint"


# ============================================================================
# GET INTELLIGENCE REPORT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_report_success(get_report):
    """Test successful single report fetch."""
    mock_resp = _mock_response(
        {
            "id": "rpt-abc",
            "title": "Test Report",
            "body": "<p>Details</p>",
            "summary": "<b>TL;DR</b>",
        }
    )
    get_report.http_request = AsyncMock(return_value=mock_resp)

    result = await get_report.execute(report_id="rpt-abc")

    assert result["status"] == STATUS_SUCCESS
    assert result["data"]["id"] == "rpt-abc"
    assert result["integration_id"] == "flashpoint"
    assert result["action_id"] == "get_intelligence_report"
    assert "processed_body" in result["data"]
    assert "processed_summary" in result["data"]


@pytest.mark.asyncio
async def test_get_report_not_found(get_report):
    """Test get report 404 returns success with not_found."""
    mock_resp = _mock_response({"detail": "Not found"}, status_code=404)
    get_report.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_resp
        )
    )

    result = await get_report.execute(report_id="nonexistent")

    assert result["status"] == STATUS_SUCCESS
    assert result["not_found"] is True
    assert result["data"]["report_id"] == "nonexistent"
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_get_report_missing_id(get_report):
    """Test get report without report_id."""
    result = await get_report.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_REPORT_ID
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_get_report_missing_token():
    """Test get report without API token."""
    action = _make_action(GetIntelligenceReportAction, credentials={})
    result = await action.execute(report_id="rpt-1")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_API_TOKEN
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_get_report_http_error(get_report):
    """Test get report with 500 error."""
    mock_resp = _mock_response({"error": "Server error"}, status_code=500)
    get_report.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_resp
        )
    )
    result = await get_report.execute(report_id="rpt-1")

    assert result["status"] == STATUS_ERROR
    assert result["error_type"] == ERROR_TYPE_HTTP
    assert result["integration_id"] == "flashpoint"


# ============================================================================
# LIST RELATED REPORTS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_related_reports_success(list_related):
    """Test successful related reports fetch."""
    mock_resp = _mock_response(
        {
            "data": [{"id": "rpt-rel-1", "title": "Related"}],
            "total": 1,
        }
    )
    list_related.http_request = AsyncMock(return_value=mock_resp)

    result = await list_related.execute(report_id="rpt-abc", limit=10)

    assert result["status"] == STATUS_SUCCESS
    assert len(result["data"]) == 1
    assert result["summary"]["total_related_reports"] == 1
    assert result["integration_id"] == "flashpoint"
    assert result["action_id"] == "list_related_reports"


@pytest.mark.asyncio
async def test_list_related_reports_missing_id(list_related):
    """Test related reports without report_id."""
    result = await list_related.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_REPORT_ID
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_list_related_reports_not_found(list_related):
    """Test related reports for nonexistent report."""
    mock_resp = _mock_response({}, status_code=404)
    list_related.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_resp
        )
    )

    result = await list_related.execute(report_id="nonexistent")

    assert result["status"] == STATUS_SUCCESS
    assert result["not_found"] is True
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_list_related_reports_missing_token():
    """Test related reports without API token."""
    action = _make_action(ListRelatedReportsAction, credentials={})
    result = await action.execute(report_id="rpt-1")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_API_TOKEN
    assert result["integration_id"] == "flashpoint"


# ============================================================================
# GET COMPROMISED CREDENTIALS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_compromised_creds_success(compromised_creds):
    """Test successful credential sighting search."""
    # First call: initial scroll with results
    first_resp = _mock_response(
        {
            "hits": {
                "hits": [
                    {
                        "_id": "cred-1",
                        "_source": {"email": "user@test.com", "is_fresh": True},
                    },
                ]
            },
            "_scroll_id": "scroll-123",
        }
    )
    # Second call: empty page signals end
    second_resp = _mock_response(
        {
            "hits": {"hits": []},
            "_scroll_id": "scroll-123",
        }
    )
    # Third call: disable scroll (DELETE)
    delete_resp = _mock_response({})

    compromised_creds.http_request = AsyncMock(
        side_effect=[first_resp, second_resp, delete_resp]
    )

    result = await compromised_creds.execute(filter="+is_fresh:true", limit=10)

    assert result["status"] == STATUS_SUCCESS
    assert len(result["data"]) == 1
    assert result["summary"]["total_results"] == 1
    assert result["integration_id"] == "flashpoint"
    assert result["action_id"] == "get_compromised_credentials"


@pytest.mark.asyncio
async def test_compromised_creds_no_filter(compromised_creds):
    """Test credential sighting search without filter."""
    first_resp = _mock_response(
        {
            "hits": {"hits": [{"_id": "cred-1"}]},
            "_scroll_id": None,
        }
    )
    compromised_creds.http_request = AsyncMock(return_value=first_resp)

    result = await compromised_creds.execute()

    assert result["status"] == STATUS_SUCCESS
    assert result["integration_id"] == "flashpoint"
    # Verify the query still includes basetypes:credential-sighting
    call_kwargs = compromised_creds.http_request.call_args.kwargs
    assert "credential-sighting" in call_kwargs["params"]["query"]


@pytest.mark.asyncio
async def test_compromised_creds_missing_token():
    """Test compromised credentials without API token."""
    action = _make_action(GetCompromisedCredentialsAction, credentials={})
    result = await action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_API_TOKEN
    assert result["integration_id"] == "flashpoint"


# ============================================================================
# RUN QUERY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_run_query_success(run_query):
    """Test successful universal search."""
    first_resp = _mock_response(
        {
            "hits": {
                "hits": [
                    {"_id": "hit-1", "_source": {"basetypes": ["cve"]}},
                    {"_id": "hit-2", "_source": {"basetypes": ["paste"]}},
                ]
            },
            "_scroll_id": None,
        }
    )
    run_query.http_request = AsyncMock(return_value=first_resp)

    result = await run_query.execute(query="+basetypes:cve", limit=10)

    assert result["status"] == STATUS_SUCCESS
    assert len(result["data"]) == 2
    assert result["summary"]["total_results"] == 2
    assert result["integration_id"] == "flashpoint"
    assert result["action_id"] == "run_query"


@pytest.mark.asyncio
async def test_run_query_missing_query(run_query):
    """Test run query without query parameter."""
    result = await run_query.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_QUERY
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_run_query_missing_token():
    """Test run query without API token."""
    action = _make_action(RunQueryAction, credentials={})
    result = await action.execute(query="+basetypes:cve")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_API_TOKEN
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_run_query_timeout(run_query):
    """Test run query timeout."""
    run_query.http_request = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    result = await run_query.execute(query="+basetypes:cve")

    assert result["status"] == STATUS_ERROR
    assert result["error_type"] == ERROR_TYPE_TIMEOUT
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_run_query_connection_error(run_query):
    """Test run query connection error."""
    run_query.http_request = AsyncMock(
        side_effect=httpx.RequestError("Connection refused")
    )
    result = await run_query.execute(query="+basetypes:cve")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_SERVER_CONNECTION
    assert result["error_type"] == ERROR_TYPE_HTTP
    assert result["integration_id"] == "flashpoint"


# ============================================================================
# LIST INDICATORS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_indicators_success(list_indicators):
    """Test successful indicator listing with Attribute unwrapping."""
    first_resp = _mock_response(
        {
            "results": [
                {"Attribute": {"type": "ip-dst", "value": "1.2.3.4"}},
                {"type": "domain", "value": "evil.com"},
            ],
            "scroll_id": None,
        }
    )
    list_indicators.http_request = AsyncMock(return_value=first_resp)

    result = await list_indicators.execute(limit=10)

    assert result["status"] == STATUS_SUCCESS
    assert len(result["data"]) == 2
    # First item should be unwrapped from Attribute wrapper
    assert result["data"][0]["type"] == "ip-dst"
    assert result["data"][0]["value"] == "1.2.3.4"
    # Second item had no Attribute wrapper, kept as-is
    assert result["data"][1]["type"] == "domain"
    assert result["summary"]["total_iocs"] == 2
    assert result["integration_id"] == "flashpoint"
    assert result["action_id"] == "list_indicators"


@pytest.mark.asyncio
async def test_list_indicators_with_types(list_indicators):
    """Test indicator listing with attribute type filter."""
    first_resp = _mock_response({"results": [], "scroll_id": None})
    list_indicators.http_request = AsyncMock(return_value=first_resp)

    result = await list_indicators.execute(
        attributes_types="ip-src, domain, url", limit=5
    )

    assert result["status"] == STATUS_SUCCESS
    assert result["integration_id"] == "flashpoint"
    # Verify types param was lowered and cleaned
    call_kwargs = list_indicators.http_request.call_args.kwargs
    assert call_kwargs["params"]["types"] == "ip-src,domain,url"


@pytest.mark.asyncio
async def test_list_indicators_invalid_types(list_indicators):
    """Test indicator listing with empty comma-separated types."""
    result = await list_indicators.execute(attributes_types="  ,  , ")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_INVALID_COMMA_SEPARATED
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_list_indicators_missing_token():
    """Test indicator listing without API token."""
    action = _make_action(ListIndicatorsAction, credentials={})
    result = await action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_API_TOKEN
    assert result["integration_id"] == "flashpoint"


# ============================================================================
# SEARCH INDICATORS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_search_indicators_success(search_indicators):
    """Test successful indicator search."""
    first_resp = _mock_response(
        {
            "results": [
                {
                    "Attribute": {
                        "type": "ip-dst",
                        "value": "1.2.3.4",
                        "Event": {"info": "test"},
                    }
                },
            ],
            "scroll_id": None,
        }
    )
    search_indicators.http_request = AsyncMock(return_value=first_resp)

    result = await search_indicators.execute(
        attribute_type="ip-dst", attribute_value="1.2.3.4", limit=10
    )

    assert result["status"] == STATUS_SUCCESS
    assert len(result["data"]) == 1
    assert result["data"][0]["value"] == "1.2.3.4"
    assert result["summary"]["total_iocs"] == 1
    assert result["integration_id"] == "flashpoint"
    assert result["action_id"] == "search_indicators"


@pytest.mark.asyncio
async def test_search_indicators_url_quoting(search_indicators):
    """Test that URL type values are quoted in search_fields."""
    first_resp = _mock_response({"results": [], "scroll_id": None})
    search_indicators.http_request = AsyncMock(return_value=first_resp)

    await search_indicators.execute(
        attribute_type="URL",
        attribute_value="http://evil.com/payload",
        limit=5,
    )

    call_kwargs = search_indicators.http_request.call_args.kwargs
    assert 'url=="http://evil.com/payload"' in call_kwargs["params"]["search_fields"]


@pytest.mark.asyncio
async def test_search_indicators_non_url_no_quoting(search_indicators):
    """Test that non-URL type values are not quoted."""
    first_resp = _mock_response({"results": [], "scroll_id": None})
    search_indicators.http_request = AsyncMock(return_value=first_resp)

    await search_indicators.execute(
        attribute_type="ip-dst",
        attribute_value="1.2.3.4",
        limit=5,
    )

    call_kwargs = search_indicators.http_request.call_args.kwargs
    assert call_kwargs["params"]["search_fields"] == "ip-dst==1.2.3.4"


@pytest.mark.asyncio
async def test_search_indicators_missing_type(search_indicators):
    """Test search indicators without attribute_type."""
    result = await search_indicators.execute(attribute_value="1.2.3.4")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_ATTRIBUTE_TYPE
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_search_indicators_missing_value(search_indicators):
    """Test search indicators without attribute_value."""
    result = await search_indicators.execute(attribute_type="ip-dst")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_ATTRIBUTE_VALUE
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_search_indicators_missing_token():
    """Test search indicators without API token."""
    action = _make_action(SearchIndicatorsAction, credentials={})
    result = await action.execute(attribute_type="ip-dst", attribute_value="1.2.3.4")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_API_TOKEN
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_search_indicators_timeout(search_indicators):
    """Test search indicators timeout."""
    search_indicators.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("timed out")
    )
    result = await search_indicators.execute(
        attribute_type="ip-dst", attribute_value="1.2.3.4"
    )

    assert result["status"] == STATUS_ERROR
    assert result["error_type"] == ERROR_TYPE_TIMEOUT
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_search_indicators_http_error(search_indicators):
    """Test search indicators with HTTP error."""
    mock_resp = _mock_response({"error": "Bad Request"}, status_code=400)
    search_indicators.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=mock_resp
        )
    )
    result = await search_indicators.execute(
        attribute_type="ip-dst", attribute_value="1.2.3.4"
    )

    assert result["status"] == STATUS_ERROR
    assert result["error_type"] == ERROR_TYPE_HTTP
    assert result["integration_id"] == "flashpoint"


# ============================================================================
# SCROLL PAGINATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_scroll_pagination_multi_page(run_query):
    """Test scroll pagination across multiple pages."""
    # Page 1: results + scroll_id
    page1 = _mock_response(
        {
            "hits": {"hits": [{"_id": f"h-{i}"} for i in range(500)]},
            "_scroll_id": "scroll-abc",
        }
    )
    # Page 2: more results
    page2 = _mock_response(
        {
            "hits": {"hits": [{"_id": f"h-{i}"} for i in range(500, 700)]},
            "_scroll_id": "scroll-abc",
        }
    )
    # Page 3: empty = done
    page3 = _mock_response({"hits": {"hits": []}, "_scroll_id": "scroll-abc"})
    # Disable scroll
    delete_resp = _mock_response({})

    run_query.http_request = AsyncMock(side_effect=[page1, page2, page3, delete_resp])

    result = await run_query.execute(query="+basetypes:cve", limit=700)

    assert result["status"] == STATUS_SUCCESS
    assert len(result["data"]) == 700
    assert result["summary"]["total_results"] == 700
    assert result["integration_id"] == "flashpoint"


@pytest.mark.asyncio
async def test_scroll_pagination_limit_cuts_off(run_query):
    """Test that limit truncates results even when more are available."""
    page1 = _mock_response(
        {
            "hits": {"hits": [{"_id": f"h-{i}"} for i in range(500)]},
            "_scroll_id": "scroll-abc",
        }
    )
    # Disable scroll (called because limit reached)
    delete_resp = _mock_response({})

    run_query.http_request = AsyncMock(side_effect=[page1, delete_resp])

    result = await run_query.execute(query="+basetypes:cve", limit=100)

    assert result["status"] == STATUS_SUCCESS
    assert len(result["data"]) == 100
    assert result["integration_id"] == "flashpoint"


# ============================================================================
# SKIP PAGINATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_skip_pagination_multi_page(list_reports):
    """Test skip-based pagination across multiple pages."""
    page1 = _mock_response(
        {
            "data": [{"id": f"rpt-{i}"} for i in range(500)],
            "total": 600,
        }
    )
    page2 = _mock_response(
        {
            "data": [{"id": f"rpt-{i}"} for i in range(500, 600)],
            "total": 600,
        }
    )

    list_reports.http_request = AsyncMock(side_effect=[page1, page2])

    result = await list_reports.execute(limit=600)

    assert result["status"] == STATUS_SUCCESS
    assert len(result["data"]) == 600
    assert result["integration_id"] == "flashpoint"


# ============================================================================
# get_http_headers TESTS
# ============================================================================


def test_get_http_headers_with_token():
    """Test auth headers include Bearer token."""
    action = _make_action(HealthCheckAction, action_id="health_check")
    headers = action.get_http_headers()

    assert headers["Authorization"] == "Bearer test-fp-token-123"
    assert headers["Content-Type"] == "application/json"
    assert "X-FP-IntegrationPlatform" in headers


def test_get_http_headers_without_token():
    """Test auth headers without token still include platform headers."""
    action = _make_action(HealthCheckAction, credentials={}, action_id="health_check")
    headers = action.get_http_headers()

    assert "Authorization" not in headers
    assert headers["Content-Type"] == "application/json"

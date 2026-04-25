"""Unit tests for Cofense Triage integration actions.

Tests cover:
- Health check (OAuth2 token + status endpoint)
- Get reports (pagination, filters, reporter_email lookup)
- Get report (single report, 404 not_found)
- Categorize report (by ID and by name)
- Get threat indicators (filters, validation)
- Create threat indicator (validation, success)
- Get reporters (filters)
- Get URLs (filters, operators)
- Get categories (filters)
- Validation helpers
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.cofensetriage.actions import (
    CategorizeReportAction,
    CreateThreatIndicatorAction,
    GetCategoriesAction,
    GetReportAction,
    GetReportersAction,
    GetReportsAction,
    GetThreatIndicatorsAction,
    GetUrlsAction,
    HealthCheckAction,
    _clean_comma_list,
    _validate_positive_integer,
)

# ============================================================================
# TEST FIXTURES
# ============================================================================

VALID_CREDENTIALS = {
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
}

VALID_SETTINGS = {
    "base_url": "https://triage.example.com",
    "timeout": 30,
}


def _make_action(action_cls, credentials=None, settings=None):
    """Create an action instance with defaults."""
    return action_cls(
        integration_id="cofensetriage",
        action_id=action_cls.__name__.lower().replace("action", ""),
        settings=VALID_SETTINGS.copy() if settings is None else settings,
        credentials=VALID_CREDENTIALS.copy() if credentials is None else credentials,
    )


def _mock_http_response(json_data=None, status_code=200, text=""):
    """Create a mock HTTP response."""
    mock = MagicMock(spec=httpx.Response)
    mock.json.return_value = json_data or {}
    mock.status_code = status_code
    mock.text = text
    return mock


def _mock_token_and_data(action, token_response=None, data_responses=None):
    """Set up http_request mock that returns token first, then data responses.

    Args:
        action: The action instance to mock
        token_response: Response JSON for token request (default: valid token)
        data_responses: List of response JSONs for subsequent API calls

    Returns:
        The AsyncMock for http_request
    """
    if token_response is None:
        token_response = {"access_token": "test-token-123"}

    responses = [_mock_http_response(token_response)]

    if data_responses:
        for resp_data in data_responses:
            responses.append(_mock_http_response(resp_data))

    action.http_request = AsyncMock(side_effect=responses)
    return action.http_request


# ============================================================================
# VALIDATION HELPER TESTS
# ============================================================================


class TestValidationHelpers:
    """Test validation helper functions."""

    def test_validate_positive_integer_valid(self):
        is_valid, err, val = _validate_positive_integer(42, "test")
        assert is_valid is True
        assert err == ""
        assert val == 42

    def test_validate_positive_integer_string_valid(self):
        is_valid, err, val = _validate_positive_integer("100", "test")
        assert is_valid is True
        assert val == 100

    def test_validate_positive_integer_none(self):
        is_valid, err, val = _validate_positive_integer(None, "test")
        assert is_valid is True
        assert val is None

    def test_validate_positive_integer_negative(self):
        is_valid, err, val = _validate_positive_integer(-5, "test")
        assert is_valid is False
        assert "non-negative" in err

    def test_validate_positive_integer_zero(self):
        is_valid, err, val = _validate_positive_integer(0, "test")
        assert is_valid is False
        assert "non-zero" in err

    def test_validate_positive_integer_invalid_string(self):
        is_valid, err, val = _validate_positive_integer("abc", "test")
        assert is_valid is False
        assert "valid integer" in err

    def test_clean_comma_list_normal(self):
        assert _clean_comma_list("tag1, tag2, tag3") == "tag1,tag2,tag3"

    def test_clean_comma_list_empty_items(self):
        assert _clean_comma_list("tag1,,tag2, ,tag3") == "tag1,tag2,tag3"

    def test_clean_comma_list_empty(self):
        assert _clean_comma_list("") == ""

    def test_clean_comma_list_none(self):
        assert _clean_comma_list(None) == ""


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestHealthCheckAction:
    """Test Cofense Triage health check action."""

    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_health_check_success(self, action):
        """Test successful health check obtains token and checks status."""
        _mock_token_and_data(
            action,
            data_responses=[{"status": "ok"}],  # status endpoint response
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert result["data"]["healthy"] is True
        assert result["data"]["api_version"] == "v2"
        assert "integration_id" in result
        assert result["integration_id"] == "cofensetriage"

        # Verify token request was made
        assert action.http_request.call_count == 2
        token_call = action.http_request.call_args_list[0]
        assert "/oauth/token" in token_call.kwargs["url"]

    @pytest.mark.asyncio
    async def test_health_check_missing_base_url(self):
        """Test health check fails with missing base_url."""
        action = _make_action(HealthCheckAction, settings={"timeout": 30})
        result = await action.execute()

        assert result["status"] == "error"
        assert "base_url" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_health_check_missing_credentials(self):
        """Test health check fails with missing credentials."""
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert "client_id" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_health_check_token_failure(self, action):
        """Test health check fails when token cannot be obtained."""
        action.http_request = AsyncMock(
            return_value=_mock_http_response({"error": "invalid_client"})
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "access token" in result["error"]

    @pytest.mark.asyncio
    async def test_health_check_status_endpoint_failure(self, action):
        """Test health check fails when status endpoint returns error."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"

        error = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_resp
        )

        action.http_request = AsyncMock(
            side_effect=[
                _mock_http_response({"access_token": "test-token"}),
                error,
            ]
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False


# ============================================================================
# GET REPORTS TESTS
# ============================================================================


class TestGetReportsAction:
    """Test get reports action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetReportsAction)

    @pytest.mark.asyncio
    async def test_get_reports_success(self, action):
        """Test successful reports retrieval."""
        reports_data = {
            "data": [
                {
                    "id": "1",
                    "type": "reports",
                    "attributes": {
                        "subject": "Phishing Test",
                        "location": "Processed",
                        "risk_score": 35,
                    },
                }
            ],
            "links": {},
        }

        _mock_token_and_data(action, data_responses=[reports_data])
        result = await action.execute()

        assert result["status"] == "success"
        assert len(result["data"]) == 1
        assert result["data"][0]["id"] == "1"
        assert result["summary"]["total_reports_retrieved"] == 1

    @pytest.mark.asyncio
    async def test_get_reports_with_filters(self, action):
        """Test reports retrieval with location filter."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": [], "links": {}}],
        )

        result = await action.execute(location="processed", sort="latest_first")

        assert result["status"] == "success"
        # Empty list from paginator results in {} from success_result(data=[])
        # because `[] or {}` is `{}` in the base class
        assert result["summary"]["total_reports_retrieved"] == 0

        # Verify filter was applied
        data_call = action.http_request.call_args_list[1]
        params = data_call.kwargs.get("params", {})
        assert params.get("filter[location]") == "processed"
        assert params.get("sort") == "-updated_at"

    @pytest.mark.asyncio
    async def test_get_reports_invalid_location(self, action):
        """Test reports with invalid location returns validation error."""
        result = await action.execute(location="invalid_place")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "location" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_reports_invalid_sort(self, action):
        """Test reports with invalid sort returns validation error."""
        result = await action.execute(sort="random_order")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "sort" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_reports_missing_base_url(self):
        """Test reports fails with missing base_url."""
        action = _make_action(GetReportsAction, settings={})
        result = await action.execute()

        assert result["status"] == "error"
        assert "base_url" in result["error"]

    @pytest.mark.asyncio
    async def test_get_reports_with_reporter_email(self, action):
        """Test reports filtered by reporter email resolves to reporter_id."""
        reporter_response = {"data": [{"id": "42", "type": "reporters"}]}
        reports_response = {"data": [], "links": {}}

        _mock_token_and_data(
            action,
            data_responses=[reporter_response, reports_response],
        )

        result = await action.execute(reporter_email="user@example.com")

        assert result["status"] == "success"
        # Verify reporter lookup and report fetch were both called
        assert action.http_request.call_count == 3  # token + reporter lookup + reports

    @pytest.mark.asyncio
    async def test_get_reports_reporter_email_not_found(self, action):
        """Test reports fails when reporter email is not found."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": []}],  # empty reporter response
        )

        result = await action.execute(reporter_email="nonexistent@example.com")

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_reports_location_all_excludes_filter(self, action):
        """Test that location='all' does not add location filter."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": [], "links": {}}],
        )

        result = await action.execute(location="all")

        assert result["status"] == "success"
        data_call = action.http_request.call_args_list[1]
        params = data_call.kwargs.get("params", {})
        assert "filter[location]" not in params


# ============================================================================
# GET REPORT TESTS
# ============================================================================


class TestGetReportAction:
    """Test get single report action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetReportAction)

    @pytest.mark.asyncio
    async def test_get_report_success(self, action):
        """Test successful single report retrieval."""
        report_data = {
            "data": {
                "id": "779",
                "type": "reports",
                "attributes": {
                    "subject": "Suspicious Email",
                    "location": "Processed",
                    "risk_score": 50,
                    "md5": "bf858b01ec8e0fd8219ffff0c1606ff8",
                    "sha256": "e520fe082f28de7bb25b9fa82de1e0b8ecea5922b06d5424b9829695c7c6fc06",
                    "from_address": "attacker@example.com",
                    "created_at": "2021-03-05T02:45:26.037Z",
                    "updated_at": "2021-03-11T12:19:35.470Z",
                },
                "relationships": {
                    "category": {"data": {"id": "4", "type": "categories"}},
                    "reporter": {"data": {"id": "24", "type": "reporters"}},
                },
            }
        }

        _mock_token_and_data(action, data_responses=[report_data])

        result = await action.execute(report_id=779)

        assert result["status"] == "success"
        assert result["data"]["id"] == "779"
        assert result["data"]["attributes"]["subject"] == "Suspicious Email"
        assert result["message"] == "Successfully retrieved the report"

    @pytest.mark.asyncio
    async def test_get_report_not_found_404(self, action):
        """Test that 404 returns success with not_found=True."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404

        error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_resp
        )

        action.http_request = AsyncMock(
            side_effect=[
                _mock_http_response({"access_token": "test-token"}),
                error,
            ]
        )

        result = await action.execute(report_id=99999)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["report_id"] == 99999

    @pytest.mark.asyncio
    async def test_get_report_missing_report_id(self, action):
        """Test that missing report_id returns validation error."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "report_id" in result["error"]

    @pytest.mark.asyncio
    async def test_get_report_invalid_report_id(self, action):
        """Test that non-integer report_id returns validation error."""
        result = await action.execute(report_id="abc")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_get_report_empty_data(self, action):
        """Test that empty data in response returns not_found."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": {}}],
        )

        result = await action.execute(report_id=123)

        assert result["status"] == "success"
        assert result["not_found"] is True


# ============================================================================
# CATEGORIZE REPORT TESTS
# ============================================================================


class TestCategorizeReportAction:
    """Test categorize report action."""

    @pytest.fixture
    def action(self):
        return _make_action(CategorizeReportAction)

    @pytest.mark.asyncio
    async def test_categorize_report_by_id_success(self, action):
        """Test successful categorization by category_id."""
        _mock_token_and_data(
            action,
            data_responses=[{}],  # categorize endpoint returns empty on success
        )

        result = await action.execute(report_id=779, category_id=4)

        assert result["status"] == "success"
        assert "categorized" in result["message"].lower()
        assert result["data"]["report_id"] == 779
        assert result["data"]["category_id"] == 4

    @pytest.mark.asyncio
    async def test_categorize_report_by_name_success(self, action):
        """Test successful categorization by category_name (name resolved to ID)."""
        category_lookup_response = {"data": [{"id": "4", "type": "categories"}]}

        _mock_token_and_data(
            action,
            data_responses=[category_lookup_response, {}],
        )

        result = await action.execute(report_id=779, category_name="Phishing")

        assert result["status"] == "success"
        assert result["data"]["category_id"] == 4

    @pytest.mark.asyncio
    async def test_categorize_report_missing_report_id(self, action):
        """Test categorization fails without report_id."""
        result = await action.execute(category_id=4)

        assert result["status"] == "error"
        assert "report_id" in result["error"]

    @pytest.mark.asyncio
    async def test_categorize_report_missing_category(self, action):
        """Test categorization fails without category_id or category_name."""
        result = await action.execute(report_id=779)

        assert result["status"] == "error"
        assert "category_id" in result["error"] or "category_name" in result["error"]

    @pytest.mark.asyncio
    async def test_categorize_report_category_name_not_found(self, action):
        """Test categorization fails when category_name doesn't resolve."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": []}],  # empty category lookup
        )

        result = await action.execute(
            report_id=779, category_name="NonexistentCategory"
        )

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_categorize_report_with_tags(self, action):
        """Test categorization with categorization tags."""
        _mock_token_and_data(
            action,
            data_responses=[{}],
        )

        result = await action.execute(
            report_id=779,
            category_id=4,
            categorization_tags="phishing,credential-harvest",
        )

        assert result["status"] == "success"
        # Verify the payload included tags
        categorize_call = action.http_request.call_args_list[-1]
        payload = categorize_call.kwargs.get("json_data", {})
        assert "phishing" in payload["data"]["categorization_tags"]
        assert "credential-harvest" in payload["data"]["categorization_tags"]


# ============================================================================
# GET THREAT INDICATORS TESTS
# ============================================================================


class TestGetThreatIndicatorsAction:
    """Test get threat indicators action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetThreatIndicatorsAction)

    @pytest.mark.asyncio
    async def test_get_threat_indicators_success(self, action):
        """Test successful threat indicators retrieval."""
        indicators_data = {
            "data": [
                {
                    "id": "1",
                    "type": "threat_indicators",
                    "attributes": {
                        "threat_level": "malicious",
                        "threat_type": "url",
                        "threat_value": "http://evil.example.com",
                        "threat_source": "Analysi-UI",
                    },
                }
            ],
            "links": {},
        }

        _mock_token_and_data(action, data_responses=[indicators_data])

        result = await action.execute()

        assert result["status"] == "success"
        assert len(result["data"]) == 1
        assert result["summary"]["total_threat_indicators_retrieved"] == 1

    @pytest.mark.asyncio
    async def test_get_threat_indicators_with_filters(self, action):
        """Test threat indicators with level and type filters."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": [], "links": {}}],
        )

        result = await action.execute(level="malicious", type="url")

        assert result["status"] == "success"
        data_call = action.http_request.call_args_list[1]
        params = data_call.kwargs.get("params", {})
        assert params.get("filter[threat_level]") == "malicious"
        assert params.get("filter[threat_type]") == "url"

    @pytest.mark.asyncio
    async def test_get_threat_indicators_invalid_level(self, action):
        """Test invalid level returns validation error."""
        result = await action.execute(level="critical")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_get_threat_indicators_invalid_type(self, action):
        """Test invalid type returns validation error."""
        result = await action.execute(type="file")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_get_threat_indicators_level_all_excludes_filter(self, action):
        """Test that level='all' does not add level filter."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": [], "links": {}}],
        )

        result = await action.execute(level="all")

        assert result["status"] == "success"
        data_call = action.http_request.call_args_list[1]
        params = data_call.kwargs.get("params", {})
        assert "filter[threat_level]" not in params


# ============================================================================
# CREATE THREAT INDICATOR TESTS
# ============================================================================


class TestCreateThreatIndicatorAction:
    """Test create threat indicator action."""

    @pytest.fixture
    def action(self):
        return _make_action(CreateThreatIndicatorAction)

    @pytest.mark.asyncio
    async def test_create_threat_indicator_success(self, action):
        """Test successful threat indicator creation."""
        created_indicator = {
            "data": {
                "id": "42",
                "type": "threat_indicators",
                "attributes": {
                    "threat_level": "malicious",
                    "threat_type": "url",
                    "threat_value": "http://evil.example.com",
                    "threat_source": "Analysi-UI",
                },
            }
        }

        _mock_token_and_data(action, data_responses=[created_indicator])

        result = await action.execute(
            level="malicious",
            type="url",
            value="http://evil.example.com",
        )

        assert result["status"] == "success"
        assert result["data"]["id"] == "42"
        assert result["summary"]["threat_indicator_id"] == "42"
        assert "created" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_create_threat_indicator_missing_level(self, action):
        """Test creation fails without level."""
        result = await action.execute(type="url", value="http://evil.example.com")

        assert result["status"] == "error"
        assert "level" in result["error"]

    @pytest.mark.asyncio
    async def test_create_threat_indicator_missing_type(self, action):
        """Test creation fails without type."""
        result = await action.execute(
            level="malicious", value="http://evil.example.com"
        )

        assert result["status"] == "error"
        assert "type" in result["error"]

    @pytest.mark.asyncio
    async def test_create_threat_indicator_missing_value(self, action):
        """Test creation fails without value."""
        result = await action.execute(level="malicious", type="url")

        assert result["status"] == "error"
        assert "value" in result["error"]

    @pytest.mark.asyncio
    async def test_create_threat_indicator_invalid_level(self, action):
        """Test creation fails with invalid level."""
        result = await action.execute(
            level="critical", type="url", value="http://evil.example.com"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_create_threat_indicator_invalid_type(self, action):
        """Test creation fails with invalid type."""
        result = await action.execute(
            level="malicious", type="file", value="http://evil.example.com"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_create_threat_indicator_custom_source(self, action):
        """Test creation with custom source."""
        _mock_token_and_data(
            action,
            data_responses=[
                {"data": {"id": "43", "type": "threat_indicators", "attributes": {}}}
            ],
        )

        result = await action.execute(
            level="suspicious",
            type="hostname",
            value="evil.example.com",
            source="Custom-Source",
        )

        assert result["status"] == "success"
        create_call = action.http_request.call_args_list[-1]
        payload = create_call.kwargs.get("json_data", {})
        assert payload["data"]["attributes"]["threat_source"] == "Custom-Source"


# ============================================================================
# GET REPORTERS TESTS
# ============================================================================


class TestGetReportersAction:
    """Test get reporters action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetReportersAction)

    @pytest.mark.asyncio
    async def test_get_reporters_success(self, action):
        """Test successful reporters retrieval."""
        reporters_data = {
            "data": [
                {
                    "id": "24",
                    "type": "reporters",
                    "attributes": {
                        "email": "reporter@example.com",
                        "reputation_score": 15,
                        "vip": False,
                    },
                }
            ],
            "links": {},
        }

        _mock_token_and_data(action, data_responses=[reporters_data])

        result = await action.execute()

        assert result["status"] == "success"
        assert len(result["data"]) == 1
        assert result["summary"]["total_reporters_retrieved"] == 1

    @pytest.mark.asyncio
    async def test_get_reporters_with_vip_filter(self, action):
        """Test reporters filtered by VIP status."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": [], "links": {}}],
        )

        result = await action.execute(vip=True, sort="latest_first")

        assert result["status"] == "success"
        data_call = action.http_request.call_args_list[1]
        params = data_call.kwargs.get("params", {})
        assert params.get("filter[vip]") is True
        assert params.get("sort") == "-id"

    @pytest.mark.asyncio
    async def test_get_reporters_invalid_sort(self, action):
        """Test reporters with invalid sort returns validation error."""
        result = await action.execute(sort="random")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# GET URLS TESTS
# ============================================================================


class TestGetUrlsAction:
    """Test get URLs action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetUrlsAction)

    @pytest.mark.asyncio
    async def test_get_urls_success(self, action):
        """Test successful URLs retrieval."""
        urls_data = {
            "data": [
                {
                    "id": "101",
                    "type": "urls",
                    "attributes": {
                        "url": "http://suspicious.example.com/login",
                        "risk_score": 85,
                    },
                }
            ],
            "links": {},
        }

        _mock_token_and_data(action, data_responses=[urls_data])

        result = await action.execute()

        assert result["status"] == "success"
        assert len(result["data"]) == 1
        assert result["summary"]["total_urls_retrieved"] == 1

    @pytest.mark.asyncio
    async def test_get_urls_with_risk_score_filter(self, action):
        """Test URLs filtered by risk score with operator."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": [], "links": {}}],
        )

        result = await action.execute(risk_score=50, risk_score_operator="gteq")

        assert result["status"] == "success"
        data_call = action.http_request.call_args_list[1]
        params = data_call.kwargs.get("params", {})
        assert params.get("filter[risk_score_gteq]") == 50

    @pytest.mark.asyncio
    async def test_get_urls_invalid_operator(self, action):
        """Test URLs with invalid operator returns validation error."""
        result = await action.execute(risk_score_operator="between")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_get_urls_with_date_filters(self, action):
        """Test URLs with date range filters."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": [], "links": {}}],
        )

        result = await action.execute(
            start_date="2021-01-01",
            end_date="2021-12-31",
        )

        assert result["status"] == "success"
        data_call = action.http_request.call_args_list[1]
        params = data_call.kwargs.get("params", {})
        assert params.get("filter[updated_at_gteq]") == "2021-01-01"
        assert params.get("filter[updated_at_lt]") == "2021-12-31"


# ============================================================================
# GET CATEGORIES TESTS
# ============================================================================


class TestGetCategoriesAction:
    """Test get categories action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetCategoriesAction)

    @pytest.mark.asyncio
    async def test_get_categories_success(self, action):
        """Test successful categories retrieval."""
        categories_data = {
            "data": [
                {
                    "id": "1",
                    "type": "categories",
                    "attributes": {"name": "Non-Malicious", "malicious": False},
                },
                {
                    "id": "4",
                    "type": "categories",
                    "attributes": {"name": "Phishing", "malicious": True},
                },
            ],
            "links": {},
        }

        _mock_token_and_data(action, data_responses=[categories_data])

        result = await action.execute()

        assert result["status"] == "success"
        assert len(result["data"]) == 2
        assert result["summary"]["total_categories_retrieved"] == 2

    @pytest.mark.asyncio
    async def test_get_categories_with_name_filter(self, action):
        """Test categories filtered by name."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": [], "links": {}}],
        )

        result = await action.execute(name="Phishing")

        assert result["status"] == "success"
        data_call = action.http_request.call_args_list[1]
        params = data_call.kwargs.get("params", {})
        assert params.get("filter[name_cont]") == "Phishing"

    @pytest.mark.asyncio
    async def test_get_categories_with_malicious_filter(self, action):
        """Test categories filtered by malicious flag."""
        _mock_token_and_data(
            action,
            data_responses=[{"data": [], "links": {}}],
        )

        result = await action.execute(malicious=True)

        assert result["status"] == "success"
        data_call = action.http_request.call_args_list[1]
        params = data_call.kwargs.get("params", {})
        assert params.get("filter[malicious]") is True

    @pytest.mark.asyncio
    async def test_get_categories_missing_base_url(self):
        """Test categories fails with missing base_url."""
        action = _make_action(GetCategoriesAction, settings={})
        result = await action.execute()

        assert result["status"] == "error"
        assert "base_url" in result["error"]


# ============================================================================
# RESULT ENVELOPE TESTS
# ============================================================================


class TestResultEnvelope:
    """Test that all actions return proper result envelopes with framework fields."""

    @pytest.mark.asyncio
    async def test_success_result_has_framework_fields(self):
        """Test success results include integration_id, action_id, timestamp."""
        action = _make_action(GetCategoriesAction)
        _mock_token_and_data(
            action,
            data_responses=[{"data": [], "links": {}}],
        )

        result = await action.execute()

        assert "integration_id" in result
        assert "action_id" in result
        assert "timestamp" in result
        assert result["integration_id"] == "cofensetriage"

    @pytest.mark.asyncio
    async def test_error_result_has_framework_fields(self):
        """Test error results include integration_id, action_id, timestamp."""
        action = _make_action(GetReportAction)
        result = await action.execute()  # missing report_id

        assert "integration_id" in result
        assert "action_id" in result
        assert "timestamp" in result
        assert "error" in result
        assert "error_type" in result

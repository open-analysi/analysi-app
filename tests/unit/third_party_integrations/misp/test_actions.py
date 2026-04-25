"""Unit tests for MISP integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.misp.actions import (
    AddAttributeAction,
    AddTagAction,
    CreateEventAction,
    GetAttributeAction,
    GetEventAction,
    HealthCheckAction,
    ListTagsAction,
    SearchAttributesAction,
    SearchEventsAction,
    _get_base_url,
    _validate_event_id,
)

# ============================================================================
# HELPER TESTS
# ============================================================================


class TestHelpers:
    """Test helper functions."""

    def test_get_base_url_strips_trailing_slash(self):
        assert (
            _get_base_url({"base_url": "https://misp.local/"}) == "https://misp.local"
        )

    def test_get_base_url_no_trailing_slash(self):
        assert _get_base_url({"base_url": "https://misp.local"}) == "https://misp.local"

    def test_get_base_url_missing(self):
        assert _get_base_url({}) is None

    def test_validate_event_id_valid(self):
        is_valid, msg, parsed = _validate_event_id(42)
        assert is_valid is True
        assert parsed == 42

    def test_validate_event_id_string(self):
        is_valid, msg, parsed = _validate_event_id("123")
        assert is_valid is True
        assert parsed == 123

    def test_validate_event_id_zero(self):
        is_valid, msg, parsed = _validate_event_id(0)
        assert is_valid is False

    def test_validate_event_id_negative(self):
        is_valid, msg, parsed = _validate_event_id(-1)
        assert is_valid is False

    def test_validate_event_id_none(self):
        is_valid, msg, parsed = _validate_event_id(None)
        assert is_valid is False

    def test_validate_event_id_non_numeric(self):
        is_valid, msg, parsed = _validate_event_id("abc")
        assert is_valid is False


# ============================================================================
# FIXTURES
# ============================================================================


DEFAULT_SETTINGS = {
    "base_url": "https://misp.example.com",
    "timeout": 30,
    "verify_ssl": True,
}
DEFAULT_CREDENTIALS = {"api_key": "test-misp-api-key"}


def _make_action(action_cls, settings=None, credentials=None):
    """Helper to create an action instance."""
    return action_cls(
        integration_id="misp",
        action_id=action_cls.__name__.replace("Action", "").lower(),
        settings=DEFAULT_SETTINGS.copy() if settings is None else settings,
        credentials=DEFAULT_CREDENTIALS.copy() if credentials is None else credentials,
    )


def _mock_response(json_data, status_code=200):
    """Create a mock HTTP response."""
    mock = MagicMock()
    mock.json.return_value = json_data
    mock.status_code = status_code
    mock.text = str(json_data)
    return mock


def _mock_http_status_error(status_code):
    """Create a mock HTTPStatusError."""
    request = httpx.Request("GET", "https://misp.example.com/test")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=request, response=response
    )


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestHealthCheckAction:
    """Test MISP health check action."""

    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful health check returns version info."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"version": "2.4.140"})
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["version"] == "2.4.140"
        assert "integration_id" in result
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_calls_version_endpoint(self, action):
        """Test health check calls the correct endpoint."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"version": "2.4.140"})
        )

        await action.execute()

        call_kwargs = action.http_request.call_args
        assert "/servers/getPyMISPVersion.json" in call_kwargs.kwargs["url"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key is missing."""
        action = _make_action(HealthCheckAction, credentials={})

        result = await action.execute()

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_base_url(self):
        """Test error when base_url is missing."""
        action = _make_action(HealthCheckAction, settings={})

        result = await action.execute()

        assert result["status"] == "error"
        assert "base_url" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        """Test health check handles API errors."""
        action.http_request = AsyncMock(side_effect=Exception("Connection refused"))

        result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]
        assert result["data"]["healthy"] is False


# ============================================================================
# GET EVENT TESTS
# ============================================================================


class TestGetEventAction:
    """Test MISP get event action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetEventAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful event retrieval."""
        event_data = {
            "Event": {
                "id": "42",
                "info": "Test event",
                "distribution": "1",
                "threat_level_id": "2",
                "analysis": "0",
                "Attribute": [],
                "Tag": [],
            }
        }
        action.http_request = AsyncMock(return_value=_mock_response(event_data))

        result = await action.execute(event_id=42)

        assert result["status"] == "success"
        assert result["data"]["Event"]["id"] == "42"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self, action):
        """Test get_event calls /events/view/{id}."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"Event": {"id": "1"}})
        )

        await action.execute(event_id=1)

        call_kwargs = action.http_request.call_args
        assert "/events/view/1" in call_kwargs.kwargs["url"]

    @pytest.mark.asyncio
    async def test_missing_event_id(self, action):
        """Test error when event_id is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "event_id" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_event_id(self, action):
        """Test error for non-numeric event_id."""
        result = await action.execute(event_id="abc")

        assert result["status"] == "error"
        assert "positive integer" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_zero_event_id(self, action):
        """Test error for zero event_id."""
        result = await action.execute(event_id=0)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key is missing."""
        action = _make_action(GetEventAction, credentials={})

        result = await action.execute(event_id=42)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Test 404 returns success with not_found flag."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(404))

        result = await action.execute(event_id=99999)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["event_id"] == 99999

    @pytest.mark.asyncio
    async def test_500_returns_error(self, action):
        """Test 500 error propagates as error result."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(500))

        result = await action.execute(event_id=42)

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# SEARCH EVENTS TESTS
# ============================================================================


class TestSearchEventsAction:
    """Test MISP search events action."""

    @pytest.fixture
    def action(self):
        return _make_action(SearchEventsAction)

    @pytest.mark.asyncio
    async def test_success_with_results(self, action):
        """Test successful search returning events."""
        search_response = {
            "response": [
                {"Event": {"id": "1", "info": "Event 1"}},
                {"Event": {"id": "2", "info": "Event 2"}},
            ]
        }
        action.http_request = AsyncMock(return_value=_mock_response(search_response))

        result = await action.execute(value="8.8.8.8")

        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert len(result["data"]["events"]) == 2

    @pytest.mark.asyncio
    async def test_success_no_results(self, action):
        """Test search with no results."""
        action.http_request = AsyncMock(return_value=_mock_response({"response": []}))

        result = await action.execute(value="nonexistent")

        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    @pytest.mark.asyncio
    async def test_posts_to_rest_search(self, action):
        """Test search uses POST to /events/restSearch."""
        action.http_request = AsyncMock(return_value=_mock_response({"response": []}))

        await action.execute(value="test")

        call_kwargs = action.http_request.call_args
        assert "/events/restSearch" in call_kwargs.kwargs["url"]
        assert call_kwargs.kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_search_with_tags(self, action):
        """Test tags are passed as list."""
        action.http_request = AsyncMock(return_value=_mock_response({"response": []}))

        await action.execute(tags="tlp:white,malware")

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["tags"] == ["tlp:white", "malware"]

    @pytest.mark.asyncio
    async def test_search_with_date_range(self, action):
        """Test date range filters are passed correctly."""
        action.http_request = AsyncMock(return_value=_mock_response({"response": []}))

        await action.execute(date_from="2026-04-26", date_to="2026-12-31")

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["from"] == "2026-04-26"
        assert body["to"] == "2026-12-31"

    @pytest.mark.asyncio
    async def test_search_with_limit(self, action):
        """Test custom limit is passed."""
        action.http_request = AsyncMock(return_value=_mock_response({"response": []}))

        await action.execute(limit=10)

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["limit"] == 10

    @pytest.mark.asyncio
    async def test_default_limit(self, action):
        """Test default limit is 50."""
        action.http_request = AsyncMock(return_value=_mock_response({"response": []}))

        await action.execute()

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["limit"] == 50

    @pytest.mark.asyncio
    async def test_search_with_multiple_event_ids(self, action):
        """Test comma-separated event IDs are split into list."""
        action.http_request = AsyncMock(return_value=_mock_response({"response": []}))

        await action.execute(event_id="1,2,3")

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["eventid"] == ["1", "2", "3"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key is missing."""
        action = _make_action(SearchEventsAction, credentials={})

        result = await action.execute(value="test")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        """Test API error handling."""
        action.http_request = AsyncMock(side_effect=Exception("Server error"))

        result = await action.execute(value="test")

        assert result["status"] == "error"
        assert "Server error" in result["error"]


# ============================================================================
# CREATE EVENT TESTS
# ============================================================================


class TestCreateEventAction:
    """Test MISP create event action."""

    @pytest.fixture
    def action(self):
        return _make_action(CreateEventAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful event creation."""
        created_event = {
            "Event": {
                "id": "100",
                "info": "Test Incident",
                "distribution": "1",
                "threat_level_id": "4",
                "analysis": "0",
            }
        }
        action.http_request = AsyncMock(return_value=_mock_response(created_event))

        result = await action.execute(info="Test Incident")

        assert result["status"] == "success"
        assert result["data"]["Event"]["id"] == "100"
        assert "Event created with id: 100" in result["message"]

    @pytest.mark.asyncio
    async def test_posts_to_events_add(self, action):
        """Test event creation uses POST /events/add."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"Event": {"id": "1"}})
        )

        await action.execute(info="Test")

        call_kwargs = action.http_request.call_args
        assert "/events/add" in call_kwargs.kwargs["url"]
        assert call_kwargs.kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_distribution_mapping(self, action):
        """Test distribution string is mapped to numeric code."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"Event": {"id": "1"}})
        )

        await action.execute(info="Test", distribution="Your Org Only")

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["Event"]["distribution"] == "0"

    @pytest.mark.asyncio
    async def test_threat_level_mapping(self, action):
        """Test threat level string is mapped to numeric code."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"Event": {"id": "1"}})
        )

        await action.execute(info="Test", threat_level_id="High")

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["Event"]["threat_level_id"] == "1"

    @pytest.mark.asyncio
    async def test_analysis_mapping(self, action):
        """Test analysis string is mapped to numeric code."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"Event": {"id": "1"}})
        )

        await action.execute(info="Test", analysis="Completed")

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["Event"]["analysis"] == "2"

    @pytest.mark.asyncio
    async def test_defaults(self, action):
        """Test default values for distribution, threat_level, analysis."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"Event": {"id": "1"}})
        )

        await action.execute(info="Test")

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        # Defaults: distribution=1 (This Community Only), threat_level_id=4 (Undefined), analysis=0 (Initial)
        assert body["Event"]["distribution"] == "1"
        assert body["Event"]["threat_level_id"] == "4"
        assert body["Event"]["analysis"] == "0"

    @pytest.mark.asyncio
    async def test_missing_info(self, action):
        """Test error when info parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "info" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_distribution(self, action):
        """Test error for invalid distribution value."""
        result = await action.execute(info="Test", distribution="invalid_value")

        assert result["status"] == "error"
        assert "distribution" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_threat_level(self, action):
        """Test error for invalid threat_level_id."""
        result = await action.execute(info="Test", threat_level_id="critical")

        assert result["status"] == "error"
        assert "threat_level" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_analysis(self, action):
        """Test error for invalid analysis value."""
        result = await action.execute(info="Test", analysis="nonexistent")

        assert result["status"] == "error"
        assert "analysis" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key is missing."""
        action = _make_action(CreateEventAction, credentials={})

        result = await action.execute(info="Test")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        """Test API error handling."""
        action.http_request = AsyncMock(side_effect=Exception("Server error"))

        result = await action.execute(info="Test")

        assert result["status"] == "error"
        assert "Server error" in result["error"]


# ============================================================================
# ADD ATTRIBUTE TESTS
# ============================================================================


class TestAddAttributeAction:
    """Test MISP add attribute action."""

    @pytest.fixture
    def action(self):
        return _make_action(AddAttributeAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful attribute addition."""
        attr_response = {
            "Attribute": {
                "id": "500",
                "event_id": "42",
                "type": "ip-src",
                "value": "192.168.1.1",
                "to_ids": True,
            }
        }
        action.http_request = AsyncMock(return_value=_mock_response(attr_response))

        result = await action.execute(event_id=42, type="ip-src", value="192.168.1.1")

        assert result["status"] == "success"
        assert result["data"]["Attribute"]["id"] == "500"
        assert "Attribute added to event 42" in result["message"]

    @pytest.mark.asyncio
    async def test_posts_to_attributes_add(self, action):
        """Test uses POST /attributes/add/{event_id}."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"Attribute": {"id": "1"}})
        )

        await action.execute(event_id=42, type="domain", value="attacker.example")

        call_kwargs = action.http_request.call_args
        assert "/attributes/add/42" in call_kwargs.kwargs["url"]
        assert call_kwargs.kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_sends_correct_body(self, action):
        """Test request body contains all fields."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"Attribute": {"id": "1"}})
        )

        await action.execute(
            event_id=42,
            type="ip-src",
            value="10.0.0.1",
            category="Network activity",
            to_ids=False,
            comment="Test comment",
        )

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["event_id"] == 42
        assert body["type"] == "ip-src"
        assert body["value"] == "10.0.0.1"
        assert body["category"] == "Network activity"
        assert body["to_ids"] is False
        assert body["comment"] == "Test comment"

    @pytest.mark.asyncio
    async def test_default_to_ids_true(self, action):
        """Test to_ids defaults to True."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"Attribute": {"id": "1"}})
        )

        await action.execute(event_id=42, type="ip-src", value="10.0.0.1")

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["to_ids"] is True

    @pytest.mark.asyncio
    async def test_missing_event_id(self, action):
        """Test error when event_id is missing."""
        result = await action.execute(type="ip-src", value="10.0.0.1")

        assert result["status"] == "error"
        assert "event_id" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_type(self, action):
        """Test error when type is missing."""
        result = await action.execute(event_id=42, value="10.0.0.1")

        assert result["status"] == "error"
        assert "type" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_value(self, action):
        """Test error when value is missing."""
        result = await action.execute(event_id=42, type="ip-src")

        assert result["status"] == "error"
        assert "value" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key is missing."""
        action = _make_action(AddAttributeAction, credentials={})

        result = await action.execute(event_id=42, type="ip-src", value="10.0.0.1")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Test 404 (event not found) returns not_found."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(404))

        result = await action.execute(event_id=99999, type="ip-src", value="10.0.0.1")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_500_returns_error(self, action):
        """Test 500 error propagates."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(500))

        result = await action.execute(event_id=42, type="ip-src", value="10.0.0.1")

        assert result["status"] == "error"


# ============================================================================
# SEARCH ATTRIBUTES TESTS
# ============================================================================


class TestSearchAttributesAction:
    """Test MISP search attributes action."""

    @pytest.fixture
    def action(self):
        return _make_action(SearchAttributesAction)

    @pytest.mark.asyncio
    async def test_success_with_results(self, action):
        """Test successful attribute search."""
        search_response = {
            "response": {
                "Attribute": [
                    {"id": "1", "type": "ip-src", "value": "8.8.8.8", "event_id": "42"},
                    {"id": "2", "type": "ip-src", "value": "1.1.1.1", "event_id": "43"},
                ]
            }
        }
        action.http_request = AsyncMock(return_value=_mock_response(search_response))

        result = await action.execute(type="ip-src")

        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert len(result["data"]["attributes"]) == 2

    @pytest.mark.asyncio
    async def test_success_no_results(self, action):
        """Test search with no results."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"response": {"Attribute": []}})
        )

        result = await action.execute(value="nonexistent")

        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    @pytest.mark.asyncio
    async def test_posts_to_attributes_rest_search(self, action):
        """Test uses POST /attributes/restSearch."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"response": {"Attribute": []}})
        )

        await action.execute(value="test")

        call_kwargs = action.http_request.call_args
        assert "/attributes/restSearch" in call_kwargs.kwargs["url"]
        assert call_kwargs.kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_search_by_value(self, action):
        """Test search by value."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"response": {"Attribute": []}})
        )

        await action.execute(value="8.8.8.8")

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["value"] == "8.8.8.8"

    @pytest.mark.asyncio
    async def test_search_by_category(self, action):
        """Test search by category."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"response": {"Attribute": []}})
        )

        await action.execute(category="Network activity")

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["category"] == "Network activity"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key is missing."""
        action = _make_action(SearchAttributesAction, credentials={})

        result = await action.execute(value="test")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        """Test API error handling."""
        action.http_request = AsyncMock(side_effect=Exception("Timeout"))

        result = await action.execute(value="test")

        assert result["status"] == "error"
        assert "Timeout" in result["error"]


# ============================================================================
# GET ATTRIBUTE TESTS
# ============================================================================


class TestGetAttributeAction:
    """Test MISP get attribute action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetAttributeAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful attribute retrieval."""
        attr_data = {
            "Attribute": {
                "id": "100",
                "type": "ip-src",
                "value": "8.8.8.8",
                "event_id": "42",
            }
        }
        action.http_request = AsyncMock(return_value=_mock_response(attr_data))

        result = await action.execute(attribute_id=100)

        assert result["status"] == "success"
        assert result["data"]["Attribute"]["id"] == "100"

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self, action):
        """Test calls /attributes/view/{id}."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"Attribute": {"id": "100"}})
        )

        await action.execute(attribute_id=100)

        call_kwargs = action.http_request.call_args
        assert "/attributes/view/100" in call_kwargs.kwargs["url"]

    @pytest.mark.asyncio
    async def test_missing_attribute_id(self, action):
        """Test error when attribute_id is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "attribute_id" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_attribute_id(self, action):
        """Test error for non-numeric attribute_id."""
        result = await action.execute(attribute_id="abc")

        assert result["status"] == "error"
        assert "positive integer" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_zero_attribute_id(self, action):
        """Test error for zero attribute_id."""
        result = await action.execute(attribute_id=0)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Test 404 returns success with not_found flag."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(404))

        result = await action.execute(attribute_id=99999)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["attribute_id"] == 99999

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key is missing."""
        action = _make_action(GetAttributeAction, credentials={})

        result = await action.execute(attribute_id=100)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# ADD TAG TESTS
# ============================================================================


class TestAddTagAction:
    """Test MISP add tag action."""

    @pytest.fixture
    def action(self):
        return _make_action(AddTagAction)

    @pytest.mark.asyncio
    async def test_success_event_tag(self, action):
        """Test successful tag addition to event."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"saved": True, "success": "Tag added"})
        )

        result = await action.execute(tag="tlp:white", event_id=42)

        assert result["status"] == "success"
        assert "tlp:white" in result["message"]
        assert "event" in result["message"]

    @pytest.mark.asyncio
    async def test_success_attribute_tag(self, action):
        """Test successful tag addition to attribute."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"saved": True, "success": "Tag added"})
        )

        result = await action.execute(tag="malware", attribute_id=100)

        assert result["status"] == "success"
        assert "attribute" in result["message"]

    @pytest.mark.asyncio
    async def test_calls_attach_tag_endpoint(self, action):
        """Test calls /tags/attachTagToObject/{id}."""
        action.http_request = AsyncMock(return_value=_mock_response({"saved": True}))

        await action.execute(tag="test", event_id=42)

        call_kwargs = action.http_request.call_args
        assert "/tags/attachTagToObject/42" in call_kwargs.kwargs["url"]
        assert call_kwargs.kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_tag_body_content(self, action):
        """Test request body contains tag name."""
        action.http_request = AsyncMock(return_value=_mock_response({"saved": True}))

        await action.execute(tag="tlp:green", event_id=42)

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs["json_data"]
        assert body["tag"] == "tlp:green"

    @pytest.mark.asyncio
    async def test_missing_tag(self, action):
        """Test error when tag is missing."""
        result = await action.execute(event_id=42)

        assert result["status"] == "error"
        assert "tag" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_both_ids(self, action):
        """Test error when neither event_id nor attribute_id is provided."""
        result = await action.execute(tag="test")

        assert result["status"] == "error"
        assert "event_id or attribute_id" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key is missing."""
        action = _make_action(AddTagAction, credentials={})

        result = await action.execute(tag="test", event_id=42)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Test 404 returns not_found."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(404))

        result = await action.execute(tag="test", event_id=99999)

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        """Test API error handling."""
        action.http_request = AsyncMock(side_effect=Exception("Connection error"))

        result = await action.execute(tag="test", event_id=42)

        assert result["status"] == "error"


# ============================================================================
# LIST TAGS TESTS
# ============================================================================


class TestListTagsAction:
    """Test MISP list tags action."""

    @pytest.fixture
    def action(self):
        return _make_action(ListTagsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful tag listing."""
        tags_response = {
            "Tag": [
                {"id": "1", "name": "tlp:white", "colour": "#FFFFFF"},
                {"id": "2", "name": "tlp:green", "colour": "#33FF00"},
                {"id": "3", "name": "malware", "colour": "#FF0000"},
            ]
        }
        action.http_request = AsyncMock(return_value=_mock_response(tags_response))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["count"] == 3
        assert len(result["data"]["tags"]) == 3

    @pytest.mark.asyncio
    async def test_calls_tags_endpoint(self, action):
        """Test calls GET /tags."""
        action.http_request = AsyncMock(return_value=_mock_response({"Tag": []}))

        await action.execute()

        call_kwargs = action.http_request.call_args
        assert call_kwargs.kwargs["url"].endswith("/tags")

    @pytest.mark.asyncio
    async def test_empty_tags(self, action):
        """Test empty tag list."""
        action.http_request = AsyncMock(return_value=_mock_response({"Tag": []}))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert result["data"]["tags"] == []

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key is missing."""
        action = _make_action(ListTagsAction, credentials={})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        """Test API error handling."""
        action.http_request = AsyncMock(side_effect=Exception("Server down"))

        result = await action.execute()

        assert result["status"] == "error"
        assert "Server down" in result["error"]


# ============================================================================
# AUTH HEADER TESTS
# ============================================================================


class TestAuthHeaders:
    """Test that all actions set proper auth headers."""

    @pytest.mark.asyncio
    async def test_health_check_headers(self):
        """Test health check sends auth headers."""
        action = _make_action(HealthCheckAction)
        headers = action.get_http_headers()

        assert headers["Authorization"] == "test-misp-api-key"
        assert headers["Accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_get_event_headers(self):
        """Test get event sends auth headers."""
        action = _make_action(GetEventAction)
        headers = action.get_http_headers()

        assert headers["Authorization"] == "test-misp-api-key"

    @pytest.mark.asyncio
    async def test_empty_api_key_header(self):
        """Test empty string when api_key not in credentials."""
        action = _make_action(HealthCheckAction, credentials={})
        headers = action.get_http_headers()

        assert headers["Authorization"] == ""

"""Unit tests for Cybersixgill dark web threat intelligence integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.cybersixgill.actions import (
    GetAlertAction,
    HealthCheckAction,
    ListAlertsAction,
    LookupDomainAction,
    LookupHashAction,
    LookupIpAction,
    LookupUrlAction,
    SearchThreatsAction,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {
    "client_id": "test-client-id-abc123",
    "client_secret": "test-client-secret-xyz789",
}

DEFAULT_SETTINGS = {
    "base_url": "https://api.cybersixgill.com",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="cybersixgill",
        action_id=cls.__name__,
        settings=DEFAULT_SETTINGS.copy() if settings is None else settings,
        credentials=DEFAULT_CREDENTIALS.copy() if credentials is None else credentials,
    )


def _mock_response(json_data, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.text = str(json_data)
    return resp


def _mock_http_error(status_code, message="error"):
    """Create a mock httpx.HTTPStatusError."""
    request = MagicMock(spec=httpx.Request)
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = message
    return httpx.HTTPStatusError(message, request=request, response=response)


def _token_response():
    """Create a mock OAuth2 token response."""
    return _mock_response(
        {"access_token": "test-access-token-123", "token_type": "bearer"}
    )


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Health check succeeds when token endpoint returns a valid token."""
        action.http_request = AsyncMock(return_value=_token_response())

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["has_valid_token"] is True
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Health check fails when both client_id and client_secret are missing."""
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "client_id" in result["error"] or "credentials" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_client_id(self):
        """Health check fails when client_id is missing."""
        action = _make_action(
            HealthCheckAction,
            credentials={"client_secret": "secret-only"},
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_client_secret(self):
        """Health check fails when client_secret is missing."""
        action = _make_action(
            HealthCheckAction,
            credentials={"client_id": "id-only"},
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_auth_failure(self, action):
        """Health check fails when OAuth2 token request returns 401."""
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(401, "Unauthorized")
        )
        result = await action.execute()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        """Health check fails when connection is refused."""
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await action.execute()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_token_response_missing_access_token(self, action):
        """Health check fails when token response has no access_token."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"error": "invalid_client"})
        )
        result = await action.execute()

        assert result["status"] == "error"


# ============================================================================
# LOOKUP IP
# ============================================================================


class TestLookupIpAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupIpAction)

    @pytest.mark.asyncio
    async def test_success_with_indicators(self, action):
        """Lookup IP returns indicators when found."""
        indicators = [
            {
                "indicator_value": "1.2.3.4",
                "indicator_type": "IP Address",
                "sixgill_severity": 90,
                "sixgill_confidence": 80,
                "sixgill_feedname": "dark_web_ips",
                "description": "Malicious IP found on dark web forum",
                "sixgill_source": "forum_test",
                "sixgill_actor": "TestActor",
                "valid_from": "2024-01-15T10:00:00Z",
            }
        ]
        # First call: token endpoint, second call: enrichment endpoint
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response(indicators)]
        )

        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "success"
        assert result["data"]["ip"] == "1.2.3.4"
        assert result["data"]["indicators_found"] == 1
        assert len(result["data"]["indicators"]) == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_no_indicators(self, action):
        """Lookup IP returns empty list when no indicators match."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response([])]
        )

        result = await action.execute(ip="10.0.0.1")

        assert result["status"] == "success"
        assert result["data"]["ip"] == "10.0.0.1"
        assert result["data"]["indicators_found"] == 0
        assert result["data"]["indicators"] == []

    @pytest.mark.asyncio
    async def test_missing_ip_parameter(self, action):
        """Lookup IP fails when ip parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Lookup IP fails when credentials are missing."""
        action = _make_action(LookupIpAction, credentials={})
        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_success_not_found(self, action):
        """Lookup IP returns success with not_found=True on 404."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_http_error(404, "Not found")]
        )

        result = await action.execute(ip="192.168.1.1")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["ip"] == "192.168.1.1"
        assert result["data"]["indicators_found"] == 0

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        """Lookup IP fails on server error."""
        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _mock_http_error(500, "Internal Server Error"),
            ]
        )

        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_dict_response_with_items_key(self, action):
        """Lookup IP handles dict response with 'items' key."""
        response_data = {
            "items": [
                {"indicator_value": "1.2.3.4", "indicator_type": "IP Address"},
            ]
        }
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response(response_data)]
        )

        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "success"
        assert result["data"]["indicators_found"] == 1


# ============================================================================
# LOOKUP DOMAIN
# ============================================================================


class TestLookupDomainAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupDomainAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Lookup domain returns indicators when found."""
        indicators = [
            {
                "indicator_value": "evil.example.com",
                "indicator_type": "DOMAIN",
                "sixgill_severity": 70,
            }
        ]
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response(indicators)]
        )

        result = await action.execute(domain="evil.example.com")

        assert result["status"] == "success"
        assert result["data"]["domain"] == "evil.example.com"
        assert result["data"]["indicators_found"] == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_domain_parameter(self, action):
        """Lookup domain fails when domain parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Lookup domain fails when credentials are missing."""
        action = _make_action(LookupDomainAction, credentials={})
        result = await action.execute(domain="example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Lookup domain returns not_found on 404."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_http_error(404)]
        )

        result = await action.execute(domain="safe.example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["domain"] == "safe.example.com"
        assert result["data"]["indicators_found"] == 0


# ============================================================================
# LOOKUP HASH
# ============================================================================


class TestLookupHashAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupHashAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Lookup hash returns indicators when found."""
        indicators = [
            {
                "indicator_value": "d41d8cd98f00b204e9800998ecf8427e",
                "indicator_type": "Hash - MD5",
                "sixgill_severity": 90,
                "sixgill_confidence": 95,
            }
        ]
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response(indicators)]
        )

        result = await action.execute(hash="d41d8cd98f00b204e9800998ecf8427e")

        assert result["status"] == "success"
        assert result["data"]["hash"] == "d41d8cd98f00b204e9800998ecf8427e"
        assert result["data"]["indicators_found"] == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_hash_parameter(self, action):
        """Lookup hash fails when hash parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "hash" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Lookup hash fails when credentials are missing."""
        action = _make_action(LookupHashAction, credentials={})
        result = await action.execute(hash="abc123")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Lookup hash returns not_found on 404."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_http_error(404)]
        )

        result = await action.execute(hash="deadbeef" * 8)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["indicators_found"] == 0


# ============================================================================
# LOOKUP URL
# ============================================================================


class TestLookupUrlAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupUrlAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Lookup URL returns indicators when found."""
        indicators = [
            {
                "indicator_value": "https://evil.example.com/payload",
                "indicator_type": "URL",
                "sixgill_severity": 80,
            }
        ]
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response(indicators)]
        )

        result = await action.execute(url="https://evil.example.com/payload")

        assert result["status"] == "success"
        assert result["data"]["url"] == "https://evil.example.com/payload"
        assert result["data"]["indicators_found"] == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_url_parameter(self, action):
        """Lookup URL fails when url parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "url" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Lookup URL fails when credentials are missing."""
        action = _make_action(LookupUrlAction, credentials={})
        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Lookup URL returns not_found on 404."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_http_error(404)]
        )

        result = await action.execute(url="https://safe.example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["url"] == "https://safe.example.com"
        assert result["data"]["indicators_found"] == 0


# ============================================================================
# SEARCH THREATS
# ============================================================================


class TestSearchThreatsAction:
    @pytest.fixture
    def action(self):
        return _make_action(SearchThreatsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Search threats returns results when found."""
        items = [
            {
                "title": "Threat found",
                "description": "Dark web mention",
                "date": "2024-01-15",
            },
            {
                "title": "Another threat",
                "description": "Forum post",
                "date": "2024-01-14",
            },
        ]
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response(items)]
        )

        result = await action.execute(query="malware")

        assert result["status"] == "success"
        assert result["data"]["query"] == "malware"
        assert result["data"]["total_results"] == 2
        assert len(result["data"]["items"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_with_dict_response(self, action):
        """Search threats handles dict response with 'items' key."""
        response_data = {
            "items": [{"title": "Threat", "description": "Found"}],
        }
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response(response_data)]
        )

        result = await action.execute(query="ransomware")

        assert result["status"] == "success"
        assert result["data"]["total_results"] == 1

    @pytest.mark.asyncio
    async def test_success_empty_results(self, action):
        """Search threats returns empty results for unmatched query."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response([])]
        )

        result = await action.execute(query="nonexistent_threat_xyz")

        assert result["status"] == "success"
        assert result["data"]["total_results"] == 0
        assert result["data"]["items"] == []

    @pytest.mark.asyncio
    async def test_missing_query_parameter(self, action):
        """Search threats fails when query parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Search threats fails when credentials are missing."""
        action = _make_action(SearchThreatsAction, credentials={})
        result = await action.execute(query="malware")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_with_optional_params(self, action):
        """Search threats passes optional limit and from_date."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response([])]
        )

        result = await action.execute(
            query="ransomware",
            limit=5,
            from_date="2024-01-01",
        )

        assert result["status"] == "success"
        # Verify the request body included optional params
        call_args = action.http_request.call_args_list[1]
        json_body = call_args.kwargs.get("json_data", {})
        assert json_body.get("results_size") == 5
        assert json_body.get("from_date") == "2024-01-01"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        """Search threats fails on server error."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_http_error(500)]
        )

        result = await action.execute(query="test")

        assert result["status"] == "error"


# ============================================================================
# GET ALERT
# ============================================================================


class TestGetAlertAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetAlertAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Get alert returns alert details when found."""
        alert_data = {
            "id": "alert-123",
            "title": "Credential leak detected",
            "severity": "high",
            "status": "open",
            "created": "2024-01-15T10:00:00Z",
        }
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response(alert_data)]
        )

        result = await action.execute(alert_id="alert-123")

        assert result["status"] == "success"
        assert result["data"]["id"] == "alert-123"
        assert result["data"]["severity"] == "high"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_alert_id(self, action):
        """Get alert fails when alert_id parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "alert_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Get alert fails when credentials are missing."""
        action = _make_action(GetAlertAction, credentials={})
        result = await action.execute(alert_id="alert-123")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Get alert returns not_found on 404."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_http_error(404)]
        )

        result = await action.execute(alert_id="nonexistent-alert")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["alert_id"] == "nonexistent-alert"

    @pytest.mark.asyncio
    async def test_auth_error(self, action):
        """Get alert fails on authentication error."""
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(401, "Invalid credentials")
        )

        result = await action.execute(alert_id="alert-123")

        assert result["status"] == "error"


# ============================================================================
# LIST ALERTS
# ============================================================================


class TestListAlertsAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListAlertsAction)

    @pytest.mark.asyncio
    async def test_success_list_response(self, action):
        """List alerts returns alerts when response is a list."""
        alerts = [
            {"id": "alert-1", "title": "Alert 1", "severity": "high"},
            {"id": "alert-2", "title": "Alert 2", "severity": "medium"},
        ]
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response(alerts)]
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_alerts"] == 2
        assert result["data"]["alerts_returned"] == 2
        assert len(result["data"]["alerts"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_dict_response(self, action):
        """List alerts handles dict response with items/total keys."""
        response_data = {
            "items": [
                {"id": "alert-1", "title": "Alert 1"},
            ],
            "total": 50,
        }
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response(response_data)]
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_alerts"] == 50
        assert result["data"]["alerts_returned"] == 1

    @pytest.mark.asyncio
    async def test_success_empty(self, action):
        """List alerts returns empty when no alerts exist."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response([])]
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_alerts"] == 0
        assert result["data"]["alerts"] == []

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """List alerts fails when credentials are missing."""
        action = _make_action(ListAlertsAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_with_filters(self, action):
        """List alerts passes severity and status filters."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response([])]
        )

        result = await action.execute(
            limit=10,
            offset=5,
            severity="high",
            status="open",
        )

        assert result["status"] == "success"
        # Verify query params included filters
        call_args = action.http_request.call_args_list[1]
        params = call_args.kwargs.get("params", {})
        assert params["limit"] == 10
        assert params["offset"] == 5
        assert params["severity"] == "high"
        assert params["status"] == "open"

    @pytest.mark.asyncio
    async def test_default_pagination(self, action):
        """List alerts uses default limit=25, offset=0."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response([])]
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["offset"] == 0
        assert result["data"]["limit"] == 25

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        """List alerts fails on server error."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_http_error(500)]
        )

        result = await action.execute()

        assert result["status"] == "error"


# ============================================================================
# OAUTH2 TOKEN HANDLING (tested through actions)
# ============================================================================


class TestOAuth2TokenHandling:
    """Test OAuth2 token acquisition through action execution."""

    @pytest.mark.asyncio
    async def test_token_request_sends_correct_credentials(self):
        """Verify OAuth2 token request includes client_id and client_secret."""
        action = _make_action(LookupIpAction)
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response([])]
        )

        await action.execute(ip="1.2.3.4")

        # First call should be the token endpoint
        token_call = action.http_request.call_args_list[0]
        assert "/auth/token" in token_call.kwargs["url"]
        assert token_call.kwargs["method"] == "POST"
        data = token_call.kwargs.get("data", {})
        assert data["client_id"] == "test-client-id-abc123"
        assert data["client_secret"] == "test-client-secret-xyz789"
        assert data["grant_type"] == "client_credentials"

    @pytest.mark.asyncio
    async def test_bearer_token_sent_in_enrichment_request(self):
        """Verify the access token is passed as Bearer auth to the enrichment endpoint."""
        action = _make_action(LookupIpAction)
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response([])]
        )

        await action.execute(ip="1.2.3.4")

        # Second call should use the bearer token
        enrich_call = action.http_request.call_args_list[1]
        headers = enrich_call.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer test-access-token-123"

    @pytest.mark.asyncio
    async def test_token_endpoint_failure_propagates(self):
        """Verify token endpoint failure prevents the enrichment request."""
        action = _make_action(LookupIpAction)
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(401, "Invalid client")
        )

        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "error"
        # Only one call made (token endpoint), enrichment not reached
        assert action.http_request.call_count == 1

    @pytest.mark.asyncio
    async def test_custom_base_url(self):
        """Verify custom base_url is used in requests."""
        action = _make_action(
            LookupIpAction,
            settings={
                "base_url": "https://custom.cybersixgill.com",
                "timeout": 30,
            },
        )
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _mock_response([])]
        )

        await action.execute(ip="1.2.3.4")

        token_call = action.http_request.call_args_list[0]
        assert "custom.cybersixgill.com" in token_call.kwargs["url"]

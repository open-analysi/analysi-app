"""Unit tests for Cloudflare integration actions."""

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.cloudflare.actions import (
    BlockIpAction,
    BlockUserAgentAction,
    HealthCheckAction,
    UpdateRuleAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def credentials():
    """Sample Cloudflare credentials."""
    return {"api_token": "test-cf-token"}


@pytest.fixture
def settings():
    """Sample Cloudflare settings."""
    return {
        "base_url": "https://api.cloudflare.com/client/v4",
        "timeout": 30,
    }


@pytest.fixture
def health_check_action(credentials, settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction("cloudflare", "health_check", settings, credentials)


@pytest.fixture
def block_ip_action(credentials, settings):
    """Create BlockIpAction instance."""
    return BlockIpAction("cloudflare", "block_ip", settings, credentials)


@pytest.fixture
def block_user_agent_action(credentials, settings):
    """Create BlockUserAgentAction instance."""
    return BlockUserAgentAction("cloudflare", "block_user_agent", settings, credentials)


@pytest.fixture
def update_rule_action(credentials, settings):
    """Create UpdateRuleAction instance."""
    return UpdateRuleAction("cloudflare", "update_rule", settings, credentials)


# ============================================================================
# HELPER: Build httpx.HTTPStatusError mocks
# ============================================================================


def _http_error(status_code: int, body: dict | None = None) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError with the given status and optional JSON body."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.request = MagicMock()
    mock_response.headers = {}
    if body is not None:
        mock_response.json.return_value = body
        mock_response.text = json.dumps(body)
    else:
        mock_response.json.side_effect = Exception("no json")
        mock_response.text = ""
    return httpx.HTTPStatusError(
        f"{status_code}",
        request=mock_response.request,
        response=mock_response,
    )


# ============================================================================
# AUTH HEADER TESTS
# ============================================================================


class TestAuthHeaders:
    """Test that get_http_headers returns correct auth headers."""

    def test_headers_with_api_token(self, health_check_action):
        """Test Bearer token header is set."""
        headers = health_check_action.get_http_headers()
        assert headers["Authorization"] == "Bearer test-cf-token"
        assert headers["Content-Type"] == "application/json"

    def test_headers_without_api_token(self, settings):
        """Test headers when no token provided."""
        action = HealthCheckAction("cloudflare", "health_check", settings, {})
        headers = action.get_http_headers()
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_timeout_from_settings(self, health_check_action):
        """Test timeout from settings."""
        assert health_check_action.get_timeout() == 30

    def test_timeout_default(self):
        """Test default timeout when not configured."""
        action = HealthCheckAction("cloudflare", "health_check", {}, {"api_token": "x"})
        assert action.get_timeout() == 30

    def test_base_url_from_settings(self, health_check_action):
        """Test base URL from settings."""
        assert (
            health_check_action._get_base_url()
            == "https://api.cloudflare.com/client/v4"
        )

    def test_base_url_strips_trailing_slash(self):
        """Test base URL strips trailing slash."""
        action = HealthCheckAction(
            "cloudflare",
            "health_check",
            {"base_url": "https://api.cloudflare.com/client/v4/"},
            {"api_token": "x"},
        )
        assert action._get_base_url() == "https://api.cloudflare.com/client/v4"


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestHealthCheck:
    """Tests for HealthCheckAction."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "result": [{"id": "zone1", "name": "example.com"}],
        }
        mock_response.status_code = 200
        health_check_action.http_request = AsyncMock(return_value=mock_response)

        result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["integration_id"] == "cloudflare"
        assert result["action_id"] == "health_check"
        assert result["data"]["healthy"] is True
        health_check_action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_missing_api_token(self, settings):
        """Test health check with missing API token."""
        action = HealthCheckAction("cloudflare", "health_check", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "api_token" in result["error"]

    @pytest.mark.asyncio
    async def test_health_check_auth_failure(self, health_check_action):
        """Test health check with authentication failure (401)."""
        health_check_action.http_request = AsyncMock(side_effect=_http_error(401))

        result = await health_check_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"

    @pytest.mark.asyncio
    async def test_health_check_forbidden(self, health_check_action):
        """Test health check with forbidden response (403)."""
        health_check_action.http_request = AsyncMock(side_effect=_http_error(403))

        result = await health_check_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"

    @pytest.mark.asyncio
    async def test_health_check_api_error(self, health_check_action):
        """Test health check with success=false in response body."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False, "errors": []}
        mock_response.status_code = 200
        health_check_action.http_request = AsyncMock(return_value=mock_response)

        result = await health_check_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, health_check_action):
        """Test health check with connection failure."""
        health_check_action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await health_check_action.execute()

        assert result["status"] == "error"
        assert "ConnectError" in result["error_type"]

    @pytest.mark.asyncio
    async def test_health_check_server_error(self, health_check_action):
        """Test health check with 500 server error."""
        health_check_action.http_request = AsyncMock(side_effect=_http_error(500))

        result = await health_check_action.execute()

        assert result["status"] == "error"


# ============================================================================
# BLOCK IP TESTS
# ============================================================================


class TestBlockIp:
    """Tests for BlockIpAction."""

    @pytest.mark.asyncio
    async def test_block_ip_success(self, block_ip_action):
        """Test successful IP block (new filter + new rule)."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # Get zone ID
                mock_resp.json.return_value = {
                    "result": [{"id": "zone-abc", "name": "example.com"}]
                }
            elif call_count == 2:
                # Create filter
                mock_resp.json.return_value = {"result": [{"id": "filter-123"}]}
            elif call_count == 3:
                # Create firewall rule
                mock_resp.json.return_value = {"result": [{"id": "rule-456"}]}

            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(
            ip="10.0.0.1",
            domain_name="example.com",
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "IP blocked successfully"
        assert result["data"]["ip"] == "10.0.0.1"
        assert result["data"]["domain_name"] == "example.com"
        assert result["data"]["zone_id"] == "zone-abc"
        assert result["data"]["filter_id"] == "filter-123"
        assert result["data"]["rule_id"] == "rule-456"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_block_ip_duplicate_filter_and_rule(self, block_ip_action):
        """Test block IP when filter and rule already exist (duplicate errors)."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # Get zone ID
                mock_resp.json.return_value = {"result": [{"id": "zone-abc"}]}
            elif call_count == 2:
                # Create filter: duplicate error
                raise _http_error(
                    400,
                    {"errors": [{"code": 10102, "meta": {"id": "existing-filter"}}]},
                )
            elif call_count == 3:
                # Create rule: duplicate error
                raise _http_error(
                    400,
                    {"errors": [{"code": 10102, "meta": {"id": "existing-rule"}}]},
                )
            elif call_count == 4:
                # Update existing rule (PUT)
                mock_resp.json.return_value = {"result": [{"id": "existing-rule"}]}

            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(
            ip="10.0.0.1",
            domain_name="example.com",
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Existing block rule updated for IP"
        assert result["data"]["filter_id"] == "existing-filter"
        assert result["data"]["rule_id"] == "existing-rule"
        assert call_count == 4

    @pytest.mark.asyncio
    async def test_block_ip_missing_ip(self, block_ip_action):
        """Test block IP with missing IP parameter."""
        result = await block_ip_action.execute(domain_name="example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_ip_missing_domain(self, block_ip_action):
        """Test block IP with missing domain_name parameter."""
        result = await block_ip_action.execute(ip="10.0.0.1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain_name" in result["error"]

    @pytest.mark.asyncio
    async def test_block_ip_missing_credentials(self, settings):
        """Test block IP with missing credentials."""
        action = BlockIpAction("cloudflare", "block_ip", settings, {})

        result = await action.execute(ip="10.0.0.1", domain_name="example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_block_ip_zone_not_found(self, block_ip_action):
        """Test block IP when zone is not found."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": []}
        mock_response.status_code = 200
        block_ip_action.http_request = AsyncMock(return_value=mock_response)

        result = await block_ip_action.execute(
            ip="10.0.0.1",
            domain_name="nonexistent.com",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "nonexistent.com" in result["error"]

    @pytest.mark.asyncio
    async def test_block_ip_api_error(self, block_ip_action):
        """Test block IP with API error during zone lookup."""
        block_ip_action.http_request = AsyncMock(side_effect=_http_error(500))

        result = await block_ip_action.execute(
            ip="10.0.0.1",
            domain_name="example.com",
        )

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_block_ip_custom_description(self, block_ip_action):
        """Test block IP with custom rule description."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {"result": [{"id": "zone-abc"}]}
            elif call_count == 2:
                mock_resp.json.return_value = {"result": [{"id": "f1"}]}
            elif call_count == 3:
                # Verify the description in the POST body
                payload = kwargs.get("json_data", [])
                assert payload[0]["description"] == "Custom Block Rule"
                mock_resp.json.return_value = {"result": [{"id": "r1"}]}

            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(
            ip="10.0.0.1",
            domain_name="example.com",
            rule_description="Custom Block Rule",
        )

        assert result["status"] == "success"


# ============================================================================
# BLOCK USER AGENT TESTS
# ============================================================================


class TestBlockUserAgent:
    """Tests for BlockUserAgentAction."""

    @pytest.mark.asyncio
    async def test_block_user_agent_success(self, block_user_agent_action):
        """Test successful user agent block."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {"result": [{"id": "zone-abc"}]}
            elif call_count == 2:
                mock_resp.json.return_value = {"result": [{"id": "filter-ua"}]}
            elif call_count == 3:
                mock_resp.json.return_value = {"result": [{"id": "rule-ua"}]}

            return mock_resp

        block_user_agent_action.http_request = mock_http_request

        result = await block_user_agent_action.execute(
            user_agent="BadBot/1.0",
            domain_name="example.com",
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "User agent blocked successfully"
        assert result["data"]["user_agent"] == "BadBot/1.0"
        assert result["data"]["domain_name"] == "example.com"
        assert result["data"]["filter_id"] == "filter-ua"
        assert result["data"]["rule_id"] == "rule-ua"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_block_user_agent_missing_user_agent(self, block_user_agent_action):
        """Test block user agent with missing user_agent parameter."""
        result = await block_user_agent_action.execute(domain_name="example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "user_agent" in result["error"]

    @pytest.mark.asyncio
    async def test_block_user_agent_missing_domain(self, block_user_agent_action):
        """Test block user agent with missing domain_name parameter."""
        result = await block_user_agent_action.execute(user_agent="BadBot/1.0")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain_name" in result["error"]

    @pytest.mark.asyncio
    async def test_block_user_agent_missing_credentials(self, settings):
        """Test block user agent with missing credentials."""
        action = BlockUserAgentAction("cloudflare", "block_user_agent", settings, {})

        result = await action.execute(
            user_agent="BadBot/1.0",
            domain_name="example.com",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_block_user_agent_zone_not_found(self, block_user_agent_action):
        """Test block user agent when zone is not found."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": []}
        mock_response.status_code = 200
        block_user_agent_action.http_request = AsyncMock(return_value=mock_response)

        result = await block_user_agent_action.execute(
            user_agent="BadBot/1.0",
            domain_name="nonexistent.com",
        )

        assert result["status"] == "error"
        assert "nonexistent.com" in result["error"]

    @pytest.mark.asyncio
    async def test_block_user_agent_duplicate_updated(self, block_user_agent_action):
        """Test block user agent when rule already exists and gets updated."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {"result": [{"id": "zone-abc"}]}
            elif call_count == 2:
                mock_resp.json.return_value = {"result": [{"id": "f-dup"}]}
            elif call_count == 3:
                # Rule duplicate
                raise _http_error(
                    400,
                    {"errors": [{"code": 10102, "meta": {"id": "r-dup"}}]},
                )
            elif call_count == 4:
                # Update existing rule
                mock_resp.json.return_value = {"result": [{"id": "r-dup"}]}

            return mock_resp

        block_user_agent_action.http_request = mock_http_request

        result = await block_user_agent_action.execute(
            user_agent="BadBot/1.0",
            domain_name="example.com",
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Existing block rule updated for user agent"
        assert call_count == 4


# ============================================================================
# UPDATE RULE TESTS
# ============================================================================


class TestUpdateRule:
    """Tests for UpdateRuleAction."""

    @pytest.mark.asyncio
    async def test_update_rule_block(self, update_rule_action):
        """Test enabling (blocking) a firewall rule."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # Get zone ID
                mock_resp.json.return_value = {"result": [{"id": "zone-abc"}]}
            elif call_count == 2:
                # Get firewall rules by description
                mock_resp.json.return_value = {
                    "result": [
                        {
                            "id": "rule-789",
                            "description": "My Rule",
                            "paused": True,
                            "action": "block",
                            "filter": {"id": "filter-x"},
                        }
                    ]
                }
            elif call_count == 3:
                # Update rule (PUT)
                mock_resp.json.return_value = {"result": [{"id": "rule-789"}]}

            return mock_resp

        update_rule_action.http_request = mock_http_request

        result = await update_rule_action.execute(
            rule_name="My Rule",
            domain_name="example.com",
            action="block",
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Firewall rule updated successfully"
        assert result["data"]["rule_id"] == "rule-789"
        assert result["data"]["action"] == "block"
        assert result["data"]["paused"] is False
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_update_rule_allow(self, update_rule_action):
        """Test pausing (allowing) a firewall rule."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {"result": [{"id": "zone-abc"}]}
            elif call_count == 2:
                mock_resp.json.return_value = {
                    "result": [
                        {
                            "id": "rule-789",
                            "description": "My Rule",
                            "paused": False,
                            "action": "block",
                            "filter": {"id": "filter-x"},
                        }
                    ]
                }
            elif call_count == 3:
                mock_resp.json.return_value = {"result": [{"id": "rule-789"}]}

            return mock_resp

        update_rule_action.http_request = mock_http_request

        result = await update_rule_action.execute(
            rule_name="My Rule",
            domain_name="example.com",
            action="allow",
        )

        assert result["status"] == "success"
        assert result["data"]["paused"] is True

    @pytest.mark.asyncio
    async def test_update_rule_missing_rule_name(self, update_rule_action):
        """Test update rule with missing rule_name parameter."""
        result = await update_rule_action.execute(
            domain_name="example.com",
            action="block",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "rule_name" in result["error"]

    @pytest.mark.asyncio
    async def test_update_rule_missing_domain(self, update_rule_action):
        """Test update rule with missing domain_name parameter."""
        result = await update_rule_action.execute(
            rule_name="My Rule",
            action="block",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain_name" in result["error"]

    @pytest.mark.asyncio
    async def test_update_rule_missing_action(self, update_rule_action):
        """Test update rule with missing action parameter."""
        result = await update_rule_action.execute(
            rule_name="My Rule",
            domain_name="example.com",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "action" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_update_rule_invalid_action(self, update_rule_action):
        """Test update rule with invalid action value."""
        result = await update_rule_action.execute(
            rule_name="My Rule",
            domain_name="example.com",
            action="invalid",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "invalid" in result["error"]

    @pytest.mark.asyncio
    async def test_update_rule_missing_credentials(self, settings):
        """Test update rule with missing credentials."""
        action = UpdateRuleAction("cloudflare", "update_rule", settings, {})

        result = await action.execute(
            rule_name="My Rule",
            domain_name="example.com",
            action="block",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_update_rule_not_found(self, update_rule_action):
        """Test update rule when rule is not found."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {"result": [{"id": "zone-abc"}]}
            elif call_count == 2:
                # No matching rules
                mock_resp.json.return_value = {"result": []}

            return mock_resp

        update_rule_action.http_request = mock_http_request

        result = await update_rule_action.execute(
            rule_name="Nonexistent Rule",
            domain_name="example.com",
            action="block",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "Nonexistent Rule" in result["error"]

    @pytest.mark.asyncio
    async def test_update_rule_zone_not_found(self, update_rule_action):
        """Test update rule when zone is not found."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": []}
        mock_response.status_code = 200
        update_rule_action.http_request = AsyncMock(return_value=mock_response)

        result = await update_rule_action.execute(
            rule_name="My Rule",
            domain_name="nonexistent.com",
            action="block",
        )

        assert result["status"] == "error"
        assert "nonexistent.com" in result["error"]

    @pytest.mark.asyncio
    async def test_update_rule_api_error(self, update_rule_action):
        """Test update rule with API error."""
        update_rule_action.http_request = AsyncMock(side_effect=_http_error(500))

        result = await update_rule_action.execute(
            rule_name="My Rule",
            domain_name="example.com",
            action="block",
        )

        assert result["status"] == "error"

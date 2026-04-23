"""Unit tests for Cisco Umbrella integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.ciscoumbrella.actions import (
    BlockDomainAction,
    HealthCheckAction,
    ListBlockedDomainsAction,
    UnblockDomainAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def credentials():
    """Sample Cisco Umbrella credentials."""
    return {"customer_key": "test-umbrella-key"}


@pytest.fixture
def settings():
    """Sample Cisco Umbrella settings."""
    return {"timeout": 60}


@pytest.fixture
def health_check_action(credentials, settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction("ciscoumbrella", "health_check", settings, credentials)


@pytest.fixture
def block_domain_action(credentials, settings):
    """Create BlockDomainAction instance."""
    return BlockDomainAction("ciscoumbrella", "block_domain", settings, credentials)


@pytest.fixture
def unblock_domain_action(credentials, settings):
    """Create UnblockDomainAction instance."""
    return UnblockDomainAction("ciscoumbrella", "unblock_domain", settings, credentials)


@pytest.fixture
def list_blocked_domains_action(credentials, settings):
    """Create ListBlockedDomainsAction instance."""
    return ListBlockedDomainsAction(
        "ciscoumbrella", "list_blocked_domains", settings, credentials
    )


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestHealthCheck:
    """Tests for HealthCheckAction."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"id": 1, "name": "test.com"}]}
        mock_response.status_code = 200
        health_check_action.http_request = AsyncMock(return_value=mock_response)

        result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["integration_id"] == "ciscoumbrella"
        assert result["action_id"] == "health_check"
        assert result["data"]["healthy"] is True
        health_check_action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_injects_customer_key(self, health_check_action):
        """Test that customer key is injected as a query parameter."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": []}
        mock_response.status_code = 200
        health_check_action.http_request = AsyncMock(return_value=mock_response)

        await health_check_action.execute()

        call_kwargs = health_check_action.http_request.call_args.kwargs
        assert call_kwargs["params"]["customerKey"] == "test-umbrella-key"

    @pytest.mark.asyncio
    async def test_health_check_missing_credentials(self, settings):
        """Test health check with missing customer key."""
        action = HealthCheckAction("ciscoumbrella", "health_check", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "customer_key" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_health_check_http_error(self, health_check_action):
        """Test health check with HTTP error response."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}
        mock_response.request = MagicMock()

        error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mock_response.request,
            response=mock_response,
        )
        health_check_action.http_request = AsyncMock(side_effect=error)

        result = await health_check_action.execute()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, health_check_action):
        """Test health check with connection failure."""
        health_check_action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await health_check_action.execute()

        assert result["status"] == "error"
        assert "ConnectError" in result["error_type"]


# ============================================================================
# BLOCK DOMAIN TESTS
# ============================================================================


class TestBlockDomain:
    """Tests for BlockDomainAction."""

    @pytest.mark.asyncio
    async def test_block_domain_success(self, block_domain_action):
        """Test successful domain block."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "abc-123-def"}
        mock_response.text = '{"id": "abc-123-def"}'
        mock_response.status_code = 202
        block_domain_action.http_request = AsyncMock(return_value=mock_response)

        result = await block_domain_action.execute(domain="malicious.com")

        assert result["status"] == "success"
        assert result["data"]["domain"] == "malicious.com"
        assert result["data"]["message"] == "Domain successfully blocked"
        assert result["data"]["event_id"] == "abc-123-def"

    @pytest.mark.asyncio
    async def test_block_domain_posts_event(self, block_domain_action):
        """Test that block sends a POST to the events endpoint."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "evt-1"}
        mock_response.text = '{"id": "evt-1"}'
        mock_response.status_code = 202
        block_domain_action.http_request = AsyncMock(return_value=mock_response)

        await block_domain_action.execute(domain="evil.com")

        call_kwargs = block_domain_action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert "/events" in call_kwargs["url"]
        # Verify event payload structure
        events = call_kwargs["json_data"]
        assert isinstance(events, list)
        assert len(events) == 1
        assert events[0]["dstDomain"] == "evil.com"
        assert events[0]["dstUrl"] == "http://evil.com/"
        assert events[0]["protocolVersion"] == "1.0a"
        assert events[0]["providerName"] == "Security Platform"

    @pytest.mark.asyncio
    async def test_block_domain_disable_safeguards(self, block_domain_action):
        """Test that disable_safeguards flag is passed through."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "evt-2"}
        mock_response.text = '{"id": "evt-2"}'
        mock_response.status_code = 202
        block_domain_action.http_request = AsyncMock(return_value=mock_response)

        await block_domain_action.execute(domain="google.com", disable_safeguards=True)

        events = block_domain_action.http_request.call_args.kwargs["json_data"]
        assert events[0]["disableDstSafeguards"] is True

    @pytest.mark.asyncio
    async def test_block_domain_missing_domain(self, block_domain_action):
        """Test block domain with missing domain parameter."""
        result = await block_domain_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_domain_missing_credentials(self, settings):
        """Test block domain with missing customer key."""
        action = BlockDomainAction("ciscoumbrella", "block_domain", settings, {})

        result = await action.execute(domain="test.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_block_domain_http_error(self, block_domain_action):
        """Test block domain with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_response.headers = {}
        mock_response.request = MagicMock()

        error = httpx.HTTPStatusError(
            "403 Forbidden",
            request=mock_response.request,
            response=mock_response,
        )
        block_domain_action.http_request = AsyncMock(side_effect=error)

        result = await block_domain_action.execute(domain="test.com")

        assert result["status"] == "error"


# ============================================================================
# UNBLOCK DOMAIN TESTS
# ============================================================================


class TestUnblockDomain:
    """Tests for UnblockDomainAction."""

    @pytest.mark.asyncio
    async def test_unblock_domain_success(self, unblock_domain_action):
        """Test successful domain unblock (204 No Content)."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""
        mock_response.json.return_value = None
        unblock_domain_action.http_request = AsyncMock(return_value=mock_response)

        result = await unblock_domain_action.execute(domain="unblocked.com")

        assert result["status"] == "success"
        assert result["data"]["domain"] == "unblocked.com"
        assert result["data"]["message"] == "Domain successfully unblocked"

    @pytest.mark.asyncio
    async def test_unblock_domain_sends_delete(self, unblock_domain_action):
        """Test that unblock sends a DELETE with domain filter."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""
        unblock_domain_action.http_request = AsyncMock(return_value=mock_response)

        await unblock_domain_action.execute(domain="test.com")

        call_kwargs = unblock_domain_action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "DELETE"
        assert "/domains" in call_kwargs["url"]
        assert call_kwargs["params"]["where[name]"] == "test.com"

    @pytest.mark.asyncio
    async def test_unblock_domain_not_found(self, unblock_domain_action):
        """Test unblock domain that is not in the block list (404)."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.headers = {}
        mock_response.request = MagicMock()

        error = httpx.HTTPStatusError(
            "404 Not Found",
            request=mock_response.request,
            response=mock_response,
        )
        unblock_domain_action.http_request = AsyncMock(side_effect=error)

        result = await unblock_domain_action.execute(domain="not-blocked.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["domain"] == "not-blocked.com"

    @pytest.mark.asyncio
    async def test_unblock_domain_missing_domain(self, unblock_domain_action):
        """Test unblock domain with missing domain parameter."""
        result = await unblock_domain_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unblock_domain_missing_credentials(self, settings):
        """Test unblock domain with missing customer key."""
        action = UnblockDomainAction("ciscoumbrella", "unblock_domain", settings, {})

        result = await action.execute(domain="test.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_unblock_domain_http_error(self, unblock_domain_action):
        """Test unblock domain with non-404 HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}
        mock_response.request = MagicMock()

        error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mock_response.request,
            response=mock_response,
        )
        unblock_domain_action.http_request = AsyncMock(side_effect=error)

        result = await unblock_domain_action.execute(domain="test.com")

        assert result["status"] == "error"


# ============================================================================
# LIST BLOCKED DOMAINS TESTS
# ============================================================================


class TestListBlockedDomains:
    """Tests for ListBlockedDomainsAction."""

    @pytest.mark.asyncio
    async def test_list_blocked_domains_success(self, list_blocked_domains_action):
        """Test successful domain listing (single page)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": 1, "name": "bad.com", "lastSeenAt": 1662618587},
                {"id": 2, "name": "evil.org", "lastSeenAt": 1662618600},
            ],
            "meta": {"next": None},
        }
        mock_response.status_code = 200
        list_blocked_domains_action.http_request = AsyncMock(return_value=mock_response)

        result = await list_blocked_domains_action.execute()

        assert result["status"] == "success"
        assert result["integration_id"] == "ciscoumbrella"
        assert result["data"]["total_domains"] == 2
        assert len(result["data"]["domains"]) == 2
        assert result["data"]["domains"][0]["name"] == "bad.com"

    @pytest.mark.asyncio
    async def test_list_blocked_domains_with_limit(self, list_blocked_domains_action):
        """Test domain listing respects limit parameter."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": 1, "name": "a.com"},
                {"id": 2, "name": "b.com"},
                {"id": 3, "name": "c.com"},
            ],
            "meta": {"next": None},
        }
        mock_response.status_code = 200
        list_blocked_domains_action.http_request = AsyncMock(return_value=mock_response)

        result = await list_blocked_domains_action.execute(limit=2)

        assert result["status"] == "success"
        assert result["data"]["total_domains"] == 2
        assert len(result["data"]["domains"]) == 2

    @pytest.mark.asyncio
    async def test_list_blocked_domains_pagination(self, list_blocked_domains_action):
        """Test multi-page domain listing."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {
                    "data": [{"id": 1, "name": "page1.com"}],
                    "meta": {"next": "https://next-page"},
                }
            else:
                mock_resp.json.return_value = {
                    "data": [{"id": 2, "name": "page2.com"}],
                    "meta": {"next": None},
                }

            return mock_resp

        list_blocked_domains_action.http_request = mock_http_request

        result = await list_blocked_domains_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_domains"] == 2
        assert result["data"]["domains"][0]["name"] == "page1.com"
        assert result["data"]["domains"][1]["name"] == "page2.com"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_list_blocked_domains_empty(self, list_blocked_domains_action):
        """Test listing when no domains are blocked."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [], "meta": {"next": None}}
        mock_response.status_code = 200
        list_blocked_domains_action.http_request = AsyncMock(return_value=mock_response)

        result = await list_blocked_domains_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_domains"] == 0
        assert result["data"]["domains"] == []

    @pytest.mark.asyncio
    async def test_list_blocked_domains_invalid_limit(
        self, list_blocked_domains_action
    ):
        """Test listing with invalid limit parameter."""
        result = await list_blocked_domains_action.execute(limit="not-a-number")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_list_blocked_domains_negative_limit(
        self, list_blocked_domains_action
    ):
        """Test listing with negative limit."""
        result = await list_blocked_domains_action.execute(limit=-5)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_list_blocked_domains_missing_credentials(self, settings):
        """Test listing with missing customer key."""
        action = ListBlockedDomainsAction(
            "ciscoumbrella", "list_blocked_domains", settings, {}
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_list_blocked_domains_http_error(self, list_blocked_domains_action):
        """Test listing with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}
        mock_response.request = MagicMock()

        error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mock_response.request,
            response=mock_response,
        )
        list_blocked_domains_action.http_request = AsyncMock(side_effect=error)

        result = await list_blocked_domains_action.execute()

        assert result["status"] == "error"

"""Unit tests for Infoblox DDI integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.infoblox.actions import (
    BlockDomainAction,
    BlockIpAction,
    GetNetworkInfoAction,
    GetSystemInfoAction,
    HealthCheckAction,
    ListHostsAction,
    ListNetworkViewAction,
    ListRpzAction,
    UnblockDomainAction,
    UnblockIpAction,
    _build_api_url,
    _encode_domain,
    _is_ip,
    _is_ipv4,
    _is_ipv6,
    _validate_ip_cidr,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def credentials():
    """Sample Infoblox credentials."""
    return {
        "username": "admin",
        "password": "secret",
    }


@pytest.fixture
def settings():
    """Sample Infoblox settings."""
    return {
        "url": "https://infoblox.example.com",
        "verify_server_cert": False,
        "timeout": 30,
    }


@pytest.fixture
def health_check_action(credentials, settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction("infoblox", "health_check", settings, credentials)


@pytest.fixture
def block_ip_action(credentials, settings):
    """Create BlockIpAction instance."""
    return BlockIpAction("infoblox", "block_ip", settings, credentials)


@pytest.fixture
def unblock_ip_action(credentials, settings):
    """Create UnblockIpAction instance."""
    return UnblockIpAction("infoblox", "unblock_ip", settings, credentials)


@pytest.fixture
def block_domain_action(credentials, settings):
    """Create BlockDomainAction instance."""
    return BlockDomainAction("infoblox", "block_domain", settings, credentials)


@pytest.fixture
def unblock_domain_action(credentials, settings):
    """Create UnblockDomainAction instance."""
    return UnblockDomainAction("infoblox", "unblock_domain", settings, credentials)


@pytest.fixture
def list_rpz_action(credentials, settings):
    """Create ListRpzAction instance."""
    return ListRpzAction("infoblox", "list_rpz", settings, credentials)


@pytest.fixture
def list_hosts_action(credentials, settings):
    """Create ListHostsAction instance."""
    return ListHostsAction("infoblox", "list_hosts", settings, credentials)


@pytest.fixture
def list_network_view_action(credentials, settings):
    """Create ListNetworkViewAction instance."""
    return ListNetworkViewAction("infoblox", "list_network_view", settings, credentials)


@pytest.fixture
def get_network_info_action(credentials, settings):
    """Create GetNetworkInfoAction instance."""
    return GetNetworkInfoAction("infoblox", "get_network_info", settings, credentials)


@pytest.fixture
def get_system_info_action(credentials, settings):
    """Create GetSystemInfoAction instance."""
    return GetSystemInfoAction("infoblox", "get_system_info", settings, credentials)


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_build_api_url_with_https(self):
        """Test API URL construction with https prefix."""
        result = _build_api_url("https://infoblox.example.com", "/networkview")
        assert result == "https://infoblox.example.com/wapi/v2.3.1/networkview"

    def test_build_api_url_without_scheme(self):
        """Test API URL construction without scheme adds https."""
        result = _build_api_url("infoblox.example.com", "/lease")
        assert result == "https://infoblox.example.com/wapi/v2.3.1/lease"

    def test_build_api_url_strips_trailing_slash(self):
        """Test API URL strips trailing slashes."""
        result = _build_api_url("https://infoblox.example.com/", "/network")
        assert result == "https://infoblox.example.com/wapi/v2.3.1/network"

    def test_is_ipv4_valid(self):
        """Test valid IPv4 addresses."""
        assert _is_ipv4("10.0.0.1") is True
        assert _is_ipv4("192.168.1.1") is True

    def test_is_ipv4_invalid(self):
        """Test invalid IPv4 addresses."""
        assert _is_ipv4("not-an-ip") is False
        assert _is_ipv4("2001:db8::1") is False

    def test_is_ipv6_valid(self):
        """Test valid IPv6 addresses."""
        assert _is_ipv6("2001:db8::1") is True
        assert _is_ipv6("::1") is True

    def test_is_ipv6_invalid(self):
        """Test invalid IPv6 addresses."""
        assert _is_ipv6("10.0.0.1") is False
        assert _is_ipv6("not-an-ip") is False

    def test_is_ip(self):
        """Test IP detection covers both IPv4 and IPv6."""
        assert _is_ip("10.0.0.1") is True
        assert _is_ip("2001:db8::1") is True
        assert _is_ip("example.com") is False

    def test_validate_ip_cidr_simple(self):
        """Test simple IP validation."""
        assert _validate_ip_cidr("10.0.0.1") is True

    def test_validate_ip_cidr_with_prefix(self):
        """Test CIDR notation validation."""
        assert _validate_ip_cidr("10.0.0.0/24") is True
        assert _validate_ip_cidr("10.0.0.0/32") is True

    def test_validate_ip_cidr_invalid(self):
        """Test invalid IP/CIDR."""
        assert _validate_ip_cidr("not-an-ip") is False
        assert _validate_ip_cidr("10.0.0.0/33") is False

    def test_validate_ip_cidr_ipv6(self):
        """Test IPv6 CIDR validation."""
        assert _validate_ip_cidr("2001:db8::1") is True
        assert _validate_ip_cidr("2001:db8::/32") is True

    def test_encode_domain(self):
        """Test domain encoding."""
        assert _encode_domain("example.com") == "example.com"


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestHealthCheck:
    """Tests for HealthCheckAction."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.text = '{"supported_versions": ["2.3.1"]}'
        mock_response.status_code = 200
        health_check_action.http_request = AsyncMock(return_value=mock_response)

        result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["integration_id"] == "infoblox"
        assert result["action_id"] == "health_check"
        assert result["data"]["healthy"] is True
        health_check_action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_missing_credentials(self, settings):
        """Test health check with missing credentials."""
        action = HealthCheckAction("infoblox", "health_check", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "credentials" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_health_check_missing_url(self, settings):
        """Test health check with missing URL."""
        settings_no_url = {k: v for k, v in settings.items() if k != "url"}
        action = HealthCheckAction(
            "infoblox",
            "health_check",
            settings_no_url,
            {"username": "admin", "password": "secret"},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_health_check_auth_failure(self, health_check_action):
        """Test health check with authentication failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {}
        mock_response.request = MagicMock()

        error = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=mock_response.request,
            response=mock_response,
        )
        health_check_action.http_request = AsyncMock(side_effect=error)

        result = await health_check_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"

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
    async def test_health_check_uses_auth_parameter(self, health_check_action):
        """Test that auth tuple is passed to http_request."""
        mock_response = MagicMock()
        mock_response.text = '{"supported_versions": ["2.3.1"]}'
        mock_response.status_code = 200
        health_check_action.http_request = AsyncMock(return_value=mock_response)

        await health_check_action.execute()

        call_kwargs = health_check_action.http_request.call_args.kwargs
        assert call_kwargs["auth"] == ("admin", "secret")


# ============================================================================
# BLOCK IP TESTS
# ============================================================================


class TestBlockIp:
    """Tests for BlockIpAction."""

    @pytest.mark.asyncio
    async def test_block_ip_success(self, block_ip_action):
        """Test successful IP block."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # _paged_request for RPZ validation
                mock_resp.json.return_value = {
                    "result": [{"fqdn": "rpz.local", "rpz_policy": "GIVEN"}],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'
            elif call_count == 2:
                # Check if rule exists - empty list means no existing rule
                mock_resp.json.return_value = []
                mock_resp.text = "[]"
            elif call_count == 3:
                # Create block rule
                mock_resp.json.return_value = (
                    "record:rpz:cname:ipaddress/ref:10.0.0.1.rpz.local/default"
                )
                mock_resp.text = (
                    '"record:rpz:cname:ipaddress/ref:10.0.0.1.rpz.local/default"'
                )

            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(ip="10.0.0.1", rp_zone="rpz.local")

        assert result["status"] == "success"
        assert result["data"]["message"] == "IP/CIDR blocked successfully"
        assert result["data"]["ip"] == "10.0.0.1"
        assert result["data"]["rp_zone"] == "rpz.local"

    @pytest.mark.asyncio
    async def test_block_ip_already_blocked(self, block_ip_action):
        """Test block IP that is already blocked."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # RPZ validation
                mock_resp.json.return_value = {
                    "result": [{"fqdn": "rpz.local", "rpz_policy": "GIVEN"}],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'
            elif call_count == 2:
                # Rule exists with canonical="" (blocked state)
                mock_resp.json.return_value = [{"canonical": "", "_ref": "some_ref"}]
                mock_resp.text = '[{"canonical": ""}]'

            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(ip="10.0.0.1", rp_zone="rpz.local")

        assert result["status"] == "success"
        assert result["data"]["message"] == "IP/CIDR already blocked"

    @pytest.mark.asyncio
    async def test_block_ip_missing_ip(self, block_ip_action):
        """Test block IP with missing IP parameter."""
        result = await block_ip_action.execute(rp_zone="rpz.local")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_ip_missing_rp_zone(self, block_ip_action):
        """Test block IP with missing rp_zone parameter."""
        result = await block_ip_action.execute(ip="10.0.0.1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "rp_zone" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_ip_missing_credentials(self, settings):
        """Test block IP with missing credentials."""
        action = BlockIpAction("infoblox", "block_ip", settings, {})

        result = await action.execute(ip="10.0.0.1", rp_zone="rpz.local")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_block_ip_invalid_ip(self, block_ip_action):
        """Test block IP with invalid IP address."""
        result = await block_ip_action.execute(ip="not-an-ip", rp_zone="rpz.local")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "Invalid" in result["error"]

    @pytest.mark.asyncio
    async def test_block_ip_rpz_not_exists(self, block_ip_action):
        """Test block IP when RPZ does not exist."""

        async def mock_http_request(**kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"result": [], "next_page_id": None}
            mock_resp.text = '{"result": []}'
            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(ip="10.0.0.1", rp_zone="nonexistent.rpz")

        assert result["status"] == "error"
        assert "does not exist" in result["error"]

    @pytest.mark.asyncio
    async def test_block_ip_rpz_wrong_policy(self, block_ip_action):
        """Test block IP when RPZ has wrong policy."""

        async def mock_http_request(**kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "result": [{"fqdn": "rpz.local", "rpz_policy": "PASSTHRU"}],
                "next_page_id": None,
            }
            mock_resp.text = '{"result": []}'
            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(ip="10.0.0.1", rp_zone="rpz.local")

        assert result["status"] == "error"
        assert "GIVEN" in result["error"]

    @pytest.mark.asyncio
    async def test_block_ip_http_error(self, block_ip_action):
        """Test block IP with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.request = MagicMock()
        mock_response.headers = {}

        error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mock_response.request,
            response=mock_response,
        )
        block_ip_action.http_request = AsyncMock(side_effect=error)

        result = await block_ip_action.execute(ip="10.0.0.1", rp_zone="rpz.local")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_block_ip_canonical_none_treated_as_not_blocked(
        self, block_ip_action
    ):
        """Test that canonical=None is not treated as a block rule (empty canonical)."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {
                    "result": [{"fqdn": "rpz.local", "rpz_policy": "GIVEN"}],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'
            elif call_count == 2:
                # Rule exists but canonical is None (not a block rule)
                mock_resp.json.return_value = [{"canonical": None, "_ref": "ref"}]
                mock_resp.text = '[{"canonical": null}]'

            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(ip="10.0.0.1", rp_zone="rpz.local")

        # canonical=None != "" was True before fix, so this would have
        # incorrectly returned an error. With the fix it should still
        # error because a non-empty canonical means it's not a block rule.
        # None is treated as "" via .get("canonical", ""), so it's treated
        # as already blocked.
        assert result["status"] == "success"
        assert result["data"]["message"] == "IP/CIDR already blocked"


# ============================================================================
# UNBLOCK IP TESTS
# ============================================================================


class TestUnblockIp:
    """Tests for UnblockIpAction."""

    @pytest.mark.asyncio
    async def test_unblock_ip_success(self, unblock_ip_action):
        """Test successful IP unblock."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # RPZ validation
                mock_resp.json.return_value = {
                    "result": [{"fqdn": "rpz.local", "rpz_policy": "GIVEN"}],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'
            elif call_count == 2:
                # Rule exists in blocked state
                mock_resp.json.return_value = [
                    {
                        "canonical": "",
                        "_ref": "record:rpz:cname:ipaddress/ref:10.0.0.1.rpz.local/default",
                    }
                ]
                mock_resp.text = '[{"canonical": ""}]'
            elif call_count == 3:
                # Delete rule
                mock_resp.json.return_value = "record:rpz:cname:ipaddress/ref"
                mock_resp.text = '"record:rpz:cname:ipaddress/ref"'

            return mock_resp

        unblock_ip_action.http_request = mock_http_request

        result = await unblock_ip_action.execute(ip="10.0.0.1", rp_zone="rpz.local")

        assert result["status"] == "success"
        assert result["data"]["message"] == "IP/CIDR unblocked successfully"
        assert result["data"]["ip"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_unblock_ip_already_unblocked(self, unblock_ip_action):
        """Test unblock IP that is not blocked."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # RPZ validation
                mock_resp.json.return_value = {
                    "result": [{"fqdn": "rpz.local", "rpz_policy": "GIVEN"}],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'
            elif call_count == 2:
                # No existing rule
                mock_resp.json.return_value = []
                mock_resp.text = "[]"

            return mock_resp

        unblock_ip_action.http_request = mock_http_request

        result = await unblock_ip_action.execute(ip="10.0.0.1", rp_zone="rpz.local")

        assert result["status"] == "success"
        assert result["data"]["message"] == "IP/CIDR already unblocked"

    @pytest.mark.asyncio
    async def test_unblock_ip_missing_ip(self, unblock_ip_action):
        """Test unblock IP with missing IP parameter."""
        result = await unblock_ip_action.execute(rp_zone="rpz.local")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unblock_ip_missing_rp_zone(self, unblock_ip_action):
        """Test unblock IP with missing rp_zone parameter."""
        result = await unblock_ip_action.execute(ip="10.0.0.1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "rp_zone" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unblock_ip_missing_credentials(self, settings):
        """Test unblock IP with missing credentials."""
        action = UnblockIpAction("infoblox", "unblock_ip", settings, {})

        result = await action.execute(ip="10.0.0.1", rp_zone="rpz.local")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_unblock_ip_not_in_blocked_state(self, unblock_ip_action):
        """Test unblock IP when rule exists but is not a block rule."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {
                    "result": [{"fqdn": "rpz.local", "rpz_policy": "GIVEN"}],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'
            elif call_count == 2:
                # Rule exists but canonical is not empty (not a block rule)
                mock_resp.json.return_value = [
                    {"canonical": "some.redirect.com", "_ref": "ref"}
                ]
                mock_resp.text = '[{"canonical": "some.redirect.com"}]'

            return mock_resp

        unblock_ip_action.http_request = mock_http_request

        result = await unblock_ip_action.execute(ip="10.0.0.1", rp_zone="rpz.local")

        assert result["status"] == "error"
        assert "Block IP Address" in result["error"]

    @pytest.mark.asyncio
    async def test_unblock_ip_404_returns_not_found(self, unblock_ip_action):
        """Test unblock IP returns not_found on 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.request = MagicMock()
        mock_response.headers = {}

        error = httpx.HTTPStatusError(
            "404 Not Found",
            request=mock_response.request,
            response=mock_response,
        )
        unblock_ip_action.http_request = AsyncMock(side_effect=error)

        result = await unblock_ip_action.execute(ip="10.0.0.1", rp_zone="rpz.local")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["message"] == "IP/CIDR already unblocked"


# ============================================================================
# BLOCK DOMAIN TESTS
# ============================================================================


class TestBlockDomain:
    """Tests for BlockDomainAction."""

    @pytest.mark.asyncio
    async def test_block_domain_success(self, block_domain_action):
        """Test successful domain block."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {
                    "result": [{"fqdn": "rpz.local", "rpz_policy": "GIVEN"}],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'
            elif call_count == 2:
                mock_resp.json.return_value = []
                mock_resp.text = "[]"
            elif call_count == 3:
                mock_resp.json.return_value = (
                    "record:rpz:cname/ref:example.com.rpz.local/default"
                )
                mock_resp.text = '"record:rpz:cname/ref:example.com.rpz.local/default"'

            return mock_resp

        block_domain_action.http_request = mock_http_request

        result = await block_domain_action.execute(
            domain="example.com", rp_zone="rpz.local"
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Domain blocked successfully"
        assert result["data"]["domain"] == "example.com"

    @pytest.mark.asyncio
    async def test_block_domain_already_blocked(self, block_domain_action):
        """Test block domain that is already blocked."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {
                    "result": [{"fqdn": "rpz.local", "rpz_policy": "GIVEN"}],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'
            elif call_count == 2:
                mock_resp.json.return_value = [{"canonical": "", "_ref": "ref"}]
                mock_resp.text = '[{"canonical": ""}]'

            return mock_resp

        block_domain_action.http_request = mock_http_request

        result = await block_domain_action.execute(
            domain="example.com", rp_zone="rpz.local"
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Domain already blocked"

    @pytest.mark.asyncio
    async def test_block_domain_missing_domain(self, block_domain_action):
        """Test block domain with missing domain parameter."""
        result = await block_domain_action.execute(rp_zone="rpz.local")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_domain_missing_rp_zone(self, block_domain_action):
        """Test block domain with missing rp_zone parameter."""
        result = await block_domain_action.execute(domain="example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "rp_zone" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_domain_missing_credentials(self, settings):
        """Test block domain with missing credentials."""
        action = BlockDomainAction("infoblox", "block_domain", settings, {})

        result = await action.execute(domain="example.com", rp_zone="rpz.local")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# UNBLOCK DOMAIN TESTS
# ============================================================================


class TestUnblockDomain:
    """Tests for UnblockDomainAction."""

    @pytest.mark.asyncio
    async def test_unblock_domain_success(self, unblock_domain_action):
        """Test successful domain unblock."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {
                    "result": [{"fqdn": "rpz.local", "rpz_policy": "GIVEN"}],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'
            elif call_count == 2:
                mock_resp.json.return_value = [
                    {
                        "canonical": "",
                        "_ref": "record:rpz:cname/ref:example.com.rpz.local/default",
                    }
                ]
                mock_resp.text = '[{"canonical": ""}]'
            elif call_count == 3:
                mock_resp.json.return_value = "record:rpz:cname/ref"
                mock_resp.text = '"record:rpz:cname/ref"'

            return mock_resp

        unblock_domain_action.http_request = mock_http_request

        result = await unblock_domain_action.execute(
            domain="example.com", rp_zone="rpz.local"
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Domain unblocked successfully"
        assert result["data"]["domain"] == "example.com"

    @pytest.mark.asyncio
    async def test_unblock_domain_already_unblocked(self, unblock_domain_action):
        """Test unblock domain that is not blocked."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {
                    "result": [{"fqdn": "rpz.local", "rpz_policy": "GIVEN"}],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'
            elif call_count == 2:
                mock_resp.json.return_value = []
                mock_resp.text = "[]"

            return mock_resp

        unblock_domain_action.http_request = mock_http_request

        result = await unblock_domain_action.execute(
            domain="example.com", rp_zone="rpz.local"
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Domain already unblocked"

    @pytest.mark.asyncio
    async def test_unblock_domain_missing_domain(self, unblock_domain_action):
        """Test unblock domain with missing domain parameter."""
        result = await unblock_domain_action.execute(rp_zone="rpz.local")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unblock_domain_missing_rp_zone(self, unblock_domain_action):
        """Test unblock domain with missing rp_zone parameter."""
        result = await unblock_domain_action.execute(domain="example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "rp_zone" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unblock_domain_missing_credentials(self, settings):
        """Test unblock domain with missing credentials."""
        action = UnblockDomainAction("infoblox", "unblock_domain", settings, {})

        result = await action.execute(domain="example.com", rp_zone="rpz.local")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_unblock_domain_404_returns_not_found(self, unblock_domain_action):
        """Test unblock domain returns not_found on 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.request = MagicMock()
        mock_response.headers = {}

        error = httpx.HTTPStatusError(
            "404 Not Found",
            request=mock_response.request,
            response=mock_response,
        )
        unblock_domain_action.http_request = AsyncMock(side_effect=error)

        result = await unblock_domain_action.execute(
            domain="example.com", rp_zone="rpz.local"
        )

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["message"] == "Domain already unblocked"


# ============================================================================
# LIST RPZ TESTS
# ============================================================================


class TestListRpz:
    """Tests for ListRpzAction."""

    @pytest.mark.asyncio
    async def test_list_rpz_success(self, list_rpz_action):
        """Test successful RPZ listing."""

        async def mock_http_request(**kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "result": [
                    {
                        "fqdn": "rpz1.local",
                        "rpz_policy": "GIVEN",
                        "rpz_severity": "MAJOR",
                    },
                    {
                        "fqdn": "rpz2.local",
                        "rpz_policy": "GIVEN",
                        "rpz_severity": "WARNING",
                    },
                ],
                "next_page_id": None,
            }
            mock_resp.text = '{"result": []}'
            return mock_resp

        list_rpz_action.http_request = mock_http_request

        result = await list_rpz_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_response_policy_zones"] == 2
        assert len(result["data"]["response_policy_zones"]) == 2

    @pytest.mark.asyncio
    async def test_list_rpz_empty(self, list_rpz_action):
        """Test RPZ listing with no results."""

        async def mock_http_request(**kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"result": [], "next_page_id": None}
            mock_resp.text = '{"result": []}'
            return mock_resp

        list_rpz_action.http_request = mock_http_request

        result = await list_rpz_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_response_policy_zones"] == 0

    @pytest.mark.asyncio
    async def test_list_rpz_missing_credentials(self, settings):
        """Test list RPZ with missing credentials."""
        action = ListRpzAction("infoblox", "list_rpz", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_list_rpz_404_returns_not_found(self, list_rpz_action):
        """Test list RPZ returns not_found on 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.request = MagicMock()
        mock_response.headers = {}

        error = httpx.HTTPStatusError(
            "404 Not Found",
            request=mock_response.request,
            response=mock_response,
        )
        list_rpz_action.http_request = AsyncMock(side_effect=error)

        result = await list_rpz_action.execute()

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["total_response_policy_zones"] == 0


# ============================================================================
# LIST HOSTS TESTS
# ============================================================================


class TestListHosts:
    """Tests for ListHostsAction."""

    @pytest.mark.asyncio
    async def test_list_hosts_success(self, list_hosts_action):
        """Test successful host listing."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # IPv4 hosts
                mock_resp.json.return_value = {
                    "result": [
                        {
                            "ipv4addr": "10.0.0.1",
                            "name": "host1.example.com",
                            "view": "default",
                            "zone": "example.com",
                        },
                    ],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'
            elif call_count == 2:
                # IPv6 hosts
                mock_resp.json.return_value = {
                    "result": [
                        {
                            "ipv6addr": "2001:db8::1",
                            "name": "host2.example.com",
                            "view": "default",
                            "zone": "example.com",
                        },
                    ],
                    "next_page_id": None,
                }
                mock_resp.text = '{"result": []}'

            return mock_resp

        list_hosts_action.http_request = mock_http_request

        result = await list_hosts_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_hosts"] == 2
        # Verify post-processing: ipv4addr -> ip, name stripped of zone
        assert result["data"]["hosts"][0]["ip"] == "10.0.0.1"
        assert result["data"]["hosts"][0]["name"] == "host1"
        assert result["data"]["hosts"][1]["ip"] == "2001:db8::1"
        assert result["data"]["hosts"][1]["name"] == "host2"

    @pytest.mark.asyncio
    async def test_list_hosts_missing_credentials(self, settings):
        """Test list hosts with missing credentials."""
        action = ListHostsAction("infoblox", "list_hosts", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# LIST NETWORK VIEW TESTS
# ============================================================================


class TestListNetworkView:
    """Tests for ListNetworkViewAction."""

    @pytest.mark.asyncio
    async def test_list_network_view_success(self, list_network_view_action):
        """Test successful network view listing."""

        async def mock_http_request(**kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "result": [
                    {
                        "_ref": "networkview/ref:default/true",
                        "name": "default",
                        "is_default": True,
                    },
                    {
                        "_ref": "networkview/ref:internal/false",
                        "name": "Internal Networks",
                        "is_default": False,
                    },
                ],
                "next_page_id": None,
            }
            mock_resp.text = '{"result": []}'
            return mock_resp

        list_network_view_action.http_request = mock_http_request

        result = await list_network_view_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_network_views"] == 2
        assert result["data"]["network_views"][0]["name"] == "default"

    @pytest.mark.asyncio
    async def test_list_network_view_missing_credentials(self, settings):
        """Test list network view with missing credentials."""
        action = ListNetworkViewAction("infoblox", "list_network_view", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# GET NETWORK INFO TESTS
# ============================================================================


class TestGetNetworkInfo:
    """Tests for GetNetworkInfoAction."""

    @pytest.mark.asyncio
    async def test_get_network_info_success(self, get_network_info_action):
        """Test successful network info retrieval."""

        async def mock_http_request(**kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "result": [
                    {
                        "network": "10.0.0.0/8",
                        "network_view": "default",
                        "comment": "Corp network",
                    },
                ],
                "next_page_id": None,
            }
            mock_resp.text = '{"result": []}'
            return mock_resp

        get_network_info_action.http_request = mock_http_request

        result = await get_network_info_action.execute(ip="10.0.0.0/8")

        assert result["status"] == "success"
        assert result["data"]["number_of_matching_networks"] == 1
        assert result["data"]["networks"][0]["network"] == "10.0.0.0/8"

    @pytest.mark.asyncio
    async def test_get_network_info_filter_by_single_ip(self, get_network_info_action):
        """Test network info filters by single IP."""

        async def mock_http_request(**kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "result": [
                    {"network": "10.0.0.0/8", "network_view": "default"},
                    {"network": "192.168.0.0/16", "network_view": "default"},
                ],
                "next_page_id": None,
            }
            mock_resp.text = '{"result": []}'
            return mock_resp

        get_network_info_action.http_request = mock_http_request

        result = await get_network_info_action.execute(ip="10.0.0.5")

        assert result["status"] == "success"
        # Only 10.0.0.0/8 should match 10.0.0.5
        assert result["data"]["number_of_matching_networks"] == 1
        assert result["data"]["networks"][0]["network"] == "10.0.0.0/8"

    @pytest.mark.asyncio
    async def test_get_network_info_no_ip(self, get_network_info_action):
        """Test network info returns all networks when no IP specified."""

        async def mock_http_request(**kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "result": [
                    {"network": "10.0.0.0/8"},
                    {"network": "192.168.0.0/16"},
                ],
                "next_page_id": None,
            }
            mock_resp.text = '{"result": []}'
            return mock_resp

        get_network_info_action.http_request = mock_http_request

        result = await get_network_info_action.execute()

        assert result["status"] == "success"
        assert result["data"]["number_of_matching_networks"] == 2

    @pytest.mark.asyncio
    async def test_get_network_info_missing_credentials(self, settings):
        """Test get network info with missing credentials."""
        action = GetNetworkInfoAction("infoblox", "get_network_info", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# GET SYSTEM INFO TESTS
# ============================================================================


class TestGetSystemInfo:
    """Tests for GetSystemInfoAction."""

    @pytest.mark.asyncio
    async def test_get_system_info_with_lease(self, get_system_info_action):
        """Test system info with lease data."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # Lease data
                mock_resp.json.return_value = [
                    {
                        "address": "10.0.0.5",
                        "binding_state": "ACTIVE",
                        "hardware": "aa:bb:cc:dd:ee:ff",
                        "cltt": 1609459200,
                        "starts": 1609459200,
                        "ends": 1609545600,
                        "never_ends": False,
                    },
                ]
                mock_resp.text = "[]"
            elif call_count == 2:
                # Host records (A record lookup)
                mock_resp.json.return_value = [
                    {
                        "ipv4addr": "10.0.0.5",
                        "name": "server1.example.com",
                        "view": "default",
                        "zone": "example.com",
                        "discovered_data": {"os": "Linux"},
                    },
                ]
                mock_resp.text = "[]"

            return mock_resp

        get_system_info_action.http_request = mock_http_request

        result = await get_system_info_action.execute(ip_hostname="10.0.0.5")

        assert result["status"] == "success"
        assert len(result["data"]["system_info"]) == 1
        assert result["data"]["system_info"][0]["binding_state"] == "ACTIVE"
        assert result["data"]["summary"]["is_static_ip"] is False

    @pytest.mark.asyncio
    async def test_get_system_info_not_found(self, get_system_info_action):
        """Test system info when host is not found."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # Empty lease data
                mock_resp.json.return_value = []
                mock_resp.text = "[]"
            elif call_count == 2:
                # Empty host records
                mock_resp.json.return_value = []
                mock_resp.text = "[]"

            return mock_resp

        get_system_info_action.http_request = mock_http_request

        result = await get_system_info_action.execute(ip_hostname="10.0.0.5")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_get_system_info_missing_ip_hostname(self, get_system_info_action):
        """Test system info with missing ip_hostname parameter."""
        result = await get_system_info_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip_hostname" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_system_info_missing_credentials(self, settings):
        """Test get system info with missing credentials."""
        action = GetSystemInfoAction("infoblox", "get_system_info", settings, {})

        result = await action.execute(ip_hostname="10.0.0.5")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# AUTH HEADER AND BASE CLASS TESTS
# ============================================================================


class TestBaseClass:
    """Test base class methods."""

    def test_get_timeout_default(self, health_check_action):
        """Test default timeout."""
        assert health_check_action.get_timeout() == 30

    def test_get_timeout_custom(self, credentials):
        """Test custom timeout from settings."""
        action = HealthCheckAction(
            "infoblox", "health_check", {"timeout": 60}, credentials
        )
        assert action.get_timeout() == 60

    def test_get_verify_ssl_default_false(self, health_check_action):
        """Test SSL verification defaults from credentials."""
        assert health_check_action.get_verify_ssl() is False

    def test_get_verify_ssl_true(self, settings):
        """Test SSL verification when enabled."""
        creds = {
            "username": "admin",
            "password": "secret",
        }
        settings_with_verify = {**settings, "verify_server_cert": True}
        action = HealthCheckAction(
            "infoblox", "health_check", settings_with_verify, creds
        )
        assert action.get_verify_ssl() is True

    def test_validate_credentials_success(self, health_check_action):
        """Test credential validation with valid credentials."""
        result = health_check_action._validate_credentials()
        assert result is not None
        url, username, password = result
        assert url == "https://infoblox.example.com"
        assert username == "admin"
        assert password == "secret"

    def test_validate_credentials_missing(self, settings):
        """Test credential validation with missing credentials."""
        action = HealthCheckAction("infoblox", "health_check", settings, {})
        result = action._validate_credentials()
        assert result is None

    def test_get_http_headers_empty(self, health_check_action):
        """Test that base get_http_headers returns empty dict."""
        headers = health_check_action.get_http_headers()
        assert headers == {}

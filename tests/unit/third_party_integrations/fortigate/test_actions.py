"""Unit tests for FortiGate Firewall integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.fortigate.actions import (
    BlockIpAction,
    HealthCheckAction,
    ListPoliciesAction,
    PolicyError,
    UnblockIpAction,
    _build_address_name,
    _get_base_url,
    _get_net_mask,
    _get_net_size,
    _parse_ip_address,
    _validate_ip,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def credentials():
    """Sample FortiGate credentials."""
    return {
        "api_key": "test-fortigate-key",
    }


@pytest.fixture
def settings():
    """Sample FortiGate settings."""
    return {
        "url": "https://fortigate.example.com",
        "verify_server_cert": False,
        "vdom": "root",
        "timeout": 30,
    }


@pytest.fixture
def health_check_action(credentials, settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction("fortigate", "health_check", settings, credentials)


@pytest.fixture
def block_ip_action(credentials, settings):
    """Create BlockIpAction instance."""
    return BlockIpAction("fortigate", "block_ip", settings, credentials)


@pytest.fixture
def unblock_ip_action(credentials, settings):
    """Create UnblockIpAction instance."""
    return UnblockIpAction("fortigate", "unblock_ip", settings, credentials)


@pytest.fixture
def list_policies_action(credentials, settings):
    """Create ListPoliciesAction instance."""
    return ListPoliciesAction("fortigate", "list_policies", settings, credentials)


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_get_base_url_with_https(self):
        """Test base URL construction with https prefix."""
        assert (
            _get_base_url("https://forti.example.com")
            == "https://forti.example.com/api/v2"
        )

    def test_get_base_url_without_scheme(self):
        """Test base URL construction without scheme adds https."""
        assert _get_base_url("forti.example.com") == "https://forti.example.com/api/v2"

    def test_get_base_url_strips_trailing_slash(self):
        """Test base URL strips trailing slashes."""
        assert (
            _get_base_url("https://forti.example.com/")
            == "https://forti.example.com/api/v2"
        )

    def test_get_net_mask_32(self):
        """Test /32 CIDR to subnet mask."""
        assert _get_net_mask(32) == "255.255.255.255"

    def test_get_net_mask_24(self):
        """Test /24 CIDR to subnet mask."""
        assert _get_net_mask(24) == "255.255.255.0"

    def test_get_net_mask_16(self):
        """Test /16 CIDR to subnet mask."""
        assert _get_net_mask(16) == "255.255.0.0"

    def test_get_net_size_from_mask(self):
        """Test subnet mask to CIDR conversion."""
        assert _get_net_size("255.255.255.0") == 24
        assert _get_net_size("255.255.0.0") == 16
        assert _get_net_size("255.255.255.255") == 32

    def test_parse_ip_simple(self):
        """Test parsing simple IP address."""
        ip, net_size, net_mask = _parse_ip_address("10.0.0.1")
        assert ip == "10.0.0.1"
        assert net_size == 32
        assert net_mask == "255.255.255.255"

    def test_parse_ip_cidr(self):
        """Test parsing CIDR notation."""
        ip, net_size, net_mask = _parse_ip_address("10.0.0.0/24")
        assert ip == "10.0.0.0"
        assert net_size == 24
        assert net_mask == "255.255.255.0"

    def test_parse_ip_with_mask(self):
        """Test parsing IP with subnet mask."""
        ip, net_size, net_mask = _parse_ip_address("10.0.0.0 255.255.0.0")
        assert ip == "10.0.0.0"
        assert net_size == 16
        assert net_mask == "255.255.0.0"

    def test_validate_ip_valid(self):
        """Test valid IP addresses."""
        assert _validate_ip("10.0.0.1") is True
        assert _validate_ip("192.168.1.0/24") is True
        assert _validate_ip("10.0.0.0 255.255.0.0") is True

    def test_validate_ip_invalid(self):
        """Test invalid IP addresses."""
        assert _validate_ip("not-an-ip") is False
        assert _validate_ip("999.999.999.999") is False

    def test_build_address_name(self):
        """Test address name matches the upstream convention."""
        name = _build_address_name("10.0.0.1", 32)
        assert name == "Analysi Addr 10.0.0.1_32"

        name = _build_address_name("192.168.1.0", 24)
        assert name == "Analysi Addr 192.168.1.0_24"


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestHealthCheck:
    """Tests for HealthCheckAction."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.text = '{"results": []}'
        mock_response.status_code = 200
        health_check_action.http_request = AsyncMock(return_value=mock_response)

        result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["integration_id"] == "fortigate"
        assert result["action_id"] == "health_check"
        assert result["data"]["healthy"] is True
        health_check_action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_missing_api_key(self, settings):
        """Test health check with missing API key."""
        action = HealthCheckAction(
            "fortigate",
            "health_check",
            settings,
            {},  # no api_key
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert (
            "api_key" in result["error"].lower()
            or "credentials" in result["error"].lower()
        )

    @pytest.mark.asyncio
    async def test_health_check_missing_url(self, settings):
        """Test health check with missing URL."""
        settings_no_url = {k: v for k, v in settings.items() if k != "url"}
        action = HealthCheckAction(
            "fortigate",
            "health_check",
            settings_no_url,
            {"api_key": "test-key"},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "url" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_health_check_auth_failure(self, health_check_action):
        """Test health check with authentication failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {}
        mock_response.request = MagicMock()
        mock_response.json.return_value = {"error": "Unauthorized"}

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
    async def test_health_check_empty_response(self, health_check_action):
        """Test health check with empty response."""
        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.status_code = 200
        health_check_action.http_request = AsyncMock(return_value=mock_response)

        result = await health_check_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_health_check_uses_vdom(self, health_check_action):
        """Test health check passes vdom parameter."""
        mock_response = MagicMock()
        mock_response.text = '{"results": []}'
        mock_response.status_code = 200
        health_check_action.http_request = AsyncMock(return_value=mock_response)

        await health_check_action.execute()

        call_kwargs = health_check_action.http_request.call_args.kwargs
        assert call_kwargs["params"] == {"vdom": "root"}


# ============================================================================
# BLOCK IP TESTS
# ============================================================================


class TestBlockIp:
    """Tests for BlockIpAction."""

    @pytest.mark.asyncio
    async def test_block_ip_success(self, block_ip_action):
        """Test successful IP block (address does not exist, create + block)."""
        # Mock sequence: check_address (404), create_address, get_policy, check_blocked (404), block
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # Check address exists: return 404
                mock_resp_404 = MagicMock()
                mock_resp_404.status_code = 404
                mock_resp_404.request = MagicMock()
                mock_resp_404.headers = {}
                raise httpx.HTTPStatusError(
                    "404",
                    request=mock_resp_404.request,
                    response=mock_resp_404,
                )
            if call_count == 2:
                # Create address: success
                mock_resp.json.return_value = {
                    "results": {"mkey": "Analysi Addr 10.0.0.1_32"}
                }
            elif call_count == 3:
                # Get policy: success
                mock_resp.json.return_value = {
                    "results": [
                        {"policyid": 5, "name": "deny-policy", "action": "deny"}
                    ]
                }
            elif call_count == 4:
                # Check if already blocked: 404 (not blocked)
                mock_resp_404 = MagicMock()
                mock_resp_404.status_code = 404
                mock_resp_404.request = MagicMock()
                mock_resp_404.headers = {}
                raise httpx.HTTPStatusError(
                    "404",
                    request=mock_resp_404.request,
                    response=mock_resp_404,
                )
            elif call_count == 5:
                # Block IP: success
                mock_resp.json.return_value = {
                    "results": {"mkey": "Analysi Addr 10.0.0.1_32"}
                }

            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(
            ip="10.0.0.1",
            policy="deny-policy",
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "IP blocked successfully"
        assert result["data"]["ip"] == "10.0.0.1"
        assert result["data"]["policy"] == "deny-policy"
        assert call_count == 5

    @pytest.mark.asyncio
    async def test_block_ip_already_blocked(self, block_ip_action):
        """Test block IP when address is already blocked."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # Check address exists: found
                mock_resp.json.return_value = {
                    "results": [{"name": "Analysi Addr 10.0.0.1_32"}]
                }
            elif call_count == 2:
                # Get policy
                mock_resp.json.return_value = {
                    "results": [
                        {"policyid": 5, "name": "deny-policy", "action": "deny"}
                    ]
                }
            elif call_count == 3:
                # Check if blocked: already blocked
                mock_resp.json.return_value = {
                    "results": [{"name": "Analysi Addr 10.0.0.1_32"}]
                }

            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(
            ip="10.0.0.1",
            policy="deny-policy",
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "IP is already blocked"
        assert call_count == 3  # No block call needed

    @pytest.mark.asyncio
    async def test_block_ip_missing_ip(self, block_ip_action):
        """Test block IP with missing IP parameter."""
        result = await block_ip_action.execute(policy="deny-policy")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_ip_missing_policy(self, block_ip_action):
        """Test block IP with missing policy parameter."""
        result = await block_ip_action.execute(ip="10.0.0.1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "policy" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_ip_missing_credentials(self, settings):
        """Test block IP with missing credentials."""
        action = BlockIpAction("fortigate", "block_ip", settings, {})

        result = await action.execute(ip="10.0.0.1", policy="deny-policy")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_block_ip_invalid_ip(self, block_ip_action):
        """Test block IP with invalid IP address."""
        result = await block_ip_action.execute(
            ip="not-an-ip",
            policy="deny-policy",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "Invalid IP" in result["error"]

    @pytest.mark.asyncio
    async def test_block_ip_invalid_address_type(self, block_ip_action):
        """Test block IP with invalid address type."""
        result = await block_ip_action.execute(
            ip="10.0.0.1",
            policy="deny-policy",
            address_type="invalid",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "address type" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_ip_policy_not_deny(self, block_ip_action):
        """Test block IP when policy action is not deny."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # Address exists
                mock_resp.json.return_value = {
                    "results": [{"name": "Analysi Addr 10.0.0.1_32"}]
                }
            elif call_count == 2:
                # Policy has "allow" action, not "deny"
                mock_resp.json.return_value = {
                    "results": [
                        {"policyid": 5, "name": "allow-policy", "action": "allow"}
                    ]
                }

            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(
            ip="10.0.0.1",
            policy="allow-policy",
        )

        assert result["status"] == "error"
        assert "deny" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_ip_cidr_notation(self, block_ip_action):
        """Test block IP with CIDR notation."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # Address exists
                mock_resp.json.return_value = {
                    "results": [{"name": "Analysi Addr 192.168.1.0_24"}]
                }
            elif call_count == 2:
                mock_resp.json.return_value = {
                    "results": [
                        {"policyid": 5, "name": "deny-policy", "action": "deny"}
                    ]
                }
            elif call_count == 3:
                # Already blocked
                mock_resp.json.return_value = {
                    "results": [{"name": "Analysi Addr 192.168.1.0_24"}]
                }

            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(
            ip="192.168.1.0/24",
            policy="deny-policy",
        )

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_block_ip_srcaddr_type(self, block_ip_action):
        """Test block IP as source address."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {"results": [{"name": "test"}]}
            elif call_count == 2:
                mock_resp.json.return_value = {
                    "results": [
                        {"policyid": 5, "name": "deny-policy", "action": "deny"}
                    ]
                }
            elif call_count == 3:
                mock_resp.json.return_value = {"results": [{"name": "test"}]}

            return mock_resp

        block_ip_action.http_request = mock_http_request

        result = await block_ip_action.execute(
            ip="10.0.0.1",
            policy="deny-policy",
            address_type="srcaddr",
        )

        assert result["status"] == "success"


# ============================================================================
# UNBLOCK IP TESTS
# ============================================================================


class TestUnblockIp:
    """Tests for UnblockIpAction."""

    @pytest.mark.asyncio
    async def test_unblock_ip_success(self, unblock_ip_action):
        """Test successful IP unblock."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # Address exists
                mock_resp.json.return_value = {
                    "results": [{"name": "Analysi Addr 10.0.0.1_32"}]
                }
            elif call_count == 2:
                # Get policy
                mock_resp.json.return_value = {
                    "results": [
                        {"policyid": 5, "name": "deny-policy", "action": "deny"}
                    ]
                }
            elif call_count == 3:
                # Address is in policy
                mock_resp.json.return_value = {
                    "results": [{"name": "Analysi Addr 10.0.0.1_32"}]
                }
            elif call_count == 4:
                # Delete success
                mock_resp.json.return_value = {
                    "results": {"mkey": "Analysi Addr 10.0.0.1_32"}
                }

            return mock_resp

        unblock_ip_action.http_request = mock_http_request

        result = await unblock_ip_action.execute(
            ip="10.0.0.1",
            policy="deny-policy",
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "IP unblocked successfully"
        assert result["data"]["ip"] == "10.0.0.1"
        assert call_count == 4

    @pytest.mark.asyncio
    async def test_unblock_ip_already_unblocked(self, unblock_ip_action):
        """Test unblock IP that is not in the policy."""
        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                # Address exists
                mock_resp.json.return_value = {
                    "results": [{"name": "Analysi Addr 10.0.0.1_32"}]
                }
            elif call_count == 2:
                # Get policy
                mock_resp.json.return_value = {
                    "results": [
                        {"policyid": 5, "name": "deny-policy", "action": "deny"}
                    ]
                }
            elif call_count == 3:
                # Not in policy (404)
                mock_resp_404 = MagicMock()
                mock_resp_404.status_code = 404
                mock_resp_404.request = MagicMock()
                mock_resp_404.headers = {}
                raise httpx.HTTPStatusError(
                    "404",
                    request=mock_resp_404.request,
                    response=mock_resp_404,
                )

            return mock_resp

        unblock_ip_action.http_request = mock_http_request

        result = await unblock_ip_action.execute(
            ip="10.0.0.1",
            policy="deny-policy",
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "IP is already unblocked"

    @pytest.mark.asyncio
    async def test_unblock_ip_address_not_found(self, unblock_ip_action):
        """Test unblock IP when address object does not exist."""

        async def mock_http_request(url, **kwargs):
            mock_resp_404 = MagicMock()
            mock_resp_404.status_code = 404
            mock_resp_404.request = MagicMock()
            mock_resp_404.headers = {}
            raise httpx.HTTPStatusError(
                "404",
                request=mock_resp_404.request,
                response=mock_resp_404,
            )

        unblock_ip_action.http_request = mock_http_request

        result = await unblock_ip_action.execute(
            ip="10.0.0.1",
            policy="deny-policy",
        )

        assert result["status"] == "error"
        assert "Address does not exist" in result["error"]

    @pytest.mark.asyncio
    async def test_unblock_ip_missing_ip(self, unblock_ip_action):
        """Test unblock IP with missing IP parameter."""
        result = await unblock_ip_action.execute(policy="deny-policy")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unblock_ip_missing_policy(self, unblock_ip_action):
        """Test unblock IP with missing policy parameter."""
        result = await unblock_ip_action.execute(ip="10.0.0.1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "policy" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unblock_ip_missing_credentials(self, settings):
        """Test unblock IP with missing credentials."""
        action = UnblockIpAction("fortigate", "unblock_ip", settings, {})

        result = await action.execute(ip="10.0.0.1", policy="deny-policy")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_unblock_ip_invalid_address_type(self, unblock_ip_action):
        """Test unblock IP with invalid address type."""
        result = await unblock_ip_action.execute(
            ip="10.0.0.1",
            policy="deny-policy",
            address_type="bad_type",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# LIST POLICIES TESTS
# ============================================================================


class TestListPolicies:
    """Tests for ListPoliciesAction."""

    @pytest.mark.asyncio
    async def test_list_policies_success(self, list_policies_action):
        """Test successful policy listing."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"policyid": 1, "name": "allow-all", "action": "allow"},
                {"policyid": 2, "name": "deny-bad", "action": "deny"},
            ]
        }
        list_policies_action.http_request = AsyncMock(return_value=mock_response)

        result = await list_policies_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_policies"] == 2
        assert len(result["data"]["policies"]) == 2
        assert result["data"]["policies"][0]["name"] == "allow-all"
        assert result["data"]["policies"][1]["name"] == "deny-bad"

    @pytest.mark.asyncio
    async def test_list_policies_empty(self, list_policies_action):
        """Test listing policies with no results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        list_policies_action.http_request = AsyncMock(return_value=mock_response)

        result = await list_policies_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_policies"] == 0
        assert result["data"]["policies"] == []

    @pytest.mark.asyncio
    async def test_list_policies_with_limit(self, list_policies_action):
        """Test listing policies with limit."""
        policies = [{"policyid": i, "name": f"policy-{i}"} for i in range(5)]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": policies}
        list_policies_action.http_request = AsyncMock(return_value=mock_response)

        result = await list_policies_action.execute(limit=3)

        assert result["status"] == "success"
        assert result["data"]["total_policies"] == 3
        assert len(result["data"]["policies"]) == 3

    @pytest.mark.asyncio
    async def test_list_policies_with_vdom(self, list_policies_action):
        """Test listing policies with specific vdom."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        list_policies_action.http_request = AsyncMock(return_value=mock_response)

        await list_policies_action.execute(vdom="custom-vdom")

        call_kwargs = list_policies_action.http_request.call_args.kwargs
        assert call_kwargs["params"]["vdom"] == "custom-vdom"

    @pytest.mark.asyncio
    async def test_list_policies_missing_credentials(self, settings):
        """Test list policies with missing credentials."""
        action = ListPoliciesAction("fortigate", "list_policies", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_list_policies_invalid_limit(self, list_policies_action):
        """Test list policies with invalid limit value."""
        result = await list_policies_action.execute(limit="abc")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_list_policies_zero_limit(self, list_policies_action):
        """Test list policies with zero limit."""
        result = await list_policies_action.execute(limit=0)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_list_policies_http_error(self, list_policies_action):
        """Test list policies with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.request = MagicMock()
        mock_response.headers = {}

        error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mock_response.request,
            response=mock_response,
        )
        list_policies_action.http_request = AsyncMock(side_effect=error)

        result = await list_policies_action.execute()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_list_policies_pagination(self, list_policies_action):
        """Test policy listing with pagination across multiple pages."""
        page1_policies = [{"policyid": i, "name": f"policy-{i}"} for i in range(100)]
        page2_policies = [
            {"policyid": i, "name": f"policy-{i}"} for i in range(100, 150)
        ]

        call_count = 0

        async def mock_http_request(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if call_count == 1:
                mock_resp.json.return_value = {"results": page1_policies}
            elif call_count == 2:
                mock_resp.json.return_value = {"results": page2_policies}
            else:
                mock_resp.json.return_value = {"results": []}

            return mock_resp

        list_policies_action.http_request = mock_http_request

        result = await list_policies_action.execute(limit=200)

        assert result["status"] == "success"
        assert result["data"]["total_policies"] == 150
        assert call_count >= 2


# ============================================================================
# AUTH HEADER TESTS
# ============================================================================


class TestAuthHeaders:
    """Test that get_http_headers returns correct auth headers."""

    def test_health_check_headers_with_api_key(self, health_check_action):
        """Test Bearer auth header is set."""
        headers = health_check_action.get_http_headers()
        assert headers == {"Authorization": "Bearer test-fortigate-key"}

    def test_health_check_headers_without_api_key(self, settings):
        """Test empty headers when no API key."""
        action = HealthCheckAction("fortigate", "health_check", settings, {})
        headers = action.get_http_headers()
        assert headers == {}

    def test_block_ip_headers(self, block_ip_action):
        """Test block IP action has Bearer auth header."""
        headers = block_ip_action.get_http_headers()
        assert headers == {"Authorization": "Bearer test-fortigate-key"}

    def test_list_policies_timeout(self, list_policies_action):
        """Test timeout from settings."""
        assert list_policies_action.get_timeout() == 30

    def test_verify_ssl_from_credentials(self, health_check_action):
        """Test SSL verification from credentials."""
        assert health_check_action.get_verify_ssl() is False


# ============================================================================
# POLICY ERROR TESTS
# ============================================================================


class TestPolicyError:
    """Test PolicyError exception class."""

    def test_policy_error_message(self):
        """Test PolicyError stores message correctly."""
        error = PolicyError("Policy not found")
        assert str(error) == "Policy not found"

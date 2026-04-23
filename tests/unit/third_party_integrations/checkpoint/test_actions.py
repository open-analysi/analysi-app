"""Unit tests for Check Point Firewall integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.checkpoint.actions import (
    AddHostAction,
    AddNetworkAction,
    AddUserAction,
    BlockIpAction,
    CheckPointSessionError,
    DeleteHostAction,
    DeleteNetworkAction,
    DeleteUserAction,
    HealthCheckAction,
    InstallPolicyAction,
    ListHostsAction,
    ListLayersAction,
    ListPoliciesAction,
    LogoutSessionAction,
    UnblockIpAction,
    UpdateGroupMembersAction,
    _break_ip_addr,
    _get_base_url,
    _get_net_mask,
    _get_net_size,
    _is_valid_ip,
    _parse_comma_list,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def credentials():
    """Sample Check Point credentials."""
    return {
        "username": "admin",
        "password": "test-cp-pass",
    }


@pytest.fixture
def credentials_with_domain(credentials):
    """Credentials with optional domain — domain is now in settings."""
    return {**credentials}


@pytest.fixture
def settings():
    """Sample Check Point settings."""
    return {
        "url": "https://checkpoint.example.com",
        "verify_server_cert": False,
        "timeout": 60,
    }


@pytest.fixture
def settings_with_domain(settings):
    """Settings with optional domain."""
    return {**settings, "domain": "my-domain"}


@pytest.fixture
def health_check_action(credentials, settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction("checkpoint", "health_check", settings, credentials)


@pytest.fixture
def block_ip_action(credentials, settings):
    """Create BlockIpAction instance."""
    return BlockIpAction("checkpoint", "block_ip", settings, credentials)


@pytest.fixture
def unblock_ip_action(credentials, settings):
    """Create UnblockIpAction instance."""
    return UnblockIpAction("checkpoint", "unblock_ip", settings, credentials)


@pytest.fixture
def list_policies_action(credentials, settings):
    """Create ListPoliciesAction instance."""
    return ListPoliciesAction("checkpoint", "list_policies", settings, credentials)


@pytest.fixture
def list_layers_action(credentials, settings):
    """Create ListLayersAction instance."""
    return ListLayersAction("checkpoint", "list_layers", settings, credentials)


@pytest.fixture
def list_hosts_action(credentials, settings):
    """Create ListHostsAction instance."""
    return ListHostsAction("checkpoint", "list_hosts", settings, credentials)


@pytest.fixture
def add_host_action(credentials, settings):
    """Create AddHostAction instance."""
    return AddHostAction("checkpoint", "add_host", settings, credentials)


@pytest.fixture
def delete_host_action(credentials, settings):
    """Create DeleteHostAction instance."""
    return DeleteHostAction("checkpoint", "delete_host", settings, credentials)


@pytest.fixture
def add_network_action(credentials, settings):
    """Create AddNetworkAction instance."""
    return AddNetworkAction("checkpoint", "add_network", settings, credentials)


@pytest.fixture
def delete_network_action(credentials, settings):
    """Create DeleteNetworkAction instance."""
    return DeleteNetworkAction("checkpoint", "delete_network", settings, credentials)


@pytest.fixture
def update_group_action(credentials, settings):
    """Create UpdateGroupMembersAction instance."""
    return UpdateGroupMembersAction(
        "checkpoint", "update_group_members", settings, credentials
    )


@pytest.fixture
def install_policy_action(credentials, settings):
    """Create InstallPolicyAction instance."""
    return InstallPolicyAction("checkpoint", "install_policy", settings, credentials)


@pytest.fixture
def add_user_action(credentials, settings):
    """Create AddUserAction instance."""
    return AddUserAction("checkpoint", "add_user", settings, credentials)


@pytest.fixture
def delete_user_action(credentials, settings):
    """Create DeleteUserAction instance."""
    return DeleteUserAction("checkpoint", "delete_user", settings, credentials)


@pytest.fixture
def logout_session_action(credentials, settings):
    """Create LogoutSessionAction instance."""
    return LogoutSessionAction("checkpoint", "logout_session", settings, credentials)


# ============================================================================
# HELPER: build a mock for the session-based call sequence
# ============================================================================


def _make_session_mock(api_responses: list[dict], login_sid: str = "test-sid-123"):
    """Build a mock http_request that handles login + N api calls + logout.

    ``api_responses`` is a list of dicts, one per _api_call after login.
    Login (call 0) and logout (last call) are handled automatically.
    """
    call_count = 0

    async def mock_http_request(url, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        if call_count == 1:
            # Login response
            mock_resp.json.return_value = {"sid": login_sid}
            return mock_resp

        # api_responses index is call_count - 2 (skip login)
        api_idx = call_count - 2

        if api_idx < len(api_responses):
            resp_data = api_responses[api_idx]
            if isinstance(resp_data, Exception):
                raise resp_data
            mock_resp.json.return_value = resp_data
            return mock_resp

        # Fallback: logout or extra calls
        mock_resp.json.return_value = {"message": "OK"}
        return mock_resp

    return mock_http_request


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_get_base_url_with_https(self):
        """Test base URL construction with https prefix."""
        assert (
            _get_base_url("https://checkpoint.example.com")
            == "https://checkpoint.example.com/web_api/"
        )

    def test_get_base_url_without_scheme(self):
        """Test base URL adds https when missing."""
        assert (
            _get_base_url("checkpoint.example.com")
            == "https://checkpoint.example.com/web_api/"
        )

    def test_get_base_url_strips_trailing_slash(self):
        """Test base URL strips trailing slashes."""
        assert (
            _get_base_url("https://checkpoint.example.com/")
            == "https://checkpoint.example.com/web_api/"
        )

    def test_get_net_mask_32(self):
        """Test /32 CIDR to subnet mask."""
        assert _get_net_mask("32") == "255.255.255.255"

    def test_get_net_mask_24(self):
        """Test /24 CIDR to subnet mask."""
        assert _get_net_mask("24") == "255.255.255.0"

    def test_get_net_mask_16(self):
        """Test /16 CIDR to subnet mask."""
        assert _get_net_mask("16") == "255.255.0.0"

    def test_get_net_size_from_mask(self):
        """Test subnet mask to CIDR conversion."""
        assert _get_net_size("255.255.255.0") == "24"
        assert _get_net_size("255.255.0.0") == "16"
        assert _get_net_size("255.255.255.255") == "32"

    def test_break_ip_simple(self):
        """Test parsing simple IP address."""
        ip, net_size, net_mask = _break_ip_addr("10.0.0.1")
        assert ip == "10.0.0.1"
        assert net_size == "32"
        assert net_mask == "255.255.255.255"

    def test_break_ip_cidr(self):
        """Test parsing CIDR notation."""
        ip, net_size, net_mask = _break_ip_addr("10.0.0.0/24")
        assert ip == "10.0.0.0"
        assert net_size == "24"
        assert net_mask == "255.255.255.0"

    def test_break_ip_with_mask(self):
        """Test parsing IP with subnet mask."""
        ip, net_size, net_mask = _break_ip_addr("10.0.0.0 255.255.0.0")
        assert ip == "10.0.0.0"
        assert net_size == "16"
        assert net_mask == "255.255.0.0"

    def test_is_valid_ip_simple(self):
        """Test valid simple IPs."""
        assert _is_valid_ip("10.0.0.1") is True
        assert _is_valid_ip("192.168.1.1") is True

    def test_is_valid_ip_cidr(self):
        """Test valid CIDR notation."""
        assert _is_valid_ip("10.0.0.0/24") is True
        assert _is_valid_ip("192.168.0.0/16") is True

    def test_is_valid_ip_with_mask(self):
        """Test valid IP with subnet mask."""
        assert _is_valid_ip("10.0.0.0 255.255.0.0") is True

    def test_is_valid_ip_invalid(self):
        """Test invalid IP addresses."""
        assert _is_valid_ip("not-an-ip") is False
        assert _is_valid_ip("999.999.999.999") is False

    def test_parse_comma_list(self):
        """Test comma-separated list parsing."""
        assert _parse_comma_list("a, b, c") == ["a", "b", "c"]
        assert _parse_comma_list("a,,b") == ["a", "b"]
        assert _parse_comma_list(None) == []
        assert _parse_comma_list("") == []

    def test_parse_comma_list_single(self):
        """Test single item list."""
        assert _parse_comma_list("single") == ["single"]


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestHealthCheck:
    """Tests for HealthCheckAction."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check (login + show-session + logout)."""
        health_check_action.http_request = _make_session_mock(
            api_responses=[
                {"sid": "test-sid", "uid": "session-uid"},  # show-session
            ]
        )

        result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["integration_id"] == "checkpoint"
        assert result["action_id"] == "health_check"
        assert result["data"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_health_check_missing_url(self):
        """Test health check with missing URL (url is now in settings)."""
        action = HealthCheckAction(
            "checkpoint",
            "health_check",
            {"timeout": 60},  # no url
            {"username": "admin", "password": "test-cp-pass"},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_health_check_missing_username(self, settings):
        """Test health check with missing username."""
        action = HealthCheckAction(
            "checkpoint",
            "health_check",
            settings,
            {"password": "test-cp-pass"},  # no username
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_health_check_missing_password(self, settings):
        """Test health check with missing password."""
        action = HealthCheckAction(
            "checkpoint",
            "health_check",
            settings,
            {"username": "admin"},  # no password
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_health_check_auth_failure(self, health_check_action):
        """Test health check with authentication failure (401 on login)."""
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
    async def test_health_check_uses_domain(self, credentials, settings_with_domain):
        """Test health check passes domain in login body."""
        action = HealthCheckAction(
            "checkpoint", "health_check", settings_with_domain, credentials
        )

        calls = []

        async def tracking_mock(url, **kwargs):
            calls.append((url, kwargs))
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "login" in url:
                mock_resp.json.return_value = {"sid": "test-sid"}
            else:
                mock_resp.json.return_value = {"message": "OK"}
            return mock_resp

        action.http_request = tracking_mock

        await action.execute()

        # Login call should include domain in json_data
        login_call = calls[0]
        login_body = login_call[1].get("json_data", {})
        assert login_body.get("domain") == "my-domain"


# ============================================================================
# BLOCK IP TESTS
# ============================================================================


class TestBlockIp:
    """Tests for BlockIpAction."""

    @pytest.mark.asyncio
    async def test_block_ip_success(self, block_ip_action):
        """Test successful IP block (object does not exist, create + rule + publish)."""
        block_ip_action.http_request = _make_session_mock(
            api_responses=[
                # show-hosts (check_for_object): no match
                {"objects": []},
                # add-host (create object)
                {"uid": "new-host-uid", "name": "analysi - 10.0.0.1/32"},
                # show-access-rulebase (check_for_rule): no match
                {"rulebase": []},
                # add-access-rule
                {"uid": "rule-uid", "name": "analysi - 10.0.0.1/32"},
                # publish
                {"task-id": "task-123"},
                # show-task (publish poll)
                {"tasks": [{"status": "succeeded"}]},
                # install-policy
                {"task-id": "install-task"},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await block_ip_action.execute(
                ip="10.0.0.1",
                layer="Network",
                policy="Standard",
            )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Successfully blocked IP"
        assert result["data"]["ip"] == "10.0.0.1"
        assert result["data"]["layer"] == "Network"
        assert result["data"]["policy"] == "Standard"

    @pytest.mark.asyncio
    async def test_block_ip_already_blocked(self, block_ip_action):
        """Test block IP when rule already exists."""
        block_ip_action.http_request = _make_session_mock(
            api_responses=[
                # show-hosts: object exists
                {
                    "objects": [
                        {"name": "analysi - 10.0.0.1/32", "ipv4-address": "10.0.0.1"}
                    ]
                },
                # show-access-rulebase: rule exists
                {"rulebase": [{"name": "analysi - 10.0.0.1/32"}]},
            ]
        )

        result = await block_ip_action.execute(
            ip="10.0.0.1",
            layer="Network",
            policy="Standard",
        )

        assert result["status"] == "success"
        assert "already blocked" in result["data"]["message"].lower()

    @pytest.mark.asyncio
    async def test_block_ip_subnet(self, block_ip_action):
        """Test blocking a subnet (CIDR notation)."""
        block_ip_action.http_request = _make_session_mock(
            api_responses=[
                # show-networks (not show-hosts for subnets)
                {"objects": []},
                # add-network
                {"uid": "net-uid", "name": "analysi - 192.168.0.0/16"},
                # show-access-rulebase
                {"rulebase": []},
                # add-access-rule
                {"uid": "rule-uid"},
                # publish
                {"task-id": "task-123"},
                # show-task
                {"tasks": [{"status": "succeeded"}]},
                # install-policy
                {"task-id": "install-task"},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await block_ip_action.execute(
                ip="192.168.0.0/16",
                layer="Network",
                policy="Standard",
            )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Successfully blocked subnet"

    @pytest.mark.asyncio
    async def test_block_ip_skip_install_policy(self, block_ip_action):
        """Test block IP with skip_install_policy flag."""
        call_urls = []

        async def tracking_mock(url, **kwargs):
            call_urls.append(url)
            mock_resp = MagicMock()
            mock_resp.status_code = 200

            if "login" in url:
                mock_resp.json.return_value = {"sid": "test-sid"}
            elif "show-hosts" in url:
                mock_resp.json.return_value = {"objects": []}
            elif "add-host" in url:
                mock_resp.json.return_value = {"uid": "host-uid"}
            elif "show-access-rulebase" in url:
                mock_resp.json.return_value = {"rulebase": []}
            elif "add-access-rule" in url:
                mock_resp.json.return_value = {"uid": "rule-uid"}
            elif "publish" in url:
                mock_resp.json.return_value = {"task-id": "task-123"}
            elif "show-task" in url:
                mock_resp.json.return_value = {"tasks": [{"status": "succeeded"}]}
            else:
                mock_resp.json.return_value = {"message": "OK"}

            return mock_resp

        block_ip_action.http_request = tracking_mock

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await block_ip_action.execute(
                ip="10.0.0.1",
                layer="Network",
                policy="Standard",
                skip_install_policy=True,
            )

        assert result["status"] == "success"
        # Verify install-policy was NOT called
        assert not any("install-policy" in url for url in call_urls)

    @pytest.mark.asyncio
    async def test_block_ip_missing_ip(self, block_ip_action):
        """Test block IP with missing IP parameter."""
        result = await block_ip_action.execute(layer="Network", policy="Standard")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_ip_missing_layer(self, block_ip_action):
        """Test block IP with missing layer parameter."""
        result = await block_ip_action.execute(ip="10.0.0.1", policy="Standard")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "layer" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_ip_missing_policy(self, block_ip_action):
        """Test block IP with missing policy parameter."""
        result = await block_ip_action.execute(ip="10.0.0.1", layer="Network")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "policy" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_block_ip_invalid_ip(self, block_ip_action):
        """Test block IP with invalid IP address."""
        result = await block_ip_action.execute(
            ip="not-an-ip",
            layer="Network",
            policy="Standard",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "Invalid IP" in result["error"]

    @pytest.mark.asyncio
    async def test_block_ip_missing_credentials(self, settings):
        """Test block IP with missing credentials."""
        action = BlockIpAction(
            "checkpoint",
            "block_ip",
            settings,
            {"url": "https://cp.example.com"},
        )

        result = await action.execute(ip="10.0.0.1", layer="Network", policy="Standard")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_block_ip_publish_failure(self, block_ip_action):
        """Test block IP when publish fails."""
        block_ip_action.http_request = _make_session_mock(
            api_responses=[
                {"objects": []},  # show-hosts
                {"uid": "host-uid"},  # add-host
                {"rulebase": []},  # show-access-rulebase
                {"uid": "rule-uid"},  # add-access-rule
                {"task-id": "task-123"},  # publish
                {"tasks": [{"status": "in-progress"}]},  # show-task (never succeeds)
                {"tasks": [{"status": "in-progress"}]},
                {"tasks": [{"status": "in-progress"}]},
                {"tasks": [{"status": "in-progress"}]},
                {"tasks": [{"status": "in-progress"}]},
                {"tasks": [{"status": "in-progress"}]},
                {"tasks": [{"status": "in-progress"}]},
                {"tasks": [{"status": "in-progress"}]},
                {"tasks": [{"status": "in-progress"}]},
                {"tasks": [{"status": "in-progress"}]},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await block_ip_action.execute(
                ip="10.0.0.1",
                layer="Network",
                policy="Standard",
            )

        assert result["status"] == "error"
        assert result["error_type"] == "PublishError"

    @pytest.mark.asyncio
    async def test_block_ip_existing_object_different_name(self, block_ip_action):
        """Test block IP when object exists with a different name."""
        block_ip_action.http_request = _make_session_mock(
            api_responses=[
                # show-hosts: found an existing object with different name for same IP
                {
                    "objects": [
                        {"name": "existing-host-obj", "ipv4-address": "10.0.0.1"}
                    ]
                },
                # show-access-rulebase: rule exists with existing name
                {"rulebase": [{"name": "existing-host-obj"}]},
            ]
        )

        result = await block_ip_action.execute(
            ip="10.0.0.1",
            layer="Network",
            policy="Standard",
        )

        assert result["status"] == "success"
        assert "already blocked" in result["data"]["message"].lower()


# ============================================================================
# UNBLOCK IP TESTS
# ============================================================================


class TestUnblockIp:
    """Tests for UnblockIpAction."""

    @pytest.mark.asyncio
    async def test_unblock_ip_success(self, unblock_ip_action):
        """Test successful IP unblock (rule exists, delete + publish + install)."""
        unblock_ip_action.http_request = _make_session_mock(
            api_responses=[
                # show-access-rulebase: rule exists
                {"rulebase": [{"name": "analysi - 10.0.0.1/32"}]},
                # delete-access-rule
                {"message": "OK"},
                # publish
                {"task-id": "task-123"},
                # show-task
                {"tasks": [{"status": "succeeded"}]},
                # install-policy
                {"task-id": "install-task"},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await unblock_ip_action.execute(
                ip="10.0.0.1",
                layer="Network",
                policy="Standard",
            )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Successfully unblocked IP"
        assert result["data"]["ip"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_unblock_ip_not_blocked(self, unblock_ip_action):
        """Test unblock IP when no rule exists."""
        unblock_ip_action.http_request = _make_session_mock(
            api_responses=[
                # show-access-rulebase: no matching rule
                {"rulebase": []},
            ]
        )

        result = await unblock_ip_action.execute(
            ip="10.0.0.1",
            layer="Network",
            policy="Standard",
        )

        assert result["status"] == "success"
        assert "not blocked" in result["data"]["message"].lower()

    @pytest.mark.asyncio
    async def test_unblock_ip_missing_ip(self, unblock_ip_action):
        """Test unblock IP with missing IP parameter."""
        result = await unblock_ip_action.execute(layer="Network", policy="Standard")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unblock_ip_missing_layer(self, unblock_ip_action):
        """Test unblock IP with missing layer parameter."""
        result = await unblock_ip_action.execute(ip="10.0.0.1", policy="Standard")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "layer" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unblock_ip_missing_policy(self, unblock_ip_action):
        """Test unblock IP with missing policy parameter."""
        result = await unblock_ip_action.execute(ip="10.0.0.1", layer="Network")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "policy" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unblock_ip_invalid_ip(self, unblock_ip_action):
        """Test unblock IP with invalid IP address."""
        result = await unblock_ip_action.execute(
            ip="bad-ip", layer="Network", policy="Standard"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_unblock_ip_missing_credentials(self, settings):
        """Test unblock IP with missing credentials."""
        action = UnblockIpAction(
            "checkpoint",
            "unblock_ip",
            settings,
            {"url": "https://cp.example.com"},
        )

        result = await action.execute(ip="10.0.0.1", layer="Network", policy="Standard")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_unblock_ip_subnet(self, unblock_ip_action):
        """Test unblocking a subnet."""
        unblock_ip_action.http_request = _make_session_mock(
            api_responses=[
                {"rulebase": [{"name": "analysi - 192.168.0.0/16"}]},
                {"message": "OK"},  # delete rule
                {"task-id": "task-123"},  # publish
                {"tasks": [{"status": "succeeded"}]},  # show-task
                {"task-id": "inst-task"},  # install-policy
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await unblock_ip_action.execute(
                ip="192.168.0.0/16",
                layer="Network",
                policy="Standard",
            )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Successfully unblocked subnet"


# ============================================================================
# LIST POLICIES TESTS
# ============================================================================


class TestListPolicies:
    """Tests for ListPoliciesAction."""

    @pytest.mark.asyncio
    async def test_list_policies_success(self, list_policies_action):
        """Test successful policy listing."""
        list_policies_action.http_request = _make_session_mock(
            api_responses=[
                {
                    "packages": [
                        {"name": "Standard", "uid": "pkg-1"},
                        {"name": "DMZ-Policy", "uid": "pkg-2"},
                    ]
                },
            ]
        )

        result = await list_policies_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_packages"] == 2
        assert len(result["data"]["packages"]) == 2
        assert result["data"]["packages"][0]["name"] == "Standard"

    @pytest.mark.asyncio
    async def test_list_policies_empty(self, list_policies_action):
        """Test listing policies with no results."""
        list_policies_action.http_request = _make_session_mock(
            api_responses=[{"packages": []}]
        )

        result = await list_policies_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_packages"] == 0

    @pytest.mark.asyncio
    async def test_list_policies_missing_credentials(self, settings):
        """Test list policies with missing credentials."""
        action = ListPoliciesAction("checkpoint", "list_policies", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

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


# ============================================================================
# LIST LAYERS TESTS
# ============================================================================


class TestListLayers:
    """Tests for ListLayersAction."""

    @pytest.mark.asyncio
    async def test_list_layers_success(self, list_layers_action):
        """Test successful layer listing."""
        list_layers_action.http_request = _make_session_mock(
            api_responses=[
                {
                    "access-layers": [
                        {"name": "Network", "uid": "layer-1"},
                        {"name": "App Control", "uid": "layer-2"},
                    ]
                },
            ]
        )

        result = await list_layers_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_layers"] == 2
        assert result["data"]["access_layers"][0]["name"] == "Network"

    @pytest.mark.asyncio
    async def test_list_layers_missing_credentials(self, settings):
        """Test list layers with missing credentials."""
        action = ListLayersAction("checkpoint", "list_layers", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# LIST HOSTS TESTS
# ============================================================================


class TestListHosts:
    """Tests for ListHostsAction."""

    @pytest.mark.asyncio
    async def test_list_hosts_success(self, list_hosts_action):
        """Test successful host listing."""
        list_hosts_action.http_request = _make_session_mock(
            api_responses=[
                {
                    "objects": [
                        {
                            "name": "Host_10.0.0.1",
                            "uid": "host-1",
                            "ipv4-address": "10.0.0.1",
                        },
                    ],
                    "total": 1,
                },
            ]
        )

        result = await list_hosts_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_hosts"] == 1
        assert result["data"]["hosts"][0]["name"] == "Host_10.0.0.1"

    @pytest.mark.asyncio
    async def test_list_hosts_empty(self, list_hosts_action):
        """Test listing hosts with no results."""
        list_hosts_action.http_request = _make_session_mock(
            api_responses=[{"objects": [], "total": 0}]
        )

        result = await list_hosts_action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_hosts"] == 0

    @pytest.mark.asyncio
    async def test_list_hosts_missing_credentials(self, settings):
        """Test list hosts with missing credentials."""
        action = ListHostsAction("checkpoint", "list_hosts", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# ADD HOST TESTS
# ============================================================================


class TestAddHost:
    """Tests for AddHostAction."""

    @pytest.mark.asyncio
    async def test_add_host_with_ip(self, add_host_action):
        """Test adding a host with simple IP."""
        add_host_action.http_request = _make_session_mock(
            api_responses=[
                # add-host response
                {"uid": "new-host", "name": "my-host", "ipv4-address": "10.0.0.1"},
                # publish
                {"task-id": "task-1"},
                # show-task
                {"tasks": [{"status": "succeeded"}]},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await add_host_action.execute(name="my-host", ip="10.0.0.1")

        assert result["status"] == "success"
        assert result["data"]["message"] == "Successfully added host"

    @pytest.mark.asyncio
    async def test_add_host_with_ipv4_and_ipv6(self, add_host_action):
        """Test adding a host with both IPv4 and IPv6."""
        add_host_action.http_request = _make_session_mock(
            api_responses=[
                {"uid": "host-uid", "name": "dual-host"},
                {"task-id": "task-1"},
                {"tasks": [{"status": "succeeded"}]},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await add_host_action.execute(
                name="dual-host", ipv4="10.0.0.1", ipv6="2001:db8::1"
            )

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_add_host_missing_name(self, add_host_action):
        """Test add host with missing name."""
        result = await add_host_action.execute(ip="10.0.0.1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "name" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_add_host_missing_ip(self, add_host_action):
        """Test add host with no IP address specified."""
        result = await add_host_action.execute(name="my-host")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_add_host_missing_credentials(self, settings):
        """Test add host with missing credentials."""
        action = AddHostAction("checkpoint", "add_host", settings, {})

        result = await action.execute(name="host", ip="10.0.0.1")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_add_host_with_groups(self, add_host_action):
        """Test adding a host with group memberships."""
        calls = []

        async def tracking_mock(url, **kwargs):
            calls.append((url, kwargs))
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "login" in url:
                mock_resp.json.return_value = {"sid": "test-sid"}
            elif "add-host" in url:
                mock_resp.json.return_value = {"uid": "host-uid"}
            elif "publish" in url:
                mock_resp.json.return_value = {"task-id": "task-1"}
            elif "show-task" in url:
                mock_resp.json.return_value = {"tasks": [{"status": "succeeded"}]}
            else:
                mock_resp.json.return_value = {"message": "OK"}
            return mock_resp

        add_host_action.http_request = tracking_mock

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await add_host_action.execute(
                name="my-host", ip="10.0.0.1", groups="group-a, group-b"
            )

        assert result["status"] == "success"
        # Verify groups were passed in the add-host call
        add_host_call = next(c for c in calls if "add-host" in c[0])
        body = add_host_call[1].get("json_data", {})
        assert body.get("groups") == ["group-a", "group-b"]


# ============================================================================
# DELETE HOST TESTS
# ============================================================================


class TestDeleteHost:
    """Tests for DeleteHostAction."""

    @pytest.mark.asyncio
    async def test_delete_host_by_name(self, delete_host_action):
        """Test deleting a host by name."""
        delete_host_action.http_request = _make_session_mock(
            api_responses=[
                {"message": "OK"},  # delete-host
                {"task-id": "task-1"},  # publish
                {"tasks": [{"status": "succeeded"}]},  # show-task
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await delete_host_action.execute(name="test-host")

        assert result["status"] == "success"
        assert result["data"]["message"] == "Successfully deleted host"

    @pytest.mark.asyncio
    async def test_delete_host_by_uid(self, delete_host_action):
        """Test deleting a host by UID."""
        delete_host_action.http_request = _make_session_mock(
            api_responses=[
                {"message": "OK"},
                {"task-id": "task-1"},
                {"tasks": [{"status": "succeeded"}]},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await delete_host_action.execute(uid="host-uid-123")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_delete_host_missing_identifier(self, delete_host_action):
        """Test delete host with no name or uid."""
        result = await delete_host_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_delete_host_missing_credentials(self, settings):
        """Test delete host with missing credentials."""
        action = DeleteHostAction("checkpoint", "delete_host", settings, {})

        result = await action.execute(name="test-host")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# ADD / DELETE NETWORK TESTS
# ============================================================================


class TestAddNetwork:
    """Tests for AddNetworkAction."""

    @pytest.mark.asyncio
    async def test_add_network_success(self, add_network_action):
        """Test adding a network with subnet and mask length."""
        add_network_action.http_request = _make_session_mock(
            api_responses=[
                {"uid": "net-uid", "name": "my-network"},  # add-network
                {"task-id": "task-1"},  # publish
                {"tasks": [{"status": "succeeded"}]},  # show-task
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await add_network_action.execute(
                name="my-network", subnet="10.0.0.0", subnet_mask_length=24
            )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Successfully added network"

    @pytest.mark.asyncio
    async def test_add_network_missing_name(self, add_network_action):
        """Test add network with missing name."""
        result = await add_network_action.execute(
            subnet="10.0.0.0", subnet_mask_length=24
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "name" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_add_network_missing_subnet(self, add_network_action):
        """Test add network with no subnet."""
        result = await add_network_action.execute(name="my-net", subnet_mask_length=24)

        assert result["status"] == "error"
        assert "subnet" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_add_network_missing_mask(self, add_network_action):
        """Test add network with no mask."""
        result = await add_network_action.execute(name="my-net", subnet="10.0.0.0")

        assert result["status"] == "error"
        assert "mask" in result["error"].lower()


class TestDeleteNetwork:
    """Tests for DeleteNetworkAction."""

    @pytest.mark.asyncio
    async def test_delete_network_by_name(self, delete_network_action):
        """Test deleting a network by name."""
        delete_network_action.http_request = _make_session_mock(
            api_responses=[
                {"message": "OK"},
                {"task-id": "task-1"},
                {"tasks": [{"status": "succeeded"}]},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await delete_network_action.execute(name="test-network")

        assert result["status"] == "success"
        assert result["data"]["message"] == "Successfully deleted network"

    @pytest.mark.asyncio
    async def test_delete_network_missing_identifier(self, delete_network_action):
        """Test delete network with no name or uid."""
        result = await delete_network_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# UPDATE GROUP MEMBERS TESTS
# ============================================================================


class TestUpdateGroupMembers:
    """Tests for UpdateGroupMembersAction."""

    @pytest.mark.asyncio
    async def test_update_group_add_members(self, update_group_action):
        """Test adding members to a group."""
        update_group_action.http_request = _make_session_mock(
            api_responses=[
                {"uid": "group-uid", "name": "my-group", "members": []},  # set-group
                {"task-id": "task-1"},  # publish
                {"tasks": [{"status": "succeeded"}]},  # show-task
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await update_group_action.execute(
                name="my-group", members="host-a, host-b", action="add"
            )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Successfully updated group"

    @pytest.mark.asyncio
    async def test_update_group_remove_members(self, update_group_action):
        """Test removing members from a group."""
        update_group_action.http_request = _make_session_mock(
            api_responses=[
                {"uid": "group-uid"},
                {"task-id": "task-1"},
                {"tasks": [{"status": "succeeded"}]},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await update_group_action.execute(
                name="my-group", members="host-a", action="remove"
            )

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_update_group_set_members(self, update_group_action):
        """Test setting (replacing) members in a group."""
        calls = []

        async def tracking_mock(url, **kwargs):
            calls.append((url, kwargs))
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "login" in url:
                mock_resp.json.return_value = {"sid": "test-sid"}
            elif "set-group" in url:
                mock_resp.json.return_value = {"uid": "group-uid"}
            elif "publish" in url:
                mock_resp.json.return_value = {"task-id": "t1"}
            elif "show-task" in url:
                mock_resp.json.return_value = {"tasks": [{"status": "succeeded"}]}
            else:
                mock_resp.json.return_value = {"message": "OK"}
            return mock_resp

        update_group_action.http_request = tracking_mock

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await update_group_action.execute(
                name="my-group", members="host-a, host-b", action="set"
            )

        assert result["status"] == "success"

        # For "set" action, members should be a plain list (not wrapped in {"set": [...]})
        set_group_call = next(c for c in calls if "set-group" in c[0])
        body = set_group_call[1].get("json_data", {})
        assert body["members"] == ["host-a", "host-b"]

    @pytest.mark.asyncio
    async def test_update_group_missing_identifier(self, update_group_action):
        """Test update group with no name or uid."""
        result = await update_group_action.execute(members="host-a", action="add")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_update_group_missing_members(self, update_group_action):
        """Test update group with missing members."""
        result = await update_group_action.execute(name="my-group", action="add")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_update_group_missing_action(self, update_group_action):
        """Test update group with missing action."""
        result = await update_group_action.execute(name="my-group", members="host-a")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_update_group_empty_members(self, update_group_action):
        """Test update group with empty members string."""
        result = await update_group_action.execute(
            name="my-group", members=",,", action="add"
        )

        assert result["status"] == "error"
        assert "members" in result["error"].lower()


# ============================================================================
# INSTALL POLICY TESTS
# ============================================================================


class TestInstallPolicy:
    """Tests for InstallPolicyAction."""

    @pytest.mark.asyncio
    async def test_install_policy_success(self, install_policy_action):
        """Test successful policy installation."""
        install_policy_action.http_request = _make_session_mock(
            api_responses=[
                {"task-id": "install-task"},  # install-policy
            ]
        )

        result = await install_policy_action.execute(
            policy="Standard", targets="gw1, gw2"
        )

        assert result["status"] == "success"
        assert "policy installation" in result["data"]["message"].lower()

    @pytest.mark.asyncio
    async def test_install_policy_with_access_flag(self, install_policy_action):
        """Test install policy with access flag."""
        calls = []

        async def tracking_mock(url, **kwargs):
            calls.append((url, kwargs))
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "login" in url:
                mock_resp.json.return_value = {"sid": "test-sid"}
            elif "install-policy" in url:
                mock_resp.json.return_value = {"task-id": "task-1"}
            else:
                mock_resp.json.return_value = {"message": "OK"}
            return mock_resp

        install_policy_action.http_request = tracking_mock

        result = await install_policy_action.execute(
            policy="Standard", targets="gw1", access=True
        )

        assert result["status"] == "success"

        # Verify access flag was included
        install_call = next(c for c in calls if "install-policy" in c[0])
        body = install_call[1].get("json_data", {})
        assert body.get("access") is True

    @pytest.mark.asyncio
    async def test_install_policy_missing_policy(self, install_policy_action):
        """Test install policy with missing policy name."""
        result = await install_policy_action.execute(targets="gw1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_install_policy_missing_targets(self, install_policy_action):
        """Test install policy with missing targets."""
        result = await install_policy_action.execute(policy="Standard")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_install_policy_empty_targets(self, install_policy_action):
        """Test install policy with empty targets string."""
        result = await install_policy_action.execute(policy="Standard", targets=",,")

        assert result["status"] == "error"
        assert "targets" in result["error"].lower()


# ============================================================================
# ADD / DELETE USER TESTS
# ============================================================================


class TestAddUser:
    """Tests for AddUserAction."""

    @pytest.mark.asyncio
    async def test_add_user_success(self, add_user_action):
        """Test successful user creation."""
        add_user_action.http_request = _make_session_mock(
            api_responses=[
                {"uid": "user-uid", "name": "john"},  # add-user
                {"task-id": "task-1"},  # publish
                {"tasks": [{"status": "succeeded"}]},  # show-task
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await add_user_action.execute(
                name="john", template="default-template"
            )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Successfully created user"

    @pytest.mark.asyncio
    async def test_add_user_with_optional_fields(self, add_user_action):
        """Test user creation with email and phone."""
        calls = []

        async def tracking_mock(url, **kwargs):
            calls.append((url, kwargs))
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "login" in url:
                mock_resp.json.return_value = {"sid": "test-sid"}
            elif "add-user" in url:
                mock_resp.json.return_value = {"uid": "user-uid"}
            elif "publish" in url:
                mock_resp.json.return_value = {"task-id": "t1"}
            elif "show-task" in url:
                mock_resp.json.return_value = {"tasks": [{"status": "succeeded"}]}
            else:
                mock_resp.json.return_value = {"message": "OK"}
            return mock_resp

        add_user_action.http_request = tracking_mock

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await add_user_action.execute(
                name="john",
                template="default-template",
                email="john@example.com",
                phone_number="+1234567890",
                comments="Test user",
            )

        assert result["status"] == "success"

        # Verify optional fields in add-user body
        user_call = next(c for c in calls if "add-user" in c[0])
        body = user_call[1].get("json_data", {})
        assert body.get("email") == "john@example.com"
        assert body.get("phone-number") == "+1234567890"
        assert body.get("comments") == "Test user"

    @pytest.mark.asyncio
    async def test_add_user_missing_name(self, add_user_action):
        """Test add user with missing name."""
        result = await add_user_action.execute(template="default-template")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_add_user_missing_template(self, add_user_action):
        """Test add user with missing template."""
        result = await add_user_action.execute(name="john")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_add_user_missing_credentials(self, settings):
        """Test add user with missing credentials."""
        action = AddUserAction("checkpoint", "add_user", settings, {})

        result = await action.execute(name="john", template="tmpl")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


class TestDeleteUser:
    """Tests for DeleteUserAction."""

    @pytest.mark.asyncio
    async def test_delete_user_by_name(self, delete_user_action):
        """Test deleting a user by name."""
        delete_user_action.http_request = _make_session_mock(
            api_responses=[
                {"message": "OK"},
                {"task-id": "task-1"},
                {"tasks": [{"status": "succeeded"}]},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await delete_user_action.execute(name="john")

        assert result["status"] == "success"
        assert result["data"]["message"] == "Successfully deleted user"

    @pytest.mark.asyncio
    async def test_delete_user_by_uid(self, delete_user_action):
        """Test deleting a user by UID."""
        delete_user_action.http_request = _make_session_mock(
            api_responses=[
                {"message": "OK"},
                {"task-id": "task-1"},
                {"tasks": [{"status": "succeeded"}]},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await delete_user_action.execute(uid="user-uid-123")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_delete_user_missing_identifier(self, delete_user_action):
        """Test delete user with no name or uid."""
        result = await delete_user_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# LOGOUT SESSION TESTS
# ============================================================================


class TestLogoutSession:
    """Tests for LogoutSessionAction."""

    @pytest.mark.asyncio
    async def test_logout_current_session(self, logout_session_action):
        """Test logging out the current session."""
        logout_session_action.http_request = _make_session_mock(
            api_responses=[
                {"message": "OK"},  # logout
            ]
        )

        result = await logout_session_action.execute()

        assert result["status"] == "success"
        assert "logged out" in result["data"]["message"].lower()

    @pytest.mark.asyncio
    async def test_logout_specific_session(self, logout_session_action):
        """Test logging out a specific session by ID."""
        calls = []

        async def tracking_mock(url, **kwargs):
            calls.append((url, kwargs))
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "login" in url:
                mock_resp.json.return_value = {"sid": "my-sid"}
            else:
                mock_resp.json.return_value = {"message": "OK"}
            return mock_resp

        logout_session_action.http_request = tracking_mock

        result = await logout_session_action.execute(session_id="other-sid-456")

        assert result["status"] == "success"
        assert result["data"]["session_id"] == "other-sid-456"

        # Should have a logout call with the specified session id
        logout_calls = [c for c in calls if "logout" in c[0]]
        assert len(logout_calls) >= 1
        # First logout is for the target session
        target_headers = logout_calls[0][1].get("headers", {})
        assert target_headers.get("X-chkp-sid") == "other-sid-456"

    @pytest.mark.asyncio
    async def test_logout_session_missing_credentials(self, settings):
        """Test logout with missing credentials."""
        action = LogoutSessionAction("checkpoint", "logout_session", settings, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# AUTH / BASE CLASS TESTS
# ============================================================================


class TestBaseClass:
    """Tests for _CheckPointBase shared behavior."""

    def test_timeout_from_settings(self, health_check_action):
        """Test timeout reads from settings."""
        assert health_check_action.get_timeout() == 60

    def test_timeout_default(self, credentials):
        """Test default timeout when not in settings."""
        action = HealthCheckAction("checkpoint", "health_check", {}, credentials)
        assert action.get_timeout() == 60

    def test_verify_ssl_from_credentials(self, health_check_action):
        """Test SSL verification from credentials."""
        assert health_check_action.get_verify_ssl() is False

    def test_verify_ssl_default(self, settings):
        """Test default SSL verification (False for Check Point)."""
        action = HealthCheckAction(
            "checkpoint",
            "health_check",
            settings,
            {"url": "https://cp.example.com", "username": "a", "password": "b"},
        )
        assert action.get_verify_ssl() is False


class TestCheckPointSessionError:
    """Test CheckPointSessionError exception class."""

    def test_session_error_message(self):
        """Test CheckPointSessionError stores message."""
        error = CheckPointSessionError("No session ID")
        assert str(error) == "No session ID"

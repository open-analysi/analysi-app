"""Unit tests for Nessus integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.nessus.actions import (
    GetHostVulnerabilitiesAction,
    HealthCheckAction,
    ListPoliciesAction,
    ScanHostAction,
)


@pytest.fixture
def credentials():
    """Fixture for Nessus credentials."""
    return {
        "access_key": "test_access_key",
        "secret_key": "test_secret_key",
    }


@pytest.fixture
def settings():
    """Fixture for Nessus settings."""
    return {
        "server": "nessus.example.com",
        "port": 8834,
        "verify_server_cert": False,
        "timeout": 30,
    }


@pytest.fixture
def health_check_action(credentials, settings):
    """Fixture for HealthCheckAction."""
    return HealthCheckAction(
        integration_id="nessus",
        action_id="health_check",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def list_policies_action(credentials, settings):
    """Fixture for ListPoliciesAction."""
    return ListPoliciesAction(
        integration_id="nessus",
        action_id="list_policies",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def scan_host_action(credentials, settings):
    """Fixture for ScanHostAction."""
    return ScanHostAction(
        integration_id="nessus",
        action_id="scan_host",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def get_host_vulnerabilities_action(credentials, settings):
    """Fixture for GetHostVulnerabilitiesAction."""
    return GetHostVulnerabilitiesAction(
        integration_id="nessus",
        action_id="get_host_vulnerabilities",
        settings=settings,
        credentials=credentials,
    )


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = {"users": [{"username": "admin"}]}

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response
    mock_http_response.text = '{"users": []}'

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert "server" in result["data"]
    assert "port" in result["data"]


@pytest.mark.asyncio
async def test_health_check_missing_server(settings):
    """Test health check with missing server."""
    action = HealthCheckAction(
        integration_id="nessus",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={
            "access_key": "test_key",
            "secret_key": "test_secret",
        },
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "server" in result["error"].lower()
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_missing_keys(settings):
    """Test health check with missing API keys."""
    action = HealthCheckAction(
        integration_id="nessus",
        action_id="health_check",
        settings=settings,
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "key" in result["error"].lower()
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check with HTTP error."""
    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.status_code = 401
    mock_http_response.text = "Unauthorized"

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_http_response
        ),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["data"]["healthy"] is False


# ============================================================================
# LIST POLICIES ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_policies_success(list_policies_action):
    """Test successful list policies."""
    mock_response = {
        "policies": [
            {
                "id": 1,
                "name": "Basic Network Scan",
                "description": "Basic scan policy",
                "owner": "admin",
            },
            {
                "id": 2,
                "name": "Advanced Scan",
                "description": "Advanced scan policy",
                "owner": "admin",
            },
        ]
    }

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response
    mock_http_response.text = '{"policies": []}'

    with patch.object(
        list_policies_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await list_policies_action.execute()

    assert result["status"] == "success"
    assert len(result["policies"]) == 2
    assert result["policy_count"] == 2
    assert result["policies"][0]["name"] == "Basic Network Scan"


@pytest.mark.asyncio
async def test_list_policies_empty(list_policies_action):
    """Test list policies with empty result."""
    mock_response = {"policies": []}

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response
    mock_http_response.text = '{"policies": []}'

    with patch.object(
        list_policies_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await list_policies_action.execute()

    assert result["status"] == "success"
    assert result["policy_count"] == 0
    assert result["policies"] == []


@pytest.mark.asyncio
async def test_list_policies_missing_credentials(settings):
    """Test list policies with missing credentials."""
    action = ListPoliciesAction(
        integration_id="nessus",
        action_id="list_policies",
        settings=settings,
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


# ============================================================================
# SCAN HOST ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_scan_host_success(scan_host_action):
    """Test successful host scan."""
    # Mock scan launch response
    mock_scan_launch = {"scan": {"id": 123}}

    # Mock scan status response (completed)
    mock_scan_status = {
        "info": {"status": "completed"},
        "hosts": [
            {
                "hostname": "192.168.1.100",
                "host_id": 1,
                "low": 2,
                "medium": 5,
                "high": 3,
                "critical": 1,
                "info": 10,
            }
        ],
    }

    mock_http_response_launch = MagicMock(spec=httpx.Response)
    mock_http_response_launch.json.return_value = mock_scan_launch
    mock_http_response_launch.text = '{"scan": {}}'

    mock_http_response_status = MagicMock(spec=httpx.Response)
    mock_http_response_status.json.return_value = mock_scan_status
    mock_http_response_status.text = '{"info": {}}'

    with (
        patch.object(
            scan_host_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_http_response_launch, mock_http_response_status],
        ),
        patch("asyncio.sleep", return_value=None),
    ):
        result = await scan_host_action.execute(
            target_to_scan="192.168.1.100", policy_id="4"
        )

    assert result["status"] == "success"
    assert result["scan_id"] == 123
    assert result["target"] == "192.168.1.100"
    assert result["total_vulnerabilities"] == 11  # 2+5+3+1
    assert result["summary"]["critical"] == 1
    assert result["summary"]["high"] == 3


@pytest.mark.asyncio
async def test_scan_host_missing_target(scan_host_action):
    """Test scan host with missing target."""
    result = await scan_host_action.execute(policy_id="4")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "target" in result["error"].lower()


@pytest.mark.asyncio
async def test_scan_host_missing_policy(scan_host_action):
    """Test scan host with missing policy ID."""
    result = await scan_host_action.execute(target_to_scan="192.168.1.100")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "policy" in result["error"].lower()


@pytest.mark.asyncio
async def test_scan_host_missing_credentials(settings):
    """Test scan host with missing credentials."""
    action = ScanHostAction(
        integration_id="nessus",
        action_id="scan_host",
        settings=settings,
        credentials={},
    )

    result = await action.execute(target_to_scan="192.168.1.100", policy_id="4")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_scan_host_no_results(scan_host_action):
    """Test scan host with no results."""
    mock_scan_launch = {"scan": {"id": 123}}
    mock_scan_status = {"info": {"status": "completed"}, "hosts": []}

    mock_http_response_launch = MagicMock(spec=httpx.Response)
    mock_http_response_launch.json.return_value = mock_scan_launch
    mock_http_response_launch.text = '{"scan": {}}'

    mock_http_response_status = MagicMock(spec=httpx.Response)
    mock_http_response_status.json.return_value = mock_scan_status
    mock_http_response_status.text = '{"info": {}}'

    with (
        patch.object(
            scan_host_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_http_response_launch, mock_http_response_status],
        ),
        patch("asyncio.sleep", return_value=None),
    ):
        result = await scan_host_action.execute(
            target_to_scan="192.168.1.100", policy_id="4"
        )

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# GET HOST VULNERABILITIES ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_host_vulnerabilities_success(get_host_vulnerabilities_action):
    """Test successful get host vulnerabilities."""
    mock_response = {
        "vulnerabilities": [
            {
                "plugin_id": 12345,
                "plugin_name": "Test Vulnerability",
                "severity": 3,
                "count": 1,
            },
            {
                "plugin_id": 67890,
                "plugin_name": "Another Vulnerability",
                "severity": 2,
                "count": 2,
            },
        ]
    }

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response
    mock_http_response.text = '{"vulnerabilities": []}'

    with patch.object(
        get_host_vulnerabilities_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await get_host_vulnerabilities_action.execute(
            scan_id="123", host_id="1"
        )

    assert result["status"] == "success"
    assert result["scan_id"] == "123"
    assert result["host_id"] == "1"
    assert len(result["vulnerabilities"]) == 2
    assert result["vulnerability_count"] == 2


@pytest.mark.asyncio
async def test_get_host_vulnerabilities_missing_scan_id(
    get_host_vulnerabilities_action,
):
    """Test get host vulnerabilities with missing scan ID."""
    result = await get_host_vulnerabilities_action.execute(host_id="1")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "scan_id" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_host_vulnerabilities_missing_host_id(
    get_host_vulnerabilities_action,
):
    """Test get host vulnerabilities with missing host ID."""
    result = await get_host_vulnerabilities_action.execute(scan_id="123")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "host_id" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_host_vulnerabilities_missing_credentials(settings):
    """Test get host vulnerabilities with missing credentials."""
    action = GetHostVulnerabilitiesAction(
        integration_id="nessus",
        action_id="get_host_vulnerabilities",
        settings=settings,
        credentials={},
    )

    result = await action.execute(scan_id="123", host_id="1")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_get_host_vulnerabilities_http_error(get_host_vulnerabilities_action):
    """Test get host vulnerabilities with HTTP error."""
    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.status_code = 404
    mock_http_response.text = "Not Found"

    with patch.object(
        get_host_vulnerabilities_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_http_response
        ),
    ):
        result = await get_host_vulnerabilities_action.execute(
            scan_id="123", host_id="1"
        )

    assert result["status"] == "error"

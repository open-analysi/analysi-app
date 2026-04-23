"""
Unit tests for NetWitness Endpoint integration actions.

Tests REST API integration with HTTP Basic Auth.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.netwitness_endpoint.actions import (
    BlocklistDomainAction,
    BlocklistIpAction,
    GetIocAction,
    GetScanDataAction,
    GetSystemInfoAction,
    HealthCheckAction,
    ListEndpointsAction,
    ListIocAction,
    ScanEndpointAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def health_check_action():
    """Create HealthCheckAction instance with test credentials."""
    return HealthCheckAction(
        integration_id="netwitness_endpoint",
        action_id="health_check",
        credentials={
            "username": "testuser",
            "password": "testpass",
        },
        settings={
            "url": "https://netwitness.test.com",
            "verify_server_cert": False,
            "timeout": 30,
        },
    )


@pytest.fixture
def blocklist_domain_action():
    """Create BlocklistDomainAction instance."""
    return BlocklistDomainAction(
        integration_id="netwitness_endpoint",
        action_id="blocklist_domain",
        credentials={
            "username": "testuser",
            "password": "testpass",
        },
        settings={
            "url": "https://netwitness.test.com",
            "verify_server_cert": False,
            "timeout": 30,
        },
    )


@pytest.fixture
def blocklist_ip_action():
    """Create BlocklistIpAction instance."""
    return BlocklistIpAction(
        integration_id="netwitness_endpoint",
        action_id="blocklist_ip",
        credentials={
            "username": "testuser",
            "password": "testpass",
        },
        settings={
            "url": "https://netwitness.test.com",
            "verify_server_cert": False,
            "timeout": 30,
        },
    )


@pytest.fixture
def list_endpoints_action():
    """Create ListEndpointsAction instance."""
    return ListEndpointsAction(
        integration_id="netwitness_endpoint",
        action_id="list_endpoints",
        credentials={
            "username": "testuser",
            "password": "testpass",
        },
        settings={
            "url": "https://netwitness.test.com",
            "verify_server_cert": False,
            "timeout": 30,
        },
    )


@pytest.fixture
def get_system_info_action():
    """Create GetSystemInfoAction instance."""
    return GetSystemInfoAction(
        integration_id="netwitness_endpoint",
        action_id="get_system_info",
        credentials={
            "username": "testuser",
            "password": "testpass",
        },
        settings={
            "url": "https://netwitness.test.com",
            "verify_server_cert": False,
            "timeout": 30,
        },
    )


@pytest.fixture
def scan_endpoint_action():
    """Create ScanEndpointAction instance."""
    return ScanEndpointAction(
        integration_id="netwitness_endpoint",
        action_id="scan_endpoint",
        credentials={
            "username": "testuser",
            "password": "testpass",
        },
        settings={
            "url": "https://netwitness.test.com",
            "verify_server_cert": False,
            "timeout": 30,
        },
    )


@pytest.fixture
def get_scan_data_action():
    """Create GetScanDataAction instance."""
    return GetScanDataAction(
        integration_id="netwitness_endpoint",
        action_id="get_scan_data",
        credentials={
            "username": "testuser",
            "password": "testpass",
        },
        settings={
            "url": "https://netwitness.test.com",
            "verify_server_cert": False,
            "timeout": 30,
        },
    )


@pytest.fixture
def list_ioc_action():
    """Create ListIocAction instance."""
    return ListIocAction(
        integration_id="netwitness_endpoint",
        action_id="list_ioc",
        credentials={
            "username": "testuser",
            "password": "testpass",
        },
        settings={
            "url": "https://netwitness.test.com",
            "verify_server_cert": False,
            "timeout": 30,
        },
    )


@pytest.fixture
def get_ioc_action():
    """Create GetIocAction instance."""
    return GetIocAction(
        integration_id="netwitness_endpoint",
        action_id="get_ioc",
        credentials={
            "username": "testuser",
            "password": "testpass",
        },
        settings={
            "url": "https://netwitness.test.com",
            "verify_server_cert": False,
            "timeout": 30,
        },
    )


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {"status": "healthy"}

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="netwitness_endpoint",
        action_id="health_check",
        credentials={},
        settings={},
    )
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert result["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_connection_error(health_check_action):
    """Test health check with connection error."""

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=Exception("Connection refused"),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False


# ============================================================================
# BLOCKLIST DOMAIN TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_blocklist_domain_success(blocklist_domain_action):
    """Test successful domain blocklisting."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {"Domains": ["evil.com"]}

    with patch.object(
        blocklist_domain_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await blocklist_domain_action.execute(domain="evil.com")

    assert result["status"] == "success"
    assert result["domain"] == "evil.com"
    assert "blocklisted successfully" in result["message"]


@pytest.mark.asyncio
async def test_blocklist_domain_missing_parameter(blocklist_domain_action):
    """Test blocklist domain with missing parameter."""
    result = await blocklist_domain_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "domain" in result["error"]


@pytest.mark.asyncio
async def test_blocklist_domain_http_error(blocklist_domain_action):
    """Test blocklist domain with HTTP error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 403
    mock_response.text = "Forbidden"

    with patch.object(
        blocklist_domain_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        ),
    ):
        result = await blocklist_domain_action.execute(domain="evil.com")

    assert result["status"] == "error"


# ============================================================================
# BLOCKLIST IP TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_blocklist_ip_success(blocklist_ip_action):
    """Test successful IP blocklisting."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {"Ips": ["192.168.1.100"]}

    with patch.object(
        blocklist_ip_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await blocklist_ip_action.execute(ip="192.168.1.100")

    assert result["status"] == "success"
    assert result["ip"] == "192.168.1.100"


@pytest.mark.asyncio
async def test_blocklist_ip_missing_parameter(blocklist_ip_action):
    """Test blocklist IP with missing parameter."""
    result = await blocklist_ip_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# LIST ENDPOINTS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_endpoints_success(list_endpoints_action):
    """Test successful list endpoints."""
    mock_response_list = MagicMock(spec=httpx.Response)
    mock_response_list.status_code = 200
    mock_response_list.headers = {"content-type": "application/json"}
    mock_response_list.json.return_value = {
        "Items": [
            {"Id": "guid-1", "Name": "Host1"},
            {"Id": "guid-2", "Name": "Host2"},
        ]
    }

    mock_response_detail = MagicMock(spec=httpx.Response)
    mock_response_detail.status_code = 200
    mock_response_detail.headers = {"content-type": "application/json"}
    mock_response_detail.json.return_value = {
        "Machine": {"OperatingSystem": "Windows 10", "MachineName": "Host1"}
    }

    with patch.object(
        list_endpoints_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[
            mock_response_list,
            mock_response_detail,
            mock_response_detail,
        ],
    ):
        result = await list_endpoints_action.execute(limit=10)

    assert result["status"] == "success"
    assert "endpoints" in result
    assert result["total_endpoints"] >= 0


@pytest.mark.asyncio
async def test_list_endpoints_validation_error(list_endpoints_action):
    """Test list endpoints with invalid parameters."""
    result = await list_endpoints_action.execute(ioc_score_lte=2000)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# GET SYSTEM INFO TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_system_info_success(get_system_info_action):
    """Test successful get system info."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {
        "Machine": {
            "MachineName": "TestHost",
            "IIOCScore": 100,
            "OperatingSystem": "Windows 10",
        }
    }

    with patch.object(
        get_system_info_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await get_system_info_action.execute(guid="test-guid-123")

    assert result["status"] == "success"
    assert result["machine_name"] == "TestHost"
    assert result["iiocscore"] == 100


@pytest.mark.asyncio
async def test_get_system_info_missing_parameter(get_system_info_action):
    """Test get system info with missing parameter."""
    result = await get_system_info_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_get_system_info_not_found(get_system_info_action):
    """Test get system info with not found error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.text = "Not found"

    with patch.object(
        get_system_info_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        ),
    ):
        result = await get_system_info_action.execute(guid="invalid-guid")

    assert result["status"] == "error"


# ============================================================================
# SCAN ENDPOINT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_scan_endpoint_success(scan_endpoint_action):
    """Test successful endpoint scan."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {"ScanId": "scan-123"}

    with patch.object(
        scan_endpoint_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await scan_endpoint_action.execute(guid="test-guid-123")

    assert result["status"] == "success"
    assert "Scan initiated" in result["message"]


@pytest.mark.asyncio
async def test_scan_endpoint_missing_parameter(scan_endpoint_action):
    """Test scan endpoint with missing parameter."""
    result = await scan_endpoint_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_scan_endpoint_validation_error(scan_endpoint_action):
    """Test scan endpoint with invalid CPU parameters."""
    result = await scan_endpoint_action.execute(guid="test-guid", cpu_max=150)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# GET SCAN DATA TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_scan_data_success(get_scan_data_action):
    """Test successful get scan data."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {
        "Services": [{"Name": "Service1"}],
        "Processes": [{"Name": "Process1"}],
    }

    with patch.object(
        get_scan_data_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await get_scan_data_action.execute(guid="test-guid-123")

    assert result["status"] == "success"
    assert "scan_data" in result
    assert "summary" in result


@pytest.mark.asyncio
async def test_get_scan_data_missing_parameter(get_scan_data_action):
    """Test get scan data with missing parameter."""
    result = await get_scan_data_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# LIST IOC TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_ioc_success(list_ioc_action):
    """Test successful list IOCs."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {
        "iocQueries": [
            {
                "Name": "IOC1",
                "IOCLevel": "1",
                "MachineCount": "5",
                "ModuleCount": "10",
                "Type": "Windows",
            },
            {
                "Name": "IOC2",
                "IOCLevel": "2",
                "MachineCount": "3",
                "ModuleCount": "5",
                "Type": "Windows",
            },
        ]
    }

    with patch.object(
        list_ioc_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await list_ioc_action.execute()

    assert result["status"] == "success"
    assert "iocs" in result
    assert result["available_iocs"] >= 0


# ============================================================================
# GET IOC TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_ioc_success(get_ioc_action):
    """Test successful get IOC."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {
        "iocQueries": [
            {
                "Name": "TestIOC",
                "IOCLevel": "1",
                "MachineCount": "5",
                "ModuleCount": "10",
                "Type": "Windows",
            }
        ]
    }

    with patch.object(
        get_ioc_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await get_ioc_action.execute(name="TestIOC")

    assert result["status"] == "success"
    assert result["name"] == "TestIOC"
    assert "ioc_level" in result


@pytest.mark.asyncio
async def test_get_ioc_missing_parameter(get_ioc_action):
    """Test get IOC with missing parameter."""
    result = await get_ioc_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_get_ioc_not_found(get_ioc_action):
    """Test get IOC with not found error."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {"iocQueries": []}

    with patch.object(
        get_ioc_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await get_ioc_action.execute(name="NonExistentIOC")

    assert result["status"] == "error"
    assert result["error_type"] == "NotFoundError"

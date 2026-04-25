"""Unit tests for Palo Alto Networks Firewall integration actions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.integrations.framework.integrations.paloalto_firewall.actions import (
    BlockApplicationAction,
    BlockIpAction,
    BlockUrlAction,
    HealthCheckAction,
    ListApplicationsAction,
    UnblockApplicationAction,
    UnblockIpAction,
    UnblockUrlAction,
)


@pytest.fixture
def credentials():
    """Sample credentials for testing."""
    return {
        "username": "admin",
        "password": "password123",
    }


@pytest.fixture
def settings():
    """Sample settings for testing."""
    return {"device": "firewall.example.com", "verify_server_cert": True, "timeout": 30}


@pytest.fixture
def health_check_action(credentials, settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction("paloalto_firewall", "health_check", settings, credentials)


@pytest.fixture
def block_url_action(credentials, settings):
    """Create BlockUrlAction instance."""
    return BlockUrlAction("paloalto_firewall", "block_url", settings, credentials)


@pytest.fixture
def unblock_url_action(credentials, settings):
    """Create UnblockUrlAction instance."""
    return UnblockUrlAction("paloalto_firewall", "unblock_url", settings, credentials)


@pytest.fixture
def block_application_action(credentials, settings):
    """Create BlockApplicationAction instance."""
    return BlockApplicationAction(
        "paloalto_firewall", "block_application", settings, credentials
    )


@pytest.fixture
def unblock_application_action(credentials, settings):
    """Create UnblockApplicationAction instance."""
    return UnblockApplicationAction(
        "paloalto_firewall", "unblock_application", settings, credentials
    )


@pytest.fixture
def block_ip_action(credentials, settings):
    """Create BlockIpAction instance."""
    return BlockIpAction("paloalto_firewall", "block_ip", settings, credentials)


@pytest.fixture
def unblock_ip_action(credentials, settings):
    """Create UnblockIpAction instance."""
    return UnblockIpAction("paloalto_firewall", "unblock_ip", settings, credentials)


@pytest.fixture
def list_applications_action(credentials, settings):
    """Create ListApplicationsAction instance."""
    return ListApplicationsAction(
        "paloalto_firewall", "list_applications", settings, credentials
    )


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = MagicMock()
    mock_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><key>test-api-key-123</key></result>
    </response>"""
    mock_response.raise_for_status = MagicMock()

    mock_version_response = MagicMock()
    mock_version_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><system><sw-version>10.2.1</sw-version></system></result>
    </response>"""
    mock_version_response.raise_for_status = MagicMock()

    health_check_action.http_request = AsyncMock(
        side_effect=[mock_response, mock_version_response]
    )
    result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True
    assert "connectivity" in result["message"].lower()


@pytest.mark.asyncio
async def test_health_check_missing_credentials(health_check_action):
    """Test health check with missing credentials."""
    health_check_action.credentials = {}

    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert "credentials" in result["error"].lower()


@pytest.mark.asyncio
async def test_health_check_authentication_failed(health_check_action):
    """Test health check with authentication failure."""
    mock_response = MagicMock()
    mock_response.text = """<?xml version="1.0"?>
    <response status="error">
        <msg><line>Invalid credentials</line></msg>
    </response>"""
    mock_response.raise_for_status = MagicMock()

    health_check_action.http_request = AsyncMock(return_value=mock_response)
    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check with HTTP error."""
    health_check_action.http_request = AsyncMock(
        side_effect=Exception("Connection refused")
    )
    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False


# ============================================================================
# BLOCK URL TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_block_url_success(block_url_action):
    """Test successful URL blocking."""
    mock_auth_response = MagicMock()
    mock_auth_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><key>test-api-key-123</key></result>
    </response>"""
    mock_auth_response.raise_for_status = MagicMock()

    mock_version_response = MagicMock()
    mock_version_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><system><sw-version>10.2.1</sw-version></system></result>
    </response>"""
    mock_version_response.raise_for_status = MagicMock()

    mock_success_response = MagicMock()
    mock_success_response.text = """<?xml version="1.0"?>
    <response status="success"></response>"""
    mock_success_response.raise_for_status = MagicMock()

    mock_policy_response = MagicMock()
    mock_policy_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result>
            <rules>
                <entry name="test-allow-rule">
                    <action>allow</action>
                </entry>
            </rules>
        </result>
    </response>"""
    mock_policy_response.raise_for_status = MagicMock()

    mock_commit_response = MagicMock()
    mock_commit_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job>123</job></result>
    </response>"""
    mock_commit_response.raise_for_status = MagicMock()

    mock_job_response = MagicMock()
    mock_job_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job><status>FIN</status></job></result>
    </response>"""
    mock_job_response.raise_for_status = MagicMock()

    mock_responses = [
        mock_auth_response,
        mock_version_response,
        mock_success_response,  # URL category
        mock_success_response,  # URL profile
        mock_policy_response,  # Get policies
        mock_success_response,  # Create policy
        mock_success_response,  # Move policy
        mock_commit_response,  # Commit
        mock_job_response,  # Job status
    ]

    block_url_action.http_request = AsyncMock(side_effect=mock_responses)
    result = await block_url_action.execute(url="malicious.com")

    assert result["status"] == "success"
    assert result["url"] == "malicious.com"


@pytest.mark.asyncio
async def test_block_url_missing_parameter(block_url_action):
    """Test block URL with missing URL parameter."""
    result = await block_url_action.execute()

    assert result["status"] == "error"
    assert "url" in result["error"].lower()


@pytest.mark.asyncio
async def test_block_url_missing_credentials(block_url_action):
    """Test block URL with missing credentials."""
    block_url_action.credentials = {}

    result = await block_url_action.execute(url="malicious.com")

    assert result["status"] == "error"
    assert "credentials" in result["error"].lower()


# ============================================================================
# UNBLOCK URL TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unblock_url_success(unblock_url_action):
    """Test successful URL unblocking."""
    mock_auth_response = MagicMock()
    mock_auth_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><key>test-api-key-123</key></result>
    </response>"""
    mock_auth_response.raise_for_status = MagicMock()

    mock_version_response = MagicMock()
    mock_version_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><system><sw-version>10.2.1</sw-version></system></result>
    </response>"""
    mock_version_response.raise_for_status = MagicMock()

    mock_success_response = MagicMock()
    mock_success_response.text = """<?xml version="1.0"?>
    <response status="success"></response>"""
    mock_success_response.raise_for_status = MagicMock()

    mock_commit_response = MagicMock()
    mock_commit_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job>123</job></result>
    </response>"""
    mock_commit_response.raise_for_status = MagicMock()

    mock_job_response = MagicMock()
    mock_job_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job><status>FIN</status></job></result>
    </response>"""
    mock_job_response.raise_for_status = MagicMock()

    mock_responses = [
        mock_auth_response,
        mock_version_response,
        mock_success_response,  # Delete URL
        mock_commit_response,  # Commit
        mock_job_response,  # Job status
    ]

    unblock_url_action.http_request = AsyncMock(side_effect=mock_responses)
    result = await unblock_url_action.execute(url="malicious.com")

    assert result["status"] == "success"
    assert result["url"] == "malicious.com"


@pytest.mark.asyncio
async def test_unblock_url_missing_parameter(unblock_url_action):
    """Test unblock URL with missing URL parameter."""
    result = await unblock_url_action.execute()

    assert result["status"] == "error"
    assert "url" in result["error"].lower()


# ============================================================================
# BLOCK APPLICATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_block_application_success(block_application_action):
    """Test successful application blocking."""
    mock_auth_response = MagicMock()
    mock_auth_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><key>test-api-key-123</key></result>
    </response>"""
    mock_auth_response.raise_for_status = MagicMock()

    mock_version_response = MagicMock()
    mock_version_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><system><sw-version>10.2.1</sw-version></system></result>
    </response>"""
    mock_version_response.raise_for_status = MagicMock()

    mock_success_response = MagicMock()
    mock_success_response.text = """<?xml version="1.0"?>
    <response status="success"></response>"""
    mock_success_response.raise_for_status = MagicMock()

    mock_commit_response = MagicMock()
    mock_commit_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job>123</job></result>
    </response>"""
    mock_commit_response.raise_for_status = MagicMock()

    mock_job_response = MagicMock()
    mock_job_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job><status>FIN</status></job></result>
    </response>"""
    mock_job_response.raise_for_status = MagicMock()

    mock_responses = [
        mock_auth_response,
        mock_version_response,
        mock_success_response,  # App group
        mock_success_response,  # Create policy
        mock_success_response,  # Move policy
        mock_commit_response,  # Commit
        mock_job_response,  # Job status
    ]

    block_application_action.http_request = AsyncMock(side_effect=mock_responses)
    result = await block_application_action.execute(application="bittorrent")

    assert result["status"] == "success"
    assert result["application"] == "bittorrent"


@pytest.mark.asyncio
async def test_block_application_missing_parameter(block_application_action):
    """Test block application with missing parameter."""
    result = await block_application_action.execute()

    assert result["status"] == "error"
    assert "application" in result["error"].lower()


# ============================================================================
# UNBLOCK APPLICATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unblock_application_success(unblock_application_action):
    """Test successful application unblocking."""
    mock_auth_response = MagicMock()
    mock_auth_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><key>test-api-key-123</key></result>
    </response>"""
    mock_auth_response.raise_for_status = MagicMock()

    mock_version_response = MagicMock()
    mock_version_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><system><sw-version>10.2.1</sw-version></system></result>
    </response>"""
    mock_version_response.raise_for_status = MagicMock()

    mock_success_response = MagicMock()
    mock_success_response.text = """<?xml version="1.0"?>
    <response status="success"></response>"""
    mock_success_response.raise_for_status = MagicMock()

    mock_commit_response = MagicMock()
    mock_commit_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job>123</job></result>
    </response>"""
    mock_commit_response.raise_for_status = MagicMock()

    mock_job_response = MagicMock()
    mock_job_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job><status>FIN</status></job></result>
    </response>"""
    mock_job_response.raise_for_status = MagicMock()

    mock_responses = [
        mock_auth_response,
        mock_version_response,
        mock_success_response,  # Delete app
        mock_commit_response,  # Commit
        mock_job_response,  # Job status
    ]

    unblock_application_action.http_request = AsyncMock(side_effect=mock_responses)
    result = await unblock_application_action.execute(application="bittorrent")

    assert result["status"] == "success"
    assert result["application"] == "bittorrent"


# ============================================================================
# BLOCK IP TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_block_ip_success(block_ip_action):
    """Test successful IP blocking."""
    mock_auth_response = MagicMock()
    mock_auth_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><key>test-api-key-123</key></result>
    </response>"""
    mock_auth_response.raise_for_status = MagicMock()

    mock_version_response = MagicMock()
    mock_version_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><system><sw-version>10.2.1</sw-version></system></result>
    </response>"""
    mock_version_response.raise_for_status = MagicMock()

    mock_success_response = MagicMock()
    mock_success_response.text = """<?xml version="1.0"?>
    <response status="success"></response>"""
    mock_success_response.raise_for_status = MagicMock()

    mock_commit_response = MagicMock()
    mock_commit_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job>123</job></result>
    </response>"""
    mock_commit_response.raise_for_status = MagicMock()

    mock_job_response = MagicMock()
    mock_job_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job><status>FIN</status></job></result>
    </response>"""
    mock_job_response.raise_for_status = MagicMock()

    mock_responses = [
        mock_auth_response,
        mock_version_response,
        mock_success_response,  # Tag
        mock_success_response,  # Address
        mock_success_response,  # Address group
        mock_success_response,  # Create policy
        mock_success_response,  # Move policy
        mock_commit_response,  # Commit
        mock_job_response,  # Job status
    ]

    block_ip_action.http_request = AsyncMock(side_effect=mock_responses)
    result = await block_ip_action.execute(ip="192.168.1.100")

    assert result["status"] == "success"
    assert result["ip"] == "192.168.1.100"


@pytest.mark.asyncio
async def test_block_ip_missing_parameter(block_ip_action):
    """Test block IP with missing parameter."""
    result = await block_ip_action.execute()

    assert result["status"] == "error"
    assert "ip" in result["error"].lower()


@pytest.mark.asyncio
async def test_block_ip_cidr_format(block_ip_action):
    """Test block IP with CIDR format."""
    mock_auth_response = MagicMock()
    mock_auth_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><key>test-api-key-123</key></result>
    </response>"""
    mock_auth_response.raise_for_status = MagicMock()

    mock_version_response = MagicMock()
    mock_version_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><system><sw-version>10.2.1</sw-version></system></result>
    </response>"""
    mock_version_response.raise_for_status = MagicMock()

    mock_success_response = MagicMock()
    mock_success_response.text = """<?xml version="1.0"?>
    <response status="success"></response>"""
    mock_success_response.raise_for_status = MagicMock()

    mock_commit_response = MagicMock()
    mock_commit_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job>123</job></result>
    </response>"""
    mock_commit_response.raise_for_status = MagicMock()

    mock_job_response = MagicMock()
    mock_job_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job><status>FIN</status></job></result>
    </response>"""
    mock_job_response.raise_for_status = MagicMock()

    mock_responses = [
        mock_auth_response,
        mock_version_response,
        mock_success_response,  # Tag
        mock_success_response,  # Address
        mock_success_response,  # Address group
        mock_success_response,  # Create policy
        mock_success_response,  # Move policy
        mock_commit_response,  # Commit
        mock_job_response,  # Job status
    ]

    block_ip_action.http_request = AsyncMock(side_effect=mock_responses)
    result = await block_ip_action.execute(ip="192.168.1.0/24")

    assert result["status"] == "success"
    assert result["ip"] == "192.168.1.0/24"


# ============================================================================
# UNBLOCK IP TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unblock_ip_success(unblock_ip_action):
    """Test successful IP unblocking."""
    mock_auth_response = MagicMock()
    mock_auth_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><key>test-api-key-123</key></result>
    </response>"""
    mock_auth_response.raise_for_status = MagicMock()

    mock_version_response = MagicMock()
    mock_version_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><system><sw-version>10.2.1</sw-version></system></result>
    </response>"""
    mock_version_response.raise_for_status = MagicMock()

    mock_success_response = MagicMock()
    mock_success_response.text = """<?xml version="1.0"?>
    <response status="success"></response>"""
    mock_success_response.raise_for_status = MagicMock()

    mock_commit_response = MagicMock()
    mock_commit_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job>123</job></result>
    </response>"""
    mock_commit_response.raise_for_status = MagicMock()

    mock_job_response = MagicMock()
    mock_job_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><job><status>FIN</status></job></result>
    </response>"""
    mock_job_response.raise_for_status = MagicMock()

    mock_responses = [
        mock_auth_response,
        mock_version_response,
        mock_success_response,  # Delete IP
        mock_commit_response,  # Commit
        mock_job_response,  # Job status
    ]

    unblock_ip_action.http_request = AsyncMock(side_effect=mock_responses)
    result = await unblock_ip_action.execute(ip="192.168.1.100")

    assert result["status"] == "success"
    assert result["ip"] == "192.168.1.100"


# ============================================================================
# LIST APPLICATIONS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_applications_success(list_applications_action):
    """Test successful application listing."""
    mock_auth_response = MagicMock()
    mock_auth_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><key>test-api-key-123</key></result>
    </response>"""
    mock_auth_response.raise_for_status = MagicMock()

    mock_version_response = MagicMock()
    mock_version_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><system><sw-version>10.2.1</sw-version></system></result>
    </response>"""
    mock_version_response.raise_for_status = MagicMock()

    mock_apps_response = MagicMock()
    mock_apps_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result>
            <application>
                <entry name="ssh">
                    <category>general-internet</category>
                </entry>
                <entry name="http">
                    <category>general-internet</category>
                </entry>
            </application>
        </result>
    </response>"""
    mock_apps_response.raise_for_status = MagicMock()

    mock_custom_response = MagicMock()
    mock_custom_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result></result>
    </response>"""
    mock_custom_response.raise_for_status = MagicMock()

    mock_responses = [
        mock_auth_response,
        mock_version_response,
        mock_apps_response,  # Predefined apps
        mock_custom_response,  # Custom apps
    ]

    list_applications_action.http_request = AsyncMock(side_effect=mock_responses)
    result = await list_applications_action.execute()

    assert result["status"] == "success"
    assert result["total_applications"] == 2
    assert len(result["applications"]) == 2


@pytest.mark.asyncio
async def test_list_applications_empty_result(list_applications_action):
    """Test application listing with empty result."""
    mock_auth_response = MagicMock()
    mock_auth_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><key>test-api-key-123</key></result>
    </response>"""
    mock_auth_response.raise_for_status = MagicMock()

    mock_version_response = MagicMock()
    mock_version_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result><system><sw-version>10.2.1</sw-version></system></result>
    </response>"""
    mock_version_response.raise_for_status = MagicMock()

    mock_apps_response = MagicMock()
    mock_apps_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result></result>
    </response>"""
    mock_apps_response.raise_for_status = MagicMock()

    mock_custom_response = MagicMock()
    mock_custom_response.text = """<?xml version="1.0"?>
    <response status="success">
        <result></result>
    </response>"""
    mock_custom_response.raise_for_status = MagicMock()

    mock_responses = [
        mock_auth_response,
        mock_version_response,
        mock_apps_response,
        mock_custom_response,
    ]

    list_applications_action.http_request = AsyncMock(side_effect=mock_responses)
    result = await list_applications_action.execute()

    assert result["status"] == "success"
    assert result["total_applications"] == 0

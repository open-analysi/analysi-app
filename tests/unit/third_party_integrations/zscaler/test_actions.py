"""Unit tests for ZScaler integration actions.

Tests cover:
- Health check
- URL/IP lookup
- URL/IP blocking and unblocking
- URL category listing
- Sandbox report retrieval
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.zscaler.actions import (
    BlockIpAction,
    BlockUrlAction,
    GetReportAction,
    HealthCheckAction,
    ListUrlCategoriesAction,
    LookupIpAction,
    LookupUrlAction,
    UnblockIpAction,
    UnblockUrlAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def integration_id():
    """Integration ID for testing."""
    return "test-zscaler-integration"


@pytest.fixture
def credentials():
    """Test credentials."""
    return {
        "username": "test_user",
        "password": "test_password",
        "api_key": "0123456789abcdefghijklmnopqrstuvwxyz0123456789",
        "sandbox_api_token": "sandbox_token",
    }


@pytest.fixture
def settings():
    """Test settings."""
    return {
        "base_url": "https://admin.test.net",
        "sandbox_base_url": "https://sandbox.test.net",
        "timeout": 30,
    }


@pytest.fixture
def health_check_action(integration_id, credentials, settings):
    """HealthCheckAction instance."""
    return HealthCheckAction(integration_id, "health_check", settings, credentials)


@pytest.fixture
def lookup_url_action(integration_id, credentials, settings):
    """LookupUrlAction instance."""
    return LookupUrlAction(integration_id, "lookup_url", settings, credentials)


@pytest.fixture
def lookup_ip_action(integration_id, credentials, settings):
    """LookupIpAction instance."""
    return LookupIpAction(integration_id, "lookup_ip", settings, credentials)


@pytest.fixture
def block_url_action(integration_id, credentials, settings):
    """BlockUrlAction instance."""
    return BlockUrlAction(integration_id, "block_url", settings, credentials)


@pytest.fixture
def unblock_url_action(integration_id, credentials, settings):
    """UnblockUrlAction instance."""
    return UnblockUrlAction(integration_id, "unblock_url", settings, credentials)


@pytest.fixture
def block_ip_action(integration_id, credentials, settings):
    """BlockIpAction instance."""
    return BlockIpAction(integration_id, "block_ip", settings, credentials)


@pytest.fixture
def unblock_ip_action(integration_id, credentials, settings):
    """UnblockIpAction instance."""
    return UnblockIpAction(integration_id, "unblock_ip", settings, credentials)


@pytest.fixture
def list_categories_action(integration_id, credentials, settings):
    """ListUrlCategoriesAction instance."""
    return ListUrlCategoriesAction(
        integration_id, "list_url_categories", settings, credentials
    )


@pytest.fixture
def get_report_action(integration_id, credentials, settings):
    """GetReportAction instance."""
    return GetReportAction(integration_id, "get_report", settings, credentials)


# ============================================================================
# HELPERS
# ============================================================================


def _auth_response():
    """Create a mock authentication response with session cookie."""
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {"Set-Cookie": "JSESSIONID=test_session; Path=/"}
    resp.raise_for_status = MagicMock()
    return resp


def _close_response():
    """Create a mock session close response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    return resp


def _json_response(data, status_code=200):
    """Create a mock JSON response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"Content-Type": "application/json"}
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


def _empty_response(status_code=204):
    """Create a mock empty response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"Content-Type": "application/json"}
    resp.raise_for_status = MagicMock()
    return resp


def _http_status_error(status_code: int, body: str = "Not Found"):
    """Create an httpx.HTTPStatusError for the given status code."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = body
    mock_response.json.side_effect = Exception("not json")
    request = httpx.Request("GET", "https://test.example.com")
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=request,
        response=mock_response,
    )


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    # Sequence: authenticate -> close session
    health_check_action.http_request = AsyncMock(
        side_effect=[_auth_response(), _close_response()]
    )
    result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True
    assert "accessible" in result["message"].lower()


@pytest.mark.asyncio
async def test_health_check_missing_credentials(integration_id, settings):
    """Test health check with missing credentials."""
    incomplete_credentials = {
        "base_url": "https://admin.test.net",
        # Missing username, password, api_key
    }
    action = HealthCheckAction(
        integration_id, "health_check", settings, incomplete_credentials
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert result["error_type"] == "ConfigurationError"
    assert "missing" in result["error"].lower()


@pytest.mark.asyncio
async def test_health_check_authentication_failed(health_check_action):
    """Test health check with authentication failure."""
    # Simulate authentication failure - the session gets no cookie
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {}  # No Set-Cookie header
    mock_response.raise_for_status = MagicMock()

    health_check_action.http_request = AsyncMock(return_value=mock_response)
    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert result["error_type"] == "AuthenticationError"


# ============================================================================
# LOOKUP URL TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_lookup_url_success(lookup_url_action):
    """Test successful URL lookup."""
    lookup_data = [
        {"url": "example.com", "urlClassifications": ["BUSINESS_AND_ECONOMY"]},
        {"url": "malicious.com", "urlClassifications": ["MALWARE"]},
    ]
    blocklist_data = {"blacklistUrls": ["malicious.com"]}

    # Sequence: auth -> lookup -> blocklist -> close
    lookup_url_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(lookup_data),
            _json_response(blocklist_data),
            _close_response(),
        ]
    )
    result = await lookup_url_action.execute(url="example.com,malicious.com")

    assert result["status"] == "success"
    assert result["total_urls"] == 2
    assert len(result["urls"]) == 2
    # Check blocklist annotation
    malicious_entry = next(u for u in result["urls"] if u["url"] == "malicious.com")
    assert malicious_entry["blocklisted"] is True
    example_entry = next(u for u in result["urls"] if u["url"] == "example.com")
    assert example_entry["blocklisted"] is False


@pytest.mark.asyncio
async def test_lookup_url_missing_parameter(lookup_url_action):
    """Test URL lookup with missing parameter."""
    result = await lookup_url_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "url" in result["error"].lower()


@pytest.mark.asyncio
async def test_lookup_url_protocol_truncation(lookup_url_action):
    """Test URL lookup with protocol truncation."""
    lookup_data = [{"url": "example.com"}]
    blocklist_data = {"blacklistUrls": []}

    # Sequence: auth -> lookup -> blocklist -> close
    lookup_url_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(lookup_data),
            _json_response(blocklist_data),
            _close_response(),
        ]
    )
    # Submit URL with protocol
    result = await lookup_url_action.execute(url="https://example.com")

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_lookup_url_too_long(lookup_url_action):
    """Test URL lookup with URL exceeding max length."""
    long_url = "example.com/" + ("a" * 1100)  # Exceeds 1024 char limit

    result = await lookup_url_action.execute(url=long_url)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "length" in result["error"].lower()


@pytest.mark.asyncio
async def test_lookup_url_404_returns_not_found(lookup_url_action):
    """Test URL lookup returns not_found on 404 instead of error."""
    # Sequence: auth -> lookup (404) -> close
    lookup_url_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _http_status_error(404),
            _close_response(),
        ]
    )
    result = await lookup_url_action.execute(url="nonexistent.example.com")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["total_urls"] == 0
    assert result["urls"] == []


# ============================================================================
# LOOKUP IP TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_lookup_ip_success(lookup_ip_action):
    """Test successful IP lookup."""
    lookup_data = [{"url": "1.2.3.4", "urlClassifications": ["UNKNOWN"]}]
    blocklist_data = {"blacklistUrls": []}

    # Sequence: auth -> lookup -> blocklist -> close
    lookup_ip_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(lookup_data),
            _json_response(blocklist_data),
            _close_response(),
        ]
    )
    result = await lookup_ip_action.execute(ip="1.2.3.4")

    assert result["status"] == "success"
    assert result["total_ips"] == 1


@pytest.mark.asyncio
async def test_lookup_ip_missing_parameter(lookup_ip_action):
    """Test IP lookup with missing parameter."""
    result = await lookup_ip_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "ip" in result["error"].lower()


@pytest.mark.asyncio
async def test_lookup_ip_404_returns_not_found(lookup_ip_action):
    """Test IP lookup returns not_found on 404 instead of error."""
    # Sequence: auth -> lookup (404) -> close
    lookup_ip_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _http_status_error(404),
            _close_response(),
        ]
    )
    result = await lookup_ip_action.execute(ip="192.0.2.1")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["total_ips"] == 0
    assert result["ips"] == []


# ============================================================================
# BLOCK URL TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_block_url_success_blocklist(block_url_action):
    """Test successful URL blocking via blocklist."""
    get_blocklist_data = {"blacklistUrls": []}
    update_response = _empty_response(204)

    # Sequence: auth -> get blocklist -> update blocklist -> close
    block_url_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(get_blocklist_data),
            update_response,
            _close_response(),
        ]
    )
    result = await block_url_action.execute(url="malicious.com")

    assert result["status"] == "success"
    assert "malicious.com" in result["updated"]
    assert len(result["ignored"]) == 0


@pytest.mark.asyncio
async def test_block_url_already_blocked(block_url_action):
    """Test blocking URL that's already in blocklist."""
    get_blocklist_data = {"blacklistUrls": ["malicious.com"]}

    # Sequence: auth -> get blocklist (already contains URL) -> close
    block_url_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(get_blocklist_data),
            _close_response(),
        ]
    )
    result = await block_url_action.execute(url="malicious.com")

    assert result["status"] == "success"
    assert len(result["updated"]) == 0
    assert "malicious.com" in result["ignored"]
    assert "contains all" in result["message"].lower()


@pytest.mark.asyncio
async def test_block_url_missing_parameter(block_url_action):
    """Test URL blocking with missing parameter."""
    result = await block_url_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "url" in result["error"].lower()


# ============================================================================
# UNBLOCK URL TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unblock_url_success(unblock_url_action):
    """Test successful URL unblocking."""
    get_blocklist_data = {"blacklistUrls": ["malicious.com"]}
    update_response = _empty_response(204)

    # Sequence: auth -> get blocklist -> update blocklist -> close
    unblock_url_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(get_blocklist_data),
            update_response,
            _close_response(),
        ]
    )
    result = await unblock_url_action.execute(url="malicious.com")

    assert result["status"] == "success"
    assert "malicious.com" in result["updated"]


@pytest.mark.asyncio
async def test_unblock_url_not_blocked(unblock_url_action):
    """Test unblocking URL that's not in blocklist."""
    get_blocklist_data = {"blacklistUrls": []}

    # Sequence: auth -> get blocklist (doesn't contain URL) -> close
    unblock_url_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(get_blocklist_data),
            _close_response(),
        ]
    )
    result = await unblock_url_action.execute(url="example.com")

    assert result["status"] == "success"
    assert len(result["updated"]) == 0
    assert "example.com" in result["ignored"]


# ============================================================================
# BLOCK/UNBLOCK IP TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_block_ip_success(block_ip_action):
    """Test successful IP blocking.

    BlockIpAction internally creates a new BlockUrlAction, so we need to
    patch http_request at the class level.
    """
    get_blocklist_data = {"blacklistUrls": []}
    update_response = _empty_response(204)

    mock_http = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(get_blocklist_data),
            update_response,
            _close_response(),
        ]
    )
    with patch.object(IntegrationAction, "http_request", mock_http):
        result = await block_ip_action.execute(ip="1.2.3.4")

    assert result["status"] == "success"
    assert "1.2.3.4" in result["updated"]


@pytest.mark.asyncio
async def test_unblock_ip_success(unblock_ip_action):
    """Test successful IP unblocking.

    UnblockIpAction internally creates a new UnblockUrlAction, so we need to
    patch http_request at the class level.
    """
    get_blocklist_data = {"blacklistUrls": ["1.2.3.4"]}
    update_response = _empty_response(204)

    mock_http = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(get_blocklist_data),
            update_response,
            _close_response(),
        ]
    )
    with patch.object(IntegrationAction, "http_request", mock_http):
        result = await unblock_ip_action.execute(ip="1.2.3.4")

    assert result["status"] == "success"
    assert "1.2.3.4" in result["updated"]


# ============================================================================
# LIST URL CATEGORIES TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_url_categories_success(list_categories_action):
    """Test successful URL category listing."""
    categories_data = [
        {
            "id": "CUSTOM_01",
            "configuredName": "Custom Category 1",
            "urls": ["example.com"],
        },
        {
            "id": "CUSTOM_02",
            "configuredName": "Custom Category 2",
            "urls": ["test.com"],
        },
    ]

    # Sequence: auth -> get categories -> close
    list_categories_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(categories_data),
            _close_response(),
        ]
    )
    result = await list_categories_action.execute()

    assert result["status"] == "success"
    assert result["total_url_categories"] == 2
    assert len(result["categories"]) == 2


@pytest.mark.asyncio
async def test_list_url_categories_ids_only(list_categories_action):
    """Test URL category listing with IDs and names only."""
    categories_data = [
        {
            "id": "CUSTOM_01",
            "configuredName": "Custom Category 1",
            "urls": ["example.com"],
        },
        {
            "id": "CUSTOM_02",
            "configuredName": "Custom Category 2",
            "urls": ["test.com"],
        },
    ]

    # Sequence: auth -> get categories -> close
    list_categories_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(categories_data),
            _close_response(),
        ]
    )
    result = await list_categories_action.execute(get_ids_and_names_only=True)

    assert result["status"] == "success"
    assert len(result["categories"]) == 2
    # Should only have id and configuredName
    for cat in result["categories"]:
        assert "id" in cat
        assert "configuredName" in cat
        assert "urls" not in cat


# ============================================================================
# GET SANDBOX REPORT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_report_success(get_report_action):
    """Test successful sandbox report retrieval."""
    report_data = {
        "Full Details": {
            "Summary": {
                "Status": "COMPLETED",
                "Category": "MALWARE",
            }
        }
    }

    # Sequence: auth -> get report -> close
    get_report_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(report_data),
            _close_response(),
        ]
    )
    result = await get_report_action.execute(file_hash="abc123def456")

    assert result["status"] == "success"
    assert result["file_hash"] == "abc123def456"
    assert "report" in result


@pytest.mark.asyncio
async def test_get_report_unknown_md5(get_report_action):
    """Test sandbox report for unknown MD5."""
    report_data = {
        "Full Details": "md5 is unknown or analysis has yet not been completed"
    }

    # Sequence: auth -> get report -> close
    get_report_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _json_response(report_data),
            _close_response(),
        ]
    )
    result = await get_report_action.execute(file_hash="unknown123")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "unknown" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_report_missing_parameter(get_report_action):
    """Test sandbox report with missing parameter."""
    result = await get_report_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "file_hash" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_report_404_returns_not_found(get_report_action):
    """Test sandbox report returns not_found on 404 instead of error."""
    # Sequence: auth -> get report (404) -> close
    get_report_action.http_request = AsyncMock(
        side_effect=[
            _auth_response(),
            _http_status_error(404),
            _close_response(),
        ]
    )
    result = await get_report_action.execute(file_hash="deadbeef123")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["file_hash"] == "deadbeef123"

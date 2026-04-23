"""Unit tests for CyberArk PAM integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.cyberark.actions import (
    AddAccountAction,
    ChangeCredentialAction,
    GetAccountAction,
    GetSafeAction,
    GetUserAction,
    HealthCheckAction,
    ListAccountsAction,
    ListSafesAction,
    _authenticate,
    _logoff,
    _make_cyberark_request,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def cyberark_credentials():
    """CyberArk test credentials."""
    return {
        "username": "admin",
        "password": "S3cureP@ss!",
    }


@pytest.fixture
def cyberark_settings():
    """CyberArk test settings."""
    return {
        "auth_method": "CyberArk",
        "base_url": "https://pvwa.test.com",
        "timeout": 30,
        "verify_ssl": True,
    }


def _make_action(cls, credentials=None, settings=None, action_id=None):
    """Helper to create an action instance with test defaults."""
    if settings is None:
        settings = {
            "auth_method": "CyberArk",
            "base_url": "https://pvwa.test.com",
            "timeout": 30,
        }
    if credentials is None:
        credentials = {
            "username": "admin",
            "password": "S3cureP@ss!",
        }
    return cls(
        integration_id="cyberark",
        action_id=action_id or cls.__name__.lower().replace("action", ""),
        settings=settings,
        credentials=credentials,
    )


def _mock_logon_response(token="mock-session-token-12345"):
    """Create a mock response for the CyberArk Logon endpoint."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = 200
    mock.text = f'"{token}"'
    mock.json.return_value = token
    return mock


def _mock_json_response(data, status_code=200):
    """Create a mock JSON response."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.json.return_value = data
    mock.text = str(data)
    return mock


def _mock_empty_response(status_code=204):
    """Create a mock empty response (e.g., 204 No Content)."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.text = ""
    return mock


# ============================================================================
# AUTHENTICATION HELPER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_authenticate_success():
    """Test successful CyberArk authentication."""
    action = _make_action(HealthCheckAction)
    logon_response = _mock_logon_response("session-abc-123")

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=logon_response
    ):
        ok, result = await _authenticate(
            action, "https://pvwa.test.com", "admin", "pass", "CyberArk", 30
        )

    assert ok is True
    assert result == "session-abc-123"


@pytest.mark.asyncio
async def test_authenticate_http_error():
    """Test authentication failure with HTTP error."""
    action = _make_action(HealthCheckAction)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    mock_resp.json.return_value = {"Details": "Invalid credentials"}

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_resp
        ),
    ):
        ok, result = await _authenticate(
            action, "https://pvwa.test.com", "admin", "bad", "CyberArk", 30
        )

    assert ok is False
    assert "error" in result
    assert "Invalid credentials" in result["error"]


@pytest.mark.asyncio
async def test_authenticate_timeout():
    """Test authentication timeout."""
    action = _make_action(HealthCheckAction)

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Connection timed out"),
    ):
        ok, result = await _authenticate(
            action, "https://pvwa.test.com", "admin", "pass", "CyberArk", 5
        )

    assert ok is False
    assert "timed out" in result["error"]


@pytest.mark.asyncio
async def test_authenticate_empty_token():
    """Test authentication returning empty token."""
    action = _make_action(HealthCheckAction)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = '""'

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_resp
    ):
        ok, result = await _authenticate(
            action, "https://pvwa.test.com", "admin", "pass", "CyberArk", 30
        )

    assert ok is False
    assert "error" in result


@pytest.mark.asyncio
async def test_logoff_success():
    """Test successful logoff (best-effort)."""
    action = _make_action(HealthCheckAction)
    mock_resp = _mock_empty_response()

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_resp
    ):
        # Should not raise
        await _logoff(action, "https://pvwa.test.com", "token123", 30)


@pytest.mark.asyncio
async def test_logoff_failure_does_not_raise():
    """Test that logoff failure is silently logged, not raised."""
    action = _make_action(HealthCheckAction)

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        # Should not raise even on error
        await _logoff(action, "https://pvwa.test.com", "token123", 30)


# ============================================================================
# API REQUEST HELPER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_make_cyberark_request_success():
    """Test successful API request."""
    action = _make_action(HealthCheckAction)
    mock_resp = _mock_json_response({"id": "acc123", "name": "TestAccount"})

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_resp
    ):
        ok, data, resp = await _make_cyberark_request(
            action,
            "https://pvwa.test.com",
            "token",
            "/PasswordVault/API/Accounts/acc123",
        )

    assert ok is True
    assert data["id"] == "acc123"
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_make_cyberark_request_204():
    """Test API request returning 204 No Content."""
    action = _make_action(HealthCheckAction)
    mock_resp = _mock_empty_response(204)

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_resp
    ):
        ok, data, resp = await _make_cyberark_request(
            action,
            "https://pvwa.test.com",
            "token",
            "/PasswordVault/API/Accounts/acc123",
            method="POST",
        )

    assert ok is True
    assert data == {}


@pytest.mark.asyncio
async def test_make_cyberark_request_http_error():
    """Test API request with HTTP status error."""
    action = _make_action(HealthCheckAction)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"
    mock_resp.json.return_value = {"Details": "Account not found"}

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_resp
        ),
    ):
        ok, data, resp = await _make_cyberark_request(
            action,
            "https://pvwa.test.com",
            "token",
            "/PasswordVault/API/Accounts/missing",
        )

    assert ok is False
    assert "Account not found" in data["error"]
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_make_cyberark_request_timeout():
    """Test API request timeout."""
    action = _make_action(HealthCheckAction)

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Timed out"),
    ):
        ok, data, resp = await _make_cyberark_request(
            action, "https://pvwa.test.com", "token", "/PasswordVault/API/Accounts"
        )

    assert ok is False
    assert "timed out" in data["error"]
    assert resp is None


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(cyberark_credentials, cyberark_settings):
    """Test successful health check."""
    action = _make_action(HealthCheckAction, cyberark_credentials, cyberark_settings)

    logon_resp = _mock_logon_response()
    verify_resp = _mock_json_response({"ServerName": "PVWA01", "ServerId": "abc123"})
    logoff_resp = _mock_empty_response()

    call_count = 0

    async def mock_http(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "Logon" in url:
            return logon_resp
        if "verify" in url:
            return verify_resp
        if "Logoff" in url:
            return logoff_resp
        return verify_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert result["data"]["auth_method"] == "CyberArk"
    assert "integration_id" in result
    assert result["integration_id"] == "cyberark"


@pytest.mark.asyncio
async def test_health_check_missing_base_url():
    """Test health check with missing base_url."""
    action = _make_action(
        HealthCheckAction,
        credentials={"username": "admin", "password": "pass"},
        settings={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "base_url" in result["error"]


@pytest.mark.asyncio
async def test_health_check_missing_username():
    """Test health check with missing username."""
    action = _make_action(
        HealthCheckAction,
        credentials={"password": "pass"},
        settings={"base_url": "https://pvwa.test.com"},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "username" in result["error"]


@pytest.mark.asyncio
async def test_health_check_missing_password():
    """Test health check with missing password."""
    action = _make_action(
        HealthCheckAction,
        credentials={"username": "admin"},
        settings={"base_url": "https://pvwa.test.com"},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "password" in result["error"]


@pytest.mark.asyncio
async def test_health_check_auth_failure(cyberark_credentials, cyberark_settings):
    """Test health check when authentication fails."""
    action = _make_action(HealthCheckAction, cyberark_credentials, cyberark_settings)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    mock_resp.json.return_value = {"Details": "Invalid credentials"}

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_resp
        ),
    ):
        result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_verify_endpoint_unavailable(
    cyberark_credentials, cyberark_settings
):
    """Test health check when verify endpoint is not available (older PVWA)."""
    action = _make_action(HealthCheckAction, cyberark_credentials, cyberark_settings)

    logon_resp = _mock_logon_response()
    logoff_resp = _mock_empty_response()

    mock_404_resp = MagicMock(spec=httpx.Response)
    mock_404_resp.status_code = 404
    mock_404_resp.text = "Not Found"

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "verify" in url:
            raise httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_404_resp
            )
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert "verify endpoint unavailable" in result["data"]["message"]


# ============================================================================
# GET ACCOUNT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_account_success(cyberark_credentials, cyberark_settings):
    """Test successful account retrieval."""
    action = _make_action(GetAccountAction, cyberark_credentials, cyberark_settings)

    account_data = {
        "id": "123_456",
        "name": "Operating System-WinServer-10.0.0.1-admin",
        "address": "10.0.0.1",
        "userName": "admin",
        "platformId": "WinServerLocal",
        "safeName": "Linux-Servers",
        "secretType": "password",
        "status": "success",
        "platformAccountProperties": {"LogonDomain": "MYDOM"},
        "createdTime": 1609459200,
    }

    logon_resp = _mock_logon_response()
    account_resp = _mock_json_response(account_data)
    logoff_resp = _mock_empty_response()

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Accounts/123_456" in url:
            return account_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(account_id="123_456")

    assert result["status"] == "success"
    assert result["data"]["id"] == "123_456"
    assert result["data"]["userName"] == "admin"
    assert result["data"]["platformId"] == "WinServerLocal"
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_get_account_missing_id(cyberark_credentials, cyberark_settings):
    """Test get account with missing account_id parameter."""
    action = _make_action(GetAccountAction, cyberark_credentials, cyberark_settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "account_id" in result["error"]


@pytest.mark.asyncio
async def test_get_account_auth_failure(cyberark_credentials, cyberark_settings):
    """Test get account when authentication fails."""
    action = _make_action(GetAccountAction, cyberark_credentials, cyberark_settings)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_resp.json.return_value = {"Details": "Token expired"}

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_resp
        ),
    ):
        result = await action.execute(account_id="123")

    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"


@pytest.mark.asyncio
async def test_get_account_api_error(cyberark_credentials, cyberark_settings):
    """Test get account with API error on the account endpoint."""
    action = _make_action(GetAccountAction, cyberark_credentials, cyberark_settings)

    logon_resp = _mock_logon_response()
    logoff_resp = _mock_empty_response()

    mock_500_resp = MagicMock(spec=httpx.Response)
    mock_500_resp.status_code = 500
    mock_500_resp.text = "Internal Server Error"
    mock_500_resp.json.return_value = {"Details": "Database error"}

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Accounts/" in url:
            raise httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=mock_500_resp
            )
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(account_id="123")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# LIST ACCOUNTS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_accounts_success(cyberark_credentials, cyberark_settings):
    """Test successful account listing."""
    action = _make_action(ListAccountsAction, cyberark_credentials, cyberark_settings)

    accounts_data = {
        "value": [
            {"id": "1", "name": "acc1", "safeName": "MySafe"},
            {"id": "2", "name": "acc2", "safeName": "MySafe"},
        ],
        "count": 2,
    }

    logon_resp = _mock_logon_response()
    accounts_resp = _mock_json_response(accounts_data)
    logoff_resp = _mock_empty_response()

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Accounts" in url and "Logon" not in url and "Logoff" not in url:
            return accounts_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(search="admin")

    assert result["status"] == "success"
    assert len(result["data"]["accounts"]) == 2
    assert result["data"]["total"] == 2


@pytest.mark.asyncio
async def test_list_accounts_with_safe_filter(cyberark_credentials, cyberark_settings):
    """Test account listing with safe_name filter."""
    action = _make_action(ListAccountsAction, cyberark_credentials, cyberark_settings)

    accounts_data = {
        "value": [
            {"id": "1", "name": "acc1", "safeName": "LinuxSafe"},
        ],
        "count": 1,
    }

    logon_resp = _mock_logon_response()
    accounts_resp = _mock_json_response(accounts_data)
    logoff_resp = _mock_empty_response()

    captured_params = {}

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Accounts" in url and "Logon" not in url and "Logoff" not in url:
            captured_params.update(kwargs.get("params", {}))
            return accounts_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(safe_name="LinuxSafe")

    assert result["status"] == "success"
    assert captured_params.get("filter") == "safeName eq LinuxSafe"


@pytest.mark.asyncio
async def test_list_accounts_empty_result(cyberark_credentials, cyberark_settings):
    """Test account listing with no results."""
    action = _make_action(ListAccountsAction, cyberark_credentials, cyberark_settings)

    accounts_data = {"value": [], "count": 0}

    logon_resp = _mock_logon_response()
    accounts_resp = _mock_json_response(accounts_data)
    logoff_resp = _mock_empty_response()

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Accounts" in url and "Logon" not in url and "Logoff" not in url:
            return accounts_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["accounts"] == []
    assert result["data"]["total"] == 0


@pytest.mark.asyncio
async def test_list_accounts_missing_credentials():
    """Test list accounts with missing credentials."""
    action = _make_action(
        ListAccountsAction,
        credentials={},
        settings={"base_url": "https://pvwa.test.com"},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


# ============================================================================
# CHANGE CREDENTIAL TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_change_credential_success(cyberark_credentials, cyberark_settings):
    """Test successful credential change initiation."""
    action = _make_action(
        ChangeCredentialAction, cyberark_credentials, cyberark_settings
    )

    logon_resp = _mock_logon_response()
    change_resp = _mock_empty_response(200)
    change_resp.json = MagicMock(return_value={})
    logoff_resp = _mock_empty_response()

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Change" in url:
            return change_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(account_id="acc-42")

    assert result["status"] == "success"
    assert result["data"]["account_id"] == "acc-42"
    assert "Credential change initiated" in result["data"]["message"]


@pytest.mark.asyncio
async def test_change_credential_missing_id(cyberark_credentials, cyberark_settings):
    """Test credential change with missing account_id."""
    action = _make_action(
        ChangeCredentialAction, cyberark_credentials, cyberark_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "account_id" in result["error"]


@pytest.mark.asyncio
async def test_change_credential_with_group_flag(
    cyberark_credentials, cyberark_settings
):
    """Test credential change with change_entire_group flag."""
    action = _make_action(
        ChangeCredentialAction, cyberark_credentials, cyberark_settings
    )

    logon_resp = _mock_logon_response()
    change_resp = _mock_json_response({})
    logoff_resp = _mock_empty_response()

    captured_json = {}

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Change" in url:
            captured_json.update(kwargs.get("json_data", {}) or {})
            return change_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(account_id="acc-42", change_entire_group=True)

    assert result["status"] == "success"
    assert captured_json.get("ChangeEntireGroup") is True


# ============================================================================
# GET SAFE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_safe_success(cyberark_credentials, cyberark_settings):
    """Test successful safe retrieval."""
    action = _make_action(GetSafeAction, cyberark_credentials, cyberark_settings)

    safe_data = {
        "safeName": "Linux-Servers",
        "description": "Linux server credentials",
        "numberOfDaysRetention": 7,
        "numberOfVersionsRetention": 5,
        "managingCPM": "PasswordManager",
    }

    logon_resp = _mock_logon_response()
    safe_resp = _mock_json_response(safe_data)
    logoff_resp = _mock_empty_response()

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Safes/Linux-Servers" in url:
            return safe_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(safe_name="Linux-Servers")

    assert result["status"] == "success"
    assert result["data"]["safeName"] == "Linux-Servers"
    assert result["data"]["managingCPM"] == "PasswordManager"


@pytest.mark.asyncio
async def test_get_safe_missing_name(cyberark_credentials, cyberark_settings):
    """Test get safe with missing safe_name."""
    action = _make_action(GetSafeAction, cyberark_credentials, cyberark_settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "safe_name" in result["error"]


@pytest.mark.asyncio
async def test_get_safe_not_found(cyberark_credentials, cyberark_settings):
    """Test get safe when safe does not exist (404 returns success with not_found)."""
    action = _make_action(GetSafeAction, cyberark_credentials, cyberark_settings)

    logon_resp = _mock_logon_response()
    logoff_resp = _mock_empty_response()

    mock_404_resp = MagicMock(spec=httpx.Response)
    mock_404_resp.status_code = 404
    mock_404_resp.text = "Not Found"
    mock_404_resp.json.return_value = {"Details": "Safe not found"}

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Safes/" in url and "Logon" not in url and "Logoff" not in url:
            raise httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_404_resp
            )
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(safe_name="NonExistentSafe")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["safe_name"] == "NonExistentSafe"


# ============================================================================
# LIST SAFES TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_safes_success(cyberark_credentials, cyberark_settings):
    """Test successful safe listing."""
    action = _make_action(ListSafesAction, cyberark_credentials, cyberark_settings)

    safes_data = {
        "value": [
            {"safeName": "Safe1", "description": "First safe"},
            {"safeName": "Safe2", "description": "Second safe"},
            {"safeName": "Safe3", "description": "Third safe"},
        ],
        "count": 3,
    }

    logon_resp = _mock_logon_response()
    safes_resp = _mock_json_response(safes_data)
    logoff_resp = _mock_empty_response()

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Safes" in url and "Logon" not in url and "Logoff" not in url:
            return safes_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(search="test")

    assert result["status"] == "success"
    assert len(result["data"]["safes"]) == 3
    assert result["data"]["total"] == 3


@pytest.mark.asyncio
async def test_list_safes_empty(cyberark_credentials, cyberark_settings):
    """Test safe listing with no results."""
    action = _make_action(ListSafesAction, cyberark_credentials, cyberark_settings)

    safes_data = {"value": [], "count": 0}

    logon_resp = _mock_logon_response()
    safes_resp = _mock_json_response(safes_data)
    logoff_resp = _mock_empty_response()

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Safes" in url and "Logon" not in url and "Logoff" not in url:
            return safes_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["safes"] == []
    assert result["data"]["total"] == 0


@pytest.mark.asyncio
async def test_list_safes_missing_credentials():
    """Test list safes with missing credentials."""
    action = _make_action(
        ListSafesAction,
        credentials={"username": "admin"},
        settings={"base_url": "https://pvwa.test.com"},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "password" in result["error"]


# ============================================================================
# ADD ACCOUNT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_add_account_success(cyberark_credentials, cyberark_settings):
    """Test successful account creation."""
    action = _make_action(AddAccountAction, cyberark_credentials, cyberark_settings)

    created_account = {
        "id": "new-acc-789",
        "name": "Operating System-WinServer-10.0.0.5-svcaccount",
        "address": "10.0.0.5",
        "userName": "svcaccount",
        "platformId": "WinServerLocal",
        "safeName": "Windows-Servers",
        "secretType": "password",
    }

    logon_resp = _mock_logon_response()
    create_resp = _mock_json_response(created_account, status_code=201)
    logoff_resp = _mock_empty_response()

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Accounts" in url and kwargs.get("method", "GET").upper() == "POST":
            return create_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(
            safe_name="Windows-Servers",
            platform_id="WinServerLocal",
            name="Operating System-WinServer-10.0.0.5-svcaccount",
            address="10.0.0.5",
            account_username="svcaccount",
            secret="InitialP@ss",
        )

    assert result["status"] == "success"
    assert result["data"]["id"] == "new-acc-789"
    assert result["data"]["safeName"] == "Windows-Servers"


@pytest.mark.asyncio
async def test_add_account_missing_safe_name(cyberark_credentials, cyberark_settings):
    """Test add account with missing safe_name."""
    action = _make_action(AddAccountAction, cyberark_credentials, cyberark_settings)

    result = await action.execute(platform_id="WinServerLocal", name="test")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "safe_name" in result["error"]


@pytest.mark.asyncio
async def test_add_account_missing_platform_id(cyberark_credentials, cyberark_settings):
    """Test add account with missing platform_id."""
    action = _make_action(AddAccountAction, cyberark_credentials, cyberark_settings)

    result = await action.execute(safe_name="MySafe", name="test")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "platform_id" in result["error"]


@pytest.mark.asyncio
async def test_add_account_missing_name(cyberark_credentials, cyberark_settings):
    """Test add account with missing name."""
    action = _make_action(AddAccountAction, cyberark_credentials, cyberark_settings)

    result = await action.execute(safe_name="MySafe", platform_id="WinServerLocal")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "name" in result["error"]


@pytest.mark.asyncio
async def test_add_account_with_properties(cyberark_credentials, cyberark_settings):
    """Test add account with platform-specific properties."""
    action = _make_action(AddAccountAction, cyberark_credentials, cyberark_settings)

    created_account = {
        "id": "prop-acc",
        "name": "test-acc",
        "safeName": "MySafe",
        "platformId": "WinServerLocal",
        "platformAccountProperties": {"LogonDomain": "CORP", "Port": "3389"},
    }

    logon_resp = _mock_logon_response()
    create_resp = _mock_json_response(created_account, status_code=201)
    logoff_resp = _mock_empty_response()

    captured_json = {}

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Accounts" in url and kwargs.get("method", "GET").upper() == "POST":
            captured_json.update(kwargs.get("json_data", {}) or {})
            return create_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(
            safe_name="MySafe",
            platform_id="WinServerLocal",
            name="test-acc",
            properties={"LogonDomain": "CORP", "Port": "3389"},
        )

    assert result["status"] == "success"
    assert captured_json["platformAccountProperties"] == {
        "LogonDomain": "CORP",
        "Port": "3389",
    }


# ============================================================================
# GET USER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_success(cyberark_credentials, cyberark_settings):
    """Test successful user retrieval."""
    action = _make_action(GetUserAction, cyberark_credentials, cyberark_settings)

    user_data = {
        "id": 42,
        "username": "john.doe",
        "source": "CyberArk",
        "userType": "EPVUser",
        "componentUser": False,
        "groupsMembership": [
            {"groupID": 1, "groupName": "Vault Admins"},
        ],
        "vaultAuthorization": ["AddSafes", "ManageServerFileCategories"],
        "location": "\\",
    }

    logon_resp = _mock_logon_response()
    user_resp = _mock_json_response(user_data)
    logoff_resp = _mock_empty_response()

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Users/42" in url:
            return user_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(user_id="42")

    assert result["status"] == "success"
    assert result["data"]["username"] == "john.doe"
    assert result["data"]["userType"] == "EPVUser"
    assert len(result["data"]["groupsMembership"]) == 1
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_get_user_missing_id(cyberark_credentials, cyberark_settings):
    """Test get user with missing user_id."""
    action = _make_action(GetUserAction, cyberark_credentials, cyberark_settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "user_id" in result["error"]


@pytest.mark.asyncio
async def test_get_user_not_found(cyberark_credentials, cyberark_settings):
    """Test get user when user does not exist (404 returns success with not_found)."""
    action = _make_action(GetUserAction, cyberark_credentials, cyberark_settings)

    logon_resp = _mock_logon_response()
    logoff_resp = _mock_empty_response()

    mock_404_resp = MagicMock(spec=httpx.Response)
    mock_404_resp.status_code = 404
    mock_404_resp.text = "Not Found"
    mock_404_resp.json.return_value = {"Details": "User not found"}

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Users/" in url and "Logon" not in url and "Logoff" not in url:
            raise httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_404_resp
            )
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(user_id="99999")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["user_id"] == "99999"


@pytest.mark.asyncio
async def test_get_user_auth_failure(cyberark_credentials, cyberark_settings):
    """Test get user when authentication fails."""
    action = _make_action(GetUserAction, cyberark_credentials, cyberark_settings)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_resp.json.return_value = {"Details": "Session expired"}

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_resp
        ),
    ):
        result = await action.execute(user_id="42")

    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"


# ============================================================================
# CREDENTIAL VALIDATION TESTS (shared across actions)
# ============================================================================


@pytest.mark.asyncio
async def test_all_actions_reject_empty_credentials():
    """Verify all actions return configuration error for empty credentials."""
    actions_needing_params = {
        GetAccountAction: {"account_id": "123"},
        ChangeCredentialAction: {"account_id": "123"},
        GetSafeAction: {"safe_name": "test"},
        GetUserAction: {"user_id": "42"},
        AddAccountAction: {"safe_name": "s", "platform_id": "p", "name": "n"},
    }
    actions_no_params = {
        HealthCheckAction: {},
        ListAccountsAction: {},
        ListSafesAction: {},
    }

    all_actions = {**actions_needing_params, **actions_no_params}

    for action_cls, params in all_actions.items():
        action = _make_action(
            action_cls,
            credentials={},
            settings={"base_url": "https://pvwa.test.com"},
        )
        result = await action.execute(**params)
        assert result["status"] == "error", (
            f"{action_cls.__name__} did not reject empty credentials"
        )
        assert result["error_type"] == "ConfigurationError", (
            f"{action_cls.__name__} wrong error_type: {result['error_type']}"
        )


# ============================================================================
# LOGOFF ALWAYS CALLED (session cleanup)
# ============================================================================


@pytest.mark.asyncio
async def test_logoff_called_even_on_api_error(cyberark_credentials, cyberark_settings):
    """Verify logoff is called even when the main API call fails."""
    action = _make_action(GetAccountAction, cyberark_credentials, cyberark_settings)

    logon_resp = _mock_logon_response()
    logoff_resp = _mock_empty_response()

    mock_500_resp = MagicMock(spec=httpx.Response)
    mock_500_resp.status_code = 500
    mock_500_resp.text = "Server Error"
    mock_500_resp.json.return_value = {"Details": "Internal error"}

    logoff_called = False

    async def mock_http(url, **kwargs):
        nonlocal logoff_called
        if "Logon" in url:
            return logon_resp
        if "Logoff" in url:
            logoff_called = True
            return logoff_resp
        if "Accounts/" in url:
            raise httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=mock_500_resp
            )
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        await action.execute(account_id="123")

    assert logoff_called, "Logoff was not called after API error"


# ============================================================================
# RESULT ENVELOPE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_success_result_has_standard_envelope(
    cyberark_credentials, cyberark_settings
):
    """Verify success results include integration_id, action_id, timestamp."""
    action = _make_action(GetUserAction, cyberark_credentials, cyberark_settings)

    user_data = {"id": 1, "username": "test"}

    logon_resp = _mock_logon_response()
    user_resp = _mock_json_response(user_data)
    logoff_resp = _mock_empty_response()

    async def mock_http(url, **kwargs):
        if "Logon" in url:
            return logon_resp
        if "Users/" in url:
            return user_resp
        if "Logoff" in url:
            return logoff_resp
        return logoff_resp

    with patch.object(action, "http_request", side_effect=mock_http):
        result = await action.execute(user_id="1")

    assert result["status"] == "success"
    assert result["integration_id"] == "cyberark"
    assert "timestamp" in result
    assert "action_id" in result


@pytest.mark.asyncio
async def test_error_result_has_standard_envelope():
    """Verify error results include integration_id, action_id, timestamp, error_type."""
    action = _make_action(
        GetUserAction,
        credentials={},
        settings={"base_url": "https://pvwa.test.com"},
    )

    result = await action.execute(user_id="42")

    assert result["status"] == "error"
    assert result["integration_id"] == "cyberark"
    assert "timestamp" in result
    assert "action_id" in result
    assert "error_type" in result
    assert "error" in result

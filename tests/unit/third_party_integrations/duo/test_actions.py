"""Unit tests for Duo Security integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.integrations.framework.integrations.duo.actions import (
    AuthorizeAction,
    HealthCheckAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_credentials():
    """Mock Duo credentials."""
    return {
        "ikey": "test-integration-key",
        "skey": "test-secret-key",
    }


@pytest.fixture
def mock_settings():
    """Mock Duo settings."""
    return {
        "api_host": "api-test.duosecurity.com",
        "timeout": 30,
        "verify_server_cert": True,
    }


@pytest.fixture
def health_check_action(mock_credentials, mock_settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction(
        integration_id="duo",
        action_id="health_check",
        settings=mock_settings,
        credentials=mock_credentials,
    )


@pytest.fixture
def authorize_action(mock_credentials, mock_settings):
    """Create AuthorizeAction instance."""
    return AuthorizeAction(
        integration_id="duo",
        action_id="authorize",
        settings=mock_settings,
        credentials=mock_credentials,
    )


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response_data = {"stat": "OK", "response": {"time": 1234567890}}

    mock_http_response = MagicMock()
    mock_http_response.json.return_value = mock_response_data

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True
    assert "Duo API is accessible" in result["message"]


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="duo",
        action_id="health_check",
        settings={},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert "Missing required credentials" in result["error"]
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_health_check_invalid_credentials(health_check_action):
    """Test health check with invalid credentials (401)."""
    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=Exception(
            "Invalid API credentials (integration key or secret key)"
        ),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert "Invalid API credentials" in result["error"]


@pytest.mark.asyncio
async def test_health_check_connection_error(health_check_action):
    """Test health check with connection error."""
    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=Exception("Failed to connect to Duo API"),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert "Failed to connect" in result["error"]


# ============================================================================
# AUTHORIZE ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_authorize_success(authorize_action):
    """Test successful authorization."""
    # Mock preauth response
    preauth_response = {
        "stat": "OK",
        "response": {
            "result": "auth",
            "status_msg": "Account is active",
            "devices": [{"device": "phone1", "type": "phone"}],
        },
    }

    # Mock auth response
    auth_response = {
        "stat": "OK",
        "response": {
            "result": "allow",
            "status": "allow",
            "status_msg": "Success. Logged in as user@example.com",
        },
    }

    # Mock the _make_duo_request helper function directly
    call_count = 0

    def _make_resp(data):
        r = MagicMock()
        r.json.return_value = data
        return r

    async def mock_duo_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # First call is preauth
            return _make_resp(preauth_response)
        # Second call is auth
        return _make_resp(auth_response)

    with patch.object(
        authorize_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=mock_duo_request,
    ):
        result = await authorize_action.execute(
            user="user@example.com", type="Test Request"
        )

    assert result["status"] == "success"
    assert result["result"] == "allow"
    assert result["user"] == "user@example.com"
    assert "authorized" in result["message"].lower()


@pytest.mark.asyncio
async def test_authorize_missing_user(authorize_action):
    """Test authorization with missing user parameter."""
    result = await authorize_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Missing required parameter 'user'" in result["error"]


@pytest.mark.asyncio
async def test_authorize_missing_credentials():
    """Test authorization with missing credentials."""
    action = AuthorizeAction(
        integration_id="duo",
        action_id="authorize",
        settings={},
        credentials={},
    )

    result = await action.execute(user="user@example.com")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


@pytest.mark.asyncio
async def test_authorize_user_not_permitted(authorize_action):
    """Test authorization when user is not permitted to authenticate."""
    preauth_response = {
        "stat": "OK",
        "response": {"result": "deny", "status_msg": "User is not enrolled"},
    }

    mock_http_response = MagicMock()
    mock_http_response.json.return_value = preauth_response

    with patch.object(
        authorize_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await authorize_action.execute(user="user@example.com")

    assert result["status"] == "error"
    assert result["error_type"] == "AuthorizationError"
    assert "not permitted to authenticate" in result["error"]


@pytest.mark.asyncio
async def test_authorize_user_denied(authorize_action):
    """Test authorization when user denies the push."""
    preauth_response = {
        "stat": "OK",
        "response": {"result": "auth", "status_msg": "Account is active"},
    }

    auth_response = {
        "stat": "OK",
        "response": {
            "result": "deny",
            "status": "deny",
            "status_msg": "User denied the request",
        },
    }

    call_count = 0

    def _make_resp(data):
        r = MagicMock()
        r.json.return_value = data
        return r

    async def mock_duo_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_resp(preauth_response)
        return _make_resp(auth_response)

    with patch.object(
        authorize_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=mock_duo_request,
    ):
        result = await authorize_action.execute(user="user@example.com")

    assert result["status"] == "error"
    assert result["error_type"] == "AuthorizationDenied"
    assert result["result"] == "deny"
    assert "not authorized" in result["error"].lower()


@pytest.mark.asyncio
async def test_authorize_with_optional_params(authorize_action):
    """Test authorization with optional parameters."""
    preauth_response = {
        "stat": "OK",
        "response": {"result": "auth", "status_msg": "Account is active"},
    }

    auth_response = {
        "stat": "OK",
        "response": {"result": "allow", "status": "allow", "status_msg": "Success"},
    }

    call_count = 0

    def _make_resp(data):
        r = MagicMock()
        r.json.return_value = data
        return r

    async def mock_duo_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_resp(preauth_response)
        return _make_resp(auth_response)

    with patch.object(
        authorize_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=mock_duo_request,
    ):
        result = await authorize_action.execute(
            user="user@example.com", type="Custom Request", info="Additional context"
        )

    assert result["status"] == "success"
    assert result["result"] == "allow"


@pytest.mark.asyncio
async def test_authorize_api_error(authorize_action):
    """Test authorization with API error."""
    with patch.object(
        authorize_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=Exception("API error occurred"),
    ):
        result = await authorize_action.execute(user="user@example.com")

    assert result["status"] == "error"
    assert "API error occurred" in result["error"]
    assert result["user"] == "user@example.com"

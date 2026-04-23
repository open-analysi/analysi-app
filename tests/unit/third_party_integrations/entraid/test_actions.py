"""
Unit tests for Microsoft Entra ID integration actions.

Tests cover all 9 actions: health_check, get_user, disable_user, enable_user,
reset_password, list_groups, get_group_members, revoke_sessions, list_sign_ins.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.entraid.actions import (
    DisableUserAction,
    EnableUserAction,
    GetGroupMembersAction,
    GetUserAction,
    HealthCheckAction,
    ListGroupsAction,
    ListSignInsAction,
    ResetPasswordAction,
    RevokeSessionsAction,
    _acquire_token,
    _graph_paginated_request,
    _graph_request,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def credentials():
    """Return test credentials."""
    return {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
    }


@pytest.fixture
def settings():
    """Return test settings."""
    return {
        "tenant_id": "test-tenant-id",
        "base_url": "https://graph.microsoft.com/v1.0",
        "timeout": 30,
    }


@pytest.fixture
def mock_token_response():
    """Return mock token response."""
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = {"access_token": "test-access-token-123"}
    response.status_code = 200
    return response


def _make_action(action_class, credentials, settings):
    """Helper to create action instance."""
    return action_class(
        integration_id="entraid",
        action_id=action_class.__name__.lower().replace("action", ""),
        credentials=credentials,
        settings=settings,
    )


# ============================================================================
# TOKEN ACQUISITION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_acquire_token_success(credentials, settings):
    """Test successful token acquisition."""
    action = _make_action(HealthCheckAction, credentials, settings)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {"access_token": "test-token-abc"}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        success, result = await _acquire_token(
            action, "tenant-id", "client-id", "client-secret"
        )

    assert success is True
    assert result == "test-token-abc"


@pytest.mark.asyncio
async def test_acquire_token_http_error(credentials, settings):
    """Test token acquisition failure on HTTP error."""
    action = _make_action(HealthCheckAction, credentials, settings)

    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 401
    mock_error_response.json.return_value = {
        "error": "invalid_client",
        "error_description": "Invalid client credentials",
    }

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_error_response
        ),
    ):
        success, result = await _acquire_token(
            action, "tenant-id", "client-id", "bad-secret"
        )

    assert success is False
    assert "error" in result
    assert "Invalid client credentials" in result["error"]


@pytest.mark.asyncio
async def test_acquire_token_no_access_token_in_response(credentials, settings):
    """Test token acquisition when response lacks access_token field."""
    action = _make_action(HealthCheckAction, credentials, settings)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {"token_type": "bearer"}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        success, result = await _acquire_token(
            action, "tenant-id", "client-id", "client-secret"
        )

    assert success is False
    assert "No access_token" in result["error"]


# ============================================================================
# GRAPH REQUEST TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_graph_request_success(credentials, settings):
    """Test successful Graph API request."""
    action = _make_action(HealthCheckAction, credentials, settings)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "user-123",
        "displayName": "Test User",
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        success, data, response = await _graph_request(
            action,
            "test-token",
            "https://graph.microsoft.com/v1.0",
            "/users/user-123",
        )

    assert success is True
    assert data["id"] == "user-123"


@pytest.mark.asyncio
async def test_graph_request_204_no_content(credentials, settings):
    """Test Graph API request with 204 No Content (PATCH success)."""
    action = _make_action(HealthCheckAction, credentials, settings)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 204

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        success, data, response = await _graph_request(
            action,
            "test-token",
            "https://graph.microsoft.com/v1.0",
            "/users/user-123",
            method="PATCH",
            json_data={"accountEnabled": False},
        )

    assert success is True
    assert data == {}


@pytest.mark.asyncio
async def test_graph_request_http_error_with_graph_error_body(credentials, settings):
    """Test Graph API request failure with detailed error body."""
    action = _make_action(HealthCheckAction, credentials, settings)

    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 403
    mock_error_response.text = "Forbidden"
    mock_error_response.json.return_value = {
        "error": {
            "code": "Authorization_RequestDenied",
            "message": "Insufficient privileges to complete the operation.",
        }
    }

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_error_response
        ),
    ):
        success, data, response = await _graph_request(
            action,
            "test-token",
            "https://graph.microsoft.com/v1.0",
            "/users/user-123",
        )

    assert success is False
    assert "Authorization_RequestDenied" in data["error"]
    assert data["status_code"] == 403


@pytest.mark.asyncio
async def test_graph_request_timeout(credentials, settings):
    """Test Graph API request timeout."""
    action = _make_action(HealthCheckAction, credentials, settings)

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Connection timed out"),
    ):
        success, data, response = await _graph_request(
            action,
            "test-token",
            "https://graph.microsoft.com/v1.0",
            "/users/user-123",
        )

    assert success is False
    assert "timed out" in data["error"]
    assert response is None


# ============================================================================
# PAGINATED REQUEST TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_graph_paginated_request_single_page(credentials, settings):
    """Test paginated request with single page of results."""
    action = _make_action(HealthCheckAction, credentials, settings)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "value": [
            {"id": "user-1", "displayName": "User 1"},
            {"id": "user-2", "displayName": "User 2"},
        ]
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        success, data = await _graph_paginated_request(
            action,
            "test-token",
            "https://graph.microsoft.com/v1.0",
            "/users",
        )

    assert success is True
    assert len(data) == 2
    assert data[0]["id"] == "user-1"


@pytest.mark.asyncio
async def test_graph_paginated_request_with_max_results(credentials, settings):
    """Test paginated request with max_results limit."""
    action = _make_action(HealthCheckAction, credentials, settings)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "value": [{"id": f"user-{i}"} for i in range(10)]
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        success, data = await _graph_paginated_request(
            action,
            "test-token",
            "https://graph.microsoft.com/v1.0",
            "/users",
            max_results=3,
        )

    assert success is True
    assert len(data) == 3


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(credentials, settings, mock_token_response):
    """Test successful health check."""
    action = _make_action(HealthCheckAction, credentials, settings)

    mock_graph_response = MagicMock(spec=httpx.Response)
    mock_graph_response.status_code = 200
    mock_graph_response.json.return_value = {"value": [{"id": "user-1"}]}

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_graph_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert result["data"]["tenant_id"] == "test-tenant-id"
    assert "integration_id" in result
    assert result["integration_id"] == "entraid"


@pytest.mark.asyncio
async def test_health_check_missing_client_id(settings):
    """Test health check with missing client_id."""
    creds = {"client_secret": "secret"}
    action = _make_action(HealthCheckAction, creds, settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "client_id" in result["error"]


@pytest.mark.asyncio
async def test_health_check_missing_client_secret(settings):
    """Test health check with missing client_secret."""
    creds = {"client_id": "cid"}
    action = _make_action(HealthCheckAction, creds, settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "client_secret" in result["error"]


@pytest.mark.asyncio
async def test_health_check_missing_tenant_id(credentials):
    """Test health check with missing tenant_id in settings."""
    settings_no_tenant = {"base_url": "https://graph.microsoft.com/v1.0", "timeout": 30}
    action = _make_action(HealthCheckAction, credentials, settings_no_tenant)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "tenant_id" in result["error"]


@pytest.mark.asyncio
async def test_health_check_token_failure(credentials, settings):
    """Test health check when token acquisition fails."""
    action = _make_action(HealthCheckAction, credentials, settings)

    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 401
    mock_error_response.json.return_value = {
        "error": "invalid_client",
        "error_description": "Bad credentials",
    }

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_error_response
        ),
    ):
        result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "TokenError"


@pytest.mark.asyncio
async def test_health_check_graph_api_failure(
    credentials, settings, mock_token_response
):
    """Test health check when Graph API call fails."""
    action = _make_action(HealthCheckAction, credentials, settings)

    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 500
    mock_error_response.text = "Internal Server Error"
    mock_error_response.json.return_value = {
        "error": {"code": "ServiceException", "message": "Service unavailable"}
    }

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        raise httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_error_response
        )

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute()

    assert result["status"] == "error"


# ============================================================================
# GET USER ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_success(credentials, settings, mock_token_response):
    """Test successful user lookup."""
    action = _make_action(GetUserAction, credentials, settings)

    mock_user_response = MagicMock(spec=httpx.Response)
    mock_user_response.status_code = 200
    mock_user_response.json.return_value = {
        "id": "user-obj-id-123",
        "displayName": "Jane Doe",
        "userPrincipalName": "jane@contoso.com",
        "mail": "jane@contoso.com",
        "accountEnabled": True,
        "jobTitle": "Security Analyst",
    }

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_user_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="jane@contoso.com")

    assert result["status"] == "success"
    assert result["data"]["displayName"] == "Jane Doe"
    assert result["data"]["userPrincipalName"] == "jane@contoso.com"
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_get_user_missing_user_id(credentials, settings):
    """Test get_user with missing user_id parameter."""
    action = _make_action(GetUserAction, credentials, settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "user_id" in result["error"]


@pytest.mark.asyncio
async def test_get_user_not_found(credentials, settings, mock_token_response):
    """Test get_user when user does not exist -- returns success with not_found."""
    action = _make_action(GetUserAction, credentials, settings)

    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 404
    mock_error_response.text = "Not Found"
    mock_error_response.json.return_value = {
        "error": {
            "code": "Request_ResourceNotFound",
            "message": "Resource 'nobody@contoso.com' does not exist.",
        }
    }

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        raise httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_error_response
        )

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="nobody@contoso.com")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["user_id"] == "nobody@contoso.com"


@pytest.mark.asyncio
async def test_get_user_http_403(credentials, settings, mock_token_response):
    """Test get_user with 403 Forbidden returns error."""
    action = _make_action(GetUserAction, credentials, settings)

    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 403
    mock_error_response.text = "Forbidden"
    mock_error_response.json.return_value = {
        "error": {
            "code": "Authorization_RequestDenied",
            "message": "Insufficient privileges.",
        }
    }

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        raise httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_error_response
        )

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="jane@contoso.com")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert "Authorization_RequestDenied" in result["error"]


# ============================================================================
# DISABLE USER ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_disable_user_success(credentials, settings, mock_token_response):
    """Test successful user disable."""
    action = _make_action(DisableUserAction, credentials, settings)

    mock_patch_response = MagicMock(spec=httpx.Response)
    mock_patch_response.status_code = 204

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_patch_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="jane@contoso.com")

    assert result["status"] == "success"
    assert result["data"]["user_id"] == "jane@contoso.com"
    assert result["data"]["account_enabled"] is False
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_disable_user_missing_user_id(credentials, settings):
    """Test disable_user with missing user_id."""
    action = _make_action(DisableUserAction, credentials, settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_disable_user_missing_credentials(settings):
    """Test disable_user with missing credentials."""
    action = _make_action(DisableUserAction, {}, settings)

    result = await action.execute(user_id="jane@contoso.com")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


# ============================================================================
# ENABLE USER ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_enable_user_success(credentials, settings, mock_token_response):
    """Test successful user enable."""
    action = _make_action(EnableUserAction, credentials, settings)

    mock_patch_response = MagicMock(spec=httpx.Response)
    mock_patch_response.status_code = 204

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_patch_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="jane@contoso.com")

    assert result["status"] == "success"
    assert result["data"]["user_id"] == "jane@contoso.com"
    assert result["data"]["account_enabled"] is True


@pytest.mark.asyncio
async def test_enable_user_missing_user_id(credentials, settings):
    """Test enable_user with missing user_id."""
    action = _make_action(EnableUserAction, credentials, settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# RESET PASSWORD ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_reset_password_success(credentials, settings, mock_token_response):
    """Test successful password reset."""
    action = _make_action(ResetPasswordAction, credentials, settings)

    mock_patch_response = MagicMock(spec=httpx.Response)
    mock_patch_response.status_code = 204

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_patch_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(
            user_id="jane@contoso.com",
            temp_password="TempPass123!",
            force_change=True,
        )

    assert result["status"] == "success"
    assert result["data"]["user_id"] == "jane@contoso.com"
    assert result["data"]["force_change"] is True
    assert result["data"]["message"] == "Successfully reset password"


@pytest.mark.asyncio
async def test_reset_password_default_force_change(
    credentials, settings, mock_token_response
):
    """Test password reset defaults to force_change=True."""
    action = _make_action(ResetPasswordAction, credentials, settings)

    mock_patch_response = MagicMock(spec=httpx.Response)
    mock_patch_response.status_code = 204

    call_count = 0
    captured_json_data = None

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count, captured_json_data
        call_count += 1
        if call_count == 1:
            return mock_token_response
        captured_json_data = kwargs.get("json_data")
        return mock_patch_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="jane@contoso.com")

    assert result["status"] == "success"
    assert result["data"]["force_change"] is True
    # Verify the payload sent to Graph API
    assert (
        captured_json_data["passwordProfile"]["forceChangePasswordNextSignIn"] is True
    )


@pytest.mark.asyncio
async def test_reset_password_missing_user_id(credentials, settings):
    """Test reset_password with missing user_id."""
    action = _make_action(ResetPasswordAction, credentials, settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# LIST GROUPS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_groups_success(credentials, settings, mock_token_response):
    """Test successful group listing for a user."""
    action = _make_action(ListGroupsAction, credentials, settings)

    mock_groups_response = MagicMock(spec=httpx.Response)
    mock_groups_response.status_code = 200
    mock_groups_response.json.return_value = {
        "value": [
            {
                "@odata.type": "#microsoft.graph.group",
                "id": "group-1",
                "displayName": "Security Team",
            },
            {
                "@odata.type": "#microsoft.graph.group",
                "id": "group-2",
                "displayName": "SOC Analysts",
            },
            {
                "@odata.type": "#microsoft.graph.directoryRole",
                "id": "role-1",
                "displayName": "Global Reader",
            },
        ]
    }

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_groups_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="jane@contoso.com")

    assert result["status"] == "success"
    # Only groups, not directory roles
    assert result["data"]["num_groups"] == 2
    assert len(result["data"]["groups"]) == 2
    assert result["data"]["groups"][0]["displayName"] == "Security Team"


@pytest.mark.asyncio
async def test_list_groups_missing_user_id(credentials, settings):
    """Test list_groups with missing user_id."""
    action = _make_action(ListGroupsAction, credentials, settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_list_groups_empty(credentials, settings, mock_token_response):
    """Test list_groups when user has no groups."""
    action = _make_action(ListGroupsAction, credentials, settings)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"value": []}

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="jane@contoso.com")

    assert result["status"] == "success"
    assert result["data"]["num_groups"] == 0
    assert result["data"]["groups"] == []


# ============================================================================
# GET GROUP MEMBERS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_group_members_success(credentials, settings, mock_token_response):
    """Test successful group member listing."""
    action = _make_action(GetGroupMembersAction, credentials, settings)

    mock_members_response = MagicMock(spec=httpx.Response)
    mock_members_response.status_code = 200
    mock_members_response.json.return_value = {
        "value": [
            {
                "id": "user-1",
                "displayName": "Jane Doe",
                "userPrincipalName": "jane@contoso.com",
            },
            {
                "id": "user-2",
                "displayName": "John Smith",
                "userPrincipalName": "john@contoso.com",
            },
        ]
    }

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_members_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(group_id="group-123")

    assert result["status"] == "success"
    assert result["data"]["num_members"] == 2
    assert result["data"]["group_id"] == "group-123"
    assert result["data"]["members"][0]["displayName"] == "Jane Doe"


@pytest.mark.asyncio
async def test_get_group_members_missing_group_id(credentials, settings):
    """Test get_group_members with missing group_id."""
    action = _make_action(GetGroupMembersAction, credentials, settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "group_id" in result["error"]


# ============================================================================
# REVOKE SESSIONS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_revoke_sessions_success(credentials, settings, mock_token_response):
    """Test successful session revocation."""
    action = _make_action(RevokeSessionsAction, credentials, settings)

    mock_revoke_response = MagicMock(spec=httpx.Response)
    mock_revoke_response.status_code = 200
    mock_revoke_response.json.return_value = {"value": True}

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_revoke_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="jane@contoso.com")

    assert result["status"] == "success"
    assert result["data"]["user_id"] == "jane@contoso.com"
    assert result["data"]["sessions_revoked"] is True
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_revoke_sessions_missing_user_id(credentials, settings):
    """Test revoke_sessions with missing user_id."""
    action = _make_action(RevokeSessionsAction, credentials, settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_revoke_sessions_api_error(credentials, settings, mock_token_response):
    """Test revoke_sessions when API returns error."""
    action = _make_action(RevokeSessionsAction, credentials, settings)

    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 403
    mock_error_response.text = "Forbidden"
    mock_error_response.json.return_value = {
        "error": {
            "code": "Authorization_RequestDenied",
            "message": "Insufficient privileges.",
        }
    }

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        raise httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_error_response
        )

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="jane@contoso.com")

    assert result["status"] == "error"


# ============================================================================
# LIST SIGN-INS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_sign_ins_success(credentials, settings, mock_token_response):
    """Test successful sign-in log listing."""
    action = _make_action(ListSignInsAction, credentials, settings)

    mock_signins_response = MagicMock(spec=httpx.Response)
    mock_signins_response.status_code = 200
    mock_signins_response.json.return_value = {
        "value": [
            {
                "id": "signin-1",
                "createdDateTime": "2025-01-15T10:30:00Z",
                "userPrincipalName": "jane@contoso.com",
                "appDisplayName": "Microsoft Teams",
                "ipAddress": "203.0.113.42",
                "clientAppUsed": "Browser",
                "status": {"errorCode": 0},
                "location": {
                    "city": "Seattle",
                    "state": "Washington",
                    "countryOrRegion": "US",
                },
            },
            {
                "id": "signin-2",
                "createdDateTime": "2025-01-15T09:15:00Z",
                "userPrincipalName": "jane@contoso.com",
                "appDisplayName": "Azure Portal",
                "ipAddress": "198.51.100.10",
                "clientAppUsed": "Browser",
                "status": {"errorCode": 0},
                "location": {
                    "city": "Portland",
                    "state": "Oregon",
                    "countryOrRegion": "US",
                },
            },
        ]
    }

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_signins_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="jane@contoso.com")

    assert result["status"] == "success"
    assert result["data"]["num_sign_ins"] == 2
    assert result["data"]["user_id"] == "jane@contoso.com"
    first_signin = result["data"]["sign_ins"][0]
    assert first_signin["appDisplayName"] == "Microsoft Teams"
    assert first_signin["ipAddress"] == "203.0.113.42"


@pytest.mark.asyncio
async def test_list_sign_ins_with_custom_top(
    credentials, settings, mock_token_response
):
    """Test list_sign_ins with custom top parameter."""
    action = _make_action(ListSignInsAction, credentials, settings)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "value": [{"id": f"signin-{i}"} for i in range(5)]
    }

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="jane@contoso.com", top=5)

    assert result["status"] == "success"
    assert result["data"]["num_sign_ins"] == 5


@pytest.mark.asyncio
async def test_list_sign_ins_missing_user_id(credentials, settings):
    """Test list_sign_ins with missing user_id."""
    action = _make_action(ListSignInsAction, credentials, settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_list_sign_ins_empty_results(credentials, settings, mock_token_response):
    """Test list_sign_ins when no sign-in records exist."""
    action = _make_action(ListSignInsAction, credentials, settings)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"value": []}

    call_count = 0

    async def mock_http_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_token_response
        return mock_response

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="newuser@contoso.com")

    assert result["status"] == "success"
    assert result["data"]["num_sign_ins"] == 0
    assert result["data"]["sign_ins"] == []


# ============================================================================
# CROSS-CUTTING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_all_actions_return_integration_id(
    credentials, settings, mock_token_response
):
    """Test that all actions include integration_id in results."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"value": []}

    actions_params = [
        (HealthCheckAction, {}),
        (GetUserAction, {"user_id": "jane@contoso.com"}),
        (DisableUserAction, {"user_id": "jane@contoso.com"}),
        (EnableUserAction, {"user_id": "jane@contoso.com"}),
        (ResetPasswordAction, {"user_id": "jane@contoso.com"}),
        (ListGroupsAction, {"user_id": "jane@contoso.com"}),
        (GetGroupMembersAction, {"group_id": "group-123"}),
        (RevokeSessionsAction, {"user_id": "jane@contoso.com"}),
        (ListSignInsAction, {"user_id": "jane@contoso.com"}),
    ]

    for action_class, params in actions_params:
        action = _make_action(action_class, credentials, settings)

        # For PATCH actions (disable/enable/reset), return 204
        mock_patch_resp = MagicMock(spec=httpx.Response)
        mock_patch_resp.status_code = 204

        call_count = 0
        _patch_resp = mock_patch_resp  # bind to local for closure

        async def mock_http_request(*args, _pr=_patch_resp, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_token_response
            # PATCH endpoints return 204, others return 200 with value
            method = kwargs.get("method", args[0] if args else "GET")
            if isinstance(method, str) and method.upper() == "PATCH":
                return _pr
            return mock_response

        with patch.object(action, "http_request", side_effect=mock_http_request):
            result = await action.execute(**params)

        assert "integration_id" in result, (
            f"{action_class.__name__} missing integration_id"
        )
        assert result["integration_id"] == "entraid", (
            f"{action_class.__name__} wrong integration_id"
        )


@pytest.mark.asyncio
async def test_default_base_url_used_when_not_in_settings(credentials):
    """Test that default Graph API URL is used when not specified in settings."""
    action = _make_action(GetUserAction, credentials, {"tenant_id": "test-tenant-id"})

    mock_token = MagicMock(spec=httpx.Response)
    mock_token.json.return_value = {"access_token": "tok"}

    mock_user = MagicMock(spec=httpx.Response)
    mock_user.status_code = 200
    mock_user.json.return_value = {"id": "u1", "displayName": "User"}

    call_count = 0
    captured_urls = []

    async def mock_http_request(url, *args, **kwargs):
        nonlocal call_count
        captured_urls.append(url)
        call_count += 1
        if call_count == 1:
            return mock_token
        return mock_user

    with patch.object(action, "http_request", side_effect=mock_http_request):
        result = await action.execute(user_id="user@contoso.com")

    assert result["status"] == "success"
    # Second URL should use default Graph API base
    assert "graph.microsoft.com" in captured_urls[1]

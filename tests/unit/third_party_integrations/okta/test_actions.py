"""Unit tests for Okta integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.okta.actions import (
    AddGroupAction,
    AddGroupUserAction,
    AssignRoleAction,
    ClearUserSessionsAction,
    DisableUserAction,
    EnableUserAction,
    GetGroupAction,
    GetUserAction,
    GetUserGroupsAction,
    HealthCheckAction,
    ListProvidersAction,
    ListRolesAction,
    ListUserGroupsAction,
    ListUsersAction,
    RemoveGroupUserAction,
    ResetPasswordAction,
    SendPushNotificationAction,
    SetPasswordAction,
    UnassignRoleAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def okta_credentials():
    """Okta test credentials."""
    return {
        "api_token": "test_token_12345",
    }


@pytest.fixture
def okta_settings():
    """Okta test settings."""
    return {
        "base_url": "https://test-org.okta.com",
        "timeout": 30,
        "verify_ssl": True,
    }


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(okta_credentials, okta_settings):
    """Test successful health check."""
    action = HealthCheckAction(
        integration_id="okta",
        action_id="health_check",
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "test_user", "status": "ACTIVE"}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="okta",
        action_id="health_check",
        settings={},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_health_check_http_error(okta_credentials, okta_settings):
    """Test health check with HTTP error."""
    action = HealthCheckAction(
        integration_id="okta",
        action_id="health_check",
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_response.json.return_value = {"errorSummary": "Invalid token"}
    mock_response.text = "Unauthorized"

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        ),
    ):
        result = await action.execute()

    assert result["status"] == "error"
    assert result["data"]["healthy"] is False


# ============================================================================
# USER MANAGEMENT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_users_success(okta_credentials, okta_settings):
    """Test successful user listing."""
    action = ListUsersAction(
        integration_id="okta",
        action_id="ListUsersAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": "user1", "profile": {"email": "user1@test.com"}},
        {"id": "user2", "profile": {"email": "user2@test.com"}},
    ]
    mock_response.headers = {}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(query="test")

    assert result["status"] == "success"
    assert result["num_users"] == 2
    assert len(result["users"]) == 2


@pytest.mark.asyncio
async def test_list_users_with_limit(okta_credentials, okta_settings):
    """Test user listing with limit."""
    action = ListUsersAction(
        integration_id="okta",
        action_id="ListUsersAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [{"id": f"user{i}"} for i in range(5)]
    mock_response.headers = {}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(limit=3)

    assert result["status"] == "success"
    assert result["num_users"] == 3


@pytest.mark.asyncio
async def test_get_user_success(okta_credentials, okta_settings):
    """Test successful get user."""
    action = GetUserAction(
        integration_id="okta",
        action_id="GetUserAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "user123",
        "profile": {"email": "test@example.com"},
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(user_id="user123")

    assert result["status"] == "success"
    assert result["user"]["id"] == "user123"


@pytest.mark.asyncio
async def test_get_user_missing_parameter():
    """Test get user with missing parameter."""
    action = GetUserAction(
        integration_id="okta",
        action_id="GetUserAction".lower().replace("action", ""),
        settings={},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "user_id" in result["error"]


@pytest.mark.asyncio
async def test_get_user_not_found(okta_credentials, okta_settings):
    """Test get user returns not_found=True on 404."""
    action = GetUserAction(
        integration_id="okta",
        action_id="GetUserAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.json.return_value = {
        "errorSummary": "Not found: Resource not found: user123 (User)"
    }
    mock_response.text = "Not found: Resource not found: user123 (User)"

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        ),
    ):
        result = await action.execute(user_id="user123")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["user_id"] == "user123"


@pytest.mark.asyncio
async def test_disable_user_success(okta_credentials, okta_settings):
    """Test successful user disable."""
    action = DisableUserAction(
        integration_id="okta",
        action_id="DisableUserAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "user123", "status": "SUSPENDED"}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(id="user123")

    assert result["status"] == "success"
    assert "disabled" in result["message"].lower()


@pytest.mark.asyncio
async def test_disable_user_already_disabled(okta_credentials, okta_settings):
    """Test disable user that is already disabled."""
    action = DisableUserAction(
        integration_id="okta",
        action_id="DisableUserAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "errorSummary": "Cannot suspend a user that is not active"
    }
    mock_response.text = "Cannot suspend a user that is not active"

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=mock_response
        ),
    ):
        result = await action.execute(id="user123")

    assert result["status"] == "success"
    assert "already disabled" in result["message"].lower()


@pytest.mark.asyncio
async def test_enable_user_success(okta_credentials, okta_settings):
    """Test successful user enable."""
    action = EnableUserAction(
        integration_id="okta",
        action_id="EnableUserAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "user123", "status": "ACTIVE"}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(id="user123")

    assert result["status"] == "success"
    assert "enabled" in result["message"].lower()


@pytest.mark.asyncio
async def test_reset_password_success(okta_credentials, okta_settings):
    """Test successful password reset."""
    action = ResetPasswordAction(
        integration_id="okta",
        action_id="ResetPasswordAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "resetPasswordUrl": "https://test.okta.com/reset/token123"
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(user_id="user123", receive_type="Email")

    assert result["status"] == "success"
    assert "password" in result["message"].lower()


@pytest.mark.asyncio
async def test_reset_password_invalid_receive_type(okta_credentials, okta_settings):
    """Test password reset with invalid receive_type."""
    action = ResetPasswordAction(
        integration_id="okta",
        action_id="ResetPasswordAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    result = await action.execute(user_id="user123", receive_type="InvalidType")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_set_password_success(okta_credentials, okta_settings):
    """Test successful password set."""
    action = SetPasswordAction(
        integration_id="okta",
        action_id="SetPasswordAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "user123", "status": "ACTIVE"}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(id="user123", new_password="NewSecurePass123!")

    assert result["status"] == "success"
    assert "password" in result["message"].lower()


@pytest.mark.asyncio
async def test_set_password_missing_parameter():
    """Test set password with missing parameters."""
    action = SetPasswordAction(
        integration_id="okta",
        action_id="SetPasswordAction".lower().replace("action", ""),
        settings={},
        credentials={},
    )

    result = await action.execute(id="user123")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_clear_user_sessions_success(okta_credentials, okta_settings):
    """Test successful session clearing."""
    action = ClearUserSessionsAction(
        integration_id="okta",
        action_id="ClearUserSessionsAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 204

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(id="user123")

    assert result["status"] == "success"
    assert "sessions" in result["message"].lower()


# ============================================================================
# GROUP MANAGEMENT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_user_groups_success(okta_credentials, okta_settings):
    """Test successful group listing."""
    action = ListUserGroupsAction(
        integration_id="okta",
        action_id="ListUserGroupsAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": "group1", "profile": {"name": "Group 1"}},
        {"id": "group2", "profile": {"name": "Group 2"}},
    ]
    mock_response.headers = {}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["num_groups"] == 2


@pytest.mark.asyncio
async def test_get_group_success(okta_credentials, okta_settings):
    """Test successful get group."""
    action = GetGroupAction(
        integration_id="okta",
        action_id="GetGroupAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "group123",
        "profile": {"name": "Test Group"},
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(group_id="group123")

    assert result["status"] == "success"
    assert result["group"]["id"] == "group123"


@pytest.mark.asyncio
async def test_get_group_not_found(okta_credentials, okta_settings):
    """Test get group returns not_found=True on 404."""
    action = GetGroupAction(
        integration_id="okta",
        action_id="GetGroupAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.json.return_value = {
        "errorSummary": "Not found: Resource not found: group123 (Group)"
    }
    mock_response.text = "Not found: Resource not found: group123 (Group)"

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        ),
    ):
        result = await action.execute(group_id="group123")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["group_id"] == "group123"


@pytest.mark.asyncio
async def test_add_group_success(okta_credentials, okta_settings):
    """Test successful group creation."""
    action = AddGroupAction(
        integration_id="okta",
        action_id="AddGroupAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "new_group",
        "profile": {"name": "New Group"},
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(name="New Group", description="Test group")

    assert result["status"] == "success"
    assert result["group_id"] == "new_group"


@pytest.mark.asyncio
async def test_add_group_already_exists(okta_credentials, okta_settings):
    """Test add group that already exists."""
    action = AddGroupAction(
        integration_id="okta",
        action_id="AddGroupAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "errorSummary": "An object with this field already exists"
    }
    mock_response.text = "An object with this field already exists"

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=mock_response
        ),
    ):
        result = await action.execute(name="Existing Group", description="Test")

    assert result["status"] == "success"
    assert "already exists" in result["message"].lower()


@pytest.mark.asyncio
async def test_get_user_groups_success(okta_credentials, okta_settings):
    """Test successful get user groups."""
    action = GetUserGroupsAction(
        integration_id="okta",
        action_id="GetUserGroupsAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": "group1", "profile": {"name": "Group 1"}},
        {"id": "group2", "profile": {"name": "Group 2"}},
    ]

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(user_id="user123")

    assert result["status"] == "success"
    assert result["total_groups"] == 2


@pytest.mark.asyncio
async def test_get_user_groups_not_found(okta_credentials, okta_settings):
    """Test get user groups returns not_found=True on 404 (user not found)."""
    action = GetUserGroupsAction(
        integration_id="okta",
        action_id="GetUserGroupsAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.json.return_value = {
        "errorSummary": "Not found: Resource not found: user999 (User)"
    }
    mock_response.text = "Not found: Resource not found: user999 (User)"

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        ),
    ):
        result = await action.execute(user_id="user999")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["user_id"] == "user999"


@pytest.mark.asyncio
async def test_add_group_user_success(okta_credentials, okta_settings):
    """Test successful add user to group."""
    action = AddGroupUserAction(
        integration_id="okta",
        action_id="AddGroupUserAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_user_response = MagicMock(spec=httpx.Response)
    mock_user_response.status_code = 200
    mock_user_response.json.return_value = {
        "id": "user123",
        "profile": {"login": "test@example.com"},
    }

    mock_group_response = MagicMock(spec=httpx.Response)
    mock_group_response.status_code = 200
    mock_group_response.json.return_value = {
        "id": "group123",
        "profile": {"name": "Test Group"},
    }

    mock_put_response = MagicMock(spec=httpx.Response)
    mock_put_response.status_code = 204

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_put_response
    ):
        result = await action.execute(group_id="group123", user_id="user123")

    assert result["status"] == "success"
    assert result["user_id"] == "user123"
    assert result["group_id"] == "group123"


@pytest.mark.asyncio
async def test_remove_group_user_success(okta_credentials, okta_settings):
    """Test successful remove user from group."""
    action = RemoveGroupUserAction(
        integration_id="okta",
        action_id="RemoveGroupUserAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_user_response = MagicMock(spec=httpx.Response)
    mock_user_response.status_code = 200
    mock_user_response.json.return_value = {
        "id": "user123",
        "profile": {"login": "test@example.com"},
    }

    mock_group_response = MagicMock(spec=httpx.Response)
    mock_group_response.status_code = 200
    mock_group_response.json.return_value = {
        "id": "group123",
        "profile": {"name": "Test Group"},
    }

    mock_delete_response = MagicMock(spec=httpx.Response)
    mock_delete_response.status_code = 204

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_delete_response,
    ):
        result = await action.execute(group_id="group123", user_id="user123")

    assert result["status"] == "success"
    assert result["user_id"] == "user123"
    assert result["group_id"] == "group123"


# ============================================================================
# IDENTITY PROVIDER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_providers_success(okta_credentials, okta_settings):
    """Test successful list identity providers."""
    action = ListProvidersAction(
        integration_id="okta",
        action_id="ListProvidersAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": "idp1", "type": "SAML2", "name": "Corporate SAML"},
        {"id": "idp2", "type": "GOOGLE", "name": "Google SSO"},
    ]
    mock_response.headers = {}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["num_idps"] == 2


@pytest.mark.asyncio
async def test_list_providers_with_type_filter(okta_credentials, okta_settings):
    """Test list providers with type filter."""
    action = ListProvidersAction(
        integration_id="okta",
        action_id="ListProvidersAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [{"id": "idp1", "type": "SAML2"}]
    mock_response.headers = {}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(type="SAML2")

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_list_providers_invalid_type(okta_credentials, okta_settings):
    """Test list providers with invalid type."""
    action = ListProvidersAction(
        integration_id="okta",
        action_id="ListProvidersAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    result = await action.execute(type="INVALID_TYPE")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# ROLE MANAGEMENT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_roles_success(okta_credentials, okta_settings):
    """Test successful list user roles."""
    action = ListRolesAction(
        integration_id="okta",
        action_id="ListRolesAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": "role1", "type": "USER_ADMIN"},
        {"id": "role2", "type": "HELP_DESK_ADMIN"},
    ]
    mock_response.headers = {}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(user_id="user123")

    assert result["status"] == "success"
    assert result["num_roles"] == 2


@pytest.mark.asyncio
async def test_assign_role_success(okta_credentials, okta_settings):
    """Test successful role assignment."""
    action = AssignRoleAction(
        integration_id="okta",
        action_id="AssignRoleAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "role123", "type": "USER_ADMIN"}

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(user_id="user123", type="USER_ADMIN")

    assert result["status"] == "success"
    assert "assigned" in result["message"].lower()


@pytest.mark.asyncio
async def test_assign_role_already_assigned(okta_credentials, okta_settings):
    """Test assign role that is already assigned."""
    action = AssignRoleAction(
        integration_id="okta",
        action_id="AssignRoleAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "errorSummary": "The role specified is already assigned to the user"
    }
    mock_response.text = "The role specified is already assigned to the user"

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=mock_response
        ),
    ):
        result = await action.execute(user_id="user123", type="USER_ADMIN")

    assert result["status"] == "success"
    assert "already assigned" in result["message"].lower()


@pytest.mark.asyncio
async def test_assign_role_invalid_type():
    """Test assign role with invalid type."""
    action = AssignRoleAction(
        integration_id="okta",
        action_id="AssignRoleAction".lower().replace("action", ""),
        settings={},
        credentials={},
    )

    result = await action.execute(user_id="user123", type="INVALID_ROLE")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_unassign_role_success(okta_credentials, okta_settings):
    """Test successful role unassignment."""
    action = UnassignRoleAction(
        integration_id="okta",
        action_id="UnassignRoleAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_user_response = MagicMock(spec=httpx.Response)
    mock_user_response.status_code = 200
    mock_user_response.json.return_value = {"id": "user123"}

    mock_delete_response = MagicMock(spec=httpx.Response)
    mock_delete_response.status_code = 204

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_delete_response,
    ):
        result = await action.execute(user_id="user123", role_id="role123")

    assert result["status"] == "success"
    assert "unassigned" in result["message"].lower()


@pytest.mark.asyncio
async def test_unassign_role_not_found(okta_credentials, okta_settings):
    """Test unassign role that doesn't exist."""
    action = UnassignRoleAction(
        integration_id="okta",
        action_id="UnassignRoleAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_delete_response = MagicMock(spec=httpx.Response)
    mock_delete_response.status_code = 404
    mock_delete_response.json.return_value = {"errorSummary": "Not found"}
    mock_delete_response.text = "Not found"

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_delete_response
        ),
    ):
        result = await action.execute(user_id="user123", role_id="role123")

    assert result["status"] == "error"


# ============================================================================
# MFA TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_send_push_notification_success(okta_credentials, okta_settings):
    """Test successful push notification."""
    action = SendPushNotificationAction(
        integration_id="okta",
        action_id="SendPushNotificationAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_user_response = MagicMock(spec=httpx.Response)
    mock_user_response.status_code = 200
    mock_user_response.json.return_value = {"id": "user123"}

    mock_factors_response = MagicMock(spec=httpx.Response)
    mock_factors_response.status_code = 200
    mock_factors_response.json.return_value = [
        {
            "id": "factor123",
            "factorType": "push",
            "_links": {
                "verify": {
                    "href": "https://test.okta.com/api/v1/users/user123/factors/factor123/verify"
                }
            },
        }
    ]

    mock_verify_response = MagicMock(spec=httpx.Response)
    mock_verify_response.status_code = 200
    mock_verify_response.json.return_value = {
        "factorResult": "WAITING",
        "_links": {
            "poll": {
                "href": "https://test.okta.com/api/v1/users/user123/factors/factor123/transactions/trans123"
            }
        },
    }

    mock_poll_response = MagicMock(spec=httpx.Response)
    mock_poll_response.status_code = 200
    mock_poll_response.json.return_value = {"factorResult": "SUCCESS"}

    # Mock asyncio.sleep to avoid 5-second wait in polling loop
    with (
        patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[
                mock_user_response,
                mock_factors_response,
                mock_verify_response,
                mock_poll_response,
            ],
        ),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await action.execute(email="test@example.com", factortype="push")

    assert result["status"] == "success"
    assert result["factor_result"] == "SUCCESS"
    # Verify sleep was called (polling happened) but didn't actually wait
    assert mock_sleep.called


@pytest.mark.asyncio
async def test_send_push_notification_factor_not_configured(
    okta_credentials, okta_settings
):
    """Test push notification with factor not configured."""
    action = SendPushNotificationAction(
        integration_id="okta",
        action_id="SendPushNotificationAction".lower().replace("action", ""),
        settings=okta_settings,
        credentials=okta_credentials,
    )

    mock_user_response = MagicMock(spec=httpx.Response)
    mock_user_response.status_code = 200
    mock_user_response.json.return_value = {"id": "user123"}

    mock_factors_response = MagicMock(spec=httpx.Response)
    mock_factors_response.status_code = 200
    mock_factors_response.json.return_value = []

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[mock_user_response, mock_factors_response],
    ):
        result = await action.execute(email="test@example.com", factortype="push")

    assert result["status"] == "error"
    assert "not configured" in result["error"].lower()


@pytest.mark.asyncio
async def test_send_push_notification_invalid_factor_type():
    """Test push notification with invalid factor type."""
    action = SendPushNotificationAction(
        integration_id="okta",
        action_id="SendPushNotificationAction".lower().replace("action", ""),
        settings={},
        credentials={},
    )

    result = await action.execute(email="test@example.com", factortype="invalid")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"

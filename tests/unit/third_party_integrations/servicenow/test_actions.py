"""
Unit tests for ServiceNow integration actions.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.servicenow.actions import (
    AddCommentAction,
    CreateTicketAction,
    GetTicketAction,
    HealthCheckAction,
    ListTicketsAction,
    QueryUsersAction,
    UpdateTicketAction,
)


@pytest.fixture
def health_check_action():
    """Fixture for health check action."""
    return HealthCheckAction(
        integration_id="servicenow",
        action_id="health_check",
        settings={"url": "https://test-instance.service-now.com", "timeout": 30},
        credentials={
            "username": "test_user",
            "password": "test_pass",
        },
    )


@pytest.fixture
def create_ticket_action():
    """Fixture for create ticket action."""
    return CreateTicketAction(
        integration_id="servicenow",
        action_id="create_ticket",
        settings={"url": "https://test-instance.service-now.com", "timeout": 30},
        credentials={
            "username": "test_user",
            "password": "test_pass",
        },
    )


@pytest.fixture
def get_ticket_action():
    """Fixture for get ticket action."""
    return GetTicketAction(
        integration_id="servicenow",
        action_id="get_ticket",
        settings={"url": "https://test-instance.service-now.com", "timeout": 30},
        credentials={
            "username": "test_user",
            "password": "test_pass",
        },
    )


@pytest.fixture
def update_ticket_action():
    """Fixture for update ticket action."""
    return UpdateTicketAction(
        integration_id="servicenow",
        action_id="update_ticket",
        settings={"url": "https://test-instance.service-now.com", "timeout": 30},
        credentials={
            "username": "test_user",
            "password": "test_pass",
        },
    )


@pytest.fixture
def list_tickets_action():
    """Fixture for list tickets action."""
    return ListTicketsAction(
        integration_id="servicenow",
        action_id="list_tickets",
        settings={
            "url": "https://test-instance.service-now.com",
            "timeout": 30,
            "max_results": 100,
        },
        credentials={
            "username": "test_user",
            "password": "test_pass",
        },
    )


@pytest.fixture
def add_comment_action():
    """Fixture for add comment action."""
    return AddCommentAction(
        integration_id="servicenow",
        action_id="add_comment",
        settings={"url": "https://test-instance.service-now.com", "timeout": 30},
        credentials={
            "username": "test_user",
            "password": "test_pass",
        },
    )


@pytest.fixture
def query_users_action():
    """Fixture for query users action."""
    return QueryUsersAction(
        integration_id="servicenow",
        action_id="query_users",
        settings={
            "url": "https://test-instance.service-now.com",
            "timeout": 30,
            "max_results": 100,
        },
        credentials={
            "username": "test_user",
            "password": "test_pass",
        },
    )


# HealthCheckAction Tests


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": [{"number": "INC0001"}]}
    mock_response.raise_for_status = MagicMock()

    health_check_action.http_request = AsyncMock(return_value=mock_response)
    result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert "instance_url" in result["data"]


@pytest.mark.asyncio
async def test_health_check_missing_url():
    """Test health check with missing URL."""
    action = HealthCheckAction(
        integration_id="servicenow",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={"username": "test", "password": "test"},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "url" in result["error"].lower()


@pytest.mark.asyncio
async def test_health_check_missing_auth():
    """Test health check with missing authentication."""
    action = HealthCheckAction(
        integration_id="servicenow",
        action_id="health_check",
        settings={"url": "https://test.service-now.com", "timeout": 30},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "authentication" in result["error"].lower()


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check with HTTP error."""
    mock_response = MagicMock()
    mock_response.status_code = 401

    health_check_action.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
    )
    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


@pytest.mark.asyncio
async def test_health_check_timeout(health_check_action):
    """Test health check timeout."""
    health_check_action.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("Request timed out")
    )
    result = await health_check_action.execute()

    assert result["status"] == "error"
    # TimeoutException inherits from RequestError in httpx
    assert result["error_type"] in ["TimeoutException", "RequestError"]


# CreateTicketAction Tests


@pytest.mark.asyncio
async def test_create_ticket_success(create_ticket_action):
    """Test successful ticket creation."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": {
            "number": "INC0001234",
            "sys_id": "abc123",
            "short_description": "Test ticket",
        }
    }
    mock_response.raise_for_status = MagicMock()

    create_ticket_action.http_request = AsyncMock(return_value=mock_response)
    result = await create_ticket_action.execute(
        short_description="Test ticket", description="Test description"
    )

    assert result["status"] == "success"
    assert result["data"]["ticket_id"] == "INC0001234"
    assert result["data"]["sys_id"] == "abc123"


@pytest.mark.asyncio
async def test_create_ticket_missing_fields(create_ticket_action):
    """Test ticket creation with missing required fields."""
    result = await create_ticket_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_create_ticket_with_additional_fields(create_ticket_action):
    """Test ticket creation with additional fields."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": {
            "number": "INC0001234",
            "sys_id": "abc123",
            "priority": "1",
        }
    }
    mock_response.raise_for_status = MagicMock()

    create_ticket_action.http_request = AsyncMock(return_value=mock_response)
    result = await create_ticket_action.execute(
        short_description="Test",
        fields='{"priority": "1", "urgency": "2"}',
    )

    assert result["status"] == "success"
    create_ticket_action.http_request.assert_called_once()


@pytest.mark.asyncio
async def test_create_ticket_invalid_fields_json(create_ticket_action):
    """Test ticket creation with invalid fields JSON."""
    result = await create_ticket_action.execute(
        short_description="Test", fields="invalid json"
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "parse" in result["error"].lower()


# GetTicketAction Tests


@pytest.mark.asyncio
async def test_get_ticket_by_number(get_ticket_action):
    """Test getting ticket by ticket number."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": [
            {
                "number": "INC0001234",
                "sys_id": "abc123",
                "short_description": "Test ticket",
                "state": "2",
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    get_ticket_action.http_request = AsyncMock(return_value=mock_response)
    result = await get_ticket_action.execute(id="INC0001234", is_sys_id=False)

    assert result["status"] == "success"
    assert result["data"]["ticket_id"] == "INC0001234"
    assert result["data"]["sys_id"] == "abc123"


@pytest.mark.asyncio
async def test_get_ticket_by_sys_id(get_ticket_action):
    """Test getting ticket by sys_id."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": {
            "number": "INC0001234",
            "sys_id": "abc123",
            "short_description": "Test ticket",
        }
    }
    mock_response.raise_for_status = MagicMock()

    get_ticket_action.http_request = AsyncMock(return_value=mock_response)
    result = await get_ticket_action.execute(id="abc123", is_sys_id=True)

    assert result["status"] == "success"
    assert result["data"]["ticket_id"] == "INC0001234"


@pytest.mark.asyncio
async def test_get_ticket_not_found(get_ticket_action):
    """Test getting non-existent ticket."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": []}
    mock_response.raise_for_status = MagicMock()

    get_ticket_action.http_request = AsyncMock(return_value=mock_response)
    result = await get_ticket_action.execute(id="INC9999999", is_sys_id=False)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_ticket_missing_id(get_ticket_action):
    """Test getting ticket without ID."""
    result = await get_ticket_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# UpdateTicketAction Tests


@pytest.mark.asyncio
async def test_update_ticket_by_sys_id(update_ticket_action):
    """Test updating ticket by sys_id."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": {
            "number": "INC0001234",
            "sys_id": "abc123",
            "state": "6",
        }
    }
    mock_response.raise_for_status = MagicMock()

    update_ticket_action.http_request = AsyncMock(return_value=mock_response)
    result = await update_ticket_action.execute(
        id="abc123", is_sys_id=True, fields='{"state": "6"}'
    )

    assert result["status"] == "success"
    assert result["data"]["sys_id"] == "abc123"


@pytest.mark.asyncio
async def test_update_ticket_by_number(update_ticket_action):
    """Test updating ticket by ticket number."""
    # Mock GET to retrieve sys_id
    mock_get_response = MagicMock()
    mock_get_response.json.return_value = {
        "result": [{"number": "INC0001234", "sys_id": "abc123"}]
    }
    mock_get_response.raise_for_status = MagicMock()

    # Mock PATCH to update ticket
    mock_patch_response = MagicMock()
    mock_patch_response.json.return_value = {
        "result": {
            "number": "INC0001234",
            "sys_id": "abc123",
            "state": "3",
        }
    }
    mock_patch_response.raise_for_status = MagicMock()

    update_ticket_action.http_request = AsyncMock(
        side_effect=[mock_get_response, mock_patch_response]
    )
    result = await update_ticket_action.execute(
        id="INC0001234", is_sys_id=False, fields='{"state": "3"}'
    )

    assert result["status"] == "success"
    assert result["data"]["ticket_id"] == "INC0001234"


@pytest.mark.asyncio
async def test_update_ticket_missing_fields(update_ticket_action):
    """Test updating ticket without fields parameter."""
    result = await update_ticket_action.execute(id="abc123", is_sys_id=True)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_update_ticket_invalid_fields(update_ticket_action):
    """Test updating ticket with invalid fields JSON."""
    result = await update_ticket_action.execute(
        id="abc123", is_sys_id=True, fields="invalid json"
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ListTicketsAction Tests


@pytest.mark.asyncio
async def test_list_tickets_success(list_tickets_action):
    """Test listing tickets successfully."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": [
            {"number": "INC0001", "sys_id": "id1"},
            {"number": "INC0002", "sys_id": "id2"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    list_tickets_action.http_request = AsyncMock(return_value=mock_response)
    result = await list_tickets_action.execute()

    assert result["status"] == "success"
    assert result["data"]["total_tickets"] == 2
    assert len(result["data"]["tickets"]) == 2


@pytest.mark.asyncio
async def test_list_tickets_with_query(list_tickets_action):
    """Test listing tickets with query filter."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": [{"number": "INC0001", "state": "1"}]}
    mock_response.raise_for_status = MagicMock()

    list_tickets_action.http_request = AsyncMock(return_value=mock_response)
    result = await list_tickets_action.execute(query="state=1")

    assert result["status"] == "success"
    list_tickets_action.http_request.assert_called_once()


@pytest.mark.asyncio
async def test_list_tickets_with_max_results(list_tickets_action):
    """Test listing tickets with max_results limit."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": [{"number": f"INC{i:04d}"} for i in range(50)]
    }
    mock_response.raise_for_status = MagicMock()

    list_tickets_action.http_request = AsyncMock(return_value=mock_response)
    result = await list_tickets_action.execute(max_results=50)

    assert result["status"] == "success"
    assert result["data"]["total_tickets"] == 50


# AddCommentAction Tests


@pytest.mark.asyncio
async def test_add_comment_success(add_comment_action):
    """Test adding comment successfully."""
    # Mock GET to retrieve sys_id
    mock_get_response = MagicMock()
    mock_get_response.json.return_value = {
        "result": [{"number": "INC0001234", "sys_id": "abc123"}]
    }
    mock_get_response.raise_for_status = MagicMock()

    # Mock PATCH to add comment
    mock_patch_response = MagicMock()
    mock_patch_response.json.return_value = {
        "result": {"number": "INC0001234", "sys_id": "abc123"}
    }
    mock_patch_response.raise_for_status = MagicMock()

    add_comment_action.http_request = AsyncMock(
        side_effect=[mock_get_response, mock_patch_response]
    )
    result = await add_comment_action.execute(
        id="INC0001234", comment="Test comment", is_sys_id=False
    )

    assert result["status"] == "success"
    assert "comment added" in result["message"].lower()


@pytest.mark.asyncio
async def test_add_comment_missing_id(add_comment_action):
    """Test adding comment without ticket ID."""
    result = await add_comment_action.execute(comment="Test comment")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_add_comment_missing_comment(add_comment_action):
    """Test adding comment without comment text."""
    result = await add_comment_action.execute(id="INC0001234")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# QueryUsersAction Tests


@pytest.mark.asyncio
async def test_query_users_success(query_users_action):
    """Test querying users successfully."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": [
            {"user_name": "john.doe", "email": "john@example.com"},
            {"user_name": "jane.smith", "email": "jane@example.com"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    query_users_action.http_request = AsyncMock(return_value=mock_response)
    result = await query_users_action.execute()

    assert result["status"] == "success"
    assert result["data"]["total_users"] == 2
    assert len(result["data"]["users"]) == 2


@pytest.mark.asyncio
async def test_query_users_with_filter(query_users_action):
    """Test querying users with query filter."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": [{"user_name": "john.doe", "email": "john@example.com"}]
    }
    mock_response.raise_for_status = MagicMock()

    query_users_action.http_request = AsyncMock(return_value=mock_response)
    result = await query_users_action.execute(query="email=john@example.com")

    assert result["status"] == "success"
    assert result["data"]["total_users"] == 1


@pytest.mark.asyncio
async def test_query_users_http_error(query_users_action):
    """Test query users with HTTP error."""
    mock_response = MagicMock()
    mock_response.status_code = 403

    query_users_action.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )
    )
    result = await query_users_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"

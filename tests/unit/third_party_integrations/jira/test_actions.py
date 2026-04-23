"""Unit tests for JIRA integration actions."""

from unittest.mock import AsyncMock, patch

import pytest

from analysi.integrations.framework.integrations.jira.actions import (
    AddCommentAction,
    CreateTicketAction,
    DeleteTicketAction,
    GetTicketAction,
    HealthCheckAction,
    ListProjectsAction,
    ListTicketsAction,
    SearchUsersAction,
    SetTicketStatusAction,
    UpdateTicketAction,
)


class TestHealthCheckAction:
    """Test JIRA health check action."""

    @pytest.fixture
    def health_check_action(self):
        """Create health check action instance."""
        return HealthCheckAction(
            integration_id="jira",
            action_id="health_check",
            settings={
                "url": "https://example.atlassian.net",
                "verify_ssl": True,
            },
            credentials={
                "username": "test@example.com",
                "password": "test-token",
            },
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check."""
        mock_user_response = {
            "displayName": "Test User",
            "emailAddress": "test@example.com",
        }
        mock_server_response = {
            "version": "8.20.0",
            "serverTitle": "JIRA Test",
        }

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
        ) as mock_request:
            mock_request.side_effect = [mock_user_response, mock_server_response]
            result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["user"] == "Test User"
        assert result["data"]["server_version"] == "8.20.0"

    @pytest.mark.asyncio
    async def test_health_check_missing_url(self):
        """Test health check with missing URL."""
        action = HealthCheckAction(
            integration_id="jira",
            action_id="health_check",
            settings={},
            credentials={"username": "test", "password": "test"},
            # url is now in settings, not credentials - empty settings means no url
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "Missing JIRA URL" in result["error"]
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_health_check_missing_auth(self):
        """Test health check with missing credentials."""
        action = HealthCheckAction(
            integration_id="jira",
            action_id="health_check",
            settings={"url": "https://example.atlassian.net"},
            credentials={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "Missing username or password" in result["error"]
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_health_check_api_error(self, health_check_action):
        """Test health check with API error."""
        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            side_effect=Exception("Authentication failed - invalid credentials"),
        ):
            result = await health_check_action.execute()

        assert result["status"] == "error"
        assert "Authentication failed" in result["error"]
        assert result["data"]["healthy"] is False


class TestCreateTicketAction:
    """Test JIRA create ticket action."""

    @pytest.fixture
    def create_ticket_action(self):
        """Create create ticket action instance."""
        return CreateTicketAction(
            integration_id="jira",
            action_id="create_ticket",
            settings={
                "url": "https://example.atlassian.net",
                "verify_ssl": True,
            },
            credentials={
                "username": "test@example.com",
                "password": "test-token",
            },
        )

    @pytest.mark.asyncio
    async def test_create_ticket_success(self, create_ticket_action):
        """Test successful ticket creation."""
        mock_response = {
            "id": "10001",
            "key": "PROJ-123",
            "self": "https://example.atlassian.net/rest/api/2/issue/10001",
        }

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await create_ticket_action.execute(
                summary="Test ticket",
                project_key="PROJ",
                issue_type="Bug",
                description="Test description",
                priority="High",
            )

        assert result["status"] == "success"
        assert result["ticket_id"] == "10001"
        assert result["ticket_key"] == "PROJ-123"
        assert "PROJ-123" in result["message"]

    @pytest.mark.asyncio
    async def test_create_ticket_with_labels(self, create_ticket_action):
        """Test ticket creation with labels."""
        mock_response = {
            "id": "10002",
            "key": "PROJ-124",
            "self": "https://example.atlassian.net/rest/api/2/issue/10002",
        }

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await create_ticket_action.execute(
                summary="Test ticket with labels",
                project_key="PROJ",
                issue_type="Task",
                labels="security,urgent,incident",
            )

        assert result["status"] == "success"
        assert result["ticket_key"] == "PROJ-124"

    @pytest.mark.asyncio
    async def test_create_ticket_missing_summary(self, create_ticket_action):
        """Test ticket creation with missing summary."""
        result = await create_ticket_action.execute(
            project_key="PROJ",
            issue_type="Bug",
        )

        assert result["status"] == "error"
        assert "Missing required parameter 'summary'" in result["error"]

    @pytest.mark.asyncio
    async def test_create_ticket_missing_project_key(self, create_ticket_action):
        """Test ticket creation with missing project key."""
        result = await create_ticket_action.execute(
            summary="Test ticket",
            issue_type="Bug",
        )

        assert result["status"] == "error"
        assert "Missing required parameter 'project_key'" in result["error"]

    @pytest.mark.asyncio
    async def test_create_ticket_missing_issue_type(self, create_ticket_action):
        """Test ticket creation with missing issue type."""
        result = await create_ticket_action.execute(
            summary="Test ticket",
            project_key="PROJ",
        )

        assert result["status"] == "error"
        assert "Missing required parameter 'issue_type'" in result["error"]


class TestGetTicketAction:
    """Test JIRA get ticket action."""

    @pytest.fixture
    def get_ticket_action(self):
        """Create get ticket action instance."""
        return GetTicketAction(
            integration_id="jira",
            action_id="get_ticket",
            settings={
                "url": "https://example.atlassian.net",
                "verify_ssl": True,
            },
            credentials={
                "username": "test@example.com",
                "password": "test-token",
            },
        )

    @pytest.mark.asyncio
    async def test_get_ticket_success(self, get_ticket_action):
        """Test successful get ticket."""
        mock_response = {
            "id": "10001",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test ticket",
                "description": "Test description",
                "status": {"name": "Open"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "John Doe"},
                "reporter": {"displayName": "Jane Smith"},
                "created": "2024-01-01T00:00:00.000+0000",
                "updated": "2024-01-02T00:00:00.000+0000",
                "labels": ["security", "urgent"],
            },
        }

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await get_ticket_action.execute(ticket_id="PROJ-123")

        assert result["status"] == "success"
        assert result["ticket_id"] == "10001"
        assert result["ticket_key"] == "PROJ-123"
        assert result["summary"] == "Test ticket"
        assert result["ticket_status"] == "Open"
        assert result["priority"] == "High"
        assert result["assignee"] == "John Doe"
        assert result["labels"] == ["security", "urgent"]

    @pytest.mark.asyncio
    async def test_get_ticket_missing_id(self, get_ticket_action):
        """Test get ticket with missing ticket ID."""
        result = await get_ticket_action.execute()

        assert result["status"] == "error"
        assert "Missing required parameter 'ticket_id'" in result["error"]

    @pytest.mark.asyncio
    async def test_get_ticket_not_found(self, get_ticket_action):
        """Test not-found returns success with not_found flag (not error)."""
        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            side_effect=Exception("Resource not found"),
        ):
            result = await get_ticket_action.execute(ticket_id="PROJ-999")

        assert result["status"] == "success"
        assert result["not_found"] is True


class TestUpdateTicketAction:
    """Test JIRA update ticket action."""

    @pytest.fixture
    def update_ticket_action(self):
        """Create update ticket action instance."""
        return UpdateTicketAction(
            integration_id="jira",
            action_id="update_ticket",
            settings={
                "url": "https://example.atlassian.net",
                "verify_ssl": True,
            },
            credentials={
                "username": "test@example.com",
                "password": "test-token",
            },
        )

    @pytest.mark.asyncio
    async def test_update_ticket_success(self, update_ticket_action):
        """Test successful ticket update."""
        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await update_ticket_action.execute(
                ticket_id="PROJ-123",
                summary="Updated summary",
                description="Updated description",
                priority="Critical",
            )

        assert result["status"] == "success"
        assert result["ticket_id"] == "PROJ-123"
        assert "Successfully updated" in result["message"]

    @pytest.mark.asyncio
    async def test_update_ticket_missing_id(self, update_ticket_action):
        """Test update ticket with missing ticket ID."""
        result = await update_ticket_action.execute(summary="Updated summary")

        assert result["status"] == "error"
        assert "Missing required parameter 'ticket_id'" in result["error"]

    @pytest.mark.asyncio
    async def test_update_ticket_no_fields(self, update_ticket_action):
        """Test update ticket with no fields to update."""
        result = await update_ticket_action.execute(ticket_id="PROJ-123")

        assert result["status"] == "error"
        assert "No fields provided to update" in result["error"]


class TestAddCommentAction:
    """Test JIRA add comment action."""

    @pytest.fixture
    def add_comment_action(self):
        """Create add comment action instance."""
        return AddCommentAction(
            integration_id="jira",
            action_id="add_comment",
            settings={
                "url": "https://example.atlassian.net",
                "verify_ssl": True,
            },
            credentials={
                "username": "test@example.com",
                "password": "test-token",
            },
        )

    @pytest.mark.asyncio
    async def test_add_comment_success(self, add_comment_action):
        """Test successful comment addition."""
        mock_response = {
            "id": "10050",
            "body": "Test comment",
            "author": {"displayName": "Test User"},
        }

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await add_comment_action.execute(
                ticket_id="PROJ-123",
                comment="Test comment",
            )

        assert result["status"] == "success"
        assert result["ticket_id"] == "PROJ-123"
        assert result["comment_id"] == "10050"
        assert "Successfully added comment" in result["message"]

    @pytest.mark.asyncio
    async def test_add_comment_missing_ticket_id(self, add_comment_action):
        """Test add comment with missing ticket ID."""
        result = await add_comment_action.execute(comment="Test comment")

        assert result["status"] == "error"
        assert "Missing required parameter 'ticket_id'" in result["error"]

    @pytest.mark.asyncio
    async def test_add_comment_missing_comment(self, add_comment_action):
        """Test add comment with missing comment text."""
        result = await add_comment_action.execute(ticket_id="PROJ-123")

        assert result["status"] == "error"
        assert "Missing required parameter 'comment'" in result["error"]


class TestSetTicketStatusAction:
    """Test JIRA set ticket status action."""

    @pytest.fixture
    def set_status_action(self):
        """Create set ticket status action instance."""
        return SetTicketStatusAction(
            integration_id="jira",
            action_id="set_ticket_status",
            settings={
                "url": "https://example.atlassian.net",
                "verify_ssl": True,
            },
            credentials={
                "username": "test@example.com",
                "password": "test-token",
            },
        )

    @pytest.mark.asyncio
    async def test_set_status_success(self, set_status_action):
        """Test successful status change."""
        mock_transitions_response = {
            "transitions": [
                {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
                {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
                {"id": "31", "name": "Done", "to": {"name": "Done"}},
            ]
        }

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
        ) as mock_request:
            mock_request.side_effect = [mock_transitions_response, {}]
            result = await set_status_action.execute(
                ticket_id="PROJ-123",
                status="Done",
            )

        assert result["status"] == "success"
        assert result["ticket_id"] == "PROJ-123"
        assert result["new_status"] == "Done"
        assert "Successfully set ticket" in result["message"]

    @pytest.mark.asyncio
    async def test_set_status_with_comment(self, set_status_action):
        """Test status change with comment."""
        mock_transitions_response = {
            "transitions": [
                {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
            ]
        }

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
        ) as mock_request:
            mock_request.side_effect = [mock_transitions_response, {}]
            result = await set_status_action.execute(
                ticket_id="PROJ-123",
                status="In Progress",
                comment="Starting work on this",
            )

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_set_status_invalid_status(self, set_status_action):
        """Test status change with invalid status."""
        mock_transitions_response = {
            "transitions": [
                {"id": "11", "name": "To Do", "to": {"name": "To Do"}},
            ]
        }

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            return_value=mock_transitions_response,
        ):
            result = await set_status_action.execute(
                ticket_id="PROJ-123",
                status="InvalidStatus",
            )

        assert result["status"] == "error"
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_set_status_missing_ticket_id(self, set_status_action):
        """Test status change with missing ticket ID."""
        result = await set_status_action.execute(status="Done")

        assert result["status"] == "error"
        assert "Missing required parameter 'ticket_id'" in result["error"]

    @pytest.mark.asyncio
    async def test_set_status_missing_status(self, set_status_action):
        """Test status change with missing status."""
        result = await set_status_action.execute(ticket_id="PROJ-123")

        assert result["status"] == "error"
        assert "Missing required parameter 'status'" in result["error"]


class TestDeleteTicketAction:
    """Test JIRA delete ticket action."""

    @pytest.fixture
    def delete_ticket_action(self):
        """Create delete ticket action instance."""
        return DeleteTicketAction(
            integration_id="jira",
            action_id="delete_ticket",
            settings={
                "url": "https://example.atlassian.net",
                "verify_ssl": True,
            },
            credentials={
                "username": "test@example.com",
                "password": "test-token",
            },
        )

    @pytest.mark.asyncio
    async def test_delete_ticket_success(self, delete_ticket_action):
        """Test successful ticket deletion."""
        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await delete_ticket_action.execute(ticket_id="PROJ-123")

        assert result["status"] == "success"
        assert result["ticket_id"] == "PROJ-123"
        assert "Successfully deleted" in result["message"]

    @pytest.mark.asyncio
    async def test_delete_ticket_missing_id(self, delete_ticket_action):
        """Test delete ticket with missing ticket ID."""
        result = await delete_ticket_action.execute()

        assert result["status"] == "error"
        assert "Missing required parameter 'ticket_id'" in result["error"]


class TestListProjectsAction:
    """Test JIRA list projects action."""

    @pytest.fixture
    def list_projects_action(self):
        """Create list projects action instance."""
        return ListProjectsAction(
            integration_id="jira",
            action_id="list_projects",
            settings={
                "url": "https://example.atlassian.net",
                "verify_ssl": True,
            },
            credentials={
                "username": "test@example.com",
                "password": "test-token",
            },
        )

    @pytest.mark.asyncio
    async def test_list_projects_success(self, list_projects_action):
        """Test successful project listing."""
        mock_response = [
            {
                "id": "10000",
                "key": "PROJ",
                "name": "Project 1",
                "projectTypeKey": "software",
            },
            {
                "id": "10001",
                "key": "TEST",
                "name": "Test Project",
                "projectTypeKey": "business",
            },
        ]

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await list_projects_action.execute()

        assert result["status"] == "success"
        assert result["total_projects"] == 2
        assert len(result["projects"]) == 2
        assert result["projects"][0]["key"] == "PROJ"
        assert result["projects"][1]["key"] == "TEST"


class TestListTicketsAction:
    """Test JIRA list tickets action."""

    @pytest.fixture
    def list_tickets_action(self):
        """Create list tickets action instance."""
        return ListTicketsAction(
            integration_id="jira",
            action_id="list_tickets",
            settings={
                "url": "https://example.atlassian.net",
                "verify_ssl": True,
            },
            credentials={
                "username": "test@example.com",
                "password": "test-token",
            },
        )

    @pytest.mark.asyncio
    async def test_list_tickets_success(self, list_tickets_action):
        """Test successful ticket listing."""
        mock_response = {
            "total": 2,
            "startAt": 0,
            "maxResults": 50,
            "issues": [
                {
                    "id": "10001",
                    "key": "PROJ-123",
                    "fields": {
                        "summary": "Test ticket 1",
                        "status": {"name": "Open"},
                        "priority": {"name": "High"},
                        "assignee": {"displayName": "John Doe"},
                        "created": "2024-01-01T00:00:00.000+0000",
                        "updated": "2024-01-02T00:00:00.000+0000",
                    },
                },
                {
                    "id": "10002",
                    "key": "PROJ-124",
                    "fields": {
                        "summary": "Test ticket 2",
                        "status": {"name": "In Progress"},
                        "priority": None,
                        "assignee": None,
                        "created": "2024-01-03T00:00:00.000+0000",
                        "updated": "2024-01-04T00:00:00.000+0000",
                    },
                },
            ],
        }

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await list_tickets_action.execute(project_key="PROJ")

        assert result["status"] == "success"
        assert result["total_issues"] == 2
        assert len(result["issues"]) == 2
        assert result["issues"][0]["key"] == "PROJ-123"
        assert result["issues"][1]["assignee"] is None

    @pytest.mark.asyncio
    async def test_list_tickets_with_jql(self, list_tickets_action):
        """Test ticket listing with custom JQL."""
        mock_response = {
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
            "issues": [
                {
                    "id": "10001",
                    "key": "PROJ-123",
                    "fields": {
                        "summary": "Test ticket",
                        "status": {"name": "Open"},
                        "priority": {"name": "High"},
                        "assignee": {"displayName": "John Doe"},
                        "created": "2024-01-01T00:00:00.000+0000",
                        "updated": "2024-01-02T00:00:00.000+0000",
                    },
                },
            ],
        }

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await list_tickets_action.execute(
                jql="project = PROJ AND status = Open"
            )

        assert result["status"] == "success"
        assert result["total_issues"] == 1


class TestSearchUsersAction:
    """Test JIRA search users action."""

    @pytest.fixture
    def search_users_action(self):
        """Create search users action instance."""
        return SearchUsersAction(
            integration_id="jira",
            action_id="search_users",
            settings={
                "url": "https://example.atlassian.net",
                "verify_ssl": True,
            },
            credentials={
                "username": "test@example.com",
                "password": "test-token",
            },
        )

    @pytest.mark.asyncio
    async def test_search_users_success(self, search_users_action):
        """Test successful user search."""
        mock_response = [
            {
                "accountId": "123456:abcd-efgh",
                "name": "jdoe",
                "displayName": "John Doe",
                "emailAddress": "jdoe@example.com",
                "active": True,
            },
            {
                "accountId": "789012:ijkl-mnop",
                "name": "jsmith",
                "displayName": "Jane Smith",
                "emailAddress": "jsmith@example.com",
                "active": True,
            },
        ]

        with patch(
            "analysi.integrations.framework.integrations.jira.actions._make_jira_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await search_users_action.execute(query="john")

        assert result["status"] == "success"
        assert result["total_users"] == 2
        assert len(result["users"]) == 2
        assert result["users"][0]["display_name"] == "John Doe"

    @pytest.mark.asyncio
    async def test_search_users_missing_query(self, search_users_action):
        """Test user search with missing query."""
        result = await search_users_action.execute()

        assert result["status"] == "error"
        assert "Missing required parameter 'query'" in result["error"]

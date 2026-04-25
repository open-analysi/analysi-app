"""Unit tests for Google Gmail integration actions."""

import json
from unittest.mock import MagicMock, patch

import pytest

from analysi.integrations.framework.integrations.google_gmail.actions import (
    DeleteEmailAction,
    GetEmailAction,
    GetUserAction,
    HealthCheckAction,
    ListUsersAction,
    RunQueryAction,
    SendEmailAction,
)


@pytest.fixture
def credentials():
    """Sample credentials for testing."""
    return {
        "key_json": json.dumps(
            {
                "type": "service_account",
                "project_id": "test-project",
                "private_key_id": "key123",
                "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
                "client_email": "test@test-project.iam.gserviceaccount.com",
                "client_id": "123456789",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
    }


@pytest.fixture
def settings():
    """Sample settings for testing."""
    return {
        "login_email": "admin@example.com",
        "timeout": 30,
        "default_format": "metadata",
    }


# HealthCheckAction Tests


class TestHealthCheckAction:
    """Test Google Gmail health check action."""

    @pytest.fixture
    def health_check_action(self, credentials, settings):
        """Create health check action instance."""
        return HealthCheckAction(
            integration_id="google_gmail",
            action_id="health_check",
            credentials=credentials,
            settings=settings,
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check."""
        mock_service = MagicMock()
        mock_users = MagicMock()
        mock_list = MagicMock()
        mock_execute = MagicMock(return_value={"users": []})

        mock_list.execute = mock_execute
        mock_users.list.return_value = mock_list
        mock_service.users.return_value = mock_users

        with (
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.service_account.Credentials.from_service_account_info"
            ) as mock_creds,
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.discovery.build",
                return_value=mock_service,
            ),
        ):
            mock_creds_obj = MagicMock()
            mock_creds_obj.with_subject.return_value = mock_creds_obj
            mock_creds.return_value = mock_creds_obj

            result = await health_check_action.execute()

        assert result["status"] == "success"
        assert "data" in result
        assert result["data"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_health_check_missing_credentials(self):
        """Test health check with missing credentials."""
        action = HealthCheckAction(
            integration_id="google_gmail",
            action_id="health_check",
            credentials={},
            settings={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "Missing required credentials" in result["error"]

    @pytest.mark.asyncio
    async def test_health_check_invalid_json(self, credentials, settings):
        """Test health check with invalid JSON credentials."""
        invalid_creds = credentials.copy()
        invalid_creds["key_json"] = "invalid json"

        action = HealthCheckAction(
            integration_id="google_gmail",
            action_id="health_check",
            credentials=invalid_creds,
            settings=settings,
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_health_check_api_error(self, health_check_action):
        """Test health check with API error."""
        with (
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.service_account.Credentials.from_service_account_info"
            ) as mock_creds,
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.discovery.build"
            ) as mock_build,
        ):
            mock_creds_obj = MagicMock()
            mock_creds_obj.with_subject.return_value = mock_creds_obj
            mock_creds.return_value = mock_creds_obj
            mock_build.side_effect = Exception("API Error")

            result = await health_check_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "GoogleAPIError"


# ListUsersAction Tests


class TestListUsersAction:
    """Test Google Gmail list users action."""

    @pytest.fixture
    def list_users_action(self, credentials, settings):
        """Create list users action instance."""
        return ListUsersAction(
            integration_id="google_gmail",
            action_id="list_users",
            credentials=credentials,
            settings=settings,
        )

    @pytest.mark.asyncio
    async def test_list_users_success(self, list_users_action):
        """Test successful list users."""
        mock_service = MagicMock()
        mock_users_resp = {
            "users": [
                {"primaryEmail": "user1@example.com", "id": "123"},
                {"primaryEmail": "user2@example.com", "id": "456"},
            ]
        }

        mock_service.users().list().execute.return_value = mock_users_resp

        with (
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.service_account.Credentials.from_service_account_info"
            ) as mock_creds,
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.discovery.build",
                return_value=mock_service,
            ),
        ):
            mock_creds_obj = MagicMock()
            mock_creds_obj.with_subject.return_value = mock_creds_obj
            mock_creds.return_value = mock_creds_obj

            result = await list_users_action.execute(max_items=500)

        assert result["status"] == "success"
        assert len(result["data"]) == 2
        assert result["summary"]["total_users_returned"] == 2

    @pytest.mark.asyncio
    async def test_list_users_missing_credentials(self):
        """Test list users with missing credentials."""
        action = ListUsersAction(
            integration_id="google_gmail",
            action_id="list_users",
            credentials={},
            settings={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# RunQueryAction Tests


class TestRunQueryAction:
    """Test Google Gmail run query action."""

    @pytest.fixture
    def run_query_action(self, credentials, settings):
        """Create run query action instance."""
        return RunQueryAction(
            integration_id="google_gmail",
            action_id="run_query",
            credentials=credentials,
            settings=settings,
        )

    @pytest.mark.asyncio
    async def test_run_query_success(self, run_query_action):
        """Test successful run query."""
        mock_service = MagicMock()
        mock_messages_resp = {"messages": [{"id": "msg123"}, {"id": "msg456"}]}
        mock_email_details = {
            "id": "msg123",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                ]
            },
        }

        mock_service.users().messages().list().execute.return_value = mock_messages_resp
        mock_service.users().messages().get().execute.return_value = mock_email_details

        with (
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.service_account.Credentials.from_service_account_info"
            ) as mock_creds,
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.discovery.build",
                return_value=mock_service,
            ),
        ):
            mock_creds_obj = MagicMock()
            mock_creds_obj.with_subject.return_value = mock_creds_obj
            mock_creds.return_value = mock_creds_obj

            result = await run_query_action.execute(
                email="user@example.com", subject="Test"
            )

        assert result["status"] == "success"
        assert "data" in result

    @pytest.mark.asyncio
    async def test_run_query_missing_email(self):
        """Test run query with missing email parameter."""
        action = RunQueryAction(
            integration_id="google_gmail",
            action_id="run_query",
            credentials={"key_json": "{}"},
            settings={"login_email": "admin@example.com"},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "email" in result["error"]


# DeleteEmailAction Tests


class TestDeleteEmailAction:
    """Test Google Gmail delete email action."""

    @pytest.fixture
    def delete_email_action(self, credentials, settings):
        """Create delete email action instance."""
        return DeleteEmailAction(
            integration_id="google_gmail",
            action_id="delete_email",
            credentials=credentials,
            settings=settings,
        )

    @pytest.mark.asyncio
    async def test_delete_email_success(self, delete_email_action):
        """Test successful delete email."""
        mock_service = MagicMock()
        mock_service.users().messages().get().execute.return_value = {"id": "msg123"}
        mock_service.users().messages().batchDelete().execute.return_value = {}

        with (
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.service_account.Credentials.from_service_account_info"
            ) as mock_creds,
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.discovery.build",
                return_value=mock_service,
            ),
        ):
            mock_creds_obj = MagicMock()
            mock_creds_obj.with_subject.return_value = mock_creds_obj
            mock_creds.return_value = mock_creds_obj

            result = await delete_email_action.execute(
                id="msg123", email="user@example.com"
            )

        assert result["status"] == "success"
        assert "summary" in result
        assert "msg123" in result["summary"]["deleted_emails"]

    @pytest.mark.asyncio
    async def test_delete_email_missing_parameters(self):
        """Test delete email with missing parameters."""
        action = DeleteEmailAction(
            integration_id="google_gmail",
            action_id="delete_email",
            credentials={"key_json": "{}"},
            settings={"login_email": "admin@example.com"},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# GetEmailAction Tests


class TestGetEmailAction:
    """Test Google Gmail get email action."""

    @pytest.fixture
    def get_email_action(self, credentials, settings):
        """Create get email action instance."""
        return GetEmailAction(
            integration_id="google_gmail",
            action_id="get_email",
            credentials=credentials,
            settings=settings,
        )

    @pytest.mark.asyncio
    async def test_get_email_success(self, get_email_action):
        """Test successful get email."""
        mock_service = MagicMock()
        mock_messages_resp = {"messages": [{"id": "msg123"}]}
        mock_email_details = {
            "id": "msg123",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                ]
            },
        }

        mock_service.users().messages().list().execute.return_value = mock_messages_resp
        mock_service.users().messages().get().execute.return_value = mock_email_details

        with (
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.service_account.Credentials.from_service_account_info"
            ) as mock_creds,
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.discovery.build",
                return_value=mock_service,
            ),
        ):
            mock_creds_obj = MagicMock()
            mock_creds_obj.with_subject.return_value = mock_creds_obj
            mock_creds.return_value = mock_creds_obj

            result = await get_email_action.execute(
                email="user@example.com", internet_message_id="<test@example.com>"
            )

        assert result["status"] == "success"
        assert "data" in result

    @pytest.mark.asyncio
    async def test_get_email_missing_parameters(self):
        """Test get email with missing parameters."""
        action = GetEmailAction(
            integration_id="google_gmail",
            action_id="get_email",
            credentials={"key_json": "{}"},
            settings={"login_email": "admin@example.com"},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_get_email_invalid_format(self, get_email_action):
        """Test get email with invalid format for download."""
        result = await get_email_action.execute(
            email="user@example.com",
            internet_message_id="<test@example.com>",
            download_email=True,
            format="metadata",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "raw" in result["error"]


# GetUserAction Tests


class TestGetUserAction:
    """Test Google Gmail get user action."""

    @pytest.fixture
    def get_user_action(self, credentials, settings):
        """Create get user action instance."""
        return GetUserAction(
            integration_id="google_gmail",
            action_id="get_user",
            credentials=credentials,
            settings=settings,
        )

    @pytest.mark.asyncio
    async def test_get_user_success(self, get_user_action):
        """Test successful get user."""
        mock_service = MagicMock()
        mock_user_info = {
            "emailAddress": "user@example.com",
            "messagesTotal": 100,
            "threadsTotal": 50,
        }

        mock_service.users().getProfile().execute.return_value = mock_user_info

        with (
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.service_account.Credentials.from_service_account_info"
            ) as mock_creds,
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.discovery.build",
                return_value=mock_service,
            ),
        ):
            mock_creds_obj = MagicMock()
            mock_creds_obj.with_subject.return_value = mock_creds_obj
            mock_creds.return_value = mock_creds_obj

            result = await get_user_action.execute(email="user@example.com")

        assert result["status"] == "success"
        assert result["data"]["emailAddress"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_get_user_missing_email(self):
        """Test get user with missing email parameter."""
        action = GetUserAction(
            integration_id="google_gmail",
            action_id="get_user",
            credentials={"key_json": "{}"},
            settings={"login_email": "admin@example.com"},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# SendEmailAction Tests


class TestSendEmailAction:
    """Test Google Gmail send email action."""

    @pytest.fixture
    def send_email_action(self, credentials, settings):
        """Create send email action instance."""
        return SendEmailAction(
            integration_id="google_gmail",
            action_id="send_email",
            credentials=credentials,
            settings=settings,
        )

    @pytest.mark.asyncio
    async def test_send_email_success(self, send_email_action):
        """Test successful send email."""
        mock_service = MagicMock()
        mock_sent_message = {"id": "sent123", "threadId": "thread123"}

        mock_service.users().messages().send().execute.return_value = mock_sent_message

        with (
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.service_account.Credentials.from_service_account_info"
            ) as mock_creds,
            patch(
                "analysi.integrations.framework.integrations.google_gmail.actions.discovery.build",
                return_value=mock_service,
            ),
        ):
            mock_creds_obj = MagicMock()
            mock_creds_obj.with_subject.return_value = mock_creds_obj
            mock_creds.return_value = mock_creds_obj

            result = await send_email_action.execute(
                to="recipient@example.com",
                subject="Test Email",
                body="This is a test email",
            )

        assert result["status"] == "success"
        assert "sent123" in result["message"]

    @pytest.mark.asyncio
    async def test_send_email_missing_parameters(self):
        """Test send email with missing parameters."""
        action = SendEmailAction(
            integration_id="google_gmail",
            action_id="send_email",
            credentials={"key_json": "{}"},
            settings={"login_email": "admin@example.com"},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

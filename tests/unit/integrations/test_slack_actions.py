"""
Unit tests for Slack integration actions.

Tests token fallback behavior: create_channel and invite_users
should accept either user_token or bot_token.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.integrations.framework.integrations.slack.actions import (
    CreateChannelAction,
    InviteUsersAction,
    UploadFileAction,
)


def _make_action(action_class, credentials):
    """Helper to instantiate a Slack action with given credentials."""
    return action_class(
        integration_id="slack-test",
        action_id="test",
        settings={"timeout": 5},
        credentials=credentials,
    )


def _mock_slack_response(data):
    """Create a mock httpx response with sync .json() and .raise_for_status()."""
    response = MagicMock()
    response.json.return_value = data
    response.raise_for_status = MagicMock()
    return response


class TestCreateChannelTokenFallback:
    """Token fallback: create_channel uses user_token, falls back to bot_token."""

    @pytest.mark.asyncio
    async def test_uses_user_token_when_available(self):
        action = _make_action(
            CreateChannelAction,
            {"user_token": "xoxp-user", "bot_token": "xoxb-bot"},
        )
        mock_response = _mock_slack_response(
            {"ok": True, "channel": {"id": "C123", "name": "sec-test"}}
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            result = await action.execute(name="sec-test")

        assert result["status"] == "success"
        # Verify user_token was used in the Authorization header
        call_kwargs = mock_req.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "xoxp-user" in headers["Authorization"]

    @pytest.mark.asyncio
    async def test_falls_back_to_bot_token(self):
        action = _make_action(
            CreateChannelAction,
            {"bot_token": "xoxb-bot"},
        )
        mock_response = _mock_slack_response(
            {"ok": True, "channel": {"id": "C456", "name": "sec-test"}}
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            result = await action.execute(name="sec-test")

        assert result["status"] == "success"
        call_kwargs = mock_req.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "xoxb-bot" in headers["Authorization"]

    @pytest.mark.asyncio
    async def test_fails_with_no_tokens(self):
        action = _make_action(CreateChannelAction, {})
        result = await action.execute(name="sec-test")

        assert result["status"] == "error"
        assert "Missing user_token or bot_token" in result["error"]

    @pytest.mark.asyncio
    async def test_fails_with_missing_name(self):
        action = _make_action(CreateChannelAction, {"bot_token": "xoxb-bot"})
        result = await action.execute()

        assert result["status"] == "error"
        assert "Missing required parameter: name" in result["error"]

    @pytest.mark.asyncio
    async def test_name_taken_returns_channel_name_as_destination(self):
        """When channel name already exists, return #name as channel_id for send_message."""
        action = _make_action(CreateChannelAction, {"bot_token": "xoxb-bot"})
        create_response = _mock_slack_response({"ok": False, "error": "name_taken"})

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=create_response
        ):
            result = await action.execute(name="sec-test")

        assert result["status"] == "success"
        assert result["channel_id"] == "#sec-test"
        assert result["channel_name"] == "sec-test"
        assert result["already_existed"] is True


class TestInviteUsersTokenFallback:
    """Token fallback: invite_users uses user_token, falls back to bot_token."""

    @pytest.mark.asyncio
    async def test_uses_user_token_when_available(self):
        action = _make_action(
            InviteUsersAction,
            {"user_token": "xoxp-user", "bot_token": "xoxb-bot"},
        )
        mock_response = _mock_slack_response({"ok": True, "channel": {"id": "C123"}})

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            result = await action.execute(channel_id="C123", users="U001,U002")

        assert result["status"] == "success"
        call_kwargs = mock_req.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "xoxp-user" in headers["Authorization"]

    @pytest.mark.asyncio
    async def test_falls_back_to_bot_token(self):
        action = _make_action(
            InviteUsersAction,
            {"bot_token": "xoxb-bot"},
        )
        mock_response = _mock_slack_response({"ok": True, "channel": {"id": "C123"}})

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            result = await action.execute(channel_id="C123", users="U001")

        assert result["status"] == "success"
        call_kwargs = mock_req.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "xoxb-bot" in headers["Authorization"]

    @pytest.mark.asyncio
    async def test_fails_with_no_tokens(self):
        action = _make_action(InviteUsersAction, {})
        result = await action.execute(channel_id="C123", users="U001")

        assert result["status"] == "error"
        assert "Missing user_token or bot_token" in result["error"]


class TestUploadFilePathTraversal:
    """Security: upload_file must reject path traversal attempts."""

    @pytest.mark.asyncio
    async def test_rejects_relative_path_traversal(self):
        """Path with .. components should be rejected to prevent reading arbitrary files."""
        action = _make_action(UploadFileAction, {"bot_token": "xoxb-bot"})
        result = await action.execute(
            destination="#test-channel",
            file="../../../etc/passwd",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "path traversal" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_rejects_absolute_path_outside_allowed_dirs(self):
        """Absolute paths to sensitive system files should be rejected."""
        action = _make_action(UploadFileAction, {"bot_token": "xoxb-bot"})
        result = await action.execute(
            destination="#test-channel",
            file="/etc/passwd",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "path traversal" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_rejects_encoded_traversal(self):
        """Resolved path that escapes allowed directories should be rejected."""
        action = _make_action(UploadFileAction, {"bot_token": "xoxb-bot"})
        result = await action.execute(
            destination="#test-channel",
            file="/tmp/../etc/shadow",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "path traversal" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_rejects_sibling_directory_with_shared_prefix(self, monkeypatch):
        """Regression: a directory whose name shares a prefix with an allowed
        directory (e.g. /tmp_evil/) must NOT be accepted by string-prefix
        matching — Codex reviewer flag on PR #42 commit 9048f24eae.

        We patch the allowlist to a synthetic prefix so the test exercises the
        matching logic directly, independent of macOS's /tmp → /private/tmp
        symlink resolution that would mask the bug locally.
        """
        from analysi.integrations.framework.integrations.slack import actions as mod

        monkeypatch.setattr(mod, "_ALLOWED_FILE_PREFIXES", ("/safe",))

        action = _make_action(UploadFileAction, {"bot_token": "xoxb-bot"})
        # /safe_evil shares the prefix "/safe" but is a SIBLING directory.
        # A naive str.startswith check accepts this; a proper path-ancestry
        # check (Path.is_relative_to) rejects it.
        result = await action.execute(
            destination="#test-channel",
            file="/safe_evil/secret.txt",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "path traversal" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_accepts_valid_tmp_path(self):
        """Files under /tmp (artifact staging area) should be accepted."""
        import tempfile

        # Create a real temp file under /tmp to pass both path validation and isfile check
        with tempfile.NamedTemporaryFile(dir="/tmp", suffix=".txt", delete=False) as f:
            f.write(b"test content")
            test_file = f.name

        try:
            action = _make_action(UploadFileAction, {"bot_token": "xoxb-bot"})

            mock_response = _mock_slack_response({"ok": True, "file": {"id": "F123"}})
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_class.return_value = mock_client

                result = await action.execute(
                    destination="#test-channel",
                    file=test_file,
                )

            assert result["status"] == "success"
        finally:
            os.unlink(test_file)

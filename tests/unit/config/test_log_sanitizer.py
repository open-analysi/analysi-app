"""Unit tests for log sanitizer processor."""

from unittest.mock import patch

from analysi.config.log_sanitizer import sanitize_log_event


class TestSanitizeLogEvent:
    """Test PII and sensitive data redaction in log events."""

    def test_redacts_password_field(self):
        event = {"event": "login", "password": "secret123"}
        result = sanitize_log_event(None, "info", event)
        assert result["password"] == "<REDACTED>"

    def test_redacts_token_field(self):
        event = {"event": "auth", "access_token": "abc123xyz"}
        result = sanitize_log_event(None, "info", event)
        assert result["access_token"] == "<REDACTED>"

    def test_redacts_email_field(self):
        event = {"event": "lookup", "email": "user@example.com"}
        result = sanitize_log_event(None, "info", event)
        assert result["email"] == "<REDACTED>"

    def test_redacts_dict_value(self):
        event = {"event": "config", "credential": {"key": "val"}}
        result = sanitize_log_event(None, "info", event)
        assert result["credential"] == "<REDACTED dict>"

    def test_redacts_list_value(self):
        event = {"event": "batch", "secret": ["a", "b", "c"]}
        result = sanitize_log_event(None, "info", event)
        assert result["secret"] == "<REDACTED list[3]>"

    def test_safe_key_not_redacted(self):
        event = {"event": "info", "credential_id": "cred-123"}
        result = sanitize_log_event(None, "info", event)
        assert result["credential_id"] == "cred-123"

    def test_email_id_safe(self):
        event = {"event": "delete", "email_id": "msg-abc"}
        result = sanitize_log_event(None, "info", event)
        assert result["email_id"] == "msg-abc"

    def test_preserves_normal_fields(self):
        event = {"event": "process", "alert_id": "123", "status": "ok"}
        result = sanitize_log_event(None, "info", event)
        assert result["alert_id"] == "123"
        assert result["status"] == "ok"

    def test_preserves_structlog_internal_keys(self):
        event = {
            "event": "test",
            "level": "info",
            "logger_name": "my.module",
            "timestamp": "2026-01-01",
        }
        result = sanitize_log_event(None, "info", event)
        assert result["event"] == "test"
        assert result["level"] == "info"

    @patch.dict("os.environ", {"ANALYSI_LOG_PAYLOADS": "false"})
    def test_truncates_long_values_when_payloads_disabled(self):
        long_val = "x" * 2000
        event = {"event": "data", "output": long_val}
        result = sanitize_log_event(None, "info", event)
        assert result["output"].startswith("<truncated")
        assert "2000" in result["output"]

    @patch.dict("os.environ", {"ANALYSI_LOG_PAYLOADS": "true"})
    def test_preserves_long_values_when_payloads_enabled(self):
        long_val = "x" * 2000
        event = {"event": "data", "output": long_val}
        result = sanitize_log_event(None, "info", event)
        assert result["output"] == long_val

    def test_nested_dict_sanitization(self):
        event = {
            "event": "config",
            "settings": {"password": "secret", "name": "test"},
        }
        result = sanitize_log_event(None, "info", event)
        assert result["settings"]["password"] == "<REDACTED>"
        assert result["settings"]["name"] == "test"

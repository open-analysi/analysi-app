"""Unit tests for log sanitization in middleware and structlog processor."""

from analysi.config.log_sanitizer import _sanitize_event_string, sanitize_log_event
from analysi.middleware.logging import sanitize_dict


class TestLogSanitization:
    """Test sensitive data sanitization in logs."""

    def test_sanitize_credential_request(self):
        """Test sanitization of credential creation request."""
        request_body = {
            "provider": "splunk",
            "account": "prod-instance",
            "secret": {
                "username": "admin",
                "password": "super_secret_password",
                "host": "splunk.example.com",
                "port": 8089,
            },
            "credential_metadata": {"environment": "production", "region": "us-east-1"},
        }

        sanitized = sanitize_dict(request_body)

        # Provider and account should be preserved
        assert sanitized["provider"] == "splunk"
        assert sanitized["account"] == "prod-instance"

        # Secret should be completely redacted (dict values show type)
        assert sanitized["secret"] == "<REDACTED dict>"

        # Credential metadata should be preserved (safe field)
        assert sanitized["credential_metadata"]["environment"] == "production"
        assert sanitized["credential_metadata"]["region"] == "us-east-1"

    def test_sanitize_nested_sensitive_fields(self):
        """Test sanitization of nested sensitive fields."""
        data = {
            "user": "john_doe",
            "auth": {"token": "Bearer abc123xyz", "refresh_token": "refresh_abc123"},
            "api_key": "sk_test_123456",
            "config": {
                "host": "api.example.com",
                "password": "hidden_password",
                "port": 443,
            },
        }

        sanitized = sanitize_dict(data)

        # Non-sensitive fields preserved
        assert sanitized["user"] == "john_doe"
        assert sanitized["config"]["host"] == "api.example.com"
        assert sanitized["config"]["port"] == 443

        # Sensitive fields redacted (dict values show type)
        assert sanitized["auth"] == "<REDACTED dict>"
        assert sanitized["api_key"] == "<REDACTED>"
        assert sanitized["config"]["password"] == "<REDACTED>"

    def test_sanitize_lists_with_sensitive_data(self):
        """Test sanitization of lists containing sensitive data."""
        data = {
            "name": "Test",
            "credentials": [
                {"username": "user1", "password": "pass1"},
                {"username": "user2", "password": "pass2"},
            ],
            "tokens": ["token1", "token2", "token3"],
            "servers": ["server1.com", "server2.com"],
        }

        sanitized = sanitize_dict(data)

        # Regular fields preserved
        assert sanitized["name"] == "Test"
        assert sanitized["servers"] == ["server1.com", "server2.com"]

        # Lists with sensitive names fully redacted
        assert sanitized["tokens"] == "<REDACTED list[3]>"

        # Lists with field names containing sensitive keywords are also redacted
        assert sanitized["credentials"] == "<REDACTED list[2]>"

    def test_safe_fields_not_redacted(self):
        """Test that explicitly safe fields are not redacted."""
        data = {
            "credential_id": "abc-123-def",
            "credential_metadata": {"created_by": "admin", "purpose": "production"},
            "credentials_count": 5,
            "credential": {  # This should be redacted (not in safe list)
                "secret": "should_be_hidden"
            },
        }

        sanitized = sanitize_dict(data)

        # Safe fields preserved
        assert sanitized["credential_id"] == "abc-123-def"
        assert sanitized["credential_metadata"]["created_by"] == "admin"
        assert sanitized["credentials_count"] == 5

        # Non-safe credential field should be redacted (dict values show type)
        assert sanitized["credential"] == "<REDACTED dict>"

    def test_empty_and_none_values(self):
        """Test handling of empty and None values."""
        data = {"password": None, "secret": {}, "token": "", "normal_field": None}

        sanitized = sanitize_dict(data)

        # All sensitive fields should be redacted regardless of value
        assert sanitized["password"] == "<REDACTED>"
        assert sanitized["secret"] == "<REDACTED dict>"
        assert sanitized["token"] == "<REDACTED>"

        # Non-sensitive None preserved
        assert sanitized["normal_field"] is None

    def test_case_insensitive_detection(self):
        """Test that detection is case-insensitive."""
        data = {
            "PASSWORD": "secret1",
            "Password": "secret2",
            "AUTH_TOKEN": "token123",
            "Client_Secret": "secret_value",
            "Normal_Field": "visible",
        }

        sanitized = sanitize_dict(data)

        # All variations should be redacted
        assert sanitized["PASSWORD"] == "<REDACTED>"
        assert sanitized["Password"] == "<REDACTED>"
        assert sanitized["AUTH_TOKEN"] == "<REDACTED>"
        assert sanitized["Client_Secret"] == "<REDACTED>"

        # Normal field preserved
        assert sanitized["Normal_Field"] == "visible"

    def test_deeply_nested_structures(self):
        """Test sanitization of deeply nested structures."""
        data = {
            "level1": {
                "level2": {"level3": {"password": "deep_secret", "data": "visible"}}
            }
        }

        sanitized = sanitize_dict(data)

        # Deep nesting preserved with sensitive data redacted
        assert sanitized["level1"]["level2"]["level3"]["password"] == "<REDACTED>"
        assert sanitized["level1"]["level2"]["level3"]["data"] == "visible"


class TestEventStringSanitization:
    """Test defense-in-depth sanitization of the event (message) string."""

    def test_password_in_event_string(self):
        """Key=value patterns with sensitive keys are redacted."""
        event = "Login failed password=super_secret123 for user admin"
        result = _sanitize_event_string(event)
        assert "super_secret123" not in result
        assert "password=<REDACTED>" in result

    def test_token_in_event_string(self):
        event = "Auth token=mytokenvalue99 expired"
        result = _sanitize_event_string(event)
        assert "mytokenvalue99" not in result
        assert "token=<REDACTED>" in result

    def test_api_key_in_event_string(self):
        event = "Request with api_key=testkey00042 failed"
        result = _sanitize_event_string(event)
        assert "testkey00042" not in result
        assert "api_key=<REDACTED>" in result

    def test_colon_separator(self):
        """Handles key: value (colon) separator."""
        event = "secret: my_secret_value in config"
        result = _sanitize_event_string(event)
        assert "my_secret_value" not in result

    def test_email_in_event_string(self):
        event = "User john.doe@example.com logged in"
        result = _sanitize_event_string(event)
        assert "john.doe@example.com" not in result
        assert "<REDACTED_EMAIL>" in result

    def test_safe_event_unchanged(self):
        """Events without sensitive patterns are not modified."""
        event = "Processing alert abc-123 for tenant acme"
        result = _sanitize_event_string(event)
        assert result == event

    def test_case_insensitive_matching(self):
        event = "Config PASSWORD=hunter2 loaded"
        result = _sanitize_event_string(event)
        assert "hunter2" not in result

    def test_sanitize_log_event_scrubs_event_field(self):
        """The structlog processor scrubs the event string."""
        event_dict = {
            "event": "Loaded credential=secret_abc for integration test-1",
            "level": "info",
            "logger": "test",
            "integration_id": "test-1",
        }
        result = sanitize_log_event(None, "info", event_dict)
        assert "secret_abc" not in result["event"]
        assert "credential=<REDACTED>" in result["event"]

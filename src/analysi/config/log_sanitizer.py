"""PII and sensitive data sanitization for structured logs.

Defense-in-depth processor that redacts sensitive values from log events
before they reach the renderer. Runs as the last processor before output.
"""

import os
import re
from typing import Any

# Maximum value length before truncation (when payload logging is disabled)
MAX_VALUE_LENGTH = 1024

# Field names that indicate sensitive content (case-insensitive substring match)
SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "auth",
    "authorization",
    "credential",
    "private",
    "passphrase",
    "pwd",
    "passwd",
    "pass",
    "client_secret",
    "refresh_token",
    "access_token",
    "oauth_token",
    "bearer",
    "private_key",
    "secret_key",
    "ssn",
    "social_security",
    "credit_card",
    "card_number",
    "email",
    "email_address",
    "ip_address",
}

# Field names that are safe even if they contain sensitive keywords
SAFE_KEYS = {
    "credential_metadata",
    "credential_id",
    "credentials_count",
    "token_count",
    "token_usage",
    "key_id",
    "key_name",
    "key_prefix",
    "pass_count",
    "password_policy",
    "email_id",
    "email_count",
    "emails_count",
}


def _is_sensitive(key: str) -> bool:
    """Check if a field name indicates sensitive content."""
    lower = key.lower()
    if lower in SAFE_KEYS:
        return False
    return any(s in lower for s in SENSITIVE_KEYS)


def _redact_value(value: Any) -> str:
    """Redact a sensitive value."""
    if isinstance(value, dict):
        return "<REDACTED dict>"
    if isinstance(value, list):
        return f"<REDACTED list[{len(value)}]>"
    return "<REDACTED>"


# Regex patterns for sensitive values that may appear in event strings (f-string fallback)
# Each tuple: (compiled regex, replacement string)
_EVENT_SCRUB_PATTERNS: list[tuple[re.Pattern, str]] = [
    # key=value patterns where key is sensitive (e.g., "password=abc123")
    (
        re.compile(
            r"(?i)\b(password|secret|token|api_key|bearer|credential|private_key"
            r"|client_secret|access_token|refresh_token|oauth_token)"
            r"\s*[=:]\s*\S+"
        ),
        r"\1=<REDACTED>",
    ),
    # Email addresses
    (
        re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
        r"<REDACTED_EMAIL>",
    ),
]


def _sanitize_event_string(event: str) -> str:
    """Scrub sensitive patterns from the log event string (defense-in-depth)."""
    for pattern, replacement in _EVENT_SCRUB_PATTERNS:
        event = pattern.sub(replacement, event)
    return event


def _truncate_value(value: Any, max_len: int) -> Any:
    """Truncate large string values."""
    if isinstance(value, str) and len(value) > max_len:
        return f"<truncated {len(value)} bytes>"
    return value


def _sanitize_dict(data: dict, log_payloads: bool, max_len: int) -> dict:
    """Recursively sanitize a dictionary."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive(key):
            result[key] = _redact_value(value)
        elif isinstance(value, dict):
            result[key] = _sanitize_dict(value, log_payloads, max_len)
        elif isinstance(value, list):
            result[key] = [
                _sanitize_dict(item, log_payloads, max_len)
                if isinstance(item, dict)
                else item
                for item in value
            ]
        elif not log_payloads:
            result[key] = _truncate_value(value, max_len)
        else:
            result[key] = value
    return result


def sanitize_log_event(logger: object, method_name: str, event_dict: dict) -> dict:
    """Structlog processor that sanitizes PII and sensitive data.

    - Redacts values for keys matching SENSITIVE_KEYS
    - Truncates large values when ANALYSI_LOG_PAYLOADS is false (default)
    - Respects SAFE_KEYS allowlist
    """
    log_payloads = os.getenv("ANALYSI_LOG_PAYLOADS", "false").lower() == "true"

    # Scrub the event string itself (catches values embedded via f-strings)
    event = event_dict.get("event")
    if isinstance(event, str):
        event_dict["event"] = _sanitize_event_string(event)

    for key in list(event_dict.keys()):
        # Skip structlog internal keys
        if key in ("event", "level", "logger", "logger_name", "timestamp", "_record"):
            continue

        value = event_dict[key]
        if _is_sensitive(key):
            event_dict[key] = _redact_value(value)
        elif isinstance(value, dict):
            event_dict[key] = _sanitize_dict(value, log_payloads, MAX_VALUE_LENGTH)
        elif not log_payloads:
            event_dict[key] = _truncate_value(value, MAX_VALUE_LENGTH)

    return event_dict

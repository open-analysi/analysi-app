"""
Duo Security integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30  # Match upstream default

# Duo API endpoints
ENDPOINT_CHECK = "/auth/v2/check"
ENDPOINT_PREAUTH = "/auth/v2/preauth"
ENDPOINT_AUTH = "/auth/v2/auth"

# Credential field names
CREDENTIAL_API_HOST = "api_host"
CREDENTIAL_IKEY = "ikey"
CREDENTIAL_SKEY = "skey"

# Settings field names
SETTINGS_TIMEOUT = "timeout"
SETTINGS_VERIFY_CERT = "verify_server_cert"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHORIZATION = "AuthorizationError"
ERROR_TYPE_AUTHORIZATION_DENIED = "AuthorizationDenied"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = (
    "Missing required credentials: api_host, ikey, and skey are required"
)
MSG_MISSING_USER = "Missing required parameter 'user'"

# Auth result values
AUTH_RESULT_ALLOW = "allow"
AUTH_RESULT_DENY = "deny"
AUTH_PREAUTH_AUTH = "auth"

# Default values
DEFAULT_REQUEST_TYPE = "Analysi request"

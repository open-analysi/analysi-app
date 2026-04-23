"""
Cisco Secure Endpoint integration constants.
"""

# API Configuration
DEFAULT_BASE_URL = "https://api.amp.cisco.com"
API_VERSION = "v1"

# Default timeout in seconds
DEFAULT_TIMEOUT = 30

# Credential field names
CREDENTIAL_API_CLIENT_ID = "api_client_id"
CREDENTIAL_API_KEY = "api_key"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP_ERROR = "HTTPError"
ERROR_TYPE_TIMEOUT = "TimeoutError"
ERROR_TYPE_REQUEST_ERROR = "RequestError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials (api_client_id and api_key)"
MSG_MISSING_CLIENT_ID = "Missing required credential: api_client_id"
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_ENDPOINT_NOT_FOUND = "Specified endpoint not found"
MSG_CONNECTOR_GUID_VALIDATION_FAILED = "Parameter connector_guid failed validation"

# Isolation status values accepted as success
ISOLATION_SUCCESS_STATUSES = [
    "pending_start",
    "pending_stop",
    "isolated",
    "not_isolated",
]

"""
Palo Alto Cortex XDR integration constants.
"""

# API Settings
DEFAULT_TIMEOUT = 30
API_VERSION = "v1"

# Credential field names
CREDENTIAL_API_KEY = "api_key"
CREDENTIAL_API_KEY_ID = "api_key_id"
SETTINGS_FQDN = "fqdn"

# Settings field names
SETTINGS_ADVANCED = "advanced"
SETTINGS_TIMEOUT = "timeout"

# API Endpoints
ENDPOINT_GET_ENDPOINTS = "/endpoints/get_endpoints/"
ENDPOINT_GET_POLICY = "/endpoints/get_policy/"
ENDPOINT_GET_ACTION_STATUS = "/actions/get_action_status/"
ENDPOINT_FILE_RETRIEVAL = "/endpoints/file_retrieval/"
ENDPOINT_FILE_RETRIEVAL_DETAILS = "/actions/file_retrieval_details/"
ENDPOINT_QUARANTINE = "/endpoints/quarantine/"
ENDPOINT_RESTORE = "/endpoints/restore/"
ENDPOINT_BLOCKLIST = "/hash_exceptions/blocklist/"
ENDPOINT_ALLOWLIST = "/hash_exceptions/allowlist/"
ENDPOINT_ISOLATE = "/endpoints/isolate/"
ENDPOINT_UNISOLATE = "/endpoints/unisolate/"
ENDPOINT_SCAN = "/endpoints/scan/"
ENDPOINT_ABORT_SCAN = "/endpoints/abort_scan/"
ENDPOINT_GET_INCIDENTS = "/incidents/get_incidents/"
ENDPOINT_GET_INCIDENT_DETAILS = "/incidents/get_incident_extra_data/"
ENDPOINT_GET_ALERTS = "/alerts/get_alerts_multi_events/"

# Authentication header names
HEADER_TIMESTAMP = "x-xdr-timestamp"
HEADER_NONCE = "x-xdr-nonce"
HEADER_AUTH_ID = "x-xdr-auth-id"
HEADER_AUTHORIZATION = "Authorization"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_REQUEST = "RequestError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_ENDPOINT_ID = "Missing required parameter 'endpoint_id'"
MSG_MISSING_ACTION_ID = "Missing required parameter 'action_id'"
MSG_MISSING_FILE_HASH = "Missing required parameter 'file_hash'"
MSG_MISSING_FILE_PATH = (
    "At least one file path (windows_path, linux_path, or macos_path) is required"
)
MSG_MISSING_SCAN_CRITERIA = "At least one filter criterion or scan_all=true is required"
MSG_INVALID_ACTION_ID = "Invalid action_id: must be a positive integer"
MSG_INVALID_INCIDENT_ID = "Invalid incident_id: must be a positive integer"
MSG_INVALID_ALERT_ID = "Invalid alert_id: must be a positive integer"

# Value Lists
PLATFORMS_LIST = ["windows", "linux", "macos", "android"]
SCAN_STATUSES = [
    "none",
    "pending",
    "in_progress",
    "canceled",
    "aborted",
    "pending_cancellation",
    "success",
    "error",
]
SORT_ORDERS = ["asc", "desc"]
INCIDENT_STATUSES = [
    "new",
    "under_investigation",
    "resolved_threat_handled",
    "resolved_known_issue",
    "resolved_false_positive",
    "resolved_other",
    "resolved_auto",
]
ALERT_SEVERITIES = ["info", "low", "medium", "high", "unknown"]

# AlertSource settings
SETTINGS_DEFAULT_LOOKBACK = "default_lookback_minutes"
DEFAULT_LOOKBACK_MINUTES = 5
DEFAULT_MAX_ALERTS = 1000

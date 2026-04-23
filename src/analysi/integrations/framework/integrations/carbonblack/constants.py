"""
Carbon Black Cloud integration constants.
Uses REST API directly (not cbc-sdk).
"""

# Timeout settings
DEFAULT_TIMEOUT = 30

# ============================================================================
# API Endpoints — Carbon Black Cloud Platform REST API
# ============================================================================

# Platform / Devices
DEVICE_SEARCH_ENDPOINT = "/appservices/v6/orgs/{org_key}/devices/_search"
DEVICE_ACTIONS_ENDPOINT = "/appservices/v6/orgs/{org_key}/device_actions"
DEVICE_GET_ENDPOINT = "/appservices/v6/orgs/{org_key}/devices/{device_id}"

# Alerts (v7 API)
ALERT_SEARCH_ENDPOINT = "/api/alerts/v7/orgs/{org_key}/alerts/_search"
ALERT_GET_ENDPOINT = "/api/alerts/v7/orgs/{org_key}/alerts/{alert_id}"

# Process search (Enterprise EDR)
PROCESS_SEARCH_ENDPOINT = "/api/investigate/v2/orgs/{org_key}/processes/search_jobs"
PROCESS_RESULTS_ENDPOINT = (
    "/api/investigate/v2/orgs/{org_key}/processes/search_jobs/{job_id}/results"
)

# Reputation overrides (ban/unban hash)
REPUTATION_OVERRIDE_ENDPOINT = "/appservices/v6/orgs/{org_key}/reputations/overrides"
REPUTATION_OVERRIDE_DELETE_ENDPOINT = (
    "/appservices/v6/orgs/{org_key}/reputations/overrides/{override_id}"
)
REPUTATION_OVERRIDE_SEARCH_ENDPOINT = (
    "/appservices/v6/orgs/{org_key}/reputations/overrides/_search"
)

# Binary metadata (UBS - Unified Binary Store)
UBS_METADATA_ENDPOINT = "/ubs/v1/orgs/{org_key}/sha256/{sha256}/metadata"
UBS_SUMMARY_ENDPOINT = "/ubs/v1/orgs/{org_key}/sha256/{sha256}/summary/device"

# ============================================================================
# Credential field names
# ============================================================================
CREDENTIAL_API_KEY = "api_key"
CREDENTIAL_API_ID = "api_id"
# ============================================================================
# Settings field names
# ============================================================================
SETTINGS_ORG_KEY = "org_key"
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# ============================================================================
# Default values
# ============================================================================
DEFAULT_BASE_URL = "https://defense.conferdeploy.net"
DEFAULT_SEARCH_ROWS = 50
MAX_SEARCH_ROWS = 10000

# ============================================================================
# Status values
# ============================================================================
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# ============================================================================
# Error types
# ============================================================================
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_NOT_FOUND = "NotFoundError"

# ============================================================================
# Error messages
# ============================================================================
MSG_MISSING_CREDENTIALS = (
    "Missing required credentials: api_key, api_id, and org_key are all required"
)
MSG_MISSING_PARAMETER = "Missing required parameter: {}"
MSG_INVALID_PARAMETER = "Invalid parameter value: {}"

# ============================================================================
# Quarantine action types
# ============================================================================
QUARANTINE_ACTION = "QUARANTINE"
UNQUARANTINE_ACTION = "UNQUARANTINE"

# ============================================================================
# Reputation override types
# ============================================================================
OVERRIDE_TYPE_SHA256 = "SHA256"
OVERRIDE_LIST_BLACK = "BLACK_LIST"

# ============================================================================
# Process search polling
# ============================================================================
PROCESS_POLL_INTERVAL = 1.0  # seconds between polls
PROCESS_MAX_POLLS = 30  # max ~30s of polling

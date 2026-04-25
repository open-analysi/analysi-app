"""
Flashpoint integration constants.
"""

# API Configuration
FLASHPOINT_DEFAULT_BASE_URL = "https://api.flashpoint.io"
DEFAULT_TIMEOUT = 30

# API Endpoints
INDICATORS_ENDPOINT = "/technical-intelligence/v1/attribute"
ALL_SEARCH_ENDPOINT = "/sources/v1/noncommunities/search"
INDICATORS_SCROLL_ENDPOINT = "/technical-intelligence/v1/scroll"
ALL_SEARCH_SCROLL_ENDPOINT = "/sources/v1/noncommunities/scroll"
LIST_REPORTS_ENDPOINT = "/finished-intelligence/v1/reports"
GET_REPORT_ENDPOINT = "/finished-intelligence/v1/reports/{report_id}"
LIST_RELATED_REPORTS_ENDPOINT = "/finished-intelligence/v1/reports/{report_id}/related"

# Integration platform header (identifies Analysi as the caller)
X_FP_INTEGRATION_PLATFORM = "Analysi"

# Pagination defaults
PER_PAGE_DEFAULT_LIMIT = 500
DEFAULT_SESSION_TIMEOUT_MINUTES = 2

# Credential field names
CREDENTIAL_API_TOKEN = "api_token"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_SESSION_TIMEOUT = "session_timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_TIMEOUT = "TimeoutError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_API_TOKEN = "Missing API token in credentials"
MSG_MISSING_REPORT_ID = "Missing required parameter: report_id"
MSG_MISSING_QUERY = "Missing required parameter: query"
MSG_MISSING_ATTRIBUTE_TYPE = "Missing required parameter: attribute_type"
MSG_MISSING_ATTRIBUTE_VALUE = "Missing required parameter: attribute_value"
MSG_INVALID_LIMIT = "Limit must be a positive integer"
MSG_INVALID_COMMA_SEPARATED = (
    "Please provide a valid comma-separated list of attribute types"
)
MSG_SERVER_CONNECTION = "Connection to Flashpoint server failed"

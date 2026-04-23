"""Netskope integration constants.
"""

# API Endpoints
CONNECTIVITY_ENDPOINT = "/api/v1/clients"
QUARANTINE_ENDPOINT = "/api/v1/quarantine"
FILE_LIST_ENDPOINT = "/api/v1/updateFileHashList"
V2_EVENT_ENDPOINT = "/api/v2/events/data"
V2_URL_LIST_ENDPOINT = "/api/v2/policy/urllist"

# Event types
EVENT_TYPE_PAGE = "page"
EVENT_TYPE_APPLICATION = "application"

# URL list operations
URL_LIST_DEPLOY = "deploy"

# Pagination defaults
DEFAULT_LIMIT = 50
INITIAL_SKIP_VALUE = 0

# Time constants
SECONDS_24_HOURS = 86400
TEST_CONNECTIVITY_LIMIT = 1

# Timeout
DEFAULT_TIMEOUT = 30

# Credential field names
CREDENTIAL_API_KEY = "api_key"
CREDENTIAL_V2_API_KEY = "v2_api_key"

# Settings field names
SETTINGS_SERVER_URL = "server_url"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_LIST_NAME = "list_name"

# Default list name
DEFAULT_LIST_NAME = "phantom_list"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_HTTP = "HTTPError"

# Error messages
MSG_MISSING_SERVER_URL = "Missing required setting: server_url"
MSG_MISSING_V1_API_KEY = "Missing required credential: api_key (v1)"
MSG_MISSING_V2_API_KEY = "Missing required credential: v2_api_key"
MSG_MISSING_ANY_API_KEY = (
    "Please configure either 'api_key' (v1) or 'v2_api_key' (v2, recommended)"
)
MSG_INVALID_START_TIME = "Parameter 'start_time' failed validation"
MSG_INVALID_END_TIME = "Parameter 'end_time' failed validation"
MSG_INVALID_TIME_RANGE = (
    "Invalid time range. 'end_time' should be greater than 'start_time'"
)
MSG_INVALID_TIME_NEGATIVE = "Invalid time. Time cannot be negative"

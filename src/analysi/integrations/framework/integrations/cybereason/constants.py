"""
Cybereason EDR integration constants.
"""

# API Configuration
DEFAULT_TIMEOUT = 60  # Match upstream default
LOGIN_PATH = "/login.html"
API_BASE = "/rest"

# API Endpoints
ENDPOINT_VISUAL_SEARCH = f"{API_BASE}/visualsearch/query/simple"
ENDPOINT_ISOLATE = f"{API_BASE}/monitor/global/commands/isolate"
ENDPOINT_UNISOLATE = f"{API_BASE}/monitor/global/commands/un-isolate"
ENDPOINT_REMEDIATE = f"{API_BASE}/remediate"
ENDPOINT_SENSORS_QUERY = f"{API_BASE}/sensors/query"
ENDPOINT_CLASSIFICATION_UPDATE = f"{API_BASE}/classification/update"

# Credential field names
CREDENTIAL_BASE_URL = "base_url"
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_TIMEOUT = "timeout"
SETTINGS_VERIFY_SSL = "verify_ssl"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_HTTP_ERROR = "HTTPError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required configuration: base_url (setting), username and password (credentials) are required"
MSG_MISSING_BASE_URL = "Missing Cybereason base URL"
MSG_MISSING_USERNAME = "Missing Cybereason username"
MSG_MISSING_PASSWORD = "Missing Cybereason password"
MSG_AUTH_FAILED = (
    "Authentication failed: unable to get session cookie from Cybereason console"
)
MSG_NO_SENSOR_IDS = "No sensor IDs found for the given identifier"

# Custom reputation values
CUSTOM_REPUTATION_LIST = ["whitelist", "blacklist", "remove"]

# Query defaults
DEFAULT_TOTAL_RESULT_LIMIT = 1000
DEFAULT_PER_GROUP_LIMIT = 100
DEFAULT_PER_FEATURE_LIMIT = 100
DEFAULT_QUERY_TIMEOUT = 120000  # milliseconds

# Default headers for Cybereason API
DEFAULT_CONTENT_TYPE = "application/json"
USER_AGENT = "CybereasonNaxos/1.0.0"

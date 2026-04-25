"""
Shodan integration constants.
"""

# API Configuration
SHODAN_BASE_URL = "https://api.shodan.io/"
DEFAULT_TIMEOUT = 30

# Credential field names
CREDENTIAL_API_KEY = "api_key"

# Settings field names
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_TIMEOUT = "TimeoutError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_API_KEY = "Missing API key in credentials"
MSG_QUERY_FAILED = "Query failed"
MSG_SERVER_CONNECTION = "Connection to server failed"
MSG_INVALID_JSON = "Response is not a valid JSON"
MSG_INVALID_IP = "IP address must be a non-empty string"
MSG_INVALID_DOMAIN = "Domain must be a non-empty string"

# API endpoints
ENDPOINT_API_INFO = "api-info"
ENDPOINT_HOST_SEARCH = "shodan/host/search"
ENDPOINT_HOST_DETAIL = "shodan/host/{0}"

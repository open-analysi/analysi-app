"""
Cisco Webex integration constants.

Webex REST API v1 endpoints and configuration.
"""

# Webex REST API base URL
WEBEX_API_BASE_URL = "https://webexapis.com/v1"

# Default timeout in seconds
DEFAULT_TIMEOUT = 30

# API Endpoints
ENDPOINT_MESSAGES = "/messages"
ENDPOINT_ROOMS = "/rooms"
ENDPOINT_PEOPLE = "/people"
ENDPOINT_PEOPLE_ME = "/people/me"

# Credential field names
CREDENTIAL_BOT_TOKEN = "bot_token"

# Settings field names
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP_STATUS = "HTTPStatusError"
ERROR_TYPE_REQUEST = "RequestError"
ERROR_TYPE_TIMEOUT = "TimeoutException"
ERROR_TYPE_WEBEX_API = "WebexAPIError"

# Error messages
MSG_MISSING_BOT_TOKEN = "Missing required credential: bot_token"
MSG_MISSING_REQUIRED_PARAM = "Missing required parameter: {param}"

# Pagination
MAX_ITEMS_PER_PAGE = 100

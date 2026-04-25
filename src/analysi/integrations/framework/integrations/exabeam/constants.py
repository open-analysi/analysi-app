"""
Exabeam Advanced Analytics integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30

# API endpoints (relative to base_url)
ENDPOINT_WATCHLIST = "/watchlist"
ENDPOINT_WATCHLIST_BY_ID = "/watchlist/{watchlist_id}/"
ENDPOINT_WATCHLIST_ADD_USER = "/watchlist/user/{username}/add"
ENDPOINT_WATCHLIST_REMOVE_USER = "/watchlist/user/{username}/remove"
ENDPOINT_USER_INFO = "/user/{username}/info"
ENDPOINT_SEARCH_USERS = "/search/users"
ENDPOINT_SEARCH_ASSETS = "/search/assets"
ENDPOINT_ASSET_DATA = "/asset/{asset_id}/data"

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_VERIFY_SSL = "verify_ssl"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP_ERROR = "HTTPStatusError"
ERROR_TYPE_REQUEST = "RequestError"
ERROR_TYPE_TIMEOUT = "TimeoutError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials (username, password)"
MSG_MISSING_BASE_URL = "Missing required base_url in settings"
MSG_MISSING_USERNAME = "Missing required parameter: username"
MSG_MISSING_KEYWORD = "Missing required parameter: keyword"
MSG_MISSING_WATCHLIST_ID = "Missing required parameter: watchlist_id"
MSG_MISSING_ASSET_ID = "One of hostname or ip must be specified"
MSG_CONNECTIVITY_SUCCESS = "Exabeam connection successful"
MSG_CONNECTIVITY_FAILED = "Exabeam connection failed"

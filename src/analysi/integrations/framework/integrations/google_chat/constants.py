"""
Google Chat integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30

# Google API URLs
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CHAT_BASE_URL = "https://chat.googleapis.com"

# Credential field names
CREDENTIAL_CLIENT_ID = "client_id"
CREDENTIAL_CLIENT_SECRET = "client_secret"
CREDENTIAL_REFRESH_TOKEN = "refresh_token"

# Settings field names
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_HTTP_STATUS = "HTTPStatusError"
ERROR_TYPE_REQUEST = "RequestError"
ERROR_TYPE_TIMEOUT = "TimeoutException"
ERROR_TYPE_GOOGLE_API = "GoogleAPIError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_PARAMETER = "Missing required parameter"
MSG_INVALID_RESPONSE = "Invalid response from Google Chat API"
MSG_TOKEN_REFRESH_FAILED = "Failed to refresh access token"

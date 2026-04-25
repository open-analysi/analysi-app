"""
Mimecast integration constants.
Mimecast API v2 uses OAuth2 client credentials for authentication.
"""

# API Configuration
MIMECAST_BASE_URL_DEFAULT = "https://api.services.mimecast.com"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RESULTS = 100

# OAuth2
API_PATH_OAUTH_TOKEN = "/oauth/token"

# TTP (Targeted Threat Protection) URL endpoints
API_PATH_URL_GET_ALL = "/api/ttp/url/get-all-managed-urls"
API_PATH_URL_CREATE = "/api/ttp/url/create-managed-url"
API_PATH_URL_DELETE = "/api/ttp/url/delete-managed-url"
API_PATH_URL_DECODE = "/api/ttp/url/decode-url"

# Sender Management
API_PATH_SENDER_MANAGE = "/api/managedsender/permit-or-block-sender"

# Message Management
API_PATH_MESSAGE_SEARCH = "/api/message-finder/search"
API_PATH_MESSAGE_GET = "/api/message-finder/get-message-info"

# Credential field names
CREDENTIAL_CLIENT_ID = "client_id"
CREDENTIAL_CLIENT_SECRET = "client_secret"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: client_id and client_secret"
MSG_MISSING_URL = "Missing required parameter: url"
MSG_MISSING_ID = "Missing required parameter: id"
MSG_MISSING_SENDER = "Missing required parameter: sender"
MSG_MISSING_TO = "Missing required parameter: to"
MSG_OAUTH_TOKEN_FAILED = "Failed to obtain OAuth2 access token"
MSG_PROCESSING_RESPONSE = "Error occurred while processing the response from the server"

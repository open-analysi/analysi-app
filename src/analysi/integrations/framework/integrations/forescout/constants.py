"""
Forescout integration constants.
"""

# Web API endpoints
WEB_LOGIN_ENDPOINT = "/api/login"
WEB_HOSTS_ENDPOINT = "/api/hosts"
WEB_POLICIES_ENDPOINT = "/api/policies"

# Default settings
DEFAULT_TIMEOUT = 30

# Accept header for Forescout Web API (HAL+JSON)
ACCEPT_HEADER = "application/ha1+json"

# Auth content type for login
LOGIN_CONTENT_TYPE = "application/x-www-form-urlencoded"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: username and password"
MSG_MISSING_BASE_URL = "Missing required setting: base_url"
MSG_JWT_FAILED = "Failed to obtain JWT token from Forescout"
MSG_HOST_IDENTIFIER_REQUIRED = (
    "At least one host identifier is required: host_id, host_ip, or host_mac"
)

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"

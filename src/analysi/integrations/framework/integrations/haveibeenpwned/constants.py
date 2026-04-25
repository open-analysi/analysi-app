"""
Have I Been Pwned integration constants.
"""

# API base URL (HIBP v3)
DEFAULT_BASE_URL = "https://haveibeenpwned.com/api/v3"

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 30

# Auth header name used by HIBP API
AUTH_HEADER = "hibp-api-key"

# API endpoints (relative to base URL)
ENDPOINT_BREACHED_ACCOUNT = "/breachedaccount/{email}"
ENDPOINT_BREACHES = "/breaches"

# Default email used for health check connectivity test
HEALTH_CHECK_EMAIL = "test@gmail.com"

# Error messages
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_MISSING_PARAM = "Missing required parameter: {param}"

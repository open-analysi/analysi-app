"""
IPQualityScore integration constants.
"""

# API base domain and endpoints
IPQS_BASE_URL = "https://ipqualityscore.com/api/json"

# Endpoint path templates (appended to base URL)
# Format: /{type}/{apikey}/{value}
ENDPOINT_IP = "ip"
ENDPOINT_URL = "url"
ENDPOINT_EMAIL = "email"
ENDPOINT_PHONE = "phone"
ENDPOINT_LEAKED = "leaked"

# Timeout settings
DEFAULT_TIMEOUT = 30

# Strictness validation
STRICTNESS_VALUES = {0, 1, 2}
MAX_STRICTNESS = 2

# Dark web leak lookup types
DARK_WEB_LEAK_TYPES = {"email", "password", "username"}

# Email validation regex
EMAIL_REGEX = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}"

# Error messages
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_MISSING_PARAM = "Missing required parameter: {}"
MSG_INVALID_STRICTNESS = "strictness must be 0, 1, or 2"
MSG_INVALID_TRANSACTION_STRICTNESS = (
    "transaction_strictness must be a non-negative integer"
)
MSG_INVALID_TIMEOUT = "timeout must be a non-negative integer"
MSG_INVALID_ABUSE_STRICTNESS = "abuse_strictness must be a non-negative integer"
MSG_INVALID_LEAK_TYPE = "type must be one of: email, password, username"
MSG_INVALID_EMAIL = "Please provide a valid email address"
MSG_API_FAILURE = "IPQualityScore API did not return expected response"
MSG_RATE_LIMITED = "Request rate limited by IPQualityScore (HTTP 509)"

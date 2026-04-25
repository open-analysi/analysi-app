"""
urlscan.io integration constants.
"""

# Base URL
URLSCAN_BASE_URL = "https://urlscan.io"

# Timeout settings
DEFAULT_TIMEOUT = 120  # Match upstream default

# Polling settings
MAX_POLLING_ATTEMPTS = 10
POLLING_INTERVAL = 15  # seconds
MAX_TAGS = 10

# HTTP status codes
BAD_REQUEST_CODE = 400
NOT_FOUND_CODE = 404

# API endpoints
ENDPOINT_USER_QUOTAS = "/user/quotas/"
ENDPOINT_SEARCH = "/api/v1/search/"
ENDPOINT_RESULT = "/api/v1/result/{}"
ENDPOINT_SCAN = "/api/v1/scan/"
ENDPOINT_SCREENSHOT = "/screenshots/{}.png"

# Error messages
MSG_MISSING_API_KEY = "API key is required for this action"
MSG_MISSING_REPORT_ID = "Report ID parameter is required"
MSG_MISSING_URL = "URL parameter is required"
MSG_MISSING_DOMAIN = "Domain parameter is required"
MSG_MISSING_IP = "IP address parameter is required"
MSG_REPORT_UUID_MISSING = "Unable to get report UUID from scan"
MSG_REPORT_NOT_FOUND = "Report not found or still processing"
MSG_NO_DATA = "No data found"
MSG_TAGS_EXCEED_MAX = f"Number of tags cannot exceed {MAX_TAGS}"
MSG_INVALID_IP = "Invalid IP address format"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP_ERROR = "HTTPStatusError"
ERROR_TYPE_REQUEST_ERROR = "RequestError"
ERROR_TYPE_TIMEOUT = "TimeoutError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

"""
NIST NVD integration constants.
"""

# API Configuration
NISTNVD_BASE_URL = "https://services.nvd.nist.gov"
DEFAULT_API_VERSION = "2.0"
DEFAULT_TIMEOUT = 30

# Credential field names (Note: NIST NVD API is public and doesn't require credentials)
# No credential fields needed

# Settings field names
SETTINGS_API_VERSION = "api_version"
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_NOT_FOUND = "NotFoundError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# CVE format constants
CVE_PREFIX = "CVE-"
CVE_YEAR_LENGTH = 4

# Error messages
MSG_INVALID_CVE_FORMAT = "Invalid CVE ID format. Expected: CVE-YYYY-NNNNN"
MSG_CVE_NOT_FOUND = "CVE not found in NIST NVD database"
MSG_RATE_LIMIT_EXCEEDED = "Rate limit exceeded. Please try again later."
MSG_SERVICE_UNAVAILABLE = "NIST NVD service temporarily unavailable"
MSG_REQUEST_TIMEOUT = "Request timed out"

# HTTP Status Codes
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_RATE_LIMIT = 429
HTTP_STATUS_SERVICE_UNAVAILABLE = 503

"""MAC Vendors integration constants.
"""

# API base URL
MAC_VENDORS_BASE_URL = "https://api.macvendors.com"

# Request timeout in seconds (matches the upstream DEFAULT_REQUEST_TIMEOUT)
DEFAULT_REQUEST_TIMEOUT = 30

# The test MAC address used for connectivity checks (VMware OUI)
HEALTH_CHECK_MAC = "00:0C:29:BB:47:4D"

# The text returned by the API when no vendor is found
VENDOR_NOT_FOUND_TEXT = "vendor not found"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_RATE_LIMIT = "RateLimitError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

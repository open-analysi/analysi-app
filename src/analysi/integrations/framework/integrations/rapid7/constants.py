"""
Rapid7 InsightVM integration constants.
"""

# API Configuration
DEFAULT_BASE_URL = "https://us.api.insight.rapid7.com/vm"
DEFAULT_TIMEOUT = 30
DEFAULT_PAGE_SIZE = 500  # upstream used 10, but Rapid7 API supports up to 500

# Credential field names
CREDENTIAL_API_KEY = "api_key"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# API endpoints
ENDPOINT_ADMINISTRATION_INFO = "/api/3/administration/info"
ENDPOINT_ASSETS = "/api/3/assets"
ENDPOINT_ASSETS_SEARCH = "/api/3/assets/search"
ENDPOINT_ASSET_VULNERABILITIES = "/api/3/assets/{asset_id}/vulnerabilities"
ENDPOINT_VULNERABILITIES = "/api/3/vulnerabilities/{vulnerability_id}"
ENDPOINT_SCANS = "/api/3/scans"
ENDPOINT_SCAN = "/api/3/scans/{scan_id}"

# Filter match operators
MATCH_ALL = "all"
MATCH_ANY = "any"
VALID_MATCH_OPERATORS = [MATCH_ALL, MATCH_ANY]

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_MISSING_ASSET_ID = "Missing required parameter: asset_id"
MSG_MISSING_VULNERABILITY_ID = "Missing required parameter: vulnerability_id"
MSG_MISSING_SCAN_ID = "Missing required parameter: scan_id"
MSG_MISSING_QUERY = "Missing required parameter: at least one of ip, hostname, or filters must be provided"
MSG_INVALID_ASSET_ID = "asset_id must be a positive integer"
MSG_INVALID_SCAN_ID = "scan_id must be a positive integer"

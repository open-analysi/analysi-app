"""
Tenable.io integration constants.
"""

# API Configuration
TENABLE_BASE_URL = "https://cloud.tenable.com"
DEFAULT_TIMEOUT = 60

# Credential field names
CREDENTIAL_ACCESS_KEY = "access_key"
CREDENTIAL_SECRET_KEY = "secret_key"

# Settings field names
SETTINGS_TIMEOUT = "timeout"

# API Endpoints
ENDPOINT_SCANS_LIST = "/scans"
ENDPOINT_SCANNERS_LIST = "/scanners"
ENDPOINT_POLICIES_LIST = "/policies"
ENDPOINT_SCANS_CREATE = "/scans"
ENDPOINT_SCANS_LAUNCH = "/scans/{scan_id}/launch"
ENDPOINT_SCANS_STATUS = "/scans/{scan_id}"
ENDPOINT_SCANS_DETAILS = "/scans/{scan_id}"
ENDPOINT_SCANS_DELETE = "/scans/{scan_id}"

# Scan Configuration
DEFAULT_SCAN_NAME = "Scan Launched from Naxos"
DEFAULT_SCAN_TIMEOUT = 3600  # seconds
MIN_SCAN_TIMEOUT = 0
MAX_SCAN_TIMEOUT = 14400  # 4 hours
DEFAULT_SCAN_POLLING_INTERVAL = 60  # seconds
DEFAULT_SCAN_RATE_LIMIT_TIMEOUT = 120  # seconds

# Scan Status Values
SCAN_STATUS_COMPLETED = "completed"
TERMINAL_SCAN_STATUSES = ["aborted", "canceled", "completed", "stopped"]

# Vulnerability Severity Levels
VULNERABILITY_SEVERITIES = ["low", "medium", "high", "critical"]

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_TIMEOUT = "TimeoutError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials (access_key and secret_key)"
MSG_MISSING_ACCESS_KEY = "Missing access key in credentials"
MSG_MISSING_SECRET_KEY = "Missing secret key in credentials"
MSG_MISSING_TARGET = "Missing required parameter 'target_to_scan'"
MSG_MISSING_POLICY_ID = "Missing required parameter 'policy_id'"
MSG_MISSING_SCAN_ID = "Missing required parameter 'scan_id'"
MSG_INVALID_SCAN_TIMEOUT = "Scan timeout must be between {} and {} seconds"
MSG_INVALID_DATETIME = "Invalid datetime format"
MSG_SCAN_NOT_COMPLETE = "Scan did not complete within {} seconds. Last status: {}"
MSG_SCAN_RESPONSE_EMPTY = "Scan response is empty. Please check the input parameters."
MSG_SERVER_CONNECTION = "Failed to connect to Tenable.io API"

# Output field names
OUTPUT_SCAN_ID = "scan_id"
OUTPUT_SCAN_COUNT = "scan_count"
OUTPUT_SCANNER_COUNT = "scanner_count"
OUTPUT_POLICY_COUNT = "policy_count"
OUTPUT_TOTAL_VULNS = "total_vulns"
OUTPUT_DELETE_STATUS = "delete_status"

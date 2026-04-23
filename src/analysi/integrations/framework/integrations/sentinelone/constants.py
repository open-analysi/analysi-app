"""
SentinelOne integration constants.
"""

# API Configuration
SENTINELONE_BASE_URL_SUFFIX = "/web/api/v2.1"
DEFAULT_TIMEOUT = 120

# Credential field names
CREDENTIAL_API_TOKEN = "api_token"

# Settings field names
SETTINGS_CONSOLE_URL = "console_url"
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP_ERROR = "HTTPError"
ERROR_TYPE_TIMEOUT = "TimeoutError"
ERROR_TYPE_REQUEST_ERROR = "RequestError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_CONSOLE_URL = "Missing SentinelOne console URL"
MSG_MISSING_API_TOKEN = "Missing SentinelOne API token"
MSG_ENDPOINT_NOT_FOUND = "Endpoint not found"
MSG_MULTIPLE_ENDPOINTS_FOUND = "More than one endpoint found"
MSG_THREAT_NOT_FOUND = "Threat ID not found"
MSG_HASH_ALREADY_EXISTS = "Hash already exists in blocklist"
MSG_HASH_NOT_FOUND = "Hash not found in blocklist"

# Mitigation actions
MITIGATION_ACTIONS = [
    "kill",
    "quarantine",
    "remediate",
    "rollback-remediation",
    "un-quarantine",
]

# OS Types
OS_TYPES = ["windows", "macos", "linux", "windows_legacy"]

# Firewall rule types
FIREWALL_RULE_TYPES = ["ip", "subnet", "dns"]

# Analyst verdicts
ANALYST_VERDICTS = ["true_positive", "false_positive", "suspicious", "undefined"]

# Incident statuses
INCIDENT_STATUSES = ["unresolved", "in_progress", "resolved"]

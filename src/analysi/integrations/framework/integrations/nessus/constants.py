"""
Nessus integration constants.
"""

# API Configuration
DEFAULT_TIMEOUT = 30
DEFAULT_PORT = 8834
SCAN_CHECK_INTERVAL = 30  # seconds between scan status checks

# Credential field names
CREDENTIAL_ACCESS_KEY = "access_key"
CREDENTIAL_SECRET_KEY = "secret_key"

# Settings field names
SETTINGS_SERVER = "server"
SETTINGS_PORT = "port"
SETTINGS_VERIFY_CERT = "verify_server_cert"
SETTINGS_TIMEOUT = "timeout"

# Scan parameters
PARAM_TARGET_TO_SCAN = "target_to_scan"
PARAM_POLICY_ID = "policy_id"

# Scan template UUID
ADVANCED_SCAN_TEMPLATE_UUID = "ab4bacd2-05f6-425c-9d79-3ba3940ad1c24e51e1f403febe40"

# Scan status values
SCAN_STATUS_COMPLETED = "completed"
SCAN_STATUS_RUNNING = "running"
SCAN_STATUS_PENDING = "pending"

# API endpoints
ENDPOINT_USERS = "users"
ENDPOINT_POLICIES = "policies"
ENDPOINT_SCANS = "scans"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPStatusError"
ERROR_TYPE_TIMEOUT = "TimeoutError"
ERROR_TYPE_CONNECTION = "ConnectionError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_SERVER = "Missing Nessus server address"
MSG_MISSING_KEYS = "Missing access key or secret key"
MSG_MISSING_TARGET = "Missing target to scan"
MSG_MISSING_POLICY_ID = "Missing policy ID"
MSG_INVALID_RESPONSE = "Invalid response from Nessus API"
MSG_SCAN_FAILED = "Scan failed or returned no results"

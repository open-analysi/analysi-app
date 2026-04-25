"""Microsoft Defender for Endpoint integration constants.
"""

# API Base URLs
DEFENDER_LOGIN_BASE_URL = "https://login.microsoftonline.com"
DEFENDER_LOGIN_GCC_BASE_URL = "https://login.microsoftonline.com"
DEFENDER_LOGIN_GCC_HIGH_BASE_URL = "https://login.microsoftonline.us"

DEFENDER_API_BASE_URL = "https://api.securitycenter.windows.com/api"
DEFENDER_API_GCC_BASE_URL = "https://api-gcc.securitycenter.microsoft.us/api"
DEFENDER_API_GCC_HIGH_BASE_URL = "https://api-gov.securitycenter.microsoft.us/api"

DEFENDER_RESOURCE_URL = "https://api.securitycenter.windows.com"
DEFENDER_RESOURCE_GCC_URL = "https://api-gcc.securitycenter.microsoft.us"
DEFENDER_RESOURCE_GCC_HIGH_URL = "https://api-gov.securitycenter.microsoft.us"

# Timeout settings
DEFAULT_TIMEOUT = 30
DEFAULT_STATUS_CHECK_TIMEOUT = 30
QUARANTINE_TIMEOUT_MAX = 60
SCAN_TIMEOUT_MAX = 3600
LIVE_RESPONSE_TIMEOUT_DEFAULT = 300
RUN_SCRIPT_TIMEOUT_MAX = 600

# Default limits
DEFAULT_ALERT_LIMIT = 100
DEFAULT_FILES_LIMIT = 100
DEFAULT_SOFTWARE_LIMIT = 50
DEFAULT_VULNERABILITIES_LIMIT = 25

# Status values
STATUS_IN_PROGRESS = "InProgress"
STATUS_PENDING = "Pending"
STATUS_SUCCEEDED = "Succeeded"
STATUS_FAILED = "Failed"

# Credential field names
CREDENTIAL_CLIENT_ID = "client_id"
CREDENTIAL_CLIENT_SECRET = "client_secret"

# Settings field names
SETTINGS_TENANT_ID = "tenant_id"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_ENVIRONMENT = "environment"

# Environment values
ENVIRONMENT_PUBLIC = "Public"
ENVIRONMENT_GCC = "GCC"
ENVIRONMENT_GCC_HIGH = "GCC High"

# API endpoints
ENDPOINT_MACHINES = "/machines"
ENDPOINT_ALERTS = "/alerts"
ENDPOINT_ISOLATE = "/machines/{device_id}/isolate"
ENDPOINT_UNISOLATE = "/machines/{device_id}/unisolate"
ENDPOINT_SCAN_DEVICE = "/machines/{device_id}/runAntiVirusScan"
ENDPOINT_QUARANTINE_FILE = "/machines/{device_id}/StopAndQuarantineFile"
ENDPOINT_MACHINE_ACTIONS = "/machineactions/{action_id}"
ENDPOINT_RESTRICT_APP = "/machines/{device_id}/restrictCodeExecution"
ENDPOINT_REMOVE_APP_RESTRICTION = "/machines/{device_id}/unrestrictCodeExecution"
ENDPOINT_DEVICE_DETAILS = "/machines/{device_id}"
ENDPOINT_DEVICE_ALERTS = "/machines/{device_id}/alerts"
ENDPOINT_DEVICE_VULNERABILITIES = "/machines/{device_id}/vulnerabilities"
ENDPOINT_LIST_ALERTS = "/alerts"
ENDPOINT_GET_ALERT = "/alerts/{alert_id}"
ENDPOINT_UPDATE_ALERT = "/alerts/{alert_id}"
ENDPOINT_RUN_QUERY = "/advancedqueries/run"
ENDPOINT_LIVE_RESPONSE = "/machines/{device_id}/runliveresponse"
ENDPOINT_LIVE_RESPONSE_RESULT = (
    "/machineactions/{action_id}/GetLiveResponseResultDownloadLink(index=0)"
)

# Isolation types
ISOLATION_TYPE_FULL = "Full"
ISOLATION_TYPE_SELECTIVE = "Selective"

# Scan types
SCAN_TYPE_QUICK = "Quick"
SCAN_TYPE_FULL = "Full"

# Alert statuses
ALERT_STATUS_NEW = "New"
ALERT_STATUS_IN_PROGRESS = "InProgress"
ALERT_STATUS_RESOLVED = "Resolved"

# Error messages
ERROR_MISSING_CREDENTIALS = (
    "Missing required credentials (tenant_id, client_id, client_secret)"
)
ERROR_MISSING_DEVICE_ID = "Missing required parameter 'device_id'"
ERROR_MISSING_COMMENT = "Missing required parameter 'comment'"
ERROR_MISSING_ALERT_ID = "Missing required parameter 'alert_id'"
ERROR_INVALID_ISOLATION_TYPE = "Invalid isolation_type. Must be 'Full' or 'Selective'"
ERROR_INVALID_SCAN_TYPE = "Invalid scan_type. Must be 'Quick' or 'Full'"
ERROR_INVALID_ENVIRONMENT = (
    "Invalid environment. Must be 'Public', 'GCC', or 'GCC High'"
)
ERROR_ACTION_ID_UNAVAILABLE = "Action ID not available from response"
ERROR_TOKEN_FAILED = "Failed to acquire access token"
ERROR_INVALID_TIMEOUT = "Invalid timeout value. Must be a positive integer"

# Success messages
SUCCESS_DEVICE_ISOLATED = "Device isolation initiated successfully"
SUCCESS_DEVICE_RELEASED = "Device release initiated successfully"
SUCCESS_SCAN_INITIATED = "Device scan initiated successfully"
SUCCESS_FILE_QUARANTINED = "File quarantine initiated successfully"
SUCCESS_APP_RESTRICTED = "App execution restricted successfully"
SUCCESS_APP_RESTRICTION_REMOVED = "App execution restriction removed successfully"
SUCCESS_ALERT_UPDATED = "Alert updated successfully"

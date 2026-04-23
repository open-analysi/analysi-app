"""
BMC Remedy ITSM integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30  # Match upstream default

# API endpoints (BMC Remedy AR REST API v1)
TOKEN_ENDPOINT = "/api/jwt/login"
LOGOUT_ENDPOINT = "/api/jwt/logout"
INCIDENT_INTERFACE = "/api/arsys/v1/entry/HPD:IncidentInterface"
INCIDENT_CREATE = "/api/arsys/v1/entry/HPD:IncidentInterface_Create"
WORK_LOG_ENDPOINT = "/api/arsys/v1/entry/HPD:WorkLog"

# Default list fields to request when listing tickets
LIST_TICKETS_FIELDS = (
    "Incident Number,First Name,Last Name,Description,Status,"
    "Priority,Assigned Group,Assignee"
)

# Pagination
DEFAULT_PAGE_LIMIT = 100
DEFAULT_OFFSET = 0

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_VERIFY_SSL = "verify_ssl"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTH = "AuthenticationError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials (username and password)"
MSG_MISSING_BASE_URL = "Missing required setting: base_url"
MSG_MISSING_INCIDENT_ID = "Missing required parameter: id"
MSG_MISSING_STATUS = "Missing required parameter: status"
MSG_MISSING_COMMENT_TYPE = "Missing required parameter: work_info_type"
MSG_TOKEN_GENERATION_FAILED = "Failed to generate JWT token"
MSG_INCIDENT_NOT_FOUND = "Incident not found"
MSG_UPDATE_URL_NOT_FOUND = "Could not resolve update URL for incident"

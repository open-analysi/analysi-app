"""Microsoft Sentinel integration constants.
"""

# Azure Authentication URLs
SENTINEL_LOGIN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
SENTINEL_LOGIN_SCOPE = "https://management.azure.com/.default"
LOGANALYTICS_LOGIN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/token"
LOGANALYTICS_LOGIN_RESOURCE = "https://api.loganalytics.io"

# API Base URLs
SENTINEL_API_URL = (
    "https://management.azure.com/subscriptions/{subscription_id}/"
    "resourceGroups/{resource_group}/providers/Microsoft.OperationalInsights/"
    "workspaces/{workspace_name}/providers/Microsoft.SecurityInsights"
)
LOGANALYTICS_API_URL = "https://api.loganalytics.io/v1/workspaces/{workspace_id}/query"

# API Configuration
SENTINEL_API_VERSION = "2022-08-01"
SENTINEL_API_INCIDENTS = "/incidents"
SENTINEL_API_INCIDENTS_PAGE_SIZE = 50

# Timeout settings
DEFAULT_TIMEOUT = 30

# JSON field names
SENTINEL_JSON_ACCESS_TOKEN = "access_token"
SENTINEL_JSON_VALUE = "value"
SENTINEL_JSON_NEXT_LINK = "nextLink"
SENTINEL_JSON_LAST_MODIFIED = "lastModifiedTimeUtc"

# Error messages
ERROR_MSG_UNKNOWN = "Unknown error occurred. Please check the asset configuration and/or action parameters."
ERROR_MSG_MISSING_CREDENTIALS = (
    "Missing required credentials (tenant_id, client_id, client_secret)"
)
ERROR_MSG_MISSING_SETTINGS = "Missing required settings"
ERROR_MSG_INVALID_LIMIT = "Limit parameter must be a positive integer"
ERROR_MSG_INVALID_MAX_ROWS = "Max_rows parameter must be a positive integer"
ERROR_MSG_NO_VALUE = "Could not extract value from API response"
ERROR_MSG_TOKEN_EXPIRED = [
    "The access token is invalid",
    "ExpiredAuthenticationToken",
    "InvalidTokenError",
]

# Alert pull defaults
DEFAULT_LOOKBACK_MINUTES = 5
DEFAULT_PULL_ALERTS_LIMIT = 200

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_PARTIAL = "partial"

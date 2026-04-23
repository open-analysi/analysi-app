"""
Microsoft Entra ID integration constants.
"""

# API settings
DEFAULT_TIMEOUT = 30
GRAPH_API_VERSION = "v1.0"
GRAPH_API_BASE_URL = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
TOKEN_SCOPE = "https://graph.microsoft.com/.default"
PAGINATION_PAGE_SIZE = 100

# Graph API region URLs
GRAPH_API_URLS = {
    "global": "https://graph.microsoft.com/v1.0",
    "us_gov_l4": "https://graph.microsoft.us/v1.0",
    "us_gov_l5_dod": "https://dod-graph.microsoft.us/v1.0",
    "germany": "https://graph.microsoft.de/v1.0",
    "china": "https://microsoftgraph.chinacloudapi.cn/v1.0",
}

# Token URL per region
TOKEN_URLS = {
    "global": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
    "us_gov_l4": "https://login.microsoftonline.us/{tenant_id}/oauth2/v2.0/token",
    "us_gov_l5_dod": "https://login.microsoftonline.us/{tenant_id}/oauth2/v2.0/token",
    "germany": "https://login.microsoftonline.de/{tenant_id}/oauth2/v2.0/token",
    "china": "https://login.chinacloudapi.cn/{tenant_id}/oauth2/v2.0/token",
}

# Credential field names
CREDENTIAL_CLIENT_ID = "client_id"
CREDENTIAL_CLIENT_SECRET = "client_secret"
SETTINGS_TENANT_ID = "tenant_id"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# Endpoints (relative to base_url)
ENDPOINT_USERS = "/users"
ENDPOINT_USER = "/users/{user_id}"
ENDPOINT_USER_MEMBER_OF = "/users/{user_id}/memberOf"
ENDPOINT_USER_REVOKE_SESSIONS = "/users/{user_id}/revokeSignInSessions"
ENDPOINT_GROUPS = "/groups"
ENDPOINT_GROUP_MEMBERS = "/groups/{group_id}/members"
ENDPOINT_SIGN_INS = "/auditLogs/signIns"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP_STATUS = "HTTPStatusError"
ERROR_TYPE_REQUEST = "RequestError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_TOKEN = "TokenError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_CLIENT_ID = "Missing client_id in credentials"
MSG_MISSING_CLIENT_SECRET = "Missing client_secret in credentials"
MSG_MISSING_TENANT_ID = "Missing tenant_id in settings"
MSG_MISSING_PARAMETER = "Missing required parameter: {param}"
MSG_TOKEN_ACQUISITION_FAILED = "Failed to acquire access token: {error}"
MSG_USER_NOT_FOUND = "User not found: {user_id}"

# Success messages
MSG_USER_DISABLED = "Successfully disabled user"
MSG_USER_ENABLED = "Successfully enabled user"
MSG_PASSWORD_RESET = "Successfully reset password"
MSG_SESSIONS_REVOKED = "Successfully revoked all sign-in sessions"

# OData query parameters
ODATA_NEXT_LINK = "@odata.nextLink"

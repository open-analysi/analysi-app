"""
Sophos Central integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30

# OAuth2 endpoints (Sophos Central)
OAUTH_TOKEN_URL = "https://id.sophos.com/api/v2/oauth2/token"
WHOAMI_URL = "https://api.central.sophos.com/whoami/v1"

# API endpoints (relative to tenant data-region base URL)
ENDPOINTS_ENDPOINT = "/endpoint/v1/endpoints"
ENDPOINTS_SETTINGS = "/endpoint/v1/settings"
TAMPER_PROTECTION_ENDPOINT = "/endpoint/v1/endpoints/{endpoint_id}/tamper-protection"
ISOLATION_ENDPOINT = "/endpoint/v1/endpoints/isolation"
ISOLATION_INDIVIDUAL_ENDPOINT = "/endpoint/v1/endpoints/{endpoint_id}/isolation"
SCAN_ENDPOINT = "/endpoint/v1/endpoints/{endpoint_id}/scans"
BLOCKED_ITEMS_ENDPOINT = "/endpoint/v1/settings/blocked-items"
BLOCKED_ITEM_ENDPOINT = "/endpoint/v1/settings/blocked-items/{item_id}"
ALERTS_ENDPOINT = "/common/v1/alerts"
ALERT_ENDPOINT = "/common/v1/alerts/{alert_id}"

# Credential field names
CREDENTIAL_CLIENT_ID = "client_id"
CREDENTIAL_CLIENT_SECRET = "client_secret"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# ID types returned by whoami
ID_TYPE_TENANT = "tenant"
ID_TYPE_ORGANIZATION = "organization"
ID_TYPE_PARTNER = "partner"

# ID type to header mapping
ID_TYPE_HEADERS = {
    ID_TYPE_TENANT: "X-Tenant-ID",
    ID_TYPE_ORGANIZATION: "X-Organization-ID",
    ID_TYPE_PARTNER: "X-Partner-ID",
}

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: client_id and client_secret"
MSG_MISSING_PARAMETER = "Missing required parameter: {}"
MSG_AUTHENTICATION_FAILED = "Failed to authenticate with Sophos Central API"
MSG_WHOAMI_FAILED = "Failed to determine tenant from Sophos whoami endpoint"

# Endpoint health statuses
VALID_HEALTH_STATUSES = ["bad", "good", "suspicious", "unknown"]

# Endpoint types
VALID_ENDPOINT_TYPES = ["computer", "server", "securityVm"]

# Block item types
VALID_BLOCK_TYPES = ["sha256"]

# Default page size
DEFAULT_PAGE_SIZE = 50
DEFAULT_LIMIT = 100

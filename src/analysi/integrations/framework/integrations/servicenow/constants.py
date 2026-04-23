"""
ServiceNow integration constants.
"""

# API Endpoints
API_BASE = "/api/now"
TABLE_ENDPOINT = "/table/{table}"
TICKET_ENDPOINT = "/table/{table}/{id}"
CATALOG_ITEMS_ENDPOINT = "/servicecatalog/items/{sys_id}"
CATALOG_ORDER_ENDPOINT = "/servicecatalog/items/{sys_id}/order_now"
SC_CATALOG_ENDPOINT = "/table/sc_catalog"
SC_CATEGORY_ENDPOINT = "/table/sc_category"
SC_CAT_ITEMS_ENDPOINT = "/table/sc_cat_item"
SYS_JOURNAL_FIELD_ENDPOINT = "/table/sys_journal_field"
SEARCH_SOURCE_ENDPOINT = "/search/sources/textsearch"

# Default values
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RESULTS = 100
DEFAULT_TABLE = "incident"
DEFAULT_LIMIT = 10000
DEFAULT_OFFSET = 0
MAX_LIMIT = 100

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"
CREDENTIAL_CLIENT_ID = "client_id"
CREDENTIAL_CLIENT_SECRET = "client_secret"

# Settings field names
SETTINGS_URL = "url"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_MAX_RESULTS = "max_results"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPStatusError"
ERROR_TYPE_REQUEST = "RequestError"
ERROR_TYPE_TIMEOUT = "TimeoutException"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_URL = "Missing required credential: url"
MSG_MISSING_AUTH = (
    "Missing authentication credentials (username/password or client_id/client_secret)"
)
MSG_CONNECTION_ERROR = "Connection failed: {error}"
MSG_INVALID_RESPONSE = "Invalid response format from ServiceNow API"

# Table names
TABLE_INCIDENT = "incident"
TABLE_SYS_USER = "sys_user"
TABLE_SYS_JOURNAL_FIELD = "sys_journal_field"

# Query parameters
SYSPARM_QUERY = "sysparm_query"
SYSPARM_LIMIT = "sysparm_limit"
SYSPARM_OFFSET = "sysparm_offset"
SYSPARM_FIELDS = "sysparm_fields"
SYSPARM_DISPLAY_VALUE = "sysparm_display_value"

"""Elasticsearch integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 60

# Elasticsearch endpoints
ENDPOINT_CLUSTER_HEALTH = "/_cluster/health"
ENDPOINT_GET_INDEXES = "/_cat/indices"
ENDPOINT_SEARCH = "/{index}/_search"
ENDPOINT_INDEX_DOC = "/{index}/_doc"

# JSON field names
FIELD_INDEX = "index"
FIELD_QUERY = "query"
FIELD_ROUTING = "routing"
FIELD_DOCUMENT = "document"
FIELD_TOTAL_HITS = "total_hits"
FIELD_TIMED_OUT = "timed_out"

# HTTP status codes
EMPTY_RESPONSE_STATUS_CODES = [200, 204]

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_URL = "url"
SETTINGS_VERIFY_SSL = "verify_server_cert"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP_ERROR = "HTTPStatusError"
ERROR_TYPE_REQUEST = "RequestError"
ERROR_TYPE_TIMEOUT = "TimeoutError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials (url, username, password)"
MSG_MISSING_INDEX = "Missing required parameter 'index'"
MSG_MISSING_URL = "Missing required Elasticsearch URL in settings"
MSG_CONNECTIVITY_SUCCESS = "Elasticsearch connection successful"
MSG_CONNECTIVITY_FAILED = "Elasticsearch connection failed"
MSG_INVALID_QUERY = "Unable to parse query JSON"
MSG_INVALID_INDEX = "Please provide a valid value in the 'index' parameter"
MSG_MISSING_DOCUMENT = "Missing required parameter 'document'"
MSG_INVALID_DOCUMENT = "Unable to parse document JSON"

# Alert pulling
DEFAULT_ALERT_INDEX = ".alerts-security.alerts-default"
DEFAULT_LOOKBACK_MINUTES = 5
DEFAULT_MAX_ALERTS = 1000
ALERT_PAGE_SIZE = 100
SETTINGS_ALERT_INDEX = "alert_index"
SETTINGS_DEFAULT_LOOKBACK = "default_lookback_minutes"

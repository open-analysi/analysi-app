"""
BigQuery integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30  # seconds - default timeout for query execution

# Credential field names
CREDENTIAL_SERVICE_ACCOUNT_JSON = "service_account_json"

# Settings field names
SETTINGS_DEFAULT_TIMEOUT = "default_timeout"
SETTINGS_PROJECT_ID = "project_id"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_QUERY_ERROR = "QueryError"
ERROR_TYPE_TIMEOUT = "TimeoutError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required service account credentials"
MSG_INVALID_SERVICE_ACCOUNT_JSON = "Invalid service account JSON format"
MSG_MISSING_QUERY = "Missing required parameter 'query'"
MSG_MISSING_JOB_ID = "Missing required parameter 'job_id'"
MSG_INVALID_TIMEOUT = "Timeout must be a positive integer"
MSG_QUERY_TIMEOUT = "Query timed out waiting for results"
MSG_QUERY_SUCCESS = "Successfully retrieved results from query"
MSG_HEALTH_CHECK_SUCCESS = "BigQuery API is accessible"
MSG_LIST_TABLES_SUCCESS = "Successfully listed tables"

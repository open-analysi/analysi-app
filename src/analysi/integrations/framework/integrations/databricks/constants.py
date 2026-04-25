"""
Databricks integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"
CREDENTIAL_TOKEN = "token"

# Settings field names
SETTINGS_HOST = "host"
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_API = "APIError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Either username/password or an authentication token must be specified in credentials"
MSG_MISSING_API_KEY = "Missing authentication token in credentials"
MSG_MISSING_HOST = "Missing host in settings"
MSG_TEST_CONNECTIVITY_SUCCESS = "Test connectivity passed"
MSG_TEST_CONNECTIVITY_ERROR = "Test connectivity failed"

# Alert related
MSG_CREATE_ALERT_SUCCESS = "Successfully created alert"
MSG_CREATE_ALERT_ERROR = "Alert creation failed"
MSG_DELETE_ALERT_SUCCESS = "Successfully deleted alert"
MSG_DELETE_ALERT_ERROR = "Alert deletion failed"
MSG_LIST_ALERTS_SUCCESS = "Successfully listed alerts"
MSG_LIST_ALERTS_ERROR = "List alerts failed"

# Cluster related
MSG_LIST_CLUSTERS_SUCCESS = "Successfully listed clusters"
MSG_LIST_CLUSTERS_ERROR = "List clusters failed"

# Warehouse related
MSG_LIST_WAREHOUSES_SUCCESS = "Successfully listed warehouses"
MSG_LIST_WAREHOUSES_ERROR = "List warehouses failed"

# Query related
MSG_PERFORM_QUERY_SUCCESS = "Successfully performed SQL query"
MSG_PERFORM_QUERY_ERROR = "Failed to perform SQL query"
MSG_GET_QUERY_STATUS_SUCCESS = "Successfully retrieved query status"
MSG_GET_QUERY_STATUS_ERROR = "Failed to retrieve query status"
MSG_CANCEL_QUERY_SUCCESS = "Successfully submitted query cancellation request"
MSG_CANCEL_QUERY_ERROR = "Failed to submit query cancellation request"

# Job related
MSG_EXECUTE_NOTEBOOK_SUCCESS = "Successfully executed notebook"
MSG_EXECUTE_NOTEBOOK_ERROR = "Failed to execute notebook"
MSG_GET_JOB_RUN_SUCCESS = "Successfully retrieved job run"
MSG_GET_JOB_RUN_ERROR = "Failed to retrieve job run"
MSG_GET_JOB_OUTPUT_SUCCESS = "Successfully retrieved job run output"
MSG_GET_JOB_OUTPUT_ERROR = "Failed to retrieve job run output"

# Test connectivity
TEST_CONNECTIVITY_FILE_PATH = "dbfs:/"

# Date format
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

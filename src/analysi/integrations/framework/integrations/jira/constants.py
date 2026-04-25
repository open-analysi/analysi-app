"""
JIRA integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 60  # Match upstream default

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"  # API token for Cloud, password for On-Prem

# Settings field names
SETTINGS_URL = "url"
SETTINGS_VERIFY_SSL = "verify_ssl"
SETTINGS_TIMEOUT = "timeout"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_NOT_FOUND = "NotFoundError"
ERROR_TYPE_AUTH = "AuthenticationError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_URL = "Missing JIRA URL in settings"
MSG_MISSING_AUTH = "Missing username or password/API token in credentials"
MSG_INVALID_URL = "Invalid JIRA URL format"
MSG_MISSING_TICKET_ID = "Missing required parameter 'ticket_id'"
MSG_MISSING_SUMMARY = "Missing required parameter 'summary'"
MSG_MISSING_PROJECT_KEY = "Missing required parameter 'project_key'"
MSG_MISSING_ISSUE_TYPE = "Missing required parameter 'issue_type'"
MSG_MISSING_COMMENT = "Missing required parameter 'comment'"
MSG_MISSING_STATUS = "Missing required parameter 'status'"

# Default values
DEFAULT_MAX_RESULTS = 100
DEFAULT_START_INDEX = 0

# JIRA API endpoints
API_ISSUE = "rest/api/2/issue"
API_SEARCH = "rest/api/2/search"
API_PROJECT = "rest/api/2/project"
API_SERVER_INFO = "rest/api/2/serverInfo"
API_MYSELF = "rest/api/2/myself"
API_USER_SEARCH = "rest/api/2/user/search"

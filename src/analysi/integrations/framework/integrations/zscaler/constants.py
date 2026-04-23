"""ZScaler integration constants.
"""

# API Configuration
DEFAULT_TIMEOUT = 30
MAX_PAGESIZE = 1000
DEFAULT_RETRY_COUNT = 5

# Error Messages
ERR_MSG_UNAVAILABLE = "Error message unavailable. Please check the asset configuration and|or action parameters"
ERR_MD5_UNKNOWN_MSG = "md5 is unknown or analysis has yet not been completed"
SANDBOX_GET_REPORT_MSG = "Sandbox report successfully fetched for the provided md5 hash"
SANDBOX_SUBMIT_FILE_MSG = "Successfully submitted the file to Sandbox"

# Validation Messages
VALID_INTEGER_MSG = "Please provide a valid integer value in the {param}"
NON_NEGATIVE_INTEGER_MSG = (
    "Please provide a valid non-negative integer value in the {param}"
)
POSITIVE_INTEGER_MSG = (
    "Please provide a valid non-zero positive integer value in the {param}"
)
LIMIT_KEY = "'limit' action parameter"

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"
CREDENTIAL_API_KEY = "api_key"
CREDENTIAL_SANDBOX_API_TOKEN = "sandbox_api_token"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_SANDBOX_BASE_URL = "sandbox_base_url"
SETTINGS_TIMEOUT = "timeout"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_RATE_LIMIT = "RateLimitError"

# URL Actions
ACTION_ADD_TO_LIST = "ADD_TO_LIST"
ACTION_REMOVE_FROM_LIST = "REMOVE_FROM_LIST"

# Max URL length
MAX_URL_LENGTH = 1024

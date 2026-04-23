"""Chronicle integration constants.
"""

# Chronicle API Base URL
DEFAULT_BASE_URL = "https://backstory.googleapis.com"

# Chronicle API Endpoints
ENDPOINT_LIST_IOC_DETAILS = "/v1/artifact/listiocdetails"
ENDPOINT_LIST_ASSETS = "/v1/artifact/listassets"
ENDPOINT_LIST_EVENTS = "/v1/asset/listevents"
ENDPOINT_LIST_IOCS = "/v1/ioc/listiocs"
ENDPOINT_LIST_ALERTS = "/v1/alert/listalerts"
ENDPOINT_LIST_RULES = "/v2/detect/rules"
ENDPOINT_LIST_DETECTIONS = "/v2/detect/rules/{rule_id}/detections"

# Default timeout and retry settings
DEFAULT_TIMEOUT = 30
DEFAULT_WAIT_TIMEOUT_PERIOD = 3
DEFAULT_NO_OF_RETRIES = 3
DEFAULT_PAGE_SIZE = 10000

# Google OAuth2 Scope
DEFAULT_SCOPES = ["https://www.googleapis.com/auth/chronicle-backstory"]

# Credential field names
CREDENTIAL_KEY_JSON = "key_json"
CREDENTIAL_SCOPES = "scopes"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_NO_OF_RETRIES = "no_of_retries"
SETTINGS_WAIT_TIMEOUT_PERIOD = "wait_timeout_period"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP_ERROR = "HTTPStatusError"
ERROR_TYPE_TIMEOUT = "TimeoutError"
ERROR_TYPE_AUTH_ERROR = "AuthenticationError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_KEY_JSON = "Missing 'key_json' in credentials"
MSG_INVALID_KEY_JSON = "Invalid service account JSON format"
MSG_MISSING_PARAMETER = "Missing required parameter: {}"
MSG_INVALID_PARAMETER = "Invalid parameter value: {}"
MSG_UNABLE_CREATE_CLIENT = "Unable to create Chronicle API client"
MSG_AUTH_FAILED = "Authentication failed with provided service account credentials"
MSG_INVALID_TIME_RANGE = "Invalid time range: end_time must be later than start_time"

# Artifact indicator types
ARTIFACT_DOMAIN = "Domain Name"
ARTIFACT_IP = "Destination IP Address"
ARTIFACT_MD5 = "MD5"
ARTIFACT_SHA1 = "SHA1"
ARTIFACT_SHA256 = "SHA256"

# Alert types
ALERT_TYPE_ASSET = "Asset Alerts"
ALERT_TYPE_USER = "User Alerts"
ALERT_TYPE_ALL = "All"

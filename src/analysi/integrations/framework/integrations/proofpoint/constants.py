"""
Proofpoint TAP integration constants.
"""

# API Configuration
PP_BASE_URL = "https://tap-api-v2.proofpoint.com"
DEFAULT_TIMEOUT = 30

# API Paths
API_PATH_ALL = "/v2/siem/all"
API_PATH_CAMPAIGN = "/v2/campaign/{}"
API_PATH_FORENSICS = "/v2/forensics"
API_PATH_DECODE = "/v2/url/decode"

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: username and password"
MSG_MISSING_CAMPAIGN_ID = "Missing required parameter: campaign_id"
MSG_MISSING_URL = "Missing required parameter: url"
MSG_MISSING_THREAT_OR_CAMPAIGN = "Either campaign_id or threat_id must be provided"
MSG_BOTH_THREAT_AND_CAMPAIGN = "Only one of campaign_id or threat_id must be provided"
MSG_EMPTY_URL_LIST = "Please provide a valid value in the 'url' action parameter"

# Health check window in minutes
HEALTH_CHECK_WINDOW_MINUTES = 5

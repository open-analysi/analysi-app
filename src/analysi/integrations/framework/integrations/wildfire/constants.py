"""
Palo Alto Networks WildFire sandbox integration constants.
"""

# API defaults
WILDFIRE_DEFAULT_BASE_URL = "https://wildfire.paloaltonetworks.com"
WILDFIRE_PUBLIC_API_PREFIX = "/publicapi"

# Default timeout for detonation polling (minutes)
DEFAULT_TIMEOUT_MINS = 10

# Poll interval for detonation status (seconds)
POLL_INTERVAL_SECS = 10

# Default HTTP request timeout (seconds)
DEFAULT_REQUEST_TIMEOUT = 120

# Credential field names
CREDENTIAL_API_KEY = "api_key"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# Verdict code mapping
VERDICT_MAP = {
    0: "benign",
    1: "malware",
    2: "grayware",
    4: "phishing",
    -100: "pending",
    -101: "error",
    -102: "unknown",
    -103: "invalid hash value",
}

# Error descriptions by HTTP status code
FILE_UPLOAD_ERROR_DESC = {
    401: "API key invalid",
    405: "HTTP method not allowed",
    413: "Sample file size over max limit",
    418: "Sample file type is not supported",
    419: "Max number of uploads per day exceeded",
    422: "URL download error",
    500: "Internal error",
    513: "File upload failed",
}

GET_REPORT_ERROR_DESC = {
    401: "API key invalid",
    404: "Report not found",
    405: "HTTP method not allowed",
    419: "Request report quota exceeded",
    420: "Insufficient arguments",
    421: "Invalid arguments",
    500: "Internal error",
}

GET_VERDICT_ERROR_DESC = {
    401: "API key invalid",
    405: "HTTP method not allowed",
    419: "Request quota exceeded",
    420: "Insufficient arguments",
    421: "Invalid arguments",
    500: "Internal error",
}

# Error messages
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_MISSING_URL = "Missing required parameter: url"
MSG_MISSING_HASH = "Missing required parameter: hash"
MSG_MISSING_FILE_CONTENT = "Missing required parameter: file_content"
MSG_MISSING_FILENAME = "Missing required parameter: filename"
MSG_UNABLE_TO_PARSE_XML = "Unable to parse XML response from WildFire"

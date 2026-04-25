"""
Qualys Vulnerability Management integration constants.
"""

# API defaults
QUALYS_DEFAULT_BASE_URL = "https://qualysapi.qualys.com"
DEFAULT_TIMEOUT = 30
DEFAULT_TRUNCATION_LIMIT = 1000

# API endpoints
ENDPOINT_TEST_CONNECTIVITY = "/api/2.0/fo/auth"
ENDPOINT_LIST_ASSET_GROUPS = "/api/2.0/fo/asset/group/"
ENDPOINT_LAUNCH_SCAN = "/api/2.0/fo/scan/"
ENDPOINT_LIST_HOSTS = "/api/2.0/fo/asset/host/"
ENDPOINT_HOST_ASSET_DETAILS = "/qps/rest/2.0/get/am/hostasset/{}"
ENDPOINT_GET_VULN_DETAILS = "/api/2.0/fo/knowledge_base/vuln/"
ENDPOINT_SCAN_SUMMARY = "/api/2.0/fo/scan/summary/"

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# Date formats
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT_DISPLAY = "YYYY-MM-DDTHH:MM:SSZ"
DATE_FORMAT_DISPLAY = "YYYY-MM-DD"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: username and password"
MSG_MISSING_OPTION_TITLE = "Missing required parameter: option_title"
MSG_MISSING_SCAN_DATE_SINCE = "Missing required parameter: scan_date_since"
MSG_NO_INCLUDE_PARAM = "At least one include parameter must be enabled"
MSG_INVALID_DATE = "Invalid date format for '{}'. Expected: {}"
MSG_DATE_RANGE_INVALID = "'{}' must be earlier than '{}'"
MSG_UNABLE_TO_PARSE_XML = "Unable to parse XML response from Qualys API"
MSG_INVALID_INTEGER = "Invalid value for '{}': must be a non-negative integer"

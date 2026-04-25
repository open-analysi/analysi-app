"""
Joe Sandbox v2 integration constants.

API reference: https://jbxcloud.joesecurity.org/userguide#api
"""

# API defaults
JOESANDBOX_DEFAULT_BASE_URL = "https://jbxcloud.joesecurity.org"

# Endpoints
ENDPOINT_SERVER_ONLINE = "/api/v2/server/online"
ENDPOINT_ANALYSIS_SUBMIT = "/api/v2/analysis/submit"
ENDPOINT_ANALYSIS_INFO = "/api/v2/analysis/info"
ENDPOINT_ANALYSIS_DOWNLOAD = "/api/v2/analysis/download"
ENDPOINT_ANALYSIS_SEARCH = "/api/v2/analysis/search"
ENDPOINT_COOKBOOK_LIST = "/api/v2/cookbook/list"
ENDPOINT_COOKBOOK_INFO = "/api/v2/cookbook/info"

# Default HTTP request timeout (seconds)
DEFAULT_REQUEST_TIMEOUT = 30

# Detonation time defaults and limits
DEFAULT_ANALYSIS_TIME = 120
ANALYSIS_TIME_MIN = 30
ANALYSIS_TIME_MAX = 300

# Credential field names
CREDENTIAL_API_KEY = "api_key"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_ANALYSIS_TIME = "analysis_time"

# Joe Sandbox API form field names
API_FIELD_APIKEY = "apikey"
API_FIELD_WEBID = "webid"
API_FIELD_TYPE = "type"
API_FIELD_QUERY = "q"
API_FIELD_URL = "url"
API_FIELD_ACCEPT_TAC = "accept-tac"
API_FIELD_INTERNET_ACCESS = "internet-access"
API_FIELD_REPORT_CACHE = "report-cache"
API_FIELD_ANALYSIS_TIME = "analysis-time"
API_FIELD_COOKBOOK_ID = "id"

# Detection labels
DETECTION_CLEAN = "clean"

# Error messages
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_MISSING_WEBID = "Missing required parameter: webid"
MSG_MISSING_URL = "Missing required parameter: url"
MSG_MISSING_HASH = "Missing required parameter: hash"
MSG_MISSING_COOKBOOK_ID = "Missing required parameter: cookbook_id"
MSG_ANALYSIS_NOT_FINISHED = "Analysis for webid {webid} is not finished yet"
MSG_NO_URL_ANALYSIS_FOUND = "No analysis found for the provided URL"
MSG_NO_HASH_ANALYSIS_FOUND = "No analysis found for the provided hash"

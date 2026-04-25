"""
Cofense Triage integration constants.
Cofense Triage v2 API for phishing analysis and response.
"""

# API endpoints (v2)
STATUS_ENDPOINT = "/api/public/v2/system/status"
TOKEN_ENDPOINT = "/oauth/token"

REPORTS_ENDPOINT = "/api/public/v2/reports"
REPORT_ENDPOINT = "/api/public/v2/reports/{report_id}"
CATEGORIZE_REPORT_ENDPOINT = "/api/public/v2/reports/{report_id}/categorize"
CATEGORY_REPORTS_ENDPOINT = "/api/public/v2/categories/{category_id}/reports"
REPORTER_REPORTS_ENDPOINT = "/api/public/v2/reporters/{reporter_id}/reports"

REPORTERS_ENDPOINT = "/api/public/v2/reporters"
REPORTER_ENDPOINT = "/api/public/v2/reporters/{reporter_id}"

URLS_ENDPOINT = "/api/public/v2/urls"
URL_ENDPOINT = "/api/public/v2/urls/{url_id}"

THREAT_INDICATORS_ENDPOINT = "/api/public/v2/threat_indicators"
CATEGORIES_ENDPOINT = "/api/public/v2/categories"
CATEGORY_BY_NAME_ENDPOINT = (
    "/api/public/v2/categories?filter[name_cont]={category_name}"
)

# Content types
ACCEPT_HEADER = "application/vnd.api+json"
CONTENT_TYPE_HEADER = "application/vnd.api+json"

# Default page size for pagination
DEFAULT_PAGE_SIZE = 200
DEFAULT_MAX_RESULTS = 100
DEFAULT_TIMEOUT = 30

# Valid parameter values
REPORT_LOCATIONS = ["inbox", "reconnaissance", "processed", "all"]
SORT_VALUES = ["oldest_first", "latest_first"]
THREAT_LEVELS = ["malicious", "suspicious", "benign"]
THREAT_TYPES = ["hostname", "header", "url", "md5", "sha256"]
LEVEL_VALUES = ["malicious", "suspicious", "benign", "all"]
TYPE_VALUES = ["hostname", "url", "md5", "sha256", "header", "all"]
OPERATORS = ["eq", "not_eq", "lt", "lteq", "gt", "gteq"]

DEFAULT_THREAT_SOURCE = "Analysi-UI"

# Filter mappings (action param name -> API query param)
REPORT_FILTER_MAPPING = {
    "location": "filter[location]",
    "from_address": "filter[from_address]",
    "match_priority": "filter[match_priority]",
    "subject": "filter[subject_cont]",
    "start_date": "filter[updated_at_gteq]",
    "end_date": "filter[updated_at_lt]",
    "categorization_tags": "filter[categorization_tags_any]",
    "tags": "filter[tags_any]",
}

THREAT_FILTER_MAPPING = {
    "level": "filter[threat_level]",
    "type": "filter[threat_type]",
    "source": "filter[threat_source]",
    "value": "filter[threat_value]",
    "start_date": "filter[updated_at_gteq]",
    "end_date": "filter[updated_at_lt]",
    "sort": "sort",
}

# Category ID to severity mapping
CATEGORY_ID_TO_SEVERITY = {
    "High": ["4"],
    "Medium": ["3"],
    "Low": ["1", "2", "5"],
}

# Threat level to severity mapping
THREAT_LEVEL_TO_SEVERITY = {
    "High": ["malicious"],
    "Medium": ["suspicious"],
    "Low": ["benign"],
}

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: client_id, client_secret"
MSG_MISSING_BASE_URL = "Missing required setting: base_url"
MSG_TOKEN_FAILED = "Failed to obtain OAuth2 access token"
MSG_INVALID_PARAMETER = "Please provide a valid value in the '{}' parameter"

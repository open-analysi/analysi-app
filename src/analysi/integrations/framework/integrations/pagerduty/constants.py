"""
PagerDuty integration constants.
"""

# Default PagerDuty API base URL
DEFAULT_BASE_URL = "https://api.pagerduty.com"

# Default HTTP request timeout in seconds
DEFAULT_TIMEOUT = 30

# Default pagination limit (matches the upstream PAGERDUTY_DEFAULT_LIMIT)
DEFAULT_PAGE_LIMIT = 25

# PagerDuty API version header
API_ACCEPT_HEADER = "application/vnd.pagerduty+json;version=2"

# Error messages
MSG_MISSING_API_TOKEN = "Missing required credential: api_token"
MSG_MISSING_PARAM = "Missing required parameter: {param}"
MSG_INVALID_TEAM_IDS = "Please provide valid team_ids"
MSG_INVALID_USER_IDS = "Please provide valid user_ids"

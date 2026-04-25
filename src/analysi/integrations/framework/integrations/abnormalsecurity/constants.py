"""
Abnormal Security integration constants.
"""

# API base URL (upstream default)
DEFAULT_BASE_URL = "https://api.abnormalplatform.com/v1"

# Timeout for HTTP requests (seconds) - matches the upstream REQUEST_TIMEOUT
DEFAULT_TIMEOUT = 60

# Default pagination limit
DEFAULT_PAGE_LIMIT = 100

# Maximum page size the API accepts
MAX_PAGE_SIZE = 1000

# API endpoints
ENDPOINT_THREATS = "/threats"
ENDPOINT_ABUSE_CAMPAIGNS = "/abusecampaigns"
ENDPOINT_ACTIONS = "actions"

# Valid remediation actions
VALID_THREAT_ACTIONS = ("remediate", "unremediate")

# Error messages
MSG_MISSING_ACCESS_TOKEN = "Missing required credential: access_token"
MSG_MISSING_PARAM = "Missing required parameter: {param}"
MSG_INVALID_ACTION = "Invalid action '{value}'. Must be one of: {valid}"
MSG_INVALID_LIMIT = "Limit must be a positive integer or -1 for unlimited"

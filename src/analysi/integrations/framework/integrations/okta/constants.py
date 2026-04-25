"""
Okta integration constants.
"""

# API settings
DEFAULT_TIMEOUT = 30
OKTA_API_VERSION = "v1"

# Credential field names
CREDENTIAL_API_TOKEN = "api_token"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_VERIFY_SSL = "verify_ssl"

# User-Agent for Okta API
USER_AGENT_BASE = "NaxosIntegration/"

# Pagination settings
DEFAULT_PAGINATION_LIMIT = 200

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP_ERROR = "HTTPStatusError"
ERROR_TYPE_REQUEST_ERROR = "RequestError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_BASE_URL = "Missing base_url in credentials"
MSG_MISSING_API_TOKEN = "Missing api_token in credentials"
MSG_MISSING_PARAMETER = "Missing required parameter: {param}"
MSG_INVALID_PARAMETER = "Invalid parameter value: {param}"

# Success messages
MSG_USER_DISABLED = "Successfully disabled user"
MSG_USER_ENABLED = "Successfully enabled user"
MSG_USER_ALREADY_DISABLED = "User is already disabled"
MSG_USER_ALREADY_ENABLED = "User is already enabled"
MSG_PASSWORD_RESET = "Successfully initiated password reset"
MSG_PASSWORD_SET = "Successfully set user password"
MSG_SESSIONS_CLEARED = "Successfully cleared user sessions"
MSG_ROLE_ASSIGNED = "Successfully assigned role to user"
MSG_ROLE_UNASSIGNED = "Successfully unassigned role from user"
MSG_ROLE_ALREADY_ASSIGNED = "Role is already assigned to user"
MSG_ROLE_NOT_ASSIGNED = "Role is not assigned to user"
MSG_GROUP_ADDED = "Successfully created group"
MSG_GROUP_ALREADY_EXISTS = "Group already exists"
MSG_USER_ADDED_TO_GROUP = "Successfully added user to group"
MSG_USER_REMOVED_FROM_GROUP = "Successfully removed user from group"
MSG_PUSH_NOTIFICATION_SENT = "Successfully sent push notification"

# Valid value lists
RECEIVE_TYPE_VALUES = ["Email", "UI"]
FACTOR_TYPE_VALUES = ["push", "sms", "token:software:totp"]
IDENTITY_PROVIDER_TYPES = ["SAML2", "FACEBOOK", "GOOGLE", "LINKEDIN", "MICROSOFT"]
ROLE_TYPES = [
    "SUPER_ADMIN",
    "ORG_ADMIN",
    "API_ACCESS_MANAGEMENT_ADMIN",
    "APP_ADMIN",
    "USER_ADMIN",
    "MOBILE_ADMIN",
    "READ_ONLY_ADMIN",
    "HELP_DESK_ADMIN",
    "GROUP_MEMBERSHIP_ADMIN",
    "REPORT_ADMIN",
]

# Pagination timeout for push notification
PUSH_NOTIFICATION_MAX_ATTEMPTS = 25
PUSH_NOTIFICATION_POLL_INTERVAL = 5

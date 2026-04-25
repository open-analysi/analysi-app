"""Microsoft Defender for Cloud integration constants.

Built from Azure Resource Manager REST API documentation.
"""

# Azure Authentication
LOGIN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
LOGIN_SCOPE = "https://management.azure.com/.default"

# Azure Resource Manager base
ARM_BASE_URL = "https://management.azure.com"

# API versions
SECURITY_API_VERSION = "2022-01-01"
ALERTS_API_VERSION = "2022-01-01"
SECURE_SCORES_API_VERSION = "2026-04-26"
ASSESSMENTS_API_VERSION = "2021-06-01"
SUBSCRIPTIONS_API_VERSION = "2022-12-01"

# API endpoint templates (relative to ARM_BASE_URL)
ENDPOINT_SUBSCRIPTIONS = "/subscriptions"
ENDPOINT_ALERTS = "/subscriptions/{subscription_id}/providers/Microsoft.Security/alerts"
ENDPOINT_ALERT_BY_NAME = (
    "/subscriptions/{subscription_id}/providers/Microsoft.Security"
    "/locations/{location}/alerts/{alert_name}"
)
ENDPOINT_ALERT_STATUS = (
    "/subscriptions/{subscription_id}/providers/Microsoft.Security"
    "/locations/{location}/alerts/{alert_name}/{status}"
)
ENDPOINT_SECURE_SCORES = (
    "/subscriptions/{subscription_id}/providers/Microsoft.Security/secureScores"
)
ENDPOINT_RECOMMENDATIONS = (
    "/subscriptions/{subscription_id}/providers/Microsoft.Security/recommendations"
)
ENDPOINT_RECOMMENDATION_BY_ID = (
    "/subscriptions/{subscription_id}/providers/Microsoft.Security"
    "/recommendations/{recommendation_id}"
)
ENDPOINT_ASSESSMENTS = "{resource_id}/providers/Microsoft.Security/assessments"

# Timeout settings
DEFAULT_TIMEOUT = 30

# Default limits
DEFAULT_ALERT_LIMIT = 100
DEFAULT_RECOMMENDATION_LIMIT = 100
DEFAULT_ASSESSMENT_LIMIT = 100

# JSON field names
JSON_ACCESS_TOKEN = "access_token"
JSON_VALUE = "value"
JSON_NEXT_LINK = "nextLink"

# Alert status actions
ALERT_STATUS_DISMISS = "dismiss"
ALERT_STATUS_ACTIVATE = "activate"
ALERT_STATUS_RESOLVE = "resolve"
ALERT_STATUS_IN_PROGRESS = "inProgress"
VALID_ALERT_STATUSES = {
    ALERT_STATUS_DISMISS,
    ALERT_STATUS_ACTIVATE,
    ALERT_STATUS_RESOLVE,
    ALERT_STATUS_IN_PROGRESS,
}

# Credential field names
CREDENTIAL_CLIENT_ID = "client_id"
CREDENTIAL_CLIENT_SECRET = "client_secret"

# Settings field names
SETTINGS_TENANT_ID = "tenant_id"
SETTINGS_SUBSCRIPTION_ID = "subscription_id"
SETTINGS_TIMEOUT = "timeout"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"

# Error messages
ERROR_MISSING_CREDENTIALS = "Missing required credentials (client_id, client_secret)"
ERROR_MISSING_TENANT_ID = "Missing required setting: tenant_id"
ERROR_MISSING_SUBSCRIPTION_ID = "Missing required setting: subscription_id"
ERROR_MISSING_ALERT_NAME = "Missing required parameter: alert_name"
ERROR_MISSING_LOCATION = (
    "Missing required parameter: location (Azure region, e.g. 'centralus')"
)
ERROR_MISSING_STATUS = "Missing required parameter: status"
ERROR_INVALID_STATUS = (
    "Invalid status. Must be one of: dismiss, activate, resolve, inProgress"
)
ERROR_MISSING_RESOURCE_ID = "Missing required parameter: resource_id"
ERROR_MISSING_RECOMMENDATION_ID = "Missing required parameter: recommendation_id"
ERROR_TOKEN_FAILED = "Failed to acquire access token"
ERROR_INVALID_LIMIT = "Limit must be a positive integer"

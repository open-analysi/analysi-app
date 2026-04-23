"""
AWS Security integration constants.

Covers Security Hub and GuardDuty API endpoints, credentials,
and signing configuration.
"""

# AWS Signature V4 algorithm
AWS_SIGV4_ALGORITHM = "AWS4-HMAC-SHA256"
AWS_SIGV4_TERMINATOR = "aws4_request"

# Default region
DEFAULT_REGION = "us-east-1"

# Default timeout in seconds
DEFAULT_TIMEOUT = 30

# --- Security Hub ---
SECURITYHUB_SERVICE = "securityhub"
SECURITYHUB_HOST_TEMPLATE = "securityhub.{region}.amazonaws.com"

# Security Hub uses JSON-RPC style with X-Amz-Target header.
# All requests are POST to /.
SECURITYHUB_TARGET_PREFIX = "SecurityHubService"
SECURITYHUB_TARGET_GET_FINDINGS = f"{SECURITYHUB_TARGET_PREFIX}.GetFindings"
SECURITYHUB_TARGET_BATCH_UPDATE = f"{SECURITYHUB_TARGET_PREFIX}.BatchUpdateFindings"

# New Security Hub (OCSF-native, GetFindingsV2)
SECURITYHUB_TARGET_GET_FINDINGS_V2 = f"{SECURITYHUB_TARGET_PREFIX}.GetFindingsV2"

# --- GuardDuty ---
GUARDDUTY_SERVICE = "guardduty"
GUARDDUTY_HOST_TEMPLATE = "guardduty.{region}.amazonaws.com"

# GuardDuty is a standard REST API.
GUARDDUTY_DETECTORS_PATH = "/detector"

# --- Credential field names ---
CREDENTIAL_ACCESS_KEY_ID = "access_key_id"
CREDENTIAL_SECRET_ACCESS_KEY = "secret_access_key"
CREDENTIAL_SESSION_TOKEN = "session_token"

# --- Settings field names ---
SETTINGS_REGION = "region"
SETTINGS_TIMEOUT = "timeout"

# --- Error types ---
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"

# --- Error messages ---
MSG_MISSING_CREDENTIALS = (
    "Missing required AWS credentials (access_key_id and secret_access_key)"
)
MSG_MISSING_REGION = "Missing required setting: region"
MSG_MISSING_DETECTOR_ID = (
    "Missing required setting: guardduty_detector_id (needed for pull_alerts)"
)

# --- Settings for AlertSource ---
SETTINGS_GUARDDUTY_DETECTOR_ID = "guardduty_detector_id"
SETTINGS_DEFAULT_LOOKBACK = "default_lookback_minutes"
DEFAULT_LOOKBACK_MINUTES = 5
DEFAULT_MAX_ALERTS = 200
ALERT_PAGE_SIZE = 100  # Security Hub GetFindings max is 100

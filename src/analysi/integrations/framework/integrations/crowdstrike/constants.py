"""
CrowdStrike Falcon integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30

# OAuth2 endpoints
OAUTH_TOKEN_ENDPOINT = "/oauth2/token"

# Device endpoints
GET_DEVICE_ID_ENDPOINT = "/devices/queries/devices/v1"
GET_DEVICE_DETAILS_ENDPOINT = "/devices/entities/devices/v2"
GET_DEVICE_SCROLL_ENDPOINT = "/devices/queries/devices-scroll/v1"
DEVICE_ACTION_ENDPOINT = "/devices/entities/devices-actions/v2"

# Host group endpoints
GET_HOST_GROUP_ID_ENDPOINT = "/devices/queries/host-groups/v1"
GET_HOST_GROUP_DETAILS_ENDPOINT = "/devices/entities/host-groups/v1"
GROUP_DEVICE_ACTION_ENDPOINT = "/devices/entities/host-group-actions/v1"

# RTR (Real-Time Response) endpoints
RTR_SESSION_ENDPOINT = "/real-time-response/entities/sessions/v1"
GET_RTR_SESSION_ID_ENDPOINT = "/real-time-response/queries/sessions/v1"
GET_RTR_SESSION_DETAILS_ENDPOINT = "/real-time-response/entities/sessions/GET/v1"
RUN_COMMAND_ENDPOINT = "/real-time-response/entities/command/v1"
ADMIN_COMMAND_ENDPOINT = "/real-time-response/entities/admin-command/v1"
COMMAND_ACTION_ENDPOINT = "/real-time-response/entities/active-responder-command/v1"
GET_RTR_FILES_ENDPOINT = "/real-time-response/entities/file/v1"
GET_EXTRACTED_RTR_FILE_ENDPOINT = (
    "/real-time-response/entities/extracted-file-contents/v1"
)

# Detection endpoints
LIST_DETECTIONS_ENDPOINT = "/detects/queries/detects/v1"
LIST_DETECTIONS_DETAILS_ENDPOINT = "/detects/entities/summaries/GET/v1"
RESOLVE_DETECTION_ENDPOINT = "/detects/entities/detects/v2"

# Alert endpoints
LIST_ALERTS_ENDPOINT = "/alerts/queries/alerts/v2"
LIST_ALERT_DETAILS_ENDPOINT = "/alerts/entities/alerts/v2"
GET_ALERT_DETAILS_ENDPOINT = "/alerts/entities/alerts/v2"
UPDATE_ALERT_ENDPOINT = "/alerts/entities/alerts/v3"

# Incident endpoints
LIST_INCIDENTS_ENDPOINT = "/incidents/queries/incidents/v1"
LIST_BEHAVIORS_ENDPOINT = "/incidents/queries/behaviors/v1"
GET_INCIDENT_DETAILS_ENDPOINT = "/incidents/entities/incidents/GET/v1"
GET_INCIDENT_BEHAVIORS_ENDPOINT = "/incidents/entities/behaviors/GET/v1"
LIST_CROWDSCORES_ENDPOINT = "/incidents/combined/crowdscores/v1"
UPDATE_INCIDENT_ENDPOINT = "/incidents/entities/incident-actions/v1"

# IOC (Indicator of Compromise) endpoints
GET_INDICATOR_ENDPOINT = "/iocs/entities/indicators/v1"
GET_CUSTOM_INDICATORS_ENDPOINT = "/iocs/queries/indicators/v1"
GET_COMBINED_CUSTOM_INDICATORS_ENDPOINT = "/iocs/combined/indicator/v1"
GET_DEVICE_COUNT_ENDPOINT = "/indicators/aggregates/devices-count/v1"
GET_DEVICES_RAN_ON_ENDPOINT = "/indicators/queries/devices/v1"
GET_PROCESSES_RAN_ON_ENDPOINT = "/indicators/queries/processes/v1"
GET_PROCESS_DETAIL_ENDPOINT = "/processes/entities/processes/v1"

# Sandbox/Malware Analysis endpoints
QUERY_REPORT_ENDPOINT = "/falconx/queries/reports/v1"
QUERY_FILE_ENDPOINT = "/falconx/queries/submissions/v1"
GET_REPORT_SUMMARY_ENDPOINT = "/falconx/entities/report-summaries/v1"
GET_FULL_REPORT_ENDPOINT = "/falconx/entities/reports/v1"
DOWNLOAD_REPORT_ENDPOINT = "/falconx/entities/artifacts/v1"
UPLOAD_FILE_ENDPOINT = "/samples/entities/samples/v2"
DETONATE_RESOURCE_ENDPOINT = "/falconx/entities/submissions/v1"

# User management endpoints
LIST_USERS_ENDPOINT = "/user-management/queries/users/v1"
GET_USER_INFO_ENDPOINT = "/user-management/entities/users/GET/v1"
GET_USER_ROLES_ENDPOINT = "/user-management/combined/user-roles/v1"
GET_ROLE_ENDPOINT = "/user-management/entities/roles/v1"
LIST_USER_ROLES_ENDPOINT = "/user-management/queries/roles/v1"

# Zero Trust Assessment endpoint
GET_ZERO_TRUST_ASSESSMENT_ENDPOINT = "/zero-trust-assessment/entities/assessments/v1"

# Credential field names
CREDENTIAL_CLIENT_ID = "client_id"
CREDENTIAL_CLIENT_SECRET = "client_secret"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"
ERROR_TYPE_NOT_FOUND = "NotFoundError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_PARAMETER = "Missing required parameter: {}"
MSG_INVALID_PARAMETER = "Invalid parameter value: {}"
MSG_AUTHENTICATION_FAILED = "Failed to authenticate with CrowdStrike API"
MSG_TOKEN_EXPIRED = "Access token expired"
MSG_CONNECTION_ERROR = "Failed to connect to CrowdStrike API"

# Device action names
ACTION_CONTAIN = "contain"
ACTION_LIFT_CONTAINMENT = "lift_containment"
ACTION_HIDE_HOST = "hide_host"
ACTION_UNHIDE_HOST = "unhide_host"

# Detection statuses
DETECTION_STATUSES = [
    "new",
    "in_progress",
    "true_positive",
    "false_positive",
    "ignored",
    "closed",
    "reopened",
]

# Alert statuses
ALERT_STATUSES = ["new", "in_progress", "closed", "reopened"]

# Sandbox environment IDs
SANDBOX_ENVIRONMENTS = {
    "windows 10, 64-bit": 160,
    "windows 7, 64-bit": 110,
    "windows 7, 32-bit": 100,
    "linux ubuntu 16.04, 64-bit": 300,
    "android (static analysis)": 200,
}

# Settings for AlertSource
SETTINGS_DEFAULT_LOOKBACK = "default_lookback_minutes"
DEFAULT_LOOKBACK_MINUTES = 5
DEFAULT_MAX_ALERTS = 1000
ALERT_PAGE_SIZE = 500

# API limits
DEFAULT_LIMIT = 100
MAX_BATCH_SIZE = 5000
FALCONX_API_LIMIT = 5000

# Success codes
API_SUCCESS_CODES = [200, 202, 204]

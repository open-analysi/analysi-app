"""Google Cloud SCC integration constants."""

# API base URL
GCP_SCC_BASE_URL = "https://securitycenter.googleapis.com/v1"

# OAuth2 token endpoint (for future JWT-based auth)
GCP_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Default timeout in seconds
DEFAULT_TIMEOUT = 30

# Finding states (per GCP SCC API)
FINDING_STATE_ACTIVE = "ACTIVE"
FINDING_STATE_INACTIVE = "INACTIVE"
FINDING_STATE_MUTED = "MUTED"

VALID_FINDING_STATES = {
    FINDING_STATE_ACTIVE,
    FINDING_STATE_INACTIVE,
    FINDING_STATE_MUTED,
}

# Severity levels
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"
SEVERITY_UNSPECIFIED = "SEVERITY_UNSPECIFIED"

VALID_SEVERITIES = {
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    SEVERITY_UNSPECIFIED,
}

# Default page size for list operations
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000

# Credential field names
CREDENTIAL_ACCESS_TOKEN = "access_token"

# Settings field names
SETTINGS_ORGANIZATION_ID = "organization_id"
SETTINGS_PROJECT_ID = "project_id"
SETTINGS_TIMEOUT = "timeout"

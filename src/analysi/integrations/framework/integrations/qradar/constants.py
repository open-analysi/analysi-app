"""
IBM QRadar SIEM integration constants.
"""

# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_OFFENSE_COUNT = 100
DEFAULT_EVENT_COUNT = 100
DEFAULT_FLOW_COUNT = 100
DEFAULT_INTERVAL_DAYS = 5
QUERY_HIGH_RANGE = 1000  # pagination page size used by QRadar API
ARIEL_POLL_INTERVAL = 6  # seconds between ariel search status polls

# --------------------------------------------------------------------------
# API endpoints (appended to base_url)
# --------------------------------------------------------------------------
ENDPOINT_ARIEL_DATABASES = "ariel/databases"
ENDPOINT_ARIEL_SEARCHES = "ariel/searches"
ENDPOINT_OFFENSES = "siem/offenses"
ENDPOINT_CLOSING_REASONS = "siem/offense_closing_reasons"
ENDPOINT_RULES = "analytics/rules"
ENDPOINT_REFERENCE_SETS = "reference_data/sets"

# --------------------------------------------------------------------------
# Credential field names
# --------------------------------------------------------------------------
CREDENTIAL_AUTH_TOKEN = "auth_token"
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# --------------------------------------------------------------------------
# Settings field names
# --------------------------------------------------------------------------
SETTING_SERVER = "server"
SETTING_VERIFY_SSL = "verify_ssl"
SETTING_TIMEOUT = "timeout"

# --------------------------------------------------------------------------
# Error messages
# --------------------------------------------------------------------------
ERROR_MISSING_CREDENTIALS = (
    "Missing credentials: provide either 'auth_token' or both 'username' and 'password'"
)
ERROR_MISSING_SERVER = "Missing required setting: server"

# --------------------------------------------------------------------------
# Ariel query status values
# --------------------------------------------------------------------------
ARIEL_STATUS_COMPLETED = "COMPLETED"
ARIEL_STATUS_VALUES = {"COMPLETED", "EXECUTE", "SORTING", "WAIT"}

"""
Sumo Logic integration constants.
"""

# API Endpoints by environment
API_ENDPOINT_US1 = "https://api.sumologic.com/api/v1"
API_ENDPOINT_TEMPLATE = "https://api.{environment}.sumologic.com/api/v1"

# Environment options
ENVIRONMENTS = ["us1", "us2", "eu", "au"]

# Timeout settings
DEFAULT_TIMEOUT = 120  # seconds for search jobs
DEFAULT_QUERY_TIMEOUT = 60  # seconds for initial query timeout
POLLING_INTERVAL = 2  # seconds between polling attempts
POLLING_MAX_TIME = 60  # Maximum polling time in seconds

# Response limits
DEFAULT_RESPONSE_LIMIT = 100
MAX_RESPONSE_LIMIT = 10000

# Response types
RESPONSE_TYPE_MESSAGES = "messages"
RESPONSE_TYPE_RECORDS = "records"
DEFAULT_RESPONSE_TYPE = RESPONSE_TYPE_MESSAGES

# Time calculations
FIVE_DAYS_IN_SECONDS = 432000

# Job states
JOB_STATE_DONE = "DONE GATHERING RESULTS"
JOB_STATE_CANCELLED = "CANCELLED"
JOB_STATE_PAUSED = "PAUSED"
JOB_STATE_FORCE_PAUSED = "FORCE PAUSED"

# Error messages
ERROR_MISSING_CREDENTIALS = "Missing required credentials (access_id, access_key)"
ERROR_MISSING_ENVIRONMENT = "Missing required environment configuration"
ERROR_INVALID_SEARCH_ID = "Invalid or expired search job ID"
ERROR_CONNECTION_FAILED = "Connection to Sumo Logic API failed"
ERROR_SEARCH_JOB_FAILED = "Search job creation failed"
ERROR_SEARCH_JOB_TIMEOUT = "Search job polling timeout"
ERROR_ZERO_TIME_RANGE = "Time range cannot start or end with zero"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

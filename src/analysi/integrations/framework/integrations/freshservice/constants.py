"""
Freshservice ITSM integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30

# API version
API_VERSION = "v2"

# API endpoints (relative to base URL)
API_TICKETS = "/api/v2/tickets"
API_TICKET_BY_ID = "/api/v2/tickets/{ticket_id}"
API_TICKET_NOTES = "/api/v2/tickets/{ticket_id}/notes"

# Freshservice priority values (1=Low, 2=Medium, 3=High, 4=Urgent)
PRIORITY_LOW = 1
PRIORITY_MEDIUM = 2
PRIORITY_HIGH = 3
PRIORITY_URGENT = 4

# Freshservice status values (2=Open, 3=Pending, 4=Resolved, 5=Closed)
STATUS_OPEN = 2
STATUS_PENDING = 3
STATUS_RESOLVED = 4
STATUS_CLOSED = 5

# Credential field names
CREDENTIAL_API_KEY = "api_key"

# Settings field names
SETTINGS_DOMAIN = "domain"
SETTINGS_TIMEOUT = "timeout"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"

# Error messages
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_MISSING_DOMAIN = "Missing required setting: domain"
MSG_MISSING_TICKET_ID = "Missing required parameter: ticket_id"
MSG_MISSING_SUBJECT = "Missing required parameter: subject"
MSG_MISSING_DESCRIPTION = "Missing required parameter: description"
MSG_MISSING_BODY = "Missing required parameter: body"

# Default values
DEFAULT_PAGE_SIZE = 30
DEFAULT_PAGE = 1

"""
TheHive integration constants.
"""

# Default HTTP timeout (seconds) - matches the upstream DEFAULT_TIMEOUT
DEFAULT_TIMEOUT = 30

# Severity mapping: human-readable label -> TheHive integer value
SEVERITY_MAP: dict[str, int] = {"Low": 1, "Medium": 2, "High": 3}

# TLP mapping: human-readable label -> TheHive integer value
TLP_MAP: dict[str, int] = {"White": 0, "Green": 1, "Amber": 2, "Red": 3}

# Valid task statuses
VALID_TASK_STATUSES: set[str] = {"Waiting", "InProgress", "Completed", "Cancel"}

# Valid observable data types
VALID_DATA_TYPES: set[str] = {
    "autonomous-system",
    "domain",
    "file",
    "filename",
    "fqdn",
    "hash",
    "ip",
    "mail",
    "mail_subject",
    "other",
    "regexp",
    "registry",
    "uri_path",
    "url",
    "user-agent",
}

# Valid MITRE ATT&CK tactics
VALID_TACTICS: set[str] = {
    "reconnaissance",
    "resource-development",
    "initial-access",
    "execution",
    "persistence",
    "privilege-escalation",
    "defense-evasion",
    "credential-access",
    "discovery",
    "lateral-movement",
    "collection",
    "command-and-control",
    "exfiltration",
    "impact",
}

# Auth header name used by TheHive API
AUTH_HEADER = "Authorization"

# Error messages
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_MISSING_PARAM = "Missing required parameter: {param}"
MSG_INVALID_SEVERITY = (
    "Invalid severity value '{value}'. Must be one of: Low, Medium, High"
)
MSG_INVALID_TLP = (
    "Invalid TLP value '{value}'. Must be one of: White, Green, Amber, Red"
)
MSG_INVALID_STATUS = (
    "Invalid status value '{value}'. Must be one of: "
    "Waiting, InProgress, Completed, Cancel"
)
MSG_INVALID_DATA_TYPE = (
    "Invalid data_type value '{value}'. Must be one of: "
    + ", ".join(sorted(VALID_DATA_TYPES))
)
MSG_INVALID_TACTIC = "Invalid tactic value '{value}'. Must be one of: " + ", ".join(
    sorted(VALID_TACTICS)
)
MSG_INVALID_JSON = "Unable to parse '{field}' as JSON: {error}"
MSG_INVALID_TICKET_TYPE = "Invalid ticket_type '{value}'. Must be one of: Ticket, Alert"
MSG_INVALID_ARTIFACTS = (
    "Invalid artifacts value. Must be a valid JSON list of artifact objects"
)

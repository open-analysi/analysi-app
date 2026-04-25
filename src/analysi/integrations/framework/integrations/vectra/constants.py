"""
Vectra AI NDR integration constants.
"""

# API versions
API_VERSION = "/api/v2.5"
API_V2_2_VERSION = "/api/v2.2"

# Timeout settings
DEFAULT_TIMEOUT = 30
DEFAULT_REQUEST_TIMEOUT = 240

# API endpoints
TEST_CONNECTIVITY_ENDPOINT = "/hosts"
ENTITY_ENDPOINT = "/{entity_type}/{entity_id}"
DESCRIBE_DETECTION_ENDPOINT = "/detections/{detection_id}"
DETECTIONS_ENDPOINT = "/detections"
SEARCH_DETECTIONS_ENDPOINT = "/search/detections"
ADD_NOTE_ENDPOINT = "/{object_type}/{object_id}/notes"
ADD_REMOVE_TAGS_ENDPOINT = "/tagging/{entity_type}/{entity_id}"
ASSIGNMENTS_ENDPOINT = "/assignments"
UPDATE_ASSIGNMENT_ENDPOINT = "/assignments/{assignment_id}"
RESOLVE_ASSIGNMENT_ENDPOINT = "/assignments/{assignment_id}/resolve"
OUTCOMES_ENDPOINT = "/assignment_outcomes"

# Entity type mappings
VALID_ENTITIES = ["host", "account"]
ENTITY_TYPE_MAPPING = {
    "host": "hosts",
    "account": "accounts",
    "detection": "detections",
}

# Valid object types for note/tag operations (entities + detection)
VALID_OBJECT_TYPES = ["host", "account", "detection"]

# Credential field names
CREDENTIAL_API_TOKEN = "api_token"

# Settings field names
SETTINGS_BASE_URL = "base_url"
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPError"

# Error messages
MSG_MISSING_API_TOKEN = "Missing required credential: api_token"
MSG_MISSING_BASE_URL = "Missing required setting: base_url"
MSG_MISSING_PARAMETER = "Missing required parameter: {}"
MSG_INVALID_ENTITY_TYPE = "Invalid entity_type. Must be one of: host, account"
MSG_INVALID_OBJECT_TYPE = (
    "Invalid object_type. Must be one of: host, account, detection"
)
MSG_INVALID_INTEGER = "Parameter '{}' must be a valid non-negative integer"

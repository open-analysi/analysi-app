"""
Darktrace integration constants.
"""

# Default request timeout (seconds) -- upstream used 10s
DEFAULT_TIMEOUT = 30

# --- API Endpoints ---
MODEL_BREACH_ENDPOINT = "/modelbreaches"
ACK_BREACH_SUFFIX = "/acknowledge"
UNACK_BREACH_SUFFIX = "/unacknowledge"
COMMENT_BREACH_SUFFIX = "/comments"
HEALTH_CHECK_ENDPOINT = "/summarystatistics"
TAG_ENTITIES_ENDPOINT = "/tags/entities"
MODEL_BREACH_CONNECTIONS_ENDPOINT = "/details"
MODEL_BREACH_COMMENT_ENDPOINT = "/mbcomments"
DEVICES_ENDPOINT = "/devices"
DEVICE_SUMMARY_ENDPOINT = "/devicesummary"

# --- Auth header names ---
HEADER_TOKEN = "DTAPI-Token"
HEADER_DATE = "DTAPI-Date"
HEADER_SIGNATURE = "DTAPI-Signature"

# --- Error messages ---
MSG_MISSING_CREDENTIALS = "Missing required credentials: public_token and private_token"
MSG_MISSING_BASE_URL = "Missing required setting: base_url"
MSG_MISSING_PARAM = "Missing required parameter: {param}"

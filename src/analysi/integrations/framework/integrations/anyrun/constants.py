"""
ANY.RUN sandbox integration constants.
"""

# API base URL
ANYRUN_API_BASE_URL = "https://api.any.run/v1"

# Default timeout for sandbox analysis (seconds)
DEFAULT_TIMEOUT = 300

# Default analysis timeout inside the sandbox VM (seconds)
DEFAULT_ANALYSIS_TIMEOUT = 120

# Sandbox environment defaults
DEFAULT_OS = "windows"
DEFAULT_BITNESS = 64
DEFAULT_VERSION = "10"
DEFAULT_LOCALE = "en-US"
DEFAULT_BROWSER = "Microsoft Edge"
DEFAULT_ENV_TYPE = "complete"
DEFAULT_PRIVACY_TYPE = "bylink"
DEFAULT_GEO = "fastest"

# User tags default — identifies uploads originating from Analysi.
DEFAULT_USER_TAGS = "analysi-sandbox"

# Verdict mapping (threatLevel integer to human-readable string)
VERDICT_MAP = {
    0: "No threats detected",
    1: "Suspicious activity",
    2: "Malicious activity",
}

# Credential field names
CREDENTIAL_API_KEY = "api_key"

# Settings field names
SETTINGS_TIMEOUT = "timeout"
SETTINGS_BASE_URL = "base_url"

# Error messages
MSG_MISSING_API_KEY = "Missing required credential: api_key"
MSG_MISSING_URL = "Missing required parameter: url"
MSG_MISSING_FILE_CONTENT = "Missing required parameter: file_content"
MSG_MISSING_FILENAME = "Missing required parameter: filename"
MSG_MISSING_ANALYSIS_ID = "Missing required parameter: analysis_id"

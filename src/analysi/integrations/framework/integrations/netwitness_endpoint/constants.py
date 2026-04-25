"""
NetWitness Endpoint integration constants.
RSA NetWitness Endpoint is an EDR platform.
"""

# API Endpoints
TEST_CONNECTIVITY_ENDPOINT = "/api/v2/health?format=json"
BLOCKLIST_DOMAIN_ENDPOINT = "/api/v2/blacklist/domain?format=json"
BLOCKLIST_IP_ENDPOINT = "/api/v2/blacklist/ip?format=json"
LIST_MACHINES_ENDPOINT = "/api/v2/machines?format=json"
GET_SYSTEM_INFO_ENDPOINT = "/api/v2/machines/{}?format=json"
SCAN_ENDPOINT = "/api/v2/machines/{}/scan?format=json"
GET_SCAN_DATA_ENDPOINT = "/api/v2/machines/{}/scandata/{}?format=json"
INSTANTIOC_ENDPOINT = "/api/v2/instantiocs?format=json"
INSTANTIOCS_PER_MACHINE_ENDPOINT = "/api/v2/machines/{}/instantiocs?format=json"
MACHINES_MODULES_ENDPOINT = "/api/v2/machines/{}/modules?format=json"
MACHINES_MODULES_INSTANTIOCS_ENDPOINT = (
    "/api/v2/machines/{}/modules/{}/instantiocs?format=json"
)

# Timeouts
DEFAULT_TIMEOUT = 30

# Credential field names
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_URL = "url"
SETTINGS_VERIFY_SSL = "verify_server_cert"
SETTINGS_TIMEOUT = "timeout"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP = "HTTPStatusError"
ERROR_TYPE_REQUEST = "RequestError"
ERROR_TYPE_NOT_FOUND = "NotFoundError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials (url, username, password)"
MSG_MISSING_PARAMETER = "Missing required parameter '{}'"
MSG_ENDPOINT_NOT_FOUND = "Endpoint not found with provided GUID"
MSG_IOC_NOT_FOUND = "IOC name not found"
MSG_CONNECTION_ERROR = "Connection failed: {}"

# HTTP status codes
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404

# Default values
DEFAULT_LIMIT = 50
DEFAULT_IOC_SCORE_GTE = 0
DEFAULT_IOC_SCORE_LTE = 1024
DEFAULT_MIN_MACHINE_COUNT = 0
DEFAULT_MIN_MODULE_COUNT = 0
DEFAULT_IOC_LEVEL = 2
DEFAULT_FILTER_HOOKS = "Signed Modules"
DEFAULT_SCAN_CATEGORY = "All"
DEFAULT_MIN_CPU_VALUE = 20
DEFAULT_MAX_CPU_VALUE = 95
DEFAULT_MAX_CPU_VM_VALUE = 25

# Scan category mapping
SCAN_CATEGORY_MAPPING = {
    "None": "0",
    "Drivers": "1024",
    "Processes": "2048",
    "Kernel Hooks": "8192",
    "Windows Hooks": "262144",
    "Autoruns": "524288",
    "Network": "2097152",
    "Services": "4194304",
    "Image Hooks": "8388608",
    "Files": "16777216",
    "Registry Discrepancies": "134217728",
    "Dlls": "268435456",
    "Security Products": "536870912",
    "Network Shares": "1073741824",
    "Current Users": "2147483648",
    "Loaded Files": "549755813888",
    "Tasks": "17179869184",
    "Hosts": "8589934592",
    "Suspicious Threads": "34359738368",
    "Windows Patches": "4294967296",
    "All": "618373327872",
}

# IOC Level Mapping
# IOC Level 0: Critical - Score 1024
# IOC Level 1: High - Score 128
# IOC Level 2: Medium - Score 8
# IOC Level 3: Low - Score 1
IOC_LEVEL_MAPPING = {
    "0": 1024,
    "1": 128,
    "2": 8,
    "3": 1,
}

# Scan data categories
SCAN_DATA_CATEGORIES = [
    "Services",
    "Processes",
    "Dlls",
    "Drivers",
    "AutoRuns",
    "Tasks",
    "ImageHooks",
    "KernelHooks",
    "WindowsHooks",
    "SuspiciousThreads",
    "RegistryDiscrepencies",
    "Network",
    "Tracking",
]

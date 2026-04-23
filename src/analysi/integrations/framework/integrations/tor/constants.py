"""Tor integration constants.
"""

# HTTP request timeout (seconds) — matches the upstream DEFAULT_TIMEOUT
DEFAULT_TIMEOUT = 30

# Tor Project public exit node list endpoints
TOR_EXIT_ADDRESSES_URL = "https://check.torproject.org/exit-addresses"
TOR_BULK_EXIT_LIST_URL = "https://check.torproject.org/cgi-bin/TorBulkExitList.py"

# Line prefix used in the exit-addresses file to identify exit node IPs
EXIT_ADDRESS_PREFIX = "ExitAddress"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_HTTP = "HTTPStatusError"
ERROR_TYPE_CONNECTION = "ConnectionError"
ERROR_TYPE_TIMEOUT = "TimeoutError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

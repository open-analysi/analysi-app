"""
AD LDAP integration constants.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30  # seconds

# Connection settings
DEFAULT_SSL_PORT = 636
DEFAULT_FORCE_SSL = True
DEFAULT_VALIDATE_SSL_CERT = False

# LDAP search scopes (from ldap3)
SEARCH_SCOPE_SUBTREE = "SUBTREE"
SEARCH_SCOPE_BASE = "BASE"

# Credential field names
SETTINGS_SERVER = "server"
CREDENTIAL_USERNAME = "username"
CREDENTIAL_PASSWORD = "password"

# Settings field names
SETTINGS_SSL = "force_ssl"
SETTINGS_SSL_PORT = "ssl_port"
SETTINGS_VALIDATE_SSL_CERT = "validate_ssl_cert"
SETTINGS_TIMEOUT = "timeout"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_LDAP = "LDAPException"
ERROR_TYPE_CONNECTION = "LDAPConnectionError"
ERROR_TYPE_BIND = "LDAPBindError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials"
MSG_MISSING_SERVER = "Missing server in settings"
MSG_MISSING_USERNAME = "Missing username in credentials"
MSG_MISSING_PASSWORD = "Missing password in credentials"
MSG_BIND_FAILED = "LDAP bind failed"
MSG_CONNECTION_FAILED = "LDAP connection failed"
MSG_MISSING_FILTER = "Missing required parameter 'filter'"
MSG_MISSING_ATTRIBUTES = "Missing required parameter 'attributes'"
MSG_MISSING_PRINCIPALS = "Missing required parameter 'principals'"

# Default attribute separators
ATTRIBUTE_SEPARATOR = ";"

# LDAP modify operations (from ldap3)
MODIFY_ADD = "MODIFY_ADD"
MODIFY_DELETE = "MODIFY_DELETE"
MODIFY_REPLACE = "MODIFY_REPLACE"

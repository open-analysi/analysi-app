"""
Microsoft Teams integration constants.
"""

# Microsoft Graph API endpoints
MSGRAPH_API_BASE_URL = "https://graph.microsoft.com/v1.0"
MSGRAPH_BETA_API_BASE_URL = "https://graph.microsoft.com/beta"

# Timeout settings
DEFAULT_TIMEOUT = 30

# OAuth/Token URLs
LOGIN_BASE_URL = "https://login.microsoftonline.com"
SERVER_TOKEN_URL = "/{tenant_id}/oauth2/v2.0/token"

# API Endpoints
MSGRAPH_SELF_ENDPOINT = "/me"
MSGRAPH_GROUPS_ENDPOINT = "/groups"
MSGRAPH_TEAMS_ENDPOINT = (
    "/groups?$filter=resourceProvisioningOptions/Any(x:x eq 'Team')"
)
MSGRAPH_LIST_USERS_ENDPOINT = "/users"
MSGRAPH_LIST_CHANNELS_ENDPOINT = "/teams/{group_id}/channels"
MSGRAPH_SEND_CHANNEL_MSG_ENDPOINT = "/teams/{group_id}/channels/{channel_id}/messages"
MSGRAPH_LIST_CHATS_ENDPOINT = "/me/chats"
MSGRAPH_LIST_ME_ENDPOINT = "/me"
MSGRAPH_SEND_DIRECT_MSG_ENDPOINT = "/chats/{chat_id}/messages"
MSGRAPH_GET_CHANNEL_MSG_ENDPOINT = (
    "/teams/{group_id}/channels/{channel_id}/messages/{message_id}"
)
MSGRAPH_GET_CHAT_MSG_ENDPOINT = "/chats/{chat_id}/messages/{message_id}"
MSGRAPH_CALENDAR_EVENT_ENDPOINT = "/me/calendar/events"
MSGRAPH_ONLINE_MEETING_ENDPOINT = "/me/onlineMeetings"

# Credential field names
CREDENTIAL_CLIENT_ID = "client_id"
CREDENTIAL_CLIENT_SECRET = "client_secret"
CREDENTIAL_ACCESS_TOKEN = "access_token"

# Settings field names
SETTINGS_TENANT_ID = "tenant_id"
SETTINGS_TIMEOUT = "timeout"
SETTINGS_TIMEZONE = "timezone"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_HTTP_STATUS = "HTTPStatusError"
ERROR_TYPE_REQUEST = "RequestError"
ERROR_TYPE_TIMEOUT = "TimeoutException"
ERROR_TYPE_MSGRAPH_API = "MicrosoftGraphAPIError"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error messages
MSG_MISSING_TENANT_ID = "Missing required setting: tenant_id"
MSG_MISSING_CLIENT_ID = "Missing required credential: client_id"
MSG_MISSING_CLIENT_SECRET = "Missing required credential: client_secret"
MSG_MISSING_ACCESS_TOKEN = "Missing required credential: access_token"
MSG_MISSING_REQUIRED_PARAM = "Missing required parameter: {param}"
MSG_INVALID_CHANNEL = "Channel {channel_id} does not belong to group {group_id}"

# Valid chat types
VALID_CHAT_TYPES = ["oneOnOne", "group", "meeting", "unknownFutureValue"]

# JSON field names
JSON_GROUP_ID = "group_id"
JSON_CHANNEL_ID = "channel_id"
JSON_MSG_ID = "message_id"
JSON_CHAT_ID = "chat_id"
JSON_USER_ID = "user_id"
JSON_USER_FILTER = "user"
JSON_CHAT_TYPE_FILTER = "chat_type"
JSON_MSG = "message"
JSON_SUBJECT = "subject"
JSON_CALENDAR = "add_calendar_event"
JSON_DESCRIPTION = "description"
JSON_START_TIME = "start_time"
JSON_END_TIME = "end_time"
JSON_ATTENDEES = "attendees"

# Response field names
NEXT_LINK_STRING = "@odata.nextLink"

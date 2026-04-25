"""
Tanium REST integration constants.
"""

# API endpoints
SESSION_LOGIN_URL = "/api/v2/session/login"
SAVED_QUESTIONS_URL = "/api/v2/saved_questions"
QUESTIONS_URL = "/api/v2/questions"
QUESTION_RESULTS_URL = "/api/v2/result_data/question/{question_id}"
PARSE_QUESTION_URL = "/api/v2/parse_question"
EXECUTE_ACTION_URL = "/api/v2/saved_actions"
ACTION_GROUP_URL = "/api/v2/action_groups/by-name/{action_group}"
GROUP_URL = "/api/v2/groups/by-name/{group_name}"
PACKAGE_URL = "/api/v2/packages/by-name/{package}"
SAVED_QUESTION_URL = "/api/v2/saved_questions/by-name/{saved_question}"
SAVED_QUESTION_RESULT_URL = "/api/v2/result_data/saved_question/{saved_question_id}"
SENSOR_BY_NAME_URL = "/api/v2/sensors/by-name/{sensor_name}"
SERVER_INFO_URL = "/api/v2/system_status"
PACKAGES_URL = "/api/v2/packages"

# Timeouts
DEFAULT_TIMEOUT = 30  # seconds

# Session header name
SESSION_HEADER = "session"

# Content type
CONTENT_TYPE_JSON = "application/json"

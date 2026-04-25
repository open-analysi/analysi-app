"""
Microsoft Teams integration actions.
"""

from typing import Any

import httpx

from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_ACCESS_TOKEN,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP_STATUS,
    ERROR_TYPE_MSGRAPH_API,
    ERROR_TYPE_REQUEST,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    JSON_ATTENDEES,
    JSON_CALENDAR,
    JSON_CHANNEL_ID,
    JSON_CHAT_ID,
    JSON_CHAT_TYPE_FILTER,
    JSON_DESCRIPTION,
    JSON_END_TIME,
    JSON_GROUP_ID,
    JSON_MSG,
    JSON_MSG_ID,
    JSON_START_TIME,
    JSON_SUBJECT,
    JSON_USER_FILTER,
    JSON_USER_ID,
    MSG_INVALID_CHANNEL,
    MSG_MISSING_ACCESS_TOKEN,
    MSG_MISSING_REQUIRED_PARAM,
    MSGRAPH_API_BASE_URL,
    MSGRAPH_CALENDAR_EVENT_ENDPOINT,
    MSGRAPH_GET_CHANNEL_MSG_ENDPOINT,
    MSGRAPH_GET_CHAT_MSG_ENDPOINT,
    MSGRAPH_GROUPS_ENDPOINT,
    MSGRAPH_LIST_CHANNELS_ENDPOINT,
    MSGRAPH_LIST_CHATS_ENDPOINT,
    MSGRAPH_LIST_ME_ENDPOINT,
    MSGRAPH_LIST_USERS_ENDPOINT,
    MSGRAPH_ONLINE_MEETING_ENDPOINT,
    MSGRAPH_SELF_ENDPOINT,
    MSGRAPH_SEND_CHANNEL_MSG_ENDPOINT,
    MSGRAPH_SEND_DIRECT_MSG_ENDPOINT,
    MSGRAPH_TEAMS_ENDPOINT,
    NEXT_LINK_STRING,
    SETTINGS_TIMEOUT,
    SETTINGS_TIMEZONE,
    STATUS_ERROR,
    STATUS_SUCCESS,
    VALID_CHAT_TYPES,
)


class HealthCheckAction(IntegrationAction):
    """Test connectivity to Microsoft Teams"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity to Microsoft Teams.

        Returns:
            Result with status and data or error
        """
        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_SELF_ENDPOINT}"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            response = await self.http_request(endpoint, headers=headers)

            data = response.json()

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Successfully connected to Microsoft Teams",
                "data": {
                    "user_id": data.get("id"),
                    "user_principal_name": data.get("userPrincipalName"),
                    "display_name": data.get("displayName"),
                    "mail": data.get("mail"),
                    "full_response": data,
                },
            }

        except httpx.HTTPStatusError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class ListUsersAction(IntegrationAction):
    """List all users in Microsoft Teams"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all users in Microsoft Teams.

        Returns:
            Result with status and data or error
        """
        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_LIST_USERS_ENDPOINT}"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            users = []
            while True:
                response = await self.http_request(endpoint, headers=headers)

                data = response.json()
                users.extend(data.get("value", []))

                # Check for pagination
                if not data.get(NEXT_LINK_STRING):
                    break

                endpoint = data[NEXT_LINK_STRING]

            return {
                "status": STATUS_SUCCESS,
                "total_users": len(users),
                "users": users,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class ListGroupsAction(IntegrationAction):
    """List all groups in Microsoft Teams"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all groups in Microsoft Teams.

        Returns:
            Result with status and data or error
        """
        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_GROUPS_ENDPOINT}"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            groups = []
            while True:
                response = await self.http_request(endpoint, headers=headers)

                data = response.json()
                groups.extend(data.get("value", []))

                # Check for pagination
                if not data.get(NEXT_LINK_STRING):
                    break

                endpoint = data[NEXT_LINK_STRING]

            return {
                "status": STATUS_SUCCESS,
                "total_groups": len(groups),
                "groups": groups,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class ListTeamsAction(IntegrationAction):
    """List all teams in Microsoft Teams"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all teams in Microsoft Teams.

        Returns:
            Result with status and data or error
        """
        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_TEAMS_ENDPOINT}"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            teams = []
            while True:
                response = await self.http_request(endpoint, headers=headers)

                data = response.json()
                teams.extend(data.get("value", []))

                # Check for pagination
                if not data.get(NEXT_LINK_STRING):
                    break

                endpoint = data[NEXT_LINK_STRING]

            return {
                "status": STATUS_SUCCESS,
                "total_teams": len(teams),
                "teams": teams,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class ListChannelsAction(IntegrationAction):
    """List channels in a Microsoft Teams group"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List channels in a Microsoft Teams group.

        Args:
            **kwargs: Must contain:
                - group_id (string): Group/Team ID

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        group_id = kwargs.get(JSON_GROUP_ID)

        # Validate required parameters
        if not group_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_GROUP_ID),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_LIST_CHANNELS_ENDPOINT.format(group_id=group_id)}"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            channels = []
            while True:
                response = await self.http_request(endpoint, headers=headers)

                data = response.json()
                channels.extend(data.get("value", []))

                # Check for pagination
                if not data.get(NEXT_LINK_STRING):
                    break

                endpoint = data[NEXT_LINK_STRING]

            return {
                "status": STATUS_SUCCESS,
                "total_channels": len(channels),
                "channels": channels,
            }

        except httpx.HTTPStatusError as e:
            error_message = str(e)
            if "teamId" in error_message:
                error_message = error_message.replace("teamId", "'group_id'")
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {error_message}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class SendChannelMessageAction(IntegrationAction):
    """Send a message to a Microsoft Teams channel"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Send a message to a Microsoft Teams channel.

        Args:
            **kwargs: Must contain:
                - group_id (string): Group/Team ID
                - channel_id (string): Channel ID
                - message (string): Message to send

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        group_id = kwargs.get(JSON_GROUP_ID)
        channel_id = kwargs.get(JSON_CHANNEL_ID)
        message = kwargs.get(JSON_MSG)

        # Validate required parameters
        if not group_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_GROUP_ID),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        if not channel_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_CHANNEL_ID),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        if not message:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_MSG),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # First verify the channel belongs to the group
            verify_endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_LIST_CHANNELS_ENDPOINT.format(group_id=group_id)}"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            # Verify channel exists in group
            verify_response = await self.http_request(verify_endpoint, headers=headers)
            verify_data = verify_response.json()

            channel_ids = [ch.get("id") for ch in verify_data.get("value", [])]
            if channel_id not in channel_ids:
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_CHANNEL.format(
                        channel_id=channel_id, group_id=group_id
                    ),
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            # Send message
            endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_SEND_CHANNEL_MSG_ENDPOINT.format(group_id=group_id, channel_id=channel_id)}"

            payload = {"body": {"contentType": "html", "content": message}}

            response = await self.http_request(
                endpoint, method="POST", headers=headers, json_data=payload
            )

            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "message": "Message sent successfully",
                "data": data,
            }

        except httpx.HTTPStatusError as e:
            error_message = str(e)
            if "teamId" in error_message:
                error_message = error_message.replace("teamId", "'group_id'")
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {error_message}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class ListChatsAction(IntegrationAction):
    """List chats for the current user"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List chats for the current user.

        Args:
            **kwargs: May contain:
                - user (string): Filter by user
                - chat_type (string): Filter by chat type (oneOnOne, group, meeting)

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        user_filter = kwargs.get(JSON_USER_FILTER)
        chat_type_filter = kwargs.get(JSON_CHAT_TYPE_FILTER)

        # Validate chat type if provided
        if chat_type_filter and chat_type_filter not in VALID_CHAT_TYPES:
            return {
                "status": STATUS_ERROR,
                "error": f"Invalid chat type. Must be one of: {', '.join(VALID_CHAT_TYPES)}",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_LIST_CHATS_ENDPOINT}"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            filtered_chats = []
            while True:
                response = await self.http_request(endpoint, headers=headers)

                data = response.json()

                # Apply filters
                for chat in data.get("value", []):
                    # Filter by chat type
                    if chat_type_filter and chat_type_filter != chat.get(
                        "chatType", ""
                    ):
                        continue

                    # Filter by user
                    if user_filter:
                        user_match = False
                        for member in chat.get("members", []):
                            user_id = member.get("userId", "")
                            email = member.get("email", "")
                            if user_filter in user_id or user_filter in email:
                                user_match = True
                                break
                        if not user_match:
                            continue

                    filtered_chats.append(chat)

                # Check for pagination
                if not data.get(NEXT_LINK_STRING):
                    break

                endpoint = data[NEXT_LINK_STRING]

            return {
                "status": STATUS_SUCCESS,
                "total_chats": len(filtered_chats),
                "chats": filtered_chats,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class SendChatMessageAction(IntegrationAction):
    """Send a message to a chat"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Send a message to a chat.

        Args:
            **kwargs: Must contain:
                - chat_id (string): Chat ID
                - message (string): Message to send

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        chat_id = kwargs.get(JSON_CHAT_ID)
        message = kwargs.get(JSON_MSG)

        # Validate required parameters
        if not chat_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_CHAT_ID),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        if not message:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_MSG),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_SEND_DIRECT_MSG_ENDPOINT.format(chat_id=chat_id)}"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            payload = {"body": {"contentType": "html", "content": message}}

            response = await self.http_request(
                endpoint, method="POST", headers=headers, json_data=payload
            )

            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "message": "Message sent to chat successfully",
                "data": data,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class SendDirectMessageAction(IntegrationAction):
    """Send a direct message to a user"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Send a direct message to a user.

        Args:
            **kwargs: Must contain:
                - user_id (string): User ID
                - message (string): Message to send

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        user_id = kwargs.get(JSON_USER_ID)
        message = kwargs.get(JSON_MSG)

        # Validate required parameters
        if not user_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_USER_ID),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        if not message:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_MSG),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            # Get current user ID
            me_endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_LIST_ME_ENDPOINT}"
            me_response = await self.http_request(me_endpoint, headers=headers)
            current_user_id = me_response.json().get("id")

            if not current_user_id:
                return {
                    "status": STATUS_ERROR,
                    "error": "Failed to retrieve current user ID",
                    "error_type": ERROR_TYPE_MSGRAPH_API,
                }

            # Get chats and find 1:1 chat with user
            chats_endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_LIST_CHATS_ENDPOINT}"
            chats_response = await self.http_request(chats_endpoint, headers=headers)
            chats_data = chats_response.json()

            chat_id = None
            for chat in chats_data.get("value", []):
                if chat.get("chatType") == "oneOnOne":
                    members = chat.get("members", [])
                    if len(members) == 2 and any(
                        member.get("userId") == user_id for member in members
                    ):
                        chat_id = chat.get("id")
                        break

            # Create chat if it doesn't exist
            if not chat_id:
                create_chat_endpoint = f"{MSGRAPH_API_BASE_URL}/chats"
                create_chat_payload = {
                    "chatType": "oneOnOne",
                    "members": [
                        {
                            "@odata.type": "#microsoft.graph.aadUserConversationMember",
                            "roles": ["owner"],
                            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{current_user_id}')",
                        },
                        {
                            "@odata.type": "#microsoft.graph.aadUserConversationMember",
                            "roles": ["owner"],
                            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_id}')",
                        },
                    ],
                }
                create_response = await self.http_request(
                    create_chat_endpoint,
                    method="POST",
                    headers=headers,
                    json_data=create_chat_payload,
                )
                chat_id = create_response.json().get("id")

            if not chat_id:
                return {
                    "status": STATUS_ERROR,
                    "error": "Failed to create or find chat with user",
                    "error_type": ERROR_TYPE_MSGRAPH_API,
                }

            # Send message
            send_endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_SEND_DIRECT_MSG_ENDPOINT.format(chat_id=chat_id)}"
            payload = {"body": {"contentType": "html", "content": message}}

            response = await self.http_request(
                send_endpoint, method="POST", headers=headers, json_data=payload
            )

            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "message": "Direct message sent successfully",
                "data": data,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class CreateMeetingAction(IntegrationAction):
    """Create an online meeting"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create an online meeting.

        Args:
            **kwargs: May contain:
                - subject (string): Meeting subject
                - add_calendar_event (boolean): Add to calendar
                - description (string): Meeting description
                - start_time (string): Start time (ISO 8601)
                - end_time (string): End time (ISO 8601)
                - attendees (string): Comma-separated email addresses

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        use_calendar = kwargs.get(JSON_CALENDAR, False)
        subject = kwargs.get(JSON_SUBJECT)
        description = kwargs.get(JSON_DESCRIPTION)
        start_time = kwargs.get(JSON_START_TIME)
        end_time = kwargs.get(JSON_END_TIME)
        attendees = kwargs.get(JSON_ATTENDEES)

        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        timezone = self.settings.get(SETTINGS_TIMEZONE, "UTC")

        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            payload: dict[str, Any] = {}
            if subject:
                payload["subject"] = subject

            if not use_calendar:
                endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_ONLINE_MEETING_ENDPOINT}"
            else:
                endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_CALENDAR_EVENT_ENDPOINT}"
                payload["isOnlineMeeting"] = True

                if description:
                    payload["body"] = {"content": description}
                if start_time:
                    payload["start"] = {"dateTime": start_time, "timeZone": timezone}
                if end_time:
                    payload["end"] = {"dateTime": end_time, "timeZone": timezone}
                if attendees:
                    attendees_list = []
                    for email in attendees.split(","):
                        email = email.strip()
                        if email:
                            attendees_list.append({"emailAddress": {"address": email}})
                    if attendees_list:
                        payload["attendees"] = attendees_list

            response = await self.http_request(
                endpoint, method="POST", headers=headers, json_data=payload
            )

            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "message": "Meeting created successfully",
                "data": data,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class GetChannelMessageAction(IntegrationAction):
    """Get a message from a channel"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get a message from a channel.

        Args:
            **kwargs: Must contain:
                - group_id (string): Group/Team ID
                - channel_id (string): Channel ID
                - message_id (string): Message ID

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        group_id = kwargs.get(JSON_GROUP_ID)
        channel_id = kwargs.get(JSON_CHANNEL_ID)
        message_id = kwargs.get(JSON_MSG_ID)

        # Validate required parameters
        if not group_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_GROUP_ID),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        if not channel_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_CHANNEL_ID),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        if not message_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_MSG_ID),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_GET_CHANNEL_MSG_ENDPOINT.format(group_id=group_id, channel_id=channel_id, message_id=message_id)}"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            response = await self.http_request(endpoint, headers=headers)

            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "message": "Message retrieved successfully",
                "data": data,
            }

        except httpx.HTTPStatusError as e:
            error_message = str(e)
            if "teamId" in error_message:
                error_message = error_message.replace("teamId", "'group_id'")
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {error_message}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class GetChatMessageAction(IntegrationAction):
    """Get a message from a chat"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get a message from a chat.

        Args:
            **kwargs: Must contain:
                - chat_id (string): Chat ID
                - message_id (string): Message ID

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        chat_id = kwargs.get(JSON_CHAT_ID)
        message_id = kwargs.get(JSON_MSG_ID)

        # Validate required parameters
        if not chat_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_CHAT_ID),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        if not message_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REQUIRED_PARAM.format(param=JSON_MSG_ID),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        access_token = self.credentials.get(CREDENTIAL_ACCESS_TOKEN)
        if not access_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ACCESS_TOKEN,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            endpoint = f"{MSGRAPH_API_BASE_URL}{MSGRAPH_GET_CHAT_MSG_ENDPOINT.format(chat_id=chat_id, message_id=message_id)}"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            response = await self.http_request(endpoint, headers=headers)

            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "message": "Message retrieved successfully",
                "data": data,
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e!s}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

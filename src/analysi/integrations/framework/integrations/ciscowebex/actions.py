"""
Cisco Webex integration actions.

Uses the Webex REST API v1 (https://webexapis.com/v1) with Bearer token
authentication. All HTTP calls go through self.http_request() for
automatic retry, logging, SSL, and timeout handling.
"""

from typing import Any

import httpx

from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_BOT_TOKEN,
    DEFAULT_TIMEOUT,
    ENDPOINT_MESSAGES,
    ENDPOINT_PEOPLE,
    ENDPOINT_PEOPLE_ME,
    ENDPOINT_ROOMS,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP_STATUS,
    ERROR_TYPE_REQUEST,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    MAX_ITEMS_PER_PAGE,
    MSG_MISSING_BOT_TOKEN,
    MSG_MISSING_REQUIRED_PARAM,
    SETTINGS_TIMEOUT,
    WEBEX_API_BASE_URL,
)


def _auth_headers(bot_token: str) -> dict[str, str]:
    """Build standard Webex API request headers."""
    return {
        "Authorization": f"Bearer {bot_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

class HealthCheckAction(IntegrationAction):
    """Test connectivity to Cisco Webex by verifying bot credentials."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Call GET /people/me to verify the bot token is valid.

        Returns:
            Standardized result with health status and bot identity.
        """
        bot_token = self.credentials.get(CREDENTIAL_BOT_TOKEN)
        if not bot_token:
            return {
                "healthy": False,
                **self.error_result(
                    MSG_MISSING_BOT_TOKEN,
                    error_type=ERROR_TYPE_CONFIGURATION,
                ),
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            endpoint = f"{WEBEX_API_BASE_URL}{ENDPOINT_PEOPLE_ME}"
            headers = _auth_headers(bot_token)

            response = await self.http_request(
                endpoint, headers=headers, timeout=timeout
            )
            data = response.json()

            return {
                "healthy": True,
                **self.success_result(
                    data={
                        "healthy": True,
                        "message": "Successfully connected to Cisco Webex",
                        "bot_id": data.get("id"),
                        "display_name": data.get("displayName"),
                        "emails": data.get("emails", []),
                        "org_id": data.get("orgId"),
                    }
                ),
            }

        except httpx.HTTPStatusError as e:
            return {
                "healthy": False,
                **self.error_result(
                    f"HTTP {e.response.status_code}: {e!s}",
                    error_type=ERROR_TYPE_HTTP_STATUS,
                ),
            }
        except httpx.RequestError as e:
            return {
                "healthy": False,
                **self.error_result(
                    f"Request error: {e!s}",
                    error_type=ERROR_TYPE_REQUEST,
                ),
            }
        except httpx.TimeoutException as e:
            return {
                "healthy": False,
                **self.error_result(
                    f"Request timed out: {e!s}",
                    error_type=ERROR_TYPE_TIMEOUT,
                ),
            }

class SendMessageAction(IntegrationAction):
    """Send a message to a Webex room or direct to a user by email."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Send a message via the Webex Messages API.

        Args:
            **kwargs: Must contain at least one destination (room_id or
                to_person_email) and at least one body (text or markdown).

        Returns:
            Standardized result with the created message details.
        """
        bot_token = self.credentials.get(CREDENTIAL_BOT_TOKEN)
        if not bot_token:
            return self.error_result(
                MSG_MISSING_BOT_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        room_id = kwargs.get("room_id")
        to_person_email = kwargs.get("to_person_email")
        text = kwargs.get("text")
        markdown = kwargs.get("markdown")

        # Need at least one destination
        if not room_id and not to_person_email:
            return self.error_result(
                "Either room_id or to_person_email is required",
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Need at least one body
        if not text and not markdown:
            return self.error_result(
                "Either text or markdown is required",
                error_type=ERROR_TYPE_VALIDATION,
            )

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        payload: dict[str, Any] = {}
        if room_id:
            payload["roomId"] = room_id
        if to_person_email:
            payload["toPersonEmail"] = to_person_email
        if text:
            payload["text"] = text
        if markdown:
            payload["markdown"] = markdown

        try:
            endpoint = f"{WEBEX_API_BASE_URL}{ENDPOINT_MESSAGES}"
            headers = _auth_headers(bot_token)

            response = await self.http_request(
                endpoint,
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )
            data = response.json()

            return self.success_result(
                data={
                    "message_id": data.get("id"),
                    "room_id": data.get("roomId"),
                    "person_email": data.get("personEmail"),
                    "created": data.get("created"),
                    "full_response": data,
                }
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(
                f"HTTP {e.response.status_code}: {e!s}",
                error_type=ERROR_TYPE_HTTP_STATUS,
            )
        except httpx.RequestError as e:
            return self.error_result(
                f"Request error: {e!s}", error_type=ERROR_TYPE_REQUEST
            )
        except httpx.TimeoutException as e:
            return self.error_result(
                f"Request timed out: {e!s}", error_type=ERROR_TYPE_TIMEOUT
            )

class ListRoomsAction(IntegrationAction):
    """List Webex rooms (spaces) the bot is a member of."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List rooms via the Webex Rooms API.

        Args:
            **kwargs: Optional filters:
                - max_results (int): Maximum rooms to return (default 100)
                - room_type (str): 'direct' or 'group'

        Returns:
            Standardized result with list of rooms.
        """
        bot_token = self.credentials.get(CREDENTIAL_BOT_TOKEN)
        if not bot_token:
            return self.error_result(
                MSG_MISSING_BOT_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        max_results = kwargs.get("max_results", MAX_ITEMS_PER_PAGE)
        room_type = kwargs.get("room_type")

        params: dict[str, Any] = {"max": min(max_results, MAX_ITEMS_PER_PAGE)}
        if room_type:
            params["type"] = room_type

        try:
            endpoint = f"{WEBEX_API_BASE_URL}{ENDPOINT_ROOMS}"
            headers = _auth_headers(bot_token)

            response = await self.http_request(
                endpoint, headers=headers, params=params, timeout=timeout
            )
            data = response.json()

            rooms = data.get("items", [])

            return self.success_result(
                data={
                    "total_rooms": len(rooms),
                    "rooms": rooms,
                }
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(
                f"HTTP {e.response.status_code}: {e!s}",
                error_type=ERROR_TYPE_HTTP_STATUS,
            )
        except httpx.RequestError as e:
            return self.error_result(
                f"Request error: {e!s}", error_type=ERROR_TYPE_REQUEST
            )
        except httpx.TimeoutException as e:
            return self.error_result(
                f"Request timed out: {e!s}", error_type=ERROR_TYPE_TIMEOUT
            )

class CreateRoomAction(IntegrationAction):
    """Create a new Webex room (space)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create a room via the Webex Rooms API.

        Args:
            **kwargs: Must contain:
                - title (str): Title of the new room

        Returns:
            Standardized result with the created room details.
        """
        bot_token = self.credentials.get(CREDENTIAL_BOT_TOKEN)
        if not bot_token:
            return self.error_result(
                MSG_MISSING_BOT_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        title = kwargs.get("title")
        if not title:
            return self.error_result(
                MSG_MISSING_REQUIRED_PARAM.format(param="title"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            endpoint = f"{WEBEX_API_BASE_URL}{ENDPOINT_ROOMS}"
            headers = _auth_headers(bot_token)

            response = await self.http_request(
                endpoint,
                method="POST",
                headers=headers,
                json_data={"title": title},
                timeout=timeout,
            )
            data = response.json()

            return self.success_result(
                data={
                    "room_id": data.get("id"),
                    "title": data.get("title"),
                    "room_type": data.get("type"),
                    "created": data.get("created"),
                    "full_response": data,
                }
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(
                f"HTTP {e.response.status_code}: {e!s}",
                error_type=ERROR_TYPE_HTTP_STATUS,
            )
        except httpx.RequestError as e:
            return self.error_result(
                f"Request error: {e!s}", error_type=ERROR_TYPE_REQUEST
            )
        except httpx.TimeoutException as e:
            return self.error_result(
                f"Request timed out: {e!s}", error_type=ERROR_TYPE_TIMEOUT
            )

class GetUserAction(IntegrationAction):
    """Get details for a Webex user by person ID or email."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up a user via the Webex People API.

        Args:
            **kwargs: Must contain one of:
                - person_id (str): Webex person ID
                - email (str): Email address to look up

        Returns:
            Standardized result with user details, or not_found indicator.
        """
        bot_token = self.credentials.get(CREDENTIAL_BOT_TOKEN)
        if not bot_token:
            return self.error_result(
                MSG_MISSING_BOT_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        person_id = kwargs.get("person_id")
        email = kwargs.get("email")

        if not person_id and not email:
            return self.error_result(
                "Either person_id or email is required",
                error_type=ERROR_TYPE_VALIDATION,
            )

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            headers = _auth_headers(bot_token)

            if person_id:
                # Direct lookup by ID
                endpoint = f"{WEBEX_API_BASE_URL}{ENDPOINT_PEOPLE}/{person_id}"
                response = await self.http_request(
                    endpoint, headers=headers, timeout=timeout
                )
                data = response.json()
            else:
                # Search by email
                endpoint = f"{WEBEX_API_BASE_URL}{ENDPOINT_PEOPLE}"
                response = await self.http_request(
                    endpoint,
                    headers=headers,
                    params={"email": email},
                    timeout=timeout,
                )
                result = response.json()
                items = result.get("items", [])
                if not items:
                    return self.success_result(
                        data={"status": "success", "not_found": True}
                    )
                data = items[0]

            return self.success_result(
                data={
                    "person_id": data.get("id"),
                    "display_name": data.get("displayName"),
                    "emails": data.get("emails", []),
                    "org_id": data.get("orgId"),
                    "created": data.get("created"),
                    "last_activity": data.get("lastActivity"),
                    "status": data.get("status"),
                    "full_response": data,
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    data={"status": "success", "not_found": True}
                )
            return self.error_result(
                f"HTTP {e.response.status_code}: {e!s}",
                error_type=ERROR_TYPE_HTTP_STATUS,
            )
        except httpx.RequestError as e:
            return self.error_result(
                f"Request error: {e!s}", error_type=ERROR_TYPE_REQUEST
            )
        except httpx.TimeoutException as e:
            return self.error_result(
                f"Request timed out: {e!s}", error_type=ERROR_TYPE_TIMEOUT
            )

class ListUsersAction(IntegrationAction):
    """List Webex users in the organization."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List users via the Webex People API.

        Args:
            **kwargs: Optional filters:
                - email (str): Filter by exact email address
                - display_name (str): Filter by display name prefix
                - max_results (int): Maximum users to return (default 100)

        Returns:
            Standardized result with list of users.
        """
        bot_token = self.credentials.get(CREDENTIAL_BOT_TOKEN)
        if not bot_token:
            return self.error_result(
                MSG_MISSING_BOT_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        max_results = kwargs.get("max_results", MAX_ITEMS_PER_PAGE)
        email = kwargs.get("email")
        display_name = kwargs.get("display_name")

        params: dict[str, Any] = {"max": min(max_results, MAX_ITEMS_PER_PAGE)}
        if email:
            params["email"] = email
        if display_name:
            params["displayName"] = display_name

        try:
            endpoint = f"{WEBEX_API_BASE_URL}{ENDPOINT_PEOPLE}"
            headers = _auth_headers(bot_token)

            response = await self.http_request(
                endpoint, headers=headers, params=params, timeout=timeout
            )
            data = response.json()

            users = data.get("items", [])

            return self.success_result(
                data={
                    "total_users": len(users),
                    "users": users,
                }
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(
                f"HTTP {e.response.status_code}: {e!s}",
                error_type=ERROR_TYPE_HTTP_STATUS,
            )
        except httpx.RequestError as e:
            return self.error_result(
                f"Request error: {e!s}", error_type=ERROR_TYPE_REQUEST
            )
        except httpx.TimeoutException as e:
            return self.error_result(
                f"Request timed out: {e!s}", error_type=ERROR_TYPE_TIMEOUT
            )

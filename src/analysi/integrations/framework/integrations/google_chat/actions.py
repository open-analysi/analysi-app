"""
Google Chat integration actions.
"""

from typing import Any

import httpx

from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP_STATUS,
    ERROR_TYPE_REQUEST,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    GOOGLE_CHAT_BASE_URL,
    GOOGLE_OAUTH_TOKEN_URL,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAMETER,
    MSG_TOKEN_REFRESH_FAILED,
    STATUS_ERROR,
    STATUS_SUCCESS,
)


class HealthCheckAction(IntegrationAction):
    """Test connectivity with Google Chat API"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity with Google Chat API.

        Returns:
            Result with status and data or error
        """
        # Retrieve credentials
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")
        refresh_token = self.credentials.get("refresh_token")

        if not client_id or not client_secret or not refresh_token:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        try:
            # Try to refresh the access token to validate credentials
            access_token_result = await self._refresh_access_token(
                client_id, client_secret, refresh_token
            )

            if access_token_result["status"] == STATUS_ERROR:
                return {"healthy": False, **access_token_result}

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Successfully authenticated with Google Chat API",
                "data": {"healthy": True},
            }

        except httpx.HTTPStatusError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"HTTP error occurred: {e!s}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"Request error occurred: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

    async def _refresh_access_token(
        self, client_id: str, client_secret: str, refresh_token: str
    ) -> dict[str, Any]:
        """Refresh the OAuth access token.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            refresh_token: OAuth refresh token

        Returns:
            Dictionary with access_token on success or error details
        """
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        response = await self.http_request(
            GOOGLE_OAUTH_TOKEN_URL, method="POST", data=payload
        )

        data = response.json()

        if "access_token" not in data:
            return {
                "status": STATUS_ERROR,
                "error": MSG_TOKEN_REFRESH_FAILED,
                "error_type": ERROR_TYPE_AUTHENTICATION,
                "data": data,
            }

        return {
            "status": STATUS_SUCCESS,
            "access_token": data["access_token"],
        }

class CreateMessageAction(IntegrationAction):
    """Creates a message in a Google Chat space"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Creates a message in a Google Chat space.

        Args:
            **kwargs: Must contain:
                - parent_space (string): Resource name of the space (e.g., spaces/SPACE_ID)
                - text_message (string): Message content
                - requestid (string, optional): Unique request ID for idempotency
                - messagereplyoption (string, optional): Reply option
                - messageid (string, optional): Custom message ID

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        parent_space = kwargs.get("parent_space")
        text_message = kwargs.get("text_message")
        requestid = kwargs.get("requestid")
        messagereplyoption = kwargs.get("messagereplyoption")
        messageid = kwargs.get("messageid")

        # Validate required parameters
        if not parent_space:
            return {
                "status": STATUS_ERROR,
                "error": f"{MSG_MISSING_PARAMETER}: parent_space",
                "error_type": ERROR_TYPE_VALIDATION,
            }
        if not text_message:
            return {
                "status": STATUS_ERROR,
                "error": f"{MSG_MISSING_PARAMETER}: text_message",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")
        refresh_token = self.credentials.get("refresh_token")

        if not client_id or not client_secret or not refresh_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        try:
            # Get access token
            token_result = await self._refresh_access_token(
                client_id, client_secret, refresh_token
            )

            if token_result["status"] == STATUS_ERROR:
                return token_result

            access_token = token_result["access_token"]

            # Build the API URL
            url = f"{GOOGLE_CHAT_BASE_URL}/v1/{parent_space}/messages"

            # Build request headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8",
            }

            # Build request payload
            json_content = {"text": text_message}

            # Build query parameters
            params = {}
            if requestid:
                params["requestId"] = requestid
            if messagereplyoption:
                params["messageReplyOption"] = messagereplyoption
            if messageid:
                params["messageId"] = messageid

            # Make API call
            response = await self.http_request(
                url,
                method="POST",
                headers=headers,
                json_data=json_content,
                params=params if params else None,
            )

            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "message": f"Message sent to {parent_space}",
                "data": data,
            }

        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_data = e.response.json()
                error_detail = f": {error_data.get('error', {}).get('message', str(e))}"
            except Exception:
                error_detail = f": {e!s}"

            return {
                "status": STATUS_ERROR,
                "error": f"HTTP error occurred{error_detail}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error occurred: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

    async def _refresh_access_token(
        self, client_id: str, client_secret: str, refresh_token: str
    ) -> dict[str, Any]:
        """Refresh the OAuth access token.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            refresh_token: OAuth refresh token

        Returns:
            Dictionary with access_token on success or error details
        """
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        response = await self.http_request(
            GOOGLE_OAUTH_TOKEN_URL, method="POST", data=payload
        )

        data = response.json()

        if "access_token" not in data:
            return {
                "status": STATUS_ERROR,
                "error": MSG_TOKEN_REFRESH_FAILED,
                "error_type": ERROR_TYPE_AUTHENTICATION,
                "data": data,
            }

        return {
            "status": STATUS_SUCCESS,
            "access_token": data["access_token"],
        }

class ReadMessageAction(IntegrationAction):
    """Returns details about a message"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Returns details about a message.

        Args:
            **kwargs: Must contain:
                - name (string): Resource name of the message
                  (e.g., spaces/SPACE_ID/messages/MESSAGE_ID)

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        name = kwargs.get("name")

        # Validate required parameters
        if not name:
            return {
                "status": STATUS_ERROR,
                "error": f"{MSG_MISSING_PARAMETER}: name",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")
        refresh_token = self.credentials.get("refresh_token")

        if not client_id or not client_secret or not refresh_token:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        try:
            # Get access token
            token_result = await self._refresh_access_token(
                client_id, client_secret, refresh_token
            )

            if token_result["status"] == STATUS_ERROR:
                return token_result

            access_token = token_result["access_token"]

            # Build the API URL
            url = f"{GOOGLE_CHAT_BASE_URL}/v1/{name}"

            # Build request headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8",
            }

            # Make API call
            response = await self.http_request(url, headers=headers)

            data = response.json()

            return {
                "status": STATUS_SUCCESS,
                "message": f"Reading message {name}",
                "data": data,
            }

        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_data = e.response.json()
                error_detail = f": {error_data.get('error', {}).get('message', str(e))}"
            except Exception:
                error_detail = f": {e!s}"

            return {
                "status": STATUS_ERROR,
                "error": f"HTTP error occurred{error_detail}",
                "error_type": ERROR_TYPE_HTTP_STATUS,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request error occurred: {e!s}",
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

    async def _refresh_access_token(
        self, client_id: str, client_secret: str, refresh_token: str
    ) -> dict[str, Any]:
        """Refresh the OAuth access token.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            refresh_token: OAuth refresh token

        Returns:
            Dictionary with access_token on success or error details
        """
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        response = await self.http_request(
            GOOGLE_OAUTH_TOKEN_URL, method="POST", data=payload
        )

        data = response.json()

        if "access_token" not in data:
            return {
                "status": STATUS_ERROR,
                "error": MSG_TOKEN_REFRESH_FAILED,
                "error_type": ERROR_TYPE_AUTHENTICATION,
                "data": data,
            }

        return {
            "status": STATUS_SUCCESS,
            "access_token": data["access_token"],
        }

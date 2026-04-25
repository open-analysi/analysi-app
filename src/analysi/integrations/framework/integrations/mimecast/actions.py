"""Mimecast email security integration actions.

Provides actions for URL protection, sender management, message tracking,
and URL decoding via the Mimecast API v2 with OAuth2 client credentials.
"""

import uuid
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_PATH_MESSAGE_GET,
    API_PATH_MESSAGE_SEARCH,
    API_PATH_OAUTH_TOKEN,
    API_PATH_SENDER_MANAGE,
    API_PATH_URL_CREATE,
    API_PATH_URL_DECODE,
    API_PATH_URL_GET_ALL,
    CREDENTIAL_CLIENT_ID,
    CREDENTIAL_CLIENT_SECRET,
    DEFAULT_MAX_RESULTS,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MIMECAST_BASE_URL_DEFAULT,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_ID,
    MSG_MISSING_SENDER,
    MSG_MISSING_TO,
    MSG_MISSING_URL,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
)

logger = get_logger(__name__)

# ============================================================================
# HELPERS
# ============================================================================

def _get_base_url(settings: dict[str, Any]) -> str:
    """Extract and normalize the Mimecast API base URL from settings."""
    url = settings.get(SETTINGS_BASE_URL, MIMECAST_BASE_URL_DEFAULT)
    return url.rstrip("/")

async def _get_oauth_token(
    action: IntegrationAction,
    base_url: str,
    client_id: str,
    client_secret: str,
    timeout: int | float,
) -> str:
    """Obtain an OAuth2 access token using client credentials flow.

    Args:
        action: Integration action instance (provides http_request).
        base_url: Mimecast API base URL
        client_id: OAuth2 client ID
        client_secret: OAuth2 client secret
        timeout: HTTP request timeout in seconds

    Returns:
        Access token string

    Raises:
        httpx.HTTPStatusError: If token request fails
        ValueError: If response doesn't contain access_token
    """
    response = await action.http_request(
        f"{base_url}{API_PATH_OAUTH_TOKEN}",
        method="POST",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )

    token_data = response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise ValueError("OAuth2 response missing access_token")
    return access_token

def _validate_credentials(credentials: dict[str, Any]) -> tuple[str, str] | None:
    """Validate and extract client_id and client_secret from credentials.

    Returns:
        Tuple of (client_id, client_secret) or None if incomplete
    """
    client_id = credentials.get(CREDENTIAL_CLIENT_ID)
    client_secret = credentials.get(CREDENTIAL_CLIENT_SECRET)
    if client_id and client_secret:
        return (client_id, client_secret)
    return None

# ============================================================================
# BASE ACTION WITH OAUTH2
# ============================================================================

class MimecastBaseAction(IntegrationAction):
    """Base class for Mimecast actions with OAuth2 token management.

    Handles credential validation, OAuth2 token acquisition, and
    provides a helper to make authenticated API calls.
    """

    def _get_timeout(self) -> int | float:
        """Get configured timeout."""
        return self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

    def _get_base_url(self) -> str:
        """Get configured base URL."""
        return _get_base_url(self.settings)

    async def _get_auth_headers(self, access_token: str) -> dict[str, str]:
        """Build authenticated request headers."""
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-request-id": str(uuid.uuid4()),
        }

    async def _authenticated_request(
        self,
        *,
        endpoint: str,
        method: str = "POST",
        json_data: Any = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make an authenticated request to the Mimecast API.

        Obtains an OAuth2 token, then calls self.http_request with
        the Bearer authorization header.

        Args:
            endpoint: API endpoint path (e.g., /api/ttp/url/decode-url)
            method: HTTP method
            json_data: JSON request body
            params: Query parameters

        Returns:
            httpx.Response from the API

        Raises:
            httpx.HTTPStatusError: On HTTP errors
            ValueError: If token acquisition fails
        """
        creds = _validate_credentials(self.credentials)
        if not creds:
            raise ValueError(MSG_MISSING_CREDENTIALS)

        client_id, client_secret = creds
        base_url = self._get_base_url()
        timeout = self._get_timeout()

        access_token = await _get_oauth_token(
            self, base_url, client_id, client_secret, timeout
        )
        auth_headers = await self._get_auth_headers(access_token)

        return await self.http_request(
            url=f"{base_url}{endpoint}",
            method=method,
            headers=auth_headers,
            json_data=json_data,
            params=params,
            timeout=timeout,
        )

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(MimecastBaseAction):
    """Check Mimecast API connectivity.

    Obtains an OAuth2 token and makes a test API call to verify
    credentials and connectivity.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Mimecast API connectivity.

        Returns:
            Result with status=success if healthy, status=error otherwise
        """
        creds = _validate_credentials(self.credentials)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
                healthy=False,
            )

        try:
            response = await self._authenticated_request(
                endpoint=API_PATH_URL_GET_ALL,
                json_data={"data": []},
            )
            data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "meta": data.get("meta", {}),
                },
                healthy=True,
                message="Mimecast API is accessible",
            )

        except Exception as e:
            self.log_error("mimecast_health_check_failed", error=e)
            return self.error_result(e, healthy=False)

class DecodeUrlAction(MimecastBaseAction):
    """Decode Mimecast-rewritten URLs back to original.

    Decodes URLs that were rewritten by Mimecast for on-click protection.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Decode a Mimecast-rewritten URL.

        Args:
            **kwargs: Must contain 'url' (URL to decode)

        Returns:
            Result with decoded URL data or error
        """
        url = kwargs.get("url")
        if not url:
            return self.error_result(MSG_MISSING_URL, error_type=ERROR_TYPE_VALIDATION)

        creds = _validate_credentials(self.credentials)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            response = await self._authenticated_request(
                endpoint=API_PATH_URL_DECODE,
                json_data={"data": [{"url": url}]},
            )
            resp_data = response.json()

            result_data = {}
            if resp_data.get("data") and len(resp_data["data"]) > 0:
                result_data = resp_data["data"][0]

            return self.success_result(data=result_data)

        except httpx.HTTPStatusError as e:
            self.log_error("mimecast_decode_url_failed", error=e, url=url)
            return self.error_result(e)
        except Exception as e:
            self.log_error("mimecast_decode_url_failed", error=e, url=url)
            return self.error_result(e)

class GetEmailAction(MimecastBaseAction):
    """Get details of a specific email message.

    Retrieves detailed information about a message using its Mimecast ID.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get email message details.

        Args:
            **kwargs: Must contain 'id' (Mimecast email ID)

        Returns:
            Result with email data or error
        """
        email_id = kwargs.get("id")
        if not email_id:
            return self.error_result(MSG_MISSING_ID, error_type=ERROR_TYPE_VALIDATION)

        creds = _validate_credentials(self.credentials)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            response = await self._authenticated_request(
                endpoint=API_PATH_MESSAGE_GET,
                json_data={"data": [{"id": email_id}]},
            )
            resp_data = response.json()

            result_data = {}
            if resp_data.get("data") and len(resp_data["data"]) > 0:
                result_data = resp_data["data"][0]

            return self.success_result(data=result_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("mimecast_email_not_found", email_id=email_id)
                return self.success_result(
                    not_found=True,
                    data={"id": email_id},
                )
            self.log_error("mimecast_get_email_failed", error=e, email_id=email_id)
            return self.error_result(e)
        except Exception as e:
            self.log_error("mimecast_get_email_failed", error=e, email_id=email_id)
            return self.error_result(e)

class ListUrlsAction(MimecastBaseAction):
    """List managed URLs from the URL protection list.

    Returns URLs managed by Mimecast TTP URL Protection, with optional
    pagination via max_results.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List managed URLs.

        Args:
            **kwargs: Optional 'max_results' (int) to limit results

        Returns:
            Result with list of managed URLs or error
        """
        creds = _validate_credentials(self.credentials)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        max_results = kwargs.get("max_results")
        if max_results is not None:
            try:
                max_results = int(max_results)
                if max_results <= 0:
                    return self.error_result(
                        "max_results must be a positive integer",
                        error_type=ERROR_TYPE_VALIDATION,
                    )
            except (ValueError, TypeError):
                return self.error_result(
                    "max_results must be a valid integer",
                    error_type=ERROR_TYPE_VALIDATION,
                )

        try:
            page_size = (
                min(DEFAULT_MAX_RESULTS, max_results)
                if max_results
                else DEFAULT_MAX_RESULTS
            )
            json_body = {
                "meta": {
                    "pagination": {
                        "pageSize": page_size,
                        "pageToken": None,
                    }
                },
                "data": [],
            }

            response = await self._authenticated_request(
                endpoint=API_PATH_URL_GET_ALL,
                json_data=json_body,
            )
            resp_data = response.json()

            urls = resp_data.get("data", [])
            if max_results and len(urls) > max_results:
                urls = urls[:max_results]

            return self.success_result(data={"urls": urls, "num_urls": len(urls)})

        except httpx.HTTPStatusError as e:
            self.log_error("mimecast_list_urls_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("mimecast_list_urls_failed", error=e)
            return self.error_result(e)

class BlockSenderAction(MimecastBaseAction):
    """Add sender to the block list.

    Blocks emails from a specific sender to a specific recipient.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block a sender.

        Args:
            **kwargs: Must contain 'sender' (email to block) and 'to' (recipient)

        Returns:
            Result with block status or error
        """
        sender = kwargs.get("sender")
        if not sender:
            return self.error_result(
                MSG_MISSING_SENDER, error_type=ERROR_TYPE_VALIDATION
            )

        to = kwargs.get("to")
        if not to:
            return self.error_result(MSG_MISSING_TO, error_type=ERROR_TYPE_VALIDATION)

        creds = _validate_credentials(self.credentials)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            response = await self._authenticated_request(
                endpoint=API_PATH_SENDER_MANAGE,
                json_data={
                    "data": [
                        {
                            "sender": sender,
                            "to": to,
                            "action": "block",
                        }
                    ]
                },
            )
            resp_data = response.json()

            result_data = {}
            if resp_data.get("data") and len(resp_data["data"]) > 0:
                result_data = resp_data["data"][0]

            return self.success_result(data=result_data)

        except httpx.HTTPStatusError as e:
            self.log_error(
                "mimecast_block_sender_failed", error=e, sender=sender, to=to
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error(
                "mimecast_block_sender_failed", error=e, sender=sender, to=to
            )
            return self.error_result(e)

class UnblockSenderAction(MimecastBaseAction):
    """Remove sender from the block list.

    Permits emails from a previously blocked sender to a specific recipient.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock a sender.

        Args:
            **kwargs: Must contain 'sender' (email to unblock) and 'to' (recipient)

        Returns:
            Result with unblock status or error
        """
        sender = kwargs.get("sender")
        if not sender:
            return self.error_result(
                MSG_MISSING_SENDER, error_type=ERROR_TYPE_VALIDATION
            )

        to = kwargs.get("to")
        if not to:
            return self.error_result(MSG_MISSING_TO, error_type=ERROR_TYPE_VALIDATION)

        creds = _validate_credentials(self.credentials)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            response = await self._authenticated_request(
                endpoint=API_PATH_SENDER_MANAGE,
                json_data={
                    "data": [
                        {
                            "sender": sender,
                            "to": to,
                            "action": "permit",
                        }
                    ]
                },
            )
            resp_data = response.json()

            result_data = {}
            if resp_data.get("data") and len(resp_data["data"]) > 0:
                result_data = resp_data["data"][0]

            return self.success_result(data=result_data)

        except httpx.HTTPStatusError as e:
            self.log_error(
                "mimecast_unblock_sender_failed", error=e, sender=sender, to=to
            )
            return self.error_result(e)
        except Exception as e:
            self.log_error(
                "mimecast_unblock_sender_failed", error=e, sender=sender, to=to
            )
            return self.error_result(e)

class SearchMessagesAction(MimecastBaseAction):
    """Search tracked emails by various criteria.

    Supports searching by message ID, sender, recipient, subject,
    and sender IP within optional time boundaries.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search tracked emails.

        Args:
            **kwargs: Optional search criteria:
                - message_id: Internet message ID
                - search_reason: Reason for tracking
                - from_address: Sender email/domain
                - to_address: Recipient email/domain
                - subject: Email subject
                - sender_ip: Source IP address
                - start: Start time (ISO 8601)
                - end: End time (ISO 8601)

        Returns:
            Result with matching emails or error
        """
        creds = _validate_credentials(self.credentials)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        # Build search payload matching upstream structure
        search_data: dict[str, Any] = {}

        message_id = kwargs.get("message_id")
        if message_id:
            search_data["messageId"] = message_id

        search_reason = kwargs.get("search_reason")
        if search_reason:
            search_data["searchReason"] = search_reason

        # Advanced track-and-trace options
        from_address = kwargs.get("from_address")
        to_address = kwargs.get("to_address")
        subject = kwargs.get("subject")
        sender_ip = kwargs.get("sender_ip")

        if from_address or to_address or subject or sender_ip:
            advanced_opts: dict[str, Any] = {}
            if from_address:
                advanced_opts["from"] = from_address
            if to_address:
                advanced_opts["to"] = to_address
            if subject:
                advanced_opts["subject"] = subject
            if sender_ip:
                advanced_opts["senderIp"] = sender_ip
            search_data["advancedTrackAndTraceOptions"] = advanced_opts

        # Time boundaries
        start = kwargs.get("start")
        if start:
            search_data["start"] = start

        end = kwargs.get("end")
        if end:
            search_data["end"] = end

        try:
            response = await self._authenticated_request(
                endpoint=API_PATH_MESSAGE_SEARCH,
                json_data={"data": [search_data]},
            )
            resp_data = response.json()

            tracked_emails = []
            if resp_data.get("data") and len(resp_data["data"]) > 0:
                tracked_emails = resp_data["data"][0].get("trackedEmails", [])

            return self.success_result(
                data={
                    "tracked_emails": tracked_emails,
                    "num_emails": len(tracked_emails),
                }
            )

        except httpx.HTTPStatusError as e:
            self.log_error("mimecast_search_messages_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("mimecast_search_messages_failed", error=e)
            return self.error_result(e)

class GetManagedUrlAction(MimecastBaseAction):
    """Look up managed URL details.

    Retrieves details of a specific URL from the managed URL list
    by searching the full list and filtering by URL ID.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get managed URL details.

        Args:
            **kwargs: Must contain 'id' (Mimecast managed URL ID)

        Returns:
            Result with URL details or not_found
        """
        url_id = kwargs.get("id")
        if not url_id:
            return self.error_result(MSG_MISSING_ID, error_type=ERROR_TYPE_VALIDATION)

        creds = _validate_credentials(self.credentials)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            response = await self._authenticated_request(
                endpoint=API_PATH_URL_GET_ALL,
                json_data={
                    "meta": {
                        "pagination": {
                            "pageSize": DEFAULT_MAX_RESULTS,
                            "pageToken": None,
                        }
                    },
                    "data": [],
                },
            )
            resp_data = response.json()

            # Search for the specific URL by ID
            urls = resp_data.get("data", [])
            for url_entry in urls:
                if url_entry.get("id") == url_id:
                    return self.success_result(data=url_entry)

            # URL not found in the list
            self.log_info("mimecast_managed_url_not_found", url_id=url_id)
            return self.success_result(
                not_found=True,
                data={"id": url_id},
            )

        except httpx.HTTPStatusError as e:
            self.log_error("mimecast_get_managed_url_failed", error=e, url_id=url_id)
            return self.error_result(e)
        except Exception as e:
            self.log_error("mimecast_get_managed_url_failed", error=e, url_id=url_id)
            return self.error_result(e)

class AddManagedUrlAction(MimecastBaseAction):
    """Add URL to the managed URL list.

    Adds a URL to Mimecast TTP URL Protection with configurable
    blocking/permitting behavior.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add a URL to the managed URL list.

        Args:
            **kwargs: Must contain 'url'. Optional:
                - action: 'block' or 'permit' (default: 'block')
                - match_type: 'explicit' or 'domain' (default: 'explicit')
                - comment: Comment for the URL entry
                - disable_log_click: Disable click logging (default: False)
                - disable_rewrite: Disable URL rewriting (default: False)
                - disable_user_awareness: Disable user awareness (default: False)

        Returns:
            Result with managed URL data or error
        """
        url = kwargs.get("url")
        if not url:
            return self.error_result(MSG_MISSING_URL, error_type=ERROR_TYPE_VALIDATION)

        creds = _validate_credentials(self.credentials)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        action = kwargs.get("action", "block")
        match_type = kwargs.get("match_type", "explicit")
        comment = kwargs.get("comment")
        disable_log_click = kwargs.get("disable_log_click", False)
        disable_rewrite = kwargs.get("disable_rewrite", False)
        disable_user_awareness = kwargs.get("disable_user_awareness", False)

        url_data: dict[str, Any] = {
            "url": url,
            "action": action,
            "matchType": match_type,
            "disableLogClick": disable_log_click,
            "disableRewrite": disable_rewrite,
            "disableUserAwareness": disable_user_awareness,
        }
        if comment:
            url_data["comment"] = comment

        try:
            response = await self._authenticated_request(
                endpoint=API_PATH_URL_CREATE,
                json_data={"data": [url_data]},
            )
            resp_data = response.json()

            result_data = {}
            if resp_data.get("data") and len(resp_data["data"]) > 0:
                result_data = resp_data["data"][0]

            return self.success_result(data=result_data)

        except httpx.HTTPStatusError as e:
            self.log_error("mimecast_add_managed_url_failed", error=e, url=url)
            return self.error_result(e)
        except Exception as e:
            self.log_error("mimecast_add_managed_url_failed", error=e, url=url)
            return self.error_result(e)

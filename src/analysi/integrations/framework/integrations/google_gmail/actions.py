"""
Google Gmail integration actions.
"""

import asyncio
import json
from typing import Any

from google.oauth2 import service_account
from googleapiclient import discovery, errors

from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_KEY_JSON,
    EMAIL_FORMAT_METADATA,
    EMAIL_FORMAT_RAW,
    ERROR_DELETE_EMAIL_FAILED,
    ERROR_EMAIL_FETCH_FAILED,
    ERROR_INVALID_KEY_JSON,
    ERROR_MISSING_CREDENTIALS,
    ERROR_MISSING_PARAMETER,
    ERROR_SEND_EMAIL_FAILED,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_GOOGLE_API,
    ERROR_TYPE_VALIDATION,
    ERROR_USER_FETCH_FAILED,
    ERROR_USERS_FETCH_FAILED,
    GMAIL_MAX_RESULTS_DEFAULT,
    GMAIL_MAX_RESULTS_USERS,
    GMAIL_SCOPE_ADMIN_DIR,
    GMAIL_SCOPE_DELETE,
    GMAIL_SCOPE_READONLY,
    MSG_TEST_CONNECTIVITY_FAILED,
    MSG_TEST_CONNECTIVITY_PASSED,
    SETTINGS_DEFAULT_FORMAT,
    SETTINGS_LOGIN_EMAIL,
    STATUS_ERROR,
    STATUS_SUCCESS,
)


def _get_error_message_from_exception(e: Exception) -> str:
    """Extract error message from exception."""
    error_code = None
    error_message = "Error message unavailable"

    try:
        if hasattr(e, "args"):
            if len(e.args) > 1:
                error_code = e.args[0]
                error_message = e.args[1]
            elif len(e.args) == 1:
                error_message = str(e.args[0])
        else:
            error_message = str(e)
    except Exception:
        error_message = str(e)

    if error_code:
        return f"Error Code: {error_code}. Error Message: {error_message}"
    return f"Error Message: {error_message}"

class HealthCheckAction(IntegrationAction):
    """Test connectivity to Google Gmail API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity to Google Gmail API.

        Returns:
            Result with status and data or error
        """
        # Validate credentials
        login_email = self.settings.get(SETTINGS_LOGIN_EMAIL)
        key_json_str = self.credentials.get(CREDENTIAL_KEY_JSON)

        if not login_email or not key_json_str:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        def sync_test_connectivity():
            """Synchronous test connectivity operation."""
            try:
                # Parse key JSON
                key_dict = json.loads(key_json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"{ERROR_INVALID_KEY_JSON}: {e!s}")

            # Create credentials
            scopes = [GMAIL_SCOPE_ADMIN_DIR]
            credentials = service_account.Credentials.from_service_account_info(
                key_dict, scopes=scopes
            )

            # Create delegated credentials
            credentials = credentials.with_subject(login_email)

            # Build service
            service = discovery.build("admin", "directory_v1", credentials=credentials)

            # Extract domain from login email
            _, _, domain = login_email.partition("@")

            # Test API call
            service.users().list(
                domain=domain, maxResults=1, orderBy="email", sortOrder="ASCENDING"
            ).execute()

            return {"healthy": True, "domain": domain}

        try:
            result = await asyncio.to_thread(sync_test_connectivity)
            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": MSG_TEST_CONNECTIVITY_PASSED,
                "data": result,
            }
        except ValueError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"{MSG_TEST_CONNECTIVITY_FAILED}: {_get_error_message_from_exception(e)}",
                "error_type": ERROR_TYPE_GOOGLE_API,
            }

class ListUsersAction(IntegrationAction):
    """Get the list of users from Google Workspace."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get the list of users from Google Workspace.

        Args:
            **kwargs: May contain:
                - max_items (int): Max users to get (max 500)
                - page_token (str): Token to specify next page in list

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        max_items = kwargs.get("max_items", GMAIL_MAX_RESULTS_USERS)
        page_token = kwargs.get("page_token")

        # Validate credentials
        login_email = self.settings.get(SETTINGS_LOGIN_EMAIL)
        key_json_str = self.credentials.get(CREDENTIAL_KEY_JSON)

        if not login_email or not key_json_str:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        def sync_list_users():
            """Synchronous list users operation."""
            try:
                key_dict = json.loads(key_json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"{ERROR_INVALID_KEY_JSON}: {e!s}")

            # Validate max_items
            try:
                max_items_int = int(max_items) if max_items else GMAIL_MAX_RESULTS_USERS
                if max_items_int <= 0:
                    max_items_int = GMAIL_MAX_RESULTS_USERS
            except (TypeError, ValueError):
                max_items_int = GMAIL_MAX_RESULTS_USERS

            # Create service
            scopes = [GMAIL_SCOPE_ADMIN_DIR]
            credentials = service_account.Credentials.from_service_account_info(
                key_dict, scopes=scopes
            )
            credentials = credentials.with_subject(login_email)
            service = discovery.build("admin", "directory_v1", credentials=credentials)

            # Extract domain
            _, _, domain = login_email.partition("@")

            # Build request parameters
            params = {
                "domain": domain,
                "maxResults": max_items_int,
                "orderBy": "email",
                "sortOrder": "ASCENDING",
            }
            if page_token:
                params["pageToken"] = page_token

            # Execute request
            users_resp = service.users().list(**params).execute()

            users = users_resp.get("users", [])
            next_page = users_resp.get("nextPageToken")

            return {
                "users": users,
                "total_users_returned": len(users),
                "next_page_token": next_page,
            }

        try:
            result = await asyncio.to_thread(sync_list_users)
            return {
                "status": STATUS_SUCCESS,
                "data": result["users"],
                "summary": {
                    "total_users_returned": result["total_users_returned"],
                    "next_page_token": result.get("next_page_token"),
                },
            }
        except ValueError as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_USERS_FETCH_FAILED}: {_get_error_message_from_exception(e)}",
                "error_type": ERROR_TYPE_GOOGLE_API,
            }

class RunQueryAction(IntegrationAction):
    """Search emails with query/filtering options."""

    async def execute(self, **kwargs) -> dict[str, Any]:  # noqa: C901
        """Search emails with query/filtering options.

        Args:
            **kwargs: Must contain:
                - email (str): User's Email (Mailbox to search in)
                - label (str): Label (to search in), default: Inbox
                - subject (str): Substring to search in Subject
                - sender (str): Sender Email address to match
                - body (str): Substring to search in Body
                - internet_message_id (str): Internet Message ID
                - query (str): Gmail Query string
                - max_results (int): Max Results, default: 100
                - page_token (str): Next page token

        Returns:
            Result with status and data or error
        """
        # Extract and validate required parameters
        user_email = kwargs.get("email")
        if not user_email:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_MISSING_PARAMETER}: email",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Extract optional parameters
        label = kwargs.get("label", "Inbox")
        subject = kwargs.get("subject")
        sender = kwargs.get("sender")
        body = kwargs.get("body")
        internet_message_id = kwargs.get("internet_message_id")
        query = kwargs.get("query")
        max_results = kwargs.get("max_results", GMAIL_MAX_RESULTS_DEFAULT)
        page_token = kwargs.get("page_token")

        # Validate credentials
        login_email = self.settings.get(SETTINGS_LOGIN_EMAIL)
        key_json_str = self.credentials.get(CREDENTIAL_KEY_JSON)

        if not login_email or not key_json_str:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        def sync_run_query():
            """Synchronous run query operation."""
            try:
                key_dict = json.loads(key_json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"{ERROR_INVALID_KEY_JSON}: {e!s}")

            # Validate max_results
            try:
                max_results_int = (
                    int(max_results) if max_results else GMAIL_MAX_RESULTS_DEFAULT
                )
                if max_results_int <= 0:
                    max_results_int = GMAIL_MAX_RESULTS_DEFAULT
            except (TypeError, ValueError):
                max_results_int = GMAIL_MAX_RESULTS_DEFAULT

            # Create service
            scopes = [GMAIL_SCOPE_READONLY]
            credentials = service_account.Credentials.from_service_account_info(
                key_dict, scopes=scopes
            )
            credentials = credentials.with_subject(user_email)
            service = discovery.build("gmail", "v1", credentials=credentials)

            # Build query string
            if query:
                query_string = query
            else:
                query_parts = []
                if label:
                    query_parts.append(f"label:{label}")
                if subject:
                    query_parts.append(f"subject:{subject}")
                if sender:
                    query_parts.append(f"from:{sender}")
                if internet_message_id:
                    query_parts.append(f"rfc822msgid:{internet_message_id}")
                if body:
                    query_parts.append(body)
                query_string = " ".join(query_parts)

            # Build request parameters
            params = {
                "userId": user_email,
                "maxResults": max_results_int,
                "q": query_string,
            }
            if page_token:
                params["pageToken"] = page_token

            # Execute request
            messages_resp = service.users().messages().list(**params).execute()

            messages = messages_resp.get("messages", [])
            next_page = messages_resp.get("nextPageToken")

            # Fetch email details for each message
            email_list = []
            for msg in messages:
                try:
                    email_details = (
                        service.users()
                        .messages()
                        .get(userId=user_email, id=msg["id"], format="metadata")
                        .execute()
                    )

                    # Extract key headers
                    headers = email_details.get("payload", {}).get("headers", [])
                    header_dict = {}
                    for h in headers:
                        name = h.get("name", "").lower()
                        if name in [
                            "subject",
                            "delivered-to",
                            "from",
                            "to",
                            "message-id",
                        ]:
                            header_dict[name.replace("-", "_")] = h.get("value", "")

                    email_details.update(header_dict)
                    email_list.append(email_details)
                except Exception:
                    # Skip messages that fail to fetch
                    continue

            return {
                "messages": email_list,
                "total_messages_returned": len(email_list),
                "next_page_token": next_page,
            }

        try:
            result = await asyncio.to_thread(sync_run_query)
            return {
                "status": STATUS_SUCCESS,
                "data": result["messages"],
                "summary": {
                    "total_messages_returned": result["total_messages_returned"],
                    "next_page_token": result.get("next_page_token"),
                },
            }
        except ValueError as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Failed to run query: {_get_error_message_from_exception(e)}",
                "error_type": ERROR_TYPE_GOOGLE_API,
            }

class DeleteEmailAction(IntegrationAction):
    """Delete emails from Gmail."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Delete emails from Gmail.

        Args:
            **kwargs: Must contain:
                - id (str): Message IDs to delete (Comma separated IDs allowed)
                - email (str): Email of the mailbox owner

        Returns:
            Result with status and data or error
        """
        # Extract and validate required parameters
        email_ids_str = kwargs.get("id")
        user_email = kwargs.get("email")

        if not email_ids_str:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_MISSING_PARAMETER}: id",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not user_email:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_MISSING_PARAMETER}: email",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Parse email IDs
        email_ids = [x.strip() for x in email_ids_str.split(",")]
        email_ids = list(filter(None, email_ids))
        if not email_ids:
            return {
                "status": STATUS_ERROR,
                "error": "Please provide valid value for 'id' action parameter",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        login_email = self.settings.get(SETTINGS_LOGIN_EMAIL)
        key_json_str = self.credentials.get(CREDENTIAL_KEY_JSON)

        if not login_email or not key_json_str:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        def sync_delete_email():
            """Synchronous delete email operation."""
            try:
                key_dict = json.loads(key_json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"{ERROR_INVALID_KEY_JSON}: {e!s}")

            # Create service
            scopes = [GMAIL_SCOPE_DELETE]
            credentials = service_account.Credentials.from_service_account_info(
                key_dict, scopes=scopes
            )
            credentials = credentials.with_subject(user_email)
            service = discovery.build("gmail", "v1", credentials=credentials)

            # Check which emails exist
            good_ids = []
            bad_ids = []

            for email_id in email_ids:
                try:
                    service.users().messages().get(
                        userId=user_email, id=email_id
                    ).execute()
                    good_ids.append(email_id)
                except errors.HttpError:
                    bad_ids.append(email_id)
                except Exception:
                    bad_ids.append(email_id)

            # Delete existing emails
            if good_ids:
                service.users().messages().batchDelete(
                    userId=user_email, body={"ids": good_ids}
                ).execute()

            return {"deleted_emails": good_ids, "ignored_ids": bad_ids}

        try:
            result = await asyncio.to_thread(sync_delete_email)

            if not result["deleted_emails"]:
                message = f"All the provided emails were already deleted. Ignored IDs: {result['ignored_ids']}"
            else:
                message = f"Messages deleted. Ignored IDs: {result['ignored_ids']}"

            return {
                "status": STATUS_SUCCESS,
                "message": message,
                "summary": {
                    "deleted_emails": result["deleted_emails"],
                    "ignored_ids": result["ignored_ids"],
                },
            }
        except ValueError as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_DELETE_EMAIL_FAILED}: {_get_error_message_from_exception(e)}",
                "error_type": ERROR_TYPE_GOOGLE_API,
            }

class GetEmailAction(IntegrationAction):
    """Retrieve email details via internet message id."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve email details via internet message id.

        Args:
            **kwargs: Must contain:
                - email (str): User's Email (Mailbox to search)
                - internet_message_id (str): Internet Message ID
                - extract_attachments (bool): Add attachments to vault and create vault artifacts
                - format (str): Format used for the get email action (metadata, minimal, raw)
                - download_email (bool): Download email to vault

        Returns:
            Result with status and data or error
        """
        # Extract and validate required parameters
        user_email = kwargs.get("email")
        internet_message_id = kwargs.get("internet_message_id")

        if not user_email:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_MISSING_PARAMETER}: email",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not internet_message_id:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_MISSING_PARAMETER}: internet_message_id",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Extract optional parameters
        download_email = kwargs.get("download_email", False)

        # Get format from settings or parameters
        email_format = kwargs.get("format") or self.settings.get(
            SETTINGS_DEFAULT_FORMAT, EMAIL_FORMAT_METADATA
        )

        # Validate format parameter
        if download_email and email_format != EMAIL_FORMAT_RAW:
            return {
                "status": STATUS_ERROR,
                "error": "To download email the value for format needs to be 'raw'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        login_email = self.settings.get(SETTINGS_LOGIN_EMAIL)
        key_json_str = self.credentials.get(CREDENTIAL_KEY_JSON)

        if not login_email or not key_json_str:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        def sync_get_email():
            """Synchronous get email operation."""
            try:
                key_dict = json.loads(key_json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"{ERROR_INVALID_KEY_JSON}: {e!s}")

            # Create service
            scopes = [GMAIL_SCOPE_READONLY]
            credentials = service_account.Credentials.from_service_account_info(
                key_dict, scopes=scopes
            )
            credentials = credentials.with_subject(user_email)
            service = discovery.build("gmail", "v1", credentials=credentials)

            # Search for message by internet message id
            query_string = f"rfc822msgid:{internet_message_id}"
            messages_resp = (
                service.users()
                .messages()
                .list(userId=user_email, q=query_string)
                .execute()
            )

            messages = messages_resp.get("messages", [])
            if not messages:
                return {"messages": [], "total_messages_returned": 0}

            # Fetch email details
            email_list = []
            for msg in messages:
                email_details = (
                    service.users()
                    .messages()
                    .get(userId=user_email, id=msg["id"], format=email_format)
                    .execute()
                )

                if email_format == EMAIL_FORMAT_METADATA:
                    # Extract headers
                    headers = email_details.get("payload", {}).get("headers", [])
                    header_dict = {}
                    for h in headers:
                        header_dict[h.get("name", "").lower().replace("-", "_")] = (
                            h.get("value", "")
                        )

                    email_details["email_headers"] = [header_dict]

                email_list.append(email_details)

            return {"messages": email_list, "total_messages_returned": len(email_list)}

        try:
            result = await asyncio.to_thread(sync_get_email)
            return {
                "status": STATUS_SUCCESS,
                "data": result["messages"],
                "summary": {
                    "total_messages_returned": result["total_messages_returned"],
                },
            }
        except ValueError as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_EMAIL_FETCH_FAILED}: {_get_error_message_from_exception(e)}",
                "error_type": ERROR_TYPE_GOOGLE_API,
            }

class GetUserAction(IntegrationAction):
    """Retrieve user details via email address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve user details via email address.

        Args:
            **kwargs: Must contain:
                - email (str): User's Email (User to search)

        Returns:
            Result with status and data or error
        """
        # Extract and validate required parameters
        user_email = kwargs.get("email")
        if not user_email:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_MISSING_PARAMETER}: email",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        login_email = self.settings.get(SETTINGS_LOGIN_EMAIL)
        key_json_str = self.credentials.get(CREDENTIAL_KEY_JSON)

        if not login_email or not key_json_str:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        def sync_get_user():
            """Synchronous get user operation."""
            try:
                key_dict = json.loads(key_json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"{ERROR_INVALID_KEY_JSON}: {e!s}")

            # Create service
            scopes = [GMAIL_SCOPE_READONLY]
            credentials = service_account.Credentials.from_service_account_info(
                key_dict, scopes=scopes
            )
            credentials = credentials.with_subject(user_email)
            service = discovery.build("gmail", "v1", credentials=credentials)

            # Get user profile
            user_info = service.users().getProfile(userId="me").execute()

            return user_info

        try:
            result = await asyncio.to_thread(sync_get_user)
            return {
                "status": STATUS_SUCCESS,
                "data": result,
                "message": "Successfully retrieved user details",
            }
        except ValueError as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_USER_FETCH_FAILED}: {_get_error_message_from_exception(e)}",
                "error_type": ERROR_TYPE_GOOGLE_API,
            }

class SendEmailAction(IntegrationAction):
    """Send emails via Gmail."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Send emails via Gmail.

        Args:
            **kwargs: Must contain:
                - to (str): List of recipients email addresses
                - subject (str): Message Subject
                - body (str): Html rendering of message
                - from (str): From field (optional)
                - cc (str): List of recipients email addresses to include on cc line
                - bcc (str): List of recipients email addresses to include on bcc line
                - reply_to (str): Address that should receive replies to the sent email

        Returns:
            Result with status and data or error
        """
        # Extract and validate required parameters
        to = kwargs.get("to")
        subject = kwargs.get("subject")
        body = kwargs.get("body")

        if not to:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_MISSING_PARAMETER}: to",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not subject:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_MISSING_PARAMETER}: subject",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not body:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_MISSING_PARAMETER}: body",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Extract optional parameters
        from_email = kwargs.get("from")
        cc = kwargs.get("cc")
        bcc = kwargs.get("bcc")
        reply_to = kwargs.get("reply_to")

        # Validate credentials
        login_email = self.settings.get(SETTINGS_LOGIN_EMAIL)
        key_json_str = self.credentials.get(CREDENTIAL_KEY_JSON)

        if not login_email or not key_json_str:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        def sync_send_email():
            """Synchronous send email operation."""
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from io import BytesIO

            from googleapiclient.http import MediaIoBaseUpload

            try:
                key_dict = json.loads(key_json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"{ERROR_INVALID_KEY_JSON}: {e!s}")

            sender = from_email if from_email else login_email

            # Create service
            scopes = [GMAIL_SCOPE_DELETE]  # This scope also allows sending
            credentials = service_account.Credentials.from_service_account_info(
                key_dict, scopes=scopes
            )
            credentials = credentials.with_subject(sender)
            service = discovery.build("gmail", "v1", credentials=credentials)

            # Create message
            message = MIMEMultipart("alternative")
            message["to"] = to
            message["from"] = sender
            message["subject"] = subject

            if cc:
                message["cc"] = cc
            if bcc:
                message["bcc"] = bcc
            if reply_to:
                message["Reply-To"] = reply_to

            # Attach body
            part1 = MIMEText(body, "plain")
            message.attach(part1)
            part2 = MIMEText(body, "html")
            message.attach(part2)

            # Send email
            media = MediaIoBaseUpload(
                BytesIO(message.as_bytes()), mimetype="message/rfc822", resumable=True
            )

            sent_message = (
                service.users()
                .messages()
                .send(userId="me", body={}, media_body=media)
                .execute()
            )

            sent_message["from_email"] = sender
            return sent_message

        try:
            result = await asyncio.to_thread(sync_send_email)
            return {
                "status": STATUS_SUCCESS,
                "message": f"Email sent with id {result.get('id')}",
                "data": result,
            }
        except ValueError as e:
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_VALIDATION,
            }
        except Exception as e:
            return {
                "status": STATUS_ERROR,
                "error": f"{ERROR_SEND_EMAIL_FAILED}: {_get_error_message_from_exception(e)}",
                "error_type": ERROR_TYPE_GOOGLE_API,
            }

"""
Microsoft Exchange On-Premises EWS integration actions.

This integration uses SOAP/EWS protocol via HTTP requests (not exchangelib).
Implements async wrappers around synchronous HTTP SOAP calls.
"""

from typing import Any

import httpx
import xmltodict
from lxml import etree
from lxml.builder import ElementMaker

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_EMAIL_RANGE,
    DEFAULT_EWS_VERSION,
    DEFAULT_FOLDER,
    DEFAULT_TIMEOUT,
    ERROR_AUTHENTICATION_FAILED,
    ERROR_CONNECTION_FAILED,
    ERROR_INVALID_EWS_VERSION,
    ERROR_MISSING_CREDENTIALS,
    ERROR_MISSING_PARAMETER,
    ERROR_SOAP_FAULT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_SOAP,
    ERROR_TYPE_VALIDATION,
    MESSAGES_NAMESPACE,
    SETTINGS_TIMEOUT,
    SETTINGS_URL,
    SETTINGS_USE_IMPERSONATION,
    SETTINGS_VERIFY_CERT,
    SETTINGS_VERSION,
    SOAP_ENVELOPE_NAMESPACE,
    STATUS_ERROR,
    STATUS_SUCCESS,
    TYPES_NAMESPACE,
    VALID_EWS_VERSIONS,
)

logger = get_logger(__name__)

# Maximum XML response size to parse (10 MB). Prevents DoS from oversized
# responses returned by a compromised or malicious upstream endpoint.
_MAX_XML_RESPONSE_BYTES = 10 * 1024 * 1024

# ============================================================================
# SOAP/EWS HELPER FUNCTIONS
# ============================================================================

# namespace map
NSMAP = {"soap": SOAP_ENVELOPE_NAMESPACE, "m": MESSAGES_NAMESPACE, "t": TYPES_NAMESPACE}

# Element makers for building SOAP XML
S = ElementMaker(namespace=SOAP_ENVELOPE_NAMESPACE, nsmap=NSMAP)
M = ElementMaker(namespace=MESSAGES_NAMESPACE, nsmap=NSMAP)
T = ElementMaker(namespace=TYPES_NAMESPACE, nsmap=NSMAP)

def build_soap_envelope(
    body_element, version: str, impersonate_user: str | None = None
):
    """Build SOAP envelope with headers and body.

    Args:
        body_element: lxml element for SOAP body
        version: EWS version (e.g., "2016")
        impersonate_user: Optional email address to impersonate

    Returns:
        lxml SOAP envelope element
    """
    header = S.Header(T.RequestServerVersion({"Version": f"Exchange{version}"}))

    if impersonate_user:
        impersonation = T.ExchangeImpersonation(
            T.ConnectingSID(T.SmtpAddress(impersonate_user))
        )
        header.append(impersonation)

    return S.Envelope(header, S.Body(body_element))

def build_resolve_names_request(email: str):
    """Build ResolveNames SOAP request.

    Args:
        email: Email address to resolve

    Returns:
        lxml element for ResolveNames request
    """
    return M.ResolveNames({"ReturnFullContactData": "true"}, M.UnresolvedEntry(email))

def build_get_folder_request(user: str, folder_name: str = "Inbox"):
    """Build FindFolder SOAP request.

    Args:
        user: User email address
        folder_name: Folder name to find

    Returns:
        lxml element for FindFolder request
    """
    folder_shape = M.FolderShape(
        T.BaseShape("IdOnly"),
        T.AdditionalProperties(
            T.FieldURI({"FieldURI": "folder:DisplayName"}),
            T.FieldURI({"FieldURI": "folder:FolderClass"}),
        ),
    )

    # Build restriction to filter by folder name
    restriction = None
    if folder_name and folder_name.lower() != "inbox":
        restriction = M.Restriction(
            T.IsEqualTo(
                T.FieldURI({"FieldURI": "folder:DisplayName"}),
                T.FieldURIOrConstant(T.Constant({"Value": folder_name})),
            )
        )

    parent_folder_ids = M.ParentFolderIds(
        T.DistinguishedFolderId({"Id": "root"}, T.Mailbox(T.EmailAddress(user)))
    )

    elements = [folder_shape]
    if restriction:
        elements.append(restriction)
    elements.append(parent_folder_ids)

    return M.FindFolder({"Traversal": "Deep"}, *elements)

def build_find_items_request(user: str, folder_id: str = "inbox", max_emails: int = 10):
    """Build FindItem SOAP request.

    Args:
        user: User email address
        folder_id: Folder ID or distinguished folder name
        max_emails: Maximum number of emails to retrieve

    Returns:
        lxml element for FindItem request
    """
    item_shape = M.ItemShape(
        T.BaseShape("IdOnly"),
        T.AdditionalProperties(
            T.FieldURI({"FieldURI": "item:Subject"}),
            T.FieldURI({"FieldURI": "message:From"}),
            T.FieldURI({"FieldURI": "message:InternetMessageId"}),
            T.FieldURI({"FieldURI": "item:DateTimeReceived"}),
        ),
    )

    page = M.IndexedPageItemView(
        {"MaxEntriesReturned": str(max_emails)},
        {"Offset": "0"},
        {"BasePoint": "Beginning"},
    )

    sort_order = M.SortOrder(
        T.FieldOrder(
            {"Order": "Descending"}, T.FieldURI({"FieldURI": "item:DateTimeReceived"})
        )
    )

    # Use distinguished folder or folder ID
    if folder_id.lower() in ["inbox", "sentitems", "deleteditems", "drafts"]:
        parent_folder_ids = M.ParentFolderIds(
            T.DistinguishedFolderId(
                {"Id": folder_id.lower()}, T.Mailbox(T.EmailAddress(user))
            )
        )
    else:
        parent_folder_ids = M.ParentFolderIds(T.FolderId({"Id": folder_id}))

    return M.FindItem(
        {"Traversal": "Shallow"}, item_shape, page, sort_order, parent_folder_ids
    )

def build_get_item_request(item_id: str):
    """Build GetItem SOAP request.

    Args:
        item_id: Exchange item ID

    Returns:
        lxml element for GetItem request
    """
    item_shape = M.ItemShape(
        T.BaseShape("Default"),
        T.IncludeMimeContent("true"),
        T.AdditionalProperties(
            T.FieldURI({"FieldURI": "item:Subject"}),
            T.FieldURI({"FieldURI": "message:From"}),
            T.FieldURI({"FieldURI": "message:Sender"}),
            T.FieldURI({"FieldURI": "message:InternetMessageId"}),
            T.FieldURI({"FieldURI": "item:Body"}),
            T.FieldURI({"FieldURI": "item:DateTimeReceived"}),
        ),
    )

    item_ids = M.ItemIds(T.ItemId({"Id": item_id}))

    return M.GetItem(item_shape, item_ids)

def build_delete_item_request(item_id: str):
    """Build DeleteItem SOAP request.

    Args:
        item_id: Exchange item ID

    Returns:
        lxml element for DeleteItem request
    """
    item_ids = M.ItemIds(T.ItemId({"Id": item_id}))
    return M.DeleteItem({"DeleteType": "HardDelete"}, item_ids)

def build_move_item_request(item_id: str, folder_id: str):
    """Build MoveItem SOAP request.

    Args:
        item_id: Exchange item ID
        folder_id: Destination folder ID

    Returns:
        lxml element for MoveItem request
    """
    return M.MoveItem(
        M.ToFolderId(T.FolderId({"Id": folder_id})),
        M.ItemIds(T.ItemId({"Id": item_id})),
    )

def build_copy_item_request(item_id: str, folder_id: str):
    """Build CopyItem SOAP request.

    Args:
        item_id: Exchange item ID
        folder_id: Destination folder ID

    Returns:
        lxml element for CopyItem request
    """
    return M.CopyItem(
        M.ToFolderId(T.FolderId({"Id": folder_id})),
        M.ItemIds(T.ItemId({"Id": item_id})),
    )

def soap_to_string(lxml_obj) -> bytes:
    """Convert lxml element to XML string.

    Args:
        lxml_obj: lxml element

    Returns:
        XML as bytes
    """
    return etree.tostring(lxml_obj, encoding="utf-8")

async def make_ews_request(
    url: str,
    username: str,
    password: str,
    soap_body: Any,
    version: str = DEFAULT_EWS_VERSION,
    verify_cert: bool = True,
    impersonate_user: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    http_request=None,
) -> dict[str, Any]:
    """Make async SOAP request to Exchange Web Services.

    Args:
        url: EWS endpoint URL
        username: Username for authentication
        password: Password for authentication
        soap_body: lxml element for SOAP body
        version: EWS version
        verify_cert: Whether to verify SSL certificate
        impersonate_user: Optional email to impersonate
        timeout: Request timeout in seconds

    Returns:
        Parsed XML response as dict

    Raises:
        Exception: On connection, authentication, or SOAP errors
    """
    envelope = build_soap_envelope(soap_body, version, impersonate_user)
    xml_data = soap_to_string(envelope)

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
    }

    try:
        if http_request:
            response = await http_request(
                url,
                method="POST",
                content=xml_data,
                headers=headers,
                auth=(username, password),
                timeout=timeout,
                verify_ssl=verify_cert,
            )
        else:
            async with httpx.AsyncClient(
                verify=verify_cert, timeout=timeout, auth=(username, password)
            ) as client:
                response = await client.post(url, content=xml_data, headers=headers)
                response.raise_for_status()

        # Size guard: reject oversized responses before parsing
        response_text = response.text
        if len(response_text.encode("utf-8")) > _MAX_XML_RESPONSE_BYTES:
            raise ValueError(
                f"EWS response exceeds {_MAX_XML_RESPONSE_BYTES} byte limit"
            )

        # Parse XML response
        resp_dict = xmltodict.parse(response_text)

        # Check for SOAP fault
        fault = resp_dict.get("s:Envelope", {}).get("s:Body", {}).get("s:Fault")
        if fault:
            fault_string = fault.get("faultstring", "Unknown SOAP fault")
            raise Exception(ERROR_SOAP_FAULT.format(fault=fault_string))

        return resp_dict

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise Exception(ERROR_AUTHENTICATION_FAILED)
        raise Exception(f"HTTP {e.response.status_code}: {e.response.text}")
    except httpx.RequestError as e:
        raise Exception(f"{ERROR_CONNECTION_FAILED}: {e!s}")
    except Exception:
        raise

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Test connectivity to Exchange server."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test Exchange server connectivity.

        Returns:
            Result with healthy status or error
        """
        # Validate credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not all([url, username, password]):
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        version = self.settings.get(SETTINGS_VERSION, DEFAULT_EWS_VERSION)
        verify_cert = self.settings.get(SETTINGS_VERIFY_CERT, True)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Validate version
        if version not in VALID_EWS_VERSIONS:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": ERROR_INVALID_EWS_VERSION.format(
                    versions=", ".join(VALID_EWS_VERSIONS)
                ),
                "error_type": ERROR_TYPE_VALIDATION,
                "data": {"healthy": False},
            }

        try:
            # Try to resolve the username as a connectivity test
            soap_body = build_resolve_names_request(username)

            await make_ews_request(
                url=url,
                username=username,
                password=password,
                soap_body=soap_body,
                version=version,
                verify_cert=verify_cert,
                timeout=timeout,
                http_request=self.http_request,
            )

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Successfully connected to Exchange server",
                "data": {
                    "healthy": True,
                    "ews_version": version,
                    "server_url": url,
                },
            }

        except Exception as e:
            logger.error("exchange_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class LookupEmailAction(IntegrationAction):
    """Look up/resolve email address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Resolve email address to get user details.

        Args:
            **kwargs: Must contain 'email' parameter

        Returns:
            Result with email resolution data or error
        """
        # Validate parameters
        email = kwargs.get("email")
        if not email:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_PARAMETER.format(param="email"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Get credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not all([url, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        version = self.settings.get(SETTINGS_VERSION, DEFAULT_EWS_VERSION)
        verify_cert = self.settings.get(SETTINGS_VERIFY_CERT, True)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            soap_body = build_resolve_names_request(email)

            result = await make_ews_request(
                url=url,
                username=username,
                password=password,
                soap_body=soap_body,
                version=version,
                verify_cert=verify_cert,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Extract resolution results
            response_msg = (
                result.get("s:Envelope", {})
                .get("s:Body", {})
                .get("m:ResolveNamesResponse", {})
            )
            response_msg = response_msg.get("m:ResponseMessages", {}).get(
                "m:ResolveNamesResponseMessage", {}
            )

            resolution_set = response_msg.get("m:ResolutionSet", {})
            resolutions = resolution_set.get("t:Resolution", [])

            # Ensure resolutions is a list
            if not isinstance(resolutions, list):
                resolutions = [resolutions] if resolutions else []

            resolved_emails = []
            for resolution in resolutions:
                mailbox = resolution.get("t:Mailbox", {})
                resolved_emails.append(
                    {
                        "name": mailbox.get("t:Name"),
                        "email": mailbox.get("t:EmailAddress"),
                        "routing_type": mailbox.get("t:RoutingType"),
                        "mailbox_type": mailbox.get("t:MailboxType"),
                    }
                )

            return {
                "status": STATUS_SUCCESS,
                "email": email,
                "resolved_count": len(resolved_emails),
                "resolutions": resolved_emails,
            }

        except Exception as e:
            logger.error("email_lookup_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class RunQueryAction(IntegrationAction):
    """Search for emails in a mailbox."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search emails in Exchange mailbox.

        Args:
            **kwargs: Must contain 'email' (mailbox to search)
                     Optional: 'folder', 'range'

        Returns:
            Result with found emails or error
        """
        # Validate parameters
        email = kwargs.get("email")
        if not email:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_PARAMETER.format(param="email"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        folder = kwargs.get("folder", DEFAULT_FOLDER)
        email_range = kwargs.get("range", DEFAULT_EMAIL_RANGE)

        # Parse range
        try:
            min_offset, max_offset = email_range.split("-")
            max_emails = int(max_offset) - int(min_offset) + 1
        except (ValueError, AttributeError):
            max_emails = 10

        # Get credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not all([url, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        version = self.settings.get(SETTINGS_VERSION, DEFAULT_EWS_VERSION)
        verify_cert = self.settings.get(SETTINGS_VERIFY_CERT, True)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        use_impersonation = self.settings.get(SETTINGS_USE_IMPERSONATION, False)

        try:
            soap_body = build_find_items_request(
                user=email,
                folder_id=(
                    folder.lower()
                    if folder.lower() in ["inbox", "sentitems"]
                    else folder
                ),
                max_emails=max_emails,
            )

            result = await make_ews_request(
                url=url,
                username=username,
                password=password,
                soap_body=soap_body,
                version=version,
                verify_cert=verify_cert,
                impersonate_user=email if use_impersonation else None,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Extract found items
            response_msg = (
                result.get("s:Envelope", {})
                .get("s:Body", {})
                .get("m:FindItemResponse", {})
            )
            response_msg = response_msg.get("m:ResponseMessages", {}).get(
                "m:FindItemResponseMessage", {}
            )

            root_folder = response_msg.get("m:RootFolder", {})
            items = root_folder.get("t:Items", {})
            messages = items.get("t:Message", [])

            # Ensure messages is a list
            if not isinstance(messages, list):
                messages = [messages] if messages else []

            emails = []
            for msg in messages:
                emails.append(
                    {
                        "id": msg.get("t:ItemId", {}).get("@Id"),
                        "subject": msg.get("t:Subject"),
                        "from": msg.get("t:From", {})
                        .get("t:Mailbox", {})
                        .get("t:EmailAddress"),
                        "internet_message_id": msg.get("t:InternetMessageId"),
                        "date_received": msg.get("t:DateTimeReceived"),
                    }
                )

            return {
                "status": STATUS_SUCCESS,
                "email": email,
                "folder": folder,
                "total_items": root_folder.get("@TotalItemsInView", 0),
                "items_returned": len(emails),
                "emails": emails,
            }

        except Exception as e:
            logger.error("email_search_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetEmailAction(IntegrationAction):
    """Get full email details by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get email details from Exchange.

        Args:
            **kwargs: Must contain 'id' (Exchange item ID)

        Returns:
            Result with email details or error
        """
        # Validate parameters
        email_id = kwargs.get("id")
        if not email_id:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_PARAMETER.format(param="id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Get credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not all([url, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        version = self.settings.get(SETTINGS_VERSION, DEFAULT_EWS_VERSION)
        verify_cert = self.settings.get(SETTINGS_VERIFY_CERT, True)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            soap_body = build_get_item_request(email_id)

            result = await make_ews_request(
                url=url,
                username=username,
                password=password,
                soap_body=soap_body,
                version=version,
                verify_cert=verify_cert,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Extract item details
            response_msg = (
                result.get("s:Envelope", {})
                .get("s:Body", {})
                .get("m:GetItemResponse", {})
            )
            response_msg = response_msg.get("m:ResponseMessages", {}).get(
                "m:GetItemResponseMessage", {}
            )

            items = response_msg.get("m:Items", {})
            message = items.get("t:Message", {})

            email_data = {
                "id": message.get("t:ItemId", {}).get("@Id"),
                "subject": message.get("t:Subject"),
                "from": message.get("t:From", {})
                .get("t:Mailbox", {})
                .get("t:EmailAddress"),
                "sender": message.get("t:Sender", {})
                .get("t:Mailbox", {})
                .get("t:EmailAddress"),
                "internet_message_id": message.get("t:InternetMessageId"),
                "body": message.get("t:Body", {}).get("#text", ""),
                "body_type": message.get("t:Body", {}).get("@BodyType"),
                "date_received": message.get("t:DateTimeReceived"),
            }

            return {
                "status": STATUS_SUCCESS,
                "email": email_data,
            }

        except Exception as e:
            logger.error("get_email_failed_for_id", email_id=email_id, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class DeleteEmailAction(IntegrationAction):
    """Delete an email."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Delete email from Exchange.

        Args:
            **kwargs: Must contain 'id' (Exchange item ID)

        Returns:
            Result with deletion status or error
        """
        # Validate parameters
        email_id = kwargs.get("id")
        if not email_id:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_PARAMETER.format(param="id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Get credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not all([url, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        version = self.settings.get(SETTINGS_VERSION, DEFAULT_EWS_VERSION)
        verify_cert = self.settings.get(SETTINGS_VERIFY_CERT, True)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            soap_body = build_delete_item_request(email_id)

            result = await make_ews_request(
                url=url,
                username=username,
                password=password,
                soap_body=soap_body,
                version=version,
                verify_cert=verify_cert,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Check response
            response_msg = (
                result.get("s:Envelope", {})
                .get("s:Body", {})
                .get("m:DeleteItemResponse", {})
            )
            response_msg = response_msg.get("m:ResponseMessages", {}).get(
                "m:DeleteItemResponseMessage", {}
            )

            response_class = response_msg.get("@ResponseClass", "")

            if response_class == "Success":
                return {
                    "status": STATUS_SUCCESS,
                    "message": f"Email {email_id} deleted successfully",
                    "id": email_id,
                }
            error_msg = response_msg.get("m:MessageText", "Unknown error")
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_SOAP,
            }

        except Exception as e:
            logger.error("delete_email_failed_for_id", email_id=email_id, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class MoveEmailAction(IntegrationAction):
    """Move an email to a different folder."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Move email to a different folder.

        Args:
            **kwargs: Must contain 'id' (Exchange item ID) and 'folder' (destination folder ID)

        Returns:
            Result with move status or error
        """
        # Validate parameters
        email_id = kwargs.get("id")
        folder_id = kwargs.get("folder")

        if not email_id:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_PARAMETER.format(param="id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not folder_id:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_PARAMETER.format(param="folder"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Get credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not all([url, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        version = self.settings.get(SETTINGS_VERSION, DEFAULT_EWS_VERSION)
        verify_cert = self.settings.get(SETTINGS_VERIFY_CERT, True)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            soap_body = build_move_item_request(email_id, folder_id)

            result = await make_ews_request(
                url=url,
                username=username,
                password=password,
                soap_body=soap_body,
                version=version,
                verify_cert=verify_cert,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Check response
            response_msg = (
                result.get("s:Envelope", {})
                .get("s:Body", {})
                .get("m:MoveItemResponse", {})
            )
            response_msg = response_msg.get("m:ResponseMessages", {}).get(
                "m:MoveItemResponseMessage", {}
            )

            response_class = response_msg.get("@ResponseClass", "")

            if response_class == "Success":
                new_item = response_msg.get("m:Items", {}).get("t:Message", {})
                new_id = new_item.get("t:ItemId", {}).get("@Id")

                return {
                    "status": STATUS_SUCCESS,
                    "message": "Email moved successfully",
                    "original_id": email_id,
                    "new_id": new_id,
                    "folder": folder_id,
                }
            error_msg = response_msg.get("m:MessageText", "Unknown error")
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_SOAP,
            }

        except Exception as e:
            logger.error("move_email_failed_for_id", email_id=email_id, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class CopyEmailAction(IntegrationAction):
    """Copy an email to a different folder."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Copy email to a different folder.

        Args:
            **kwargs: Must contain 'id' (Exchange item ID) and 'folder' (destination folder ID)

        Returns:
            Result with copy status or error
        """
        # Validate parameters
        email_id = kwargs.get("id")
        folder_id = kwargs.get("folder")

        if not email_id:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_PARAMETER.format(param="id"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not folder_id:
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_PARAMETER.format(param="folder"),
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Get credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not all([url, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERROR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        version = self.settings.get(SETTINGS_VERSION, DEFAULT_EWS_VERSION)
        verify_cert = self.settings.get(SETTINGS_VERIFY_CERT, True)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            soap_body = build_copy_item_request(email_id, folder_id)

            result = await make_ews_request(
                url=url,
                username=username,
                password=password,
                soap_body=soap_body,
                version=version,
                verify_cert=verify_cert,
                timeout=timeout,
                http_request=self.http_request,
            )

            # Check response
            response_msg = (
                result.get("s:Envelope", {})
                .get("s:Body", {})
                .get("m:CopyItemResponse", {})
            )
            response_msg = response_msg.get("m:ResponseMessages", {}).get(
                "m:CopyItemResponseMessage", {}
            )

            response_class = response_msg.get("@ResponseClass", "")

            if response_class == "Success":
                new_item = response_msg.get("m:Items", {}).get("t:Message", {})
                new_id = new_item.get("t:ItemId", {}).get("@Id")

                return {
                    "status": STATUS_SUCCESS,
                    "message": "Email copied successfully",
                    "original_id": email_id,
                    "new_id": new_id,
                    "folder": folder_id,
                }
            error_msg = response_msg.get("m:MessageText", "Unknown error")
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_SOAP,
            }

        except Exception as e:
            logger.error("copy_email_failed_for_id", email_id=email_id, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

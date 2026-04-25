"""Freshservice ITSM integration actions.
HTTP Basic Auth (API key as username, "X" as password).
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_TICKET_BY_ID,
    API_TICKET_NOTES,
    API_TICKETS,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MSG_MISSING_API_KEY,
    MSG_MISSING_BODY,
    MSG_MISSING_DESCRIPTION,
    MSG_MISSING_DOMAIN,
    MSG_MISSING_SUBJECT,
    MSG_MISSING_TICKET_ID,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_base_url(domain: str) -> str:
    """Construct the Freshservice base URL from the domain subdomain.

    Args:
        domain: The Freshservice subdomain (e.g., "mycompany").

    Returns:
        Full base URL like ``https://mycompany.freshservice.com``.
    """
    # Strip protocol and trailing slashes if user included them
    domain = domain.strip().rstrip("/")
    if domain.startswith("https://"):
        domain = domain[len("https://") :]
    elif domain.startswith("http://"):
        domain = domain[len("http://") :]

    # If domain already contains ".freshservice.com", use as-is
    if ".freshservice.com" in domain:
        return f"https://{domain}"

    return f"https://{domain}.freshservice.com"

async def _make_freshservice_request(
    action: IntegrationAction,
    domain: str,
    endpoint: str,
    api_key: str,
    method: str = "GET",
    data: dict | None = None,
    params: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Make an HTTP request to the Freshservice API.

    Uses ``action.http_request()`` for automatic retry via
    ``integration_retry_policy``.

    Freshservice uses HTTP Basic Auth with the API key as the username
    and "X" as the password.

    Args:
        action: The IntegrationAction instance (provides http_request with retry).
        domain: Freshservice subdomain.
        endpoint: API endpoint (e.g., "/api/v2/tickets").
        api_key: Freshservice API key.
        method: HTTP method.
        data: Request body data.
        params: Query parameters.
        timeout: Request timeout in seconds.

    Returns:
        API response data as a dictionary.

    Raises:
        Exception: On API errors.
    """
    base_url = _get_base_url(domain)
    url = f"{base_url}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = await action.http_request(
            url,
            method=method,
            headers=headers,
            auth=(api_key, "X"),
            json_data=data,
            params=params,
            timeout=timeout,
        )

        # Some responses (204 No Content) return empty body
        if response.status_code == 204 or not response.content:
            return {}

        return response.json()

    except httpx.TimeoutException as e:
        logger.error("freshservice_api_timeout", endpoint=endpoint, error=str(e))
        raise Exception(f"Request timed out after {timeout} seconds")
    except httpx.HTTPStatusError as e:
        logger.error(
            "freshservice_api_http_error",
            endpoint=endpoint,
            status_code=e.response.status_code,
        )
        if e.response.status_code == 401:
            raise Exception("Authentication failed - invalid API key")
        if e.response.status_code == 403:
            raise Exception("Access forbidden - insufficient permissions")
        if e.response.status_code == 404:
            raise Exception("Resource not found")
        if e.response.status_code == 400:
            try:
                error_data = e.response.json()
                errors = error_data.get("errors", [])
                if errors:
                    error_msgs = [
                        f"{err.get('field', 'unknown')}: {err.get('message', str(err))}"
                        for err in errors
                    ]
                    raise Exception(f"Bad request: {'; '.join(error_msgs)}")
                description = error_data.get("description", "")
                if description:
                    raise Exception(f"Bad request: {description}")
            except (ValueError, KeyError):
                pass
            raise Exception(f"Bad request: {e.response.text}")
        raise Exception(f"HTTP {e.response.status_code}: {e.response.text}")
    except Exception as e:
        logger.error("freshservice_api_error", endpoint=endpoint, error=str(e))
        raise

def _validate_credentials(action: IntegrationAction) -> tuple[str, str, int] | dict:
    """Validate and extract credentials and settings.

    Returns:
        Tuple of (api_key, domain, timeout) if valid, or an error dict.
    """
    api_key = action.credentials.get("api_key")
    if not api_key:
        return {
            "status": STATUS_ERROR,
            "error": MSG_MISSING_API_KEY,
            "error_type": ERROR_TYPE_CONFIGURATION,
        }

    domain = action.settings.get("domain")
    if not domain:
        return {
            "status": STATUS_ERROR,
            "error": MSG_MISSING_DOMAIN,
            "error_type": ERROR_TYPE_CONFIGURATION,
        }

    timeout = action.settings.get("timeout", DEFAULT_TIMEOUT)
    return (api_key, domain, timeout)

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Freshservice API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Freshservice API connectivity.

        Attempts to list tickets with a page size of 1 to verify
        the API key and domain are valid.

        Returns:
            Result with status=success if healthy, status=error if unhealthy.
        """
        creds = _validate_credentials(self)
        if isinstance(creds, dict):
            creds["healthy"] = False
            creds["data"] = {"healthy": False}
            return creds

        api_key, domain, timeout = creds

        try:
            result = await _make_freshservice_request(
                self,
                domain,
                API_TICKETS,
                api_key,
                params={"per_page": 1},
                timeout=timeout,
            )

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Freshservice API is accessible",
                "data": {
                    "healthy": True,
                    "domain": domain,
                    "tickets_accessible": "tickets" in result,
                },
            }

        except Exception as e:
            logger.error("freshservice_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class CreateTicketAction(IntegrationAction):
    """Create a new Freshservice ticket."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create a new ticket in Freshservice.

        Args:
            **kwargs: Must contain 'subject' and 'description'.
                Optional: 'priority', 'status', 'requester_id',
                'email', 'group_id', 'responder_id', 'type',
                'category', 'sub_category', 'custom_fields'.

        Returns:
            Result with created ticket information or error.
        """
        # Validate required parameters
        subject = kwargs.get("subject")
        if not subject:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_SUBJECT,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        description = kwargs.get("description")
        if not description:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_DESCRIPTION,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        creds = _validate_credentials(self)
        if isinstance(creds, dict):
            return creds

        api_key, domain, timeout = creds

        # Build ticket payload
        payload: dict[str, Any] = {
            "subject": subject,
            "description": description,
            "priority": int(kwargs.get("priority", 1)),
            "status": int(kwargs.get("status", 2)),
        }

        # Requester: either requester_id or email is required by Freshservice
        if kwargs.get("requester_id"):
            payload["requester_id"] = int(kwargs["requester_id"])
        elif kwargs.get("email"):
            payload["email"] = kwargs["email"]

        # Optional fields
        if kwargs.get("group_id"):
            payload["group_id"] = int(kwargs["group_id"])
        if kwargs.get("responder_id"):
            payload["responder_id"] = int(kwargs["responder_id"])
        if kwargs.get("type"):
            payload["type"] = kwargs["type"]
        if kwargs.get("category"):
            payload["category"] = kwargs["category"]
        if kwargs.get("sub_category"):
            payload["sub_category"] = kwargs["sub_category"]
        if kwargs.get("item_category"):
            payload["item_category"] = kwargs["item_category"]

        # Custom fields
        if kwargs.get("custom_fields"):
            custom_fields = kwargs["custom_fields"]
            if isinstance(custom_fields, dict):
                payload["custom_fields"] = custom_fields

        try:
            result = await _make_freshservice_request(
                self,
                domain,
                API_TICKETS,
                api_key,
                method="POST",
                data=payload,
                timeout=timeout,
            )

            ticket = result.get("ticket", {})
            ticket_id = ticket.get("id")

            return {
                "status": STATUS_SUCCESS,
                "ticket_id": ticket_id,
                "message": f"Ticket created with ID {ticket_id}",
                "data": ticket,
            }

        except Exception as e:
            logger.error("freshservice_create_ticket_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetTicketAction(IntegrationAction):
    """Get Freshservice ticket information."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get ticket details by ID.

        Args:
            **kwargs: Must contain 'ticket_id'.

        Returns:
            Result with ticket information or error.
        """
        ticket_id = kwargs.get("ticket_id")
        if not ticket_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_TICKET_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        creds = _validate_credentials(self)
        if isinstance(creds, dict):
            return creds

        api_key, domain, timeout = creds

        try:
            endpoint = API_TICKET_BY_ID.format(ticket_id=ticket_id)
            result = await _make_freshservice_request(
                self,
                domain,
                endpoint,
                api_key,
                timeout=timeout,
            )

            ticket = result.get("ticket", {})

            return {
                "status": STATUS_SUCCESS,
                "ticket_id": ticket.get("id"),
                "subject": ticket.get("subject"),
                "description_text": ticket.get("description_text"),
                "ticket_status": ticket.get("status"),
                "priority": ticket.get("priority"),
                "requester_id": ticket.get("requester_id"),
                "responder_id": ticket.get("responder_id"),
                "group_id": ticket.get("group_id"),
                "type": ticket.get("type"),
                "category": ticket.get("category"),
                "sub_category": ticket.get("sub_category"),
                "created_at": ticket.get("created_at"),
                "updated_at": ticket.get("updated_at"),
                "data": ticket,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("freshservice_ticket_not_found", ticket_id=ticket_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ticket_id": ticket_id,
                    "data": {},
                }
            logger.error(
                "freshservice_get_ticket_failed",
                ticket_id=ticket_id,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class UpdateTicketAction(IntegrationAction):
    """Update a Freshservice ticket."""

    @staticmethod
    def _build_update_payload(**kwargs) -> dict[str, Any]:
        """Build the update payload from provided keyword arguments.

        Extracts recognized ticket fields from kwargs and returns a dict
        suitable for the Freshservice PUT /tickets/:id endpoint.
        """
        payload: dict[str, Any] = {}

        # Integer fields (use 'is not None' to allow 0)
        for field in ("status", "priority", "group_id", "responder_id"):
            if kwargs.get(field) is not None:
                payload[field] = int(kwargs[field])

        # String fields
        for field in (
            "subject",
            "description",
            "category",
            "sub_category",
            "item_category",
            "type",
        ):
            if kwargs.get(field):
                payload[field] = kwargs[field]

        # Custom fields
        custom_fields = kwargs.get("custom_fields")
        if isinstance(custom_fields, dict):
            payload["custom_fields"] = custom_fields

        return payload

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update ticket fields.

        Args:
            **kwargs: Must contain 'ticket_id'.
                Optional: 'status', 'priority', 'subject', 'description',
                'group_id', 'responder_id', 'category', 'sub_category',
                'item_category', 'custom_fields'.

        Returns:
            Result with updated ticket information or error.
        """
        ticket_id = kwargs.get("ticket_id")
        if not ticket_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_TICKET_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        creds = _validate_credentials(self)
        if isinstance(creds, dict):
            return creds

        api_key, domain, timeout = creds

        payload = self._build_update_payload(**kwargs)

        if not payload:
            return {
                "status": STATUS_ERROR,
                "error": "No fields provided to update",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        try:
            endpoint = API_TICKET_BY_ID.format(ticket_id=ticket_id)
            result = await _make_freshservice_request(
                self,
                domain,
                endpoint,
                api_key,
                method="PUT",
                data=payload,
                timeout=timeout,
            )

            ticket = result.get("ticket", {})

            return {
                "status": STATUS_SUCCESS,
                "ticket_id": ticket_id,
                "message": f"Successfully updated ticket {ticket_id}",
                "data": ticket,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("freshservice_ticket_not_found", ticket_id=ticket_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ticket_id": ticket_id,
                    "data": {},
                }
            logger.error(
                "freshservice_update_ticket_failed",
                ticket_id=ticket_id,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class AddNoteAction(IntegrationAction):
    """Add a note (comment) to a Freshservice ticket."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add a note to a ticket.

        Args:
            **kwargs: Must contain 'ticket_id' and 'body'.
                Optional: 'private' (bool, default True).

        Returns:
            Result with note information or error.
        """
        ticket_id = kwargs.get("ticket_id")
        if not ticket_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_TICKET_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        body = kwargs.get("body")
        if not body:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_BODY,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        creds = _validate_credentials(self)
        if isinstance(creds, dict):
            return creds

        api_key, domain, timeout = creds

        # Build note payload
        payload: dict[str, Any] = {
            "body": body,
            "private": kwargs.get("private", True),
        }

        try:
            endpoint = API_TICKET_NOTES.format(ticket_id=ticket_id)
            result = await _make_freshservice_request(
                self,
                domain,
                endpoint,
                api_key,
                method="POST",
                data=payload,
                timeout=timeout,
            )

            conversation = result.get("conversation", {})
            note_id = conversation.get("id")

            return {
                "status": STATUS_SUCCESS,
                "ticket_id": ticket_id,
                "note_id": note_id,
                "message": f"Note added to ticket {ticket_id}",
                "data": conversation,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("freshservice_ticket_not_found", ticket_id=ticket_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ticket_id": ticket_id,
                    "data": {},
                }
            logger.error(
                "freshservice_add_note_failed",
                ticket_id=ticket_id,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ListTicketsAction(IntegrationAction):
    """List Freshservice tickets with optional filters."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List tickets with optional filters.

        Args:
            **kwargs: Optional: 'filter' (predefined filter name),
                'per_page', 'page', 'order_by', 'order_type',
                'requester_id', 'email', 'updated_since'.

        Returns:
            Result with list of tickets or error.
        """
        creds = _validate_credentials(self)
        if isinstance(creds, dict):
            return creds

        api_key, domain, timeout = creds

        # Build query parameters
        params: dict[str, Any] = {
            "per_page": int(kwargs.get("per_page", DEFAULT_PAGE_SIZE)),
            "page": int(kwargs.get("page", DEFAULT_PAGE)),
        }

        # Optional filters
        if kwargs.get("filter"):
            params["filter"] = kwargs["filter"]
        if kwargs.get("order_by"):
            params["order_by"] = kwargs["order_by"]
        if kwargs.get("order_type"):
            params["order_type"] = kwargs["order_type"]
        if kwargs.get("requester_id"):
            params["requester_id"] = kwargs["requester_id"]
        if kwargs.get("email"):
            params["email"] = kwargs["email"]
        if kwargs.get("updated_since"):
            params["updated_since"] = kwargs["updated_since"]

        try:
            result = await _make_freshservice_request(
                self,
                domain,
                API_TICKETS,
                api_key,
                params=params,
                timeout=timeout,
            )

            tickets = result.get("tickets", [])

            # Build simplified ticket list
            ticket_list = []
            for ticket in tickets:
                ticket_list.append(
                    {
                        "id": ticket.get("id"),
                        "subject": ticket.get("subject"),
                        "status": ticket.get("status"),
                        "priority": ticket.get("priority"),
                        "requester_id": ticket.get("requester_id"),
                        "responder_id": ticket.get("responder_id"),
                        "group_id": ticket.get("group_id"),
                        "type": ticket.get("type"),
                        "created_at": ticket.get("created_at"),
                        "updated_at": ticket.get("updated_at"),
                    }
                )

            return {
                "status": STATUS_SUCCESS,
                "total_tickets": len(ticket_list),
                "tickets": ticket_list,
                "data": tickets,
            }

        except Exception as e:
            logger.error("freshservice_list_tickets_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

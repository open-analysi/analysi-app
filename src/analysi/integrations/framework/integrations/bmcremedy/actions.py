"""BMC Remedy ITSM integration actions for incident ticket management.

Auth flow: POST username/password to /api/jwt/login, receive plain-text JWT.
Use as ``Authorization: AR-JWT <token>`` header. Best-effort logoff via
POST /api/jwt/logout on completion.
"""

import json
import re
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    DEFAULT_OFFSET,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_AUTH,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    INCIDENT_CREATE,
    INCIDENT_INTERFACE,
    LIST_TICKETS_FIELDS,
    LOGOUT_ENDPOINT,
    MSG_INCIDENT_NOT_FOUND,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_COMMENT_TYPE,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_INCIDENT_ID,
    MSG_MISSING_STATUS,
    MSG_TOKEN_GENERATION_FAILED,
    TOKEN_ENDPOINT,
    WORK_LOG_ENDPOINT,
)

logger = get_logger(__name__)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_base_url(settings: dict[str, Any]) -> str | None:
    """Extract and normalize the base URL from settings."""
    base_url = settings.get("base_url", "")
    if base_url:
        return base_url.rstrip("/")
    return None

async def _obtain_jwt_token(
    action: IntegrationAction,
    base_url: str,
    username: str,
    password: str,
    timeout: int = DEFAULT_TIMEOUT,
    verify_ssl: bool = False,
) -> str:
    """Obtain a JWT token from BMC Remedy.

    Posts credentials to /api/jwt/login. The response body is the raw
    JWT token as plain text (not JSON).

    Args:
        action: IntegrationAction instance for http_request.
        base_url: Remedy server base URL.
        username: API username.
        password: API password.
        timeout: Request timeout in seconds.
        verify_ssl: Whether to verify SSL certificate.

    Returns:
        JWT token string.

    Raises:
        Exception: On authentication failure.
    """
    url = f"{base_url}{TOKEN_ENDPOINT}"
    response = await action.http_request(
        url,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=f"username={username}&password={password}",
        timeout=timeout,
        verify_ssl=verify_ssl,
    )

    # Check x-ar-messages header for login failure
    x_ar_messages = response.headers.get("x-ar-messages", "")
    if x_ar_messages:
        try:
            messages = json.loads(x_ar_messages)
            for msg in messages:
                text = msg.get("messageText", "")
                if "login failed" in text.lower():
                    raise Exception("Login failed, please check your credentials")
        except (json.JSONDecodeError, TypeError):
            pass

    token = response.text.strip()
    if not token:
        raise Exception(MSG_TOKEN_GENERATION_FAILED)

    return token

async def _logout_jwt_token(
    action: IntegrationAction,
    base_url: str,
    token: str,
    timeout: int = DEFAULT_TIMEOUT,
    verify_ssl: bool = False,
) -> None:
    """Best-effort logout to release the JWT token.

    Failures are logged but not raised since the action has already
    completed by this point.
    """
    try:
        url = f"{base_url}{LOGOUT_ENDPOINT}"
        await action.http_request(
            url,
            method="POST",
            headers={
                "Authorization": f"AR-JWT {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=timeout,
            verify_ssl=verify_ssl,
        )
    except Exception as e:
        logger.debug("bmcremedy_logout_failed", error=str(e))

async def _make_remedy_request(
    action: IntegrationAction,
    base_url: str,
    token: str,
    endpoint: str,
    method: str = "GET",
    data: dict | None = None,
    params: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    verify_ssl: bool = False,
) -> httpx.Response:
    """Make an authenticated request to BMC Remedy AR REST API.

    Args:
        action: IntegrationAction instance for http_request with retry.
        base_url: Remedy server base URL.
        token: JWT authentication token.
        endpoint: API endpoint path.
        method: HTTP method.
        data: JSON body data.
        params: Query parameters.
        timeout: Request timeout in seconds.
        verify_ssl: Whether to verify SSL certificate.

    Returns:
        httpx.Response object.

    Raises:
        httpx.HTTPStatusError: On non-retryable HTTP errors.
    """
    url = f"{base_url}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"AR-JWT {token}",
    }
    return await action.http_request(
        url,
        method=method,
        headers=headers,
        json_data=data,
        params=params,
        timeout=timeout,
        verify_ssl=verify_ssl,
    )

async def _resolve_incident_url(
    action: IntegrationAction,
    base_url: str,
    token: str,
    incident_number: str,
    timeout: int = DEFAULT_TIMEOUT,
    verify_ssl: bool = False,
) -> str | None:
    """Look up the self-link URL for an incident by its Incident Number.

    The BMC Remedy API requires the entry's self-link (containing the
    internal request ID) for PUT operations.

    Returns:
        The API-relative path (e.g. /api/arsys/v1/entry/HPD:Incident.../000...)
        or None if the incident is not found.
    """
    params = {"q": f"'Incident Number'=\"{incident_number}\""}
    response = await _make_remedy_request(
        action,
        base_url,
        token,
        INCIDENT_INTERFACE,
        params=params,
        timeout=timeout,
        verify_ssl=verify_ssl,
    )
    response_data = response.json()

    entries = response_data.get("entries", [])
    if not entries:
        return None

    try:
        href = entries[0].get("_links", {}).get("self", [{}])[0].get("href", "")
        if href:
            # Extract the /api/... portion of the full URL
            match = re.findall(r"(?:/api).*", href)
            if match:
                return match[0]
    except (IndexError, AttributeError):
        pass

    return None

def _validate_non_negative_int(
    value: Any,
    param_name: str,
) -> tuple[bool, int | None, str | None]:
    """Validate that a value is a non-negative integer.

    Returns:
        (ok, parsed_value, error_message)
    """
    try:
        parsed = int(value)
        if parsed < 0:
            return (
                False,
                None,
                f"Parameter '{param_name}' must be a non-negative integer",
            )
        return True, parsed, None
    except (ValueError, TypeError):
        return False, None, f"Parameter '{param_name}' must be a valid integer"

def _extract_credentials_and_settings(
    action: IntegrationAction,
) -> tuple[str, str, str, int, bool] | None:
    """Extract and validate credentials and settings.

    Returns:
        Tuple of (base_url, username, password, timeout, verify_ssl) or None.
    """
    base_url = _get_base_url(action.settings)
    username = action.credentials.get("username")
    password = action.credentials.get("password")
    timeout = action.settings.get("timeout", DEFAULT_TIMEOUT)
    verify_ssl = action.settings.get("verify_ssl", False)

    if not base_url or not username or not password:
        return None

    return base_url, username, password, timeout, verify_ssl

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Verify connectivity to BMC Remedy by obtaining a JWT token."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check BMC Remedy API connectivity.

        Attempts to obtain a JWT token to verify that the server is
        reachable and the credentials are valid.
        """
        extracted = _extract_credentials_and_settings(self)
        if not extracted:
            base_url = _get_base_url(self.settings)
            if not base_url:
                return self.error_result(
                    MSG_MISSING_BASE_URL, error_type=ERROR_TYPE_CONFIGURATION
                )
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        base_url, username, password, timeout, verify_ssl = extracted
        token = None

        try:
            token = await _obtain_jwt_token(
                self,
                base_url,
                username,
                password,
                timeout,
                verify_ssl,
            )
            return self.success_result(
                data={
                    "healthy": True,
                    "message": "Successfully authenticated with BMC Remedy",
                    "server": base_url,
                }
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return self.error_result(
                    "Authentication failed - invalid credentials",
                    error_type=ERROR_TYPE_AUTH,
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)
        finally:
            if token:
                await _logout_jwt_token(self, base_url, token, timeout, verify_ssl)

class CreateTicketAction(IntegrationAction):
    """Create a new incident ticket in BMC Remedy."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create an incident ticket.

        Accepts individual parameters (first_name, last_name, description,
        etc.) and/or a ``fields`` dict. Values in ``fields`` take precedence
        over individual parameters.
        """
        extracted = _extract_credentials_and_settings(self)
        if not extracted:
            base_url = _get_base_url(self.settings)
            if not base_url:
                return self.error_result(
                    MSG_MISSING_BASE_URL, error_type=ERROR_TYPE_CONFIGURATION
                )
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        base_url, username, password, timeout, verify_ssl = extracted
        token = None

        # Build incident fields from individual params and the fields dict
        fields_param = kwargs.get("fields") or {}
        if isinstance(fields_param, str):
            try:
                fields_param = json.loads(fields_param)
            except json.JSONDecodeError as e:
                return self.error_result(
                    f"Invalid JSON in 'fields' parameter: {e}",
                    error_type=ERROR_TYPE_VALIDATION,
                )

        # Map individual params to BMC field names (only if not already in fields)
        param_to_field = {
            "first_name": "First_Name",
            "last_name": "Last_Name",
            "description": "Description",
            "reported_source": "Reported Source",
            "service_type": "Service_Type",
            "status": "Status",
            "urgency": "Urgency",
            "impact": "Impact",
            "status_reason": "Status_Reason",
        }
        for param_name, field_name in param_to_field.items():
            if field_name not in fields_param and kwargs.get(param_name):
                fields_param[field_name] = str(kwargs[param_name])

        try:
            token = await _obtain_jwt_token(
                self,
                base_url,
                username,
                password,
                timeout,
                verify_ssl,
            )

            # Create the incident
            response = await _make_remedy_request(
                self,
                base_url,
                token,
                INCIDENT_CREATE,
                method="POST",
                data={"values": fields_param},
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            # Extract location header to fetch the new incident details
            location = response.headers.get("Location", "")
            if not location:
                return self.error_result(
                    "Incident created but location header missing in response",
                )

            # Extract /api/... path from the location URL
            match = re.findall(r"(?:/api).*", location)
            if not match:
                return self.error_result(
                    "Could not parse incident location from response",
                )

            # Fetch the newly created incident details
            detail_response = await _make_remedy_request(
                self,
                base_url,
                token,
                match[0],
                method="GET",
                timeout=timeout,
                verify_ssl=verify_ssl,
            )
            incident_data = detail_response.json()
            incident_number = incident_data.get("values", {}).get("Incident Number", "")

            return self.success_result(
                data={
                    "incident_number": incident_number,
                    "incident_data": incident_data,
                    "message": f"Created incident {incident_number}",
                }
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)
        finally:
            if token:
                await _logout_jwt_token(self, base_url, token, timeout, verify_ssl)

class GetTicketAction(IntegrationAction):
    """Get incident ticket details by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve incident details and work log entries.

        Args:
            id: Incident Number (e.g., INC000000000001).
        """
        incident_id = kwargs.get("id")
        if not incident_id:
            return self.error_result(
                MSG_MISSING_INCIDENT_ID, error_type=ERROR_TYPE_VALIDATION
            )

        extracted = _extract_credentials_and_settings(self)
        if not extracted:
            base_url = _get_base_url(self.settings)
            if not base_url:
                return self.error_result(
                    MSG_MISSING_BASE_URL, error_type=ERROR_TYPE_CONFIGURATION
                )
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        base_url, username, password, timeout, verify_ssl = extracted
        token = None

        try:
            token = await _obtain_jwt_token(
                self,
                base_url,
                username,
                password,
                timeout,
                verify_ssl,
            )

            params = {"q": f"'Incident Number'=\"{incident_id}\""}

            # Fetch incident details
            response = await _make_remedy_request(
                self,
                base_url,
                token,
                INCIDENT_INTERFACE,
                params=params,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )
            ticket_data = response.json()

            # Fetch work log (comments) for the incident
            try:
                comment_response = await _make_remedy_request(
                    self,
                    base_url,
                    token,
                    WORK_LOG_ENDPOINT,
                    params=params,
                    timeout=timeout,
                    verify_ssl=verify_ssl,
                )
                work_details = comment_response.json()
            except Exception as e:
                logger.warning(
                    "bmcremedy_get_comments_failed",
                    incident_id=incident_id,
                    error=str(e),
                )
                work_details = {}

            ticket_data["work_details"] = work_details
            has_entries = bool(ticket_data.get("entries"))

            if not has_entries:
                return self.success_result(
                    not_found=True,
                    data={
                        "id": incident_id,
                        "ticket_availability": False,
                        "ticket_data": ticket_data,
                    },
                )

            return self.success_result(
                data={
                    "id": incident_id,
                    "ticket_availability": True,
                    "ticket_data": ticket_data,
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"id": incident_id, "ticket_availability": False},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)
        finally:
            if token:
                await _logout_jwt_token(self, base_url, token, timeout, verify_ssl)

class UpdateTicketAction(IntegrationAction):
    """Update an existing incident ticket."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update incident fields.

        Args:
            id: Incident Number.
            fields: Dict of field names and values to update.
        """
        incident_id = kwargs.get("id")
        if not incident_id:
            return self.error_result(
                MSG_MISSING_INCIDENT_ID, error_type=ERROR_TYPE_VALIDATION
            )

        fields_param = kwargs.get("fields") or {}
        if isinstance(fields_param, str):
            try:
                fields_param = json.loads(fields_param)
            except json.JSONDecodeError as e:
                return self.error_result(
                    f"Invalid JSON in 'fields' parameter: {e}",
                    error_type=ERROR_TYPE_VALIDATION,
                )

        if not fields_param:
            return self.error_result(
                "No fields provided to update",
                error_type=ERROR_TYPE_VALIDATION,
            )

        extracted = _extract_credentials_and_settings(self)
        if not extracted:
            base_url = _get_base_url(self.settings)
            if not base_url:
                return self.error_result(
                    MSG_MISSING_BASE_URL, error_type=ERROR_TYPE_CONFIGURATION
                )
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        base_url, username, password, timeout, verify_ssl = extracted
        token = None

        try:
            token = await _obtain_jwt_token(
                self,
                base_url,
                username,
                password,
                timeout,
                verify_ssl,
            )

            # Resolve the incident update URL
            update_url = await _resolve_incident_url(
                self,
                base_url,
                token,
                incident_id,
                timeout,
                verify_ssl,
            )
            if not update_url:
                return self.error_result(
                    MSG_INCIDENT_NOT_FOUND, error_type=ERROR_TYPE_VALIDATION
                )

            # Update the incident
            await _make_remedy_request(
                self,
                base_url,
                token,
                update_url,
                method="PUT",
                data={"values": fields_param},
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            return self.success_result(
                data={
                    "id": incident_id,
                    "message": "Incident updated successfully",
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"id": incident_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)
        finally:
            if token:
                await _logout_jwt_token(self, base_url, token, timeout, verify_ssl)

class ListTicketsAction(IntegrationAction):
    """Search and list incident tickets with optional filters."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List incidents with optional query and pagination.

        Args:
            query: AR System qualification string.
            limit: Maximum number of results.
            offset: Starting index (default 0).
        """
        extracted = _extract_credentials_and_settings(self)
        if not extracted:
            base_url = _get_base_url(self.settings)
            if not base_url:
                return self.error_result(
                    MSG_MISSING_BASE_URL, error_type=ERROR_TYPE_CONFIGURATION
                )
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        base_url, username, password, timeout, verify_ssl = extracted

        query = kwargs.get("query")
        limit = kwargs.get("limit")
        offset = kwargs.get("offset", DEFAULT_OFFSET)

        # Validate integer params
        if limit is not None:
            ok, limit, err = _validate_non_negative_int(limit, "limit")
            if not ok:
                return self.error_result(err, error_type=ERROR_TYPE_VALIDATION)

        ok, offset, err = _validate_non_negative_int(offset, "offset")
        if not ok:
            return self.error_result(err, error_type=ERROR_TYPE_VALIDATION)

        token = None

        try:
            token = await _obtain_jwt_token(
                self,
                base_url,
                username,
                password,
                timeout,
                verify_ssl,
            )

            # Build the list tickets endpoint with field selection
            endpoint = f"{INCIDENT_INTERFACE}?fields=values({LIST_TICKETS_FIELDS})"

            params: dict[str, Any] = {
                "sort": "Last Modified Date.desc",
                "offset": offset,
                "limit": DEFAULT_PAGE_LIMIT,
            }
            if query:
                params["q"] = query

            # Paginate to collect results
            all_entries: list[dict] = []
            while True:
                response = await _make_remedy_request(
                    self,
                    base_url,
                    token,
                    endpoint,
                    params=params,
                    timeout=timeout,
                    verify_ssl=verify_ssl,
                )
                response_data = response.json()
                entries = response_data.get("entries", [])
                all_entries.extend(entries)

                # Check if we have enough results or no more pages
                if limit is not None and len(all_entries) >= limit:
                    all_entries = all_entries[:limit]
                    break

                if len(entries) < DEFAULT_PAGE_LIMIT:
                    break

                if not response_data.get("_links", {}).get("next"):
                    break

                params["offset"] = params["offset"] + DEFAULT_PAGE_LIMIT

            return self.success_result(
                data={
                    "total_tickets": len(all_entries),
                    "tickets": all_entries,
                }
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)
        finally:
            if token:
                await _logout_jwt_token(self, base_url, token, timeout, verify_ssl)

class SetStatusAction(IntegrationAction):
    """Set the status of an incident ticket."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Set incident status with optional assignment fields.

        Args:
            id: Incident Number.
            status: Target status value.
            status_reason: Optional status reason.
            assignee: Optional assignee name.
            assignee_login_id: Optional assignee login ID.
            assigned_group: Optional assigned group.
            assigned_support_company: Optional support company.
            assigned_support_organization: Optional support org.
            resolution: Optional resolution text.
        """
        incident_id = kwargs.get("id")
        if not incident_id:
            return self.error_result(
                MSG_MISSING_INCIDENT_ID, error_type=ERROR_TYPE_VALIDATION
            )

        status = kwargs.get("status")
        if not status:
            return self.error_result(
                MSG_MISSING_STATUS, error_type=ERROR_TYPE_VALIDATION
            )

        extracted = _extract_credentials_and_settings(self)
        if not extracted:
            base_url = _get_base_url(self.settings)
            if not base_url:
                return self.error_result(
                    MSG_MISSING_BASE_URL, error_type=ERROR_TYPE_CONFIGURATION
                )
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        base_url, username, password, timeout, verify_ssl = extracted
        token = None

        try:
            token = await _obtain_jwt_token(
                self,
                base_url,
                username,
                password,
                timeout,
                verify_ssl,
            )

            # Resolve the incident update URL
            update_url = await _resolve_incident_url(
                self,
                base_url,
                token,
                incident_id,
                timeout,
                verify_ssl,
            )
            if not update_url:
                return self.error_result(
                    MSG_INCIDENT_NOT_FOUND, error_type=ERROR_TYPE_VALIDATION
                )

            # Build the status fields
            fields: dict[str, str] = {"Status": status}

            if kwargs.get("status_reason"):
                fields["Status_Reason"] = kwargs["status_reason"]
            if kwargs.get("assignee_login_id"):
                fields["Assignee Login ID"] = kwargs["assignee_login_id"]

            # Map optional params with underscore names to title-case field names
            optional_title_params = [
                "assigned_support_company",
                "assigned_support_organization",
                "assigned_group",
                "assignee",
                "resolution",
            ]
            for param in optional_title_params:
                if kwargs.get(param):
                    field_name = param.replace("_", " ").title()
                    fields[field_name] = kwargs[param]

            await _make_remedy_request(
                self,
                base_url,
                token,
                update_url,
                method="PUT",
                data={"values": fields},
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            return self.success_result(
                data={
                    "id": incident_id,
                    "new_status": status,
                    "message": "Set status successful",
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"id": incident_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)
        finally:
            if token:
                await _logout_jwt_token(self, base_url, token, timeout, verify_ssl)

class AddCommentAction(IntegrationAction):
    """Add a work note/comment to an incident ticket."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add a work log entry to an incident.

        Args:
            id: Incident Number.
            work_info_type: Type of work log entry (e.g., General Information).
            comment: Detailed description / comment text.
            description: Short description for the work log entry.
        """
        incident_id = kwargs.get("id")
        if not incident_id:
            return self.error_result(
                MSG_MISSING_INCIDENT_ID, error_type=ERROR_TYPE_VALIDATION
            )

        work_info_type = kwargs.get("work_info_type")
        if not work_info_type:
            return self.error_result(
                MSG_MISSING_COMMENT_TYPE, error_type=ERROR_TYPE_VALIDATION
            )

        extracted = _extract_credentials_and_settings(self)
        if not extracted:
            base_url = _get_base_url(self.settings)
            if not base_url:
                return self.error_result(
                    MSG_MISSING_BASE_URL, error_type=ERROR_TYPE_CONFIGURATION
                )
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        base_url, username, password, timeout, verify_ssl = extracted
        token = None

        try:
            token = await _obtain_jwt_token(
                self,
                base_url,
                username,
                password,
                timeout,
                verify_ssl,
            )

            # Verify the incident exists
            update_url = await _resolve_incident_url(
                self,
                base_url,
                token,
                incident_id,
                timeout,
                verify_ssl,
            )
            if not update_url:
                return self.error_result(
                    MSG_INCIDENT_NOT_FOUND, error_type=ERROR_TYPE_VALIDATION
                )

            # Build work log entry
            work_log_values: dict[str, str] = {
                "Incident Number": incident_id,
                "Work Log Type": work_info_type,
            }

            # Optional comment fields
            if kwargs.get("comment"):
                work_log_values["Detailed Description"] = kwargs["comment"]
            if kwargs.get("description"):
                work_log_values["Description"] = kwargs["description"]

            await _make_remedy_request(
                self,
                base_url,
                token,
                WORK_LOG_ENDPOINT,
                method="POST",
                data={"values": work_log_values},
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            return self.success_result(
                data={
                    "id": incident_id,
                    "message": "Comment added successfully",
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={"id": incident_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)
        finally:
            if token:
                await _logout_jwt_token(self, base_url, token, timeout, verify_ssl)

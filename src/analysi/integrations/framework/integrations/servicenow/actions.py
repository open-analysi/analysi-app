"""
ServiceNow integration actions.
"""

import json
from typing import Any

import httpx

from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_BASE,
    CREDENTIAL_CLIENT_ID,
    CREDENTIAL_CLIENT_SECRET,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_MAX_RESULTS,
    DEFAULT_TABLE,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_REQUEST,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    MSG_CONNECTION_ERROR,
    MSG_INVALID_RESPONSE,
    MSG_MISSING_AUTH,
    MSG_MISSING_URL,
    SETTINGS_MAX_RESULTS,
    SETTINGS_TIMEOUT,
    SETTINGS_URL,
    STATUS_ERROR,
    STATUS_SUCCESS,
    SYSPARM_LIMIT,
    SYSPARM_QUERY,
    TABLE_ENDPOINT,
    TABLE_SYS_USER,
    TICKET_ENDPOINT,
)


class HealthCheckAction(IntegrationAction):
    """Test connectivity to ServiceNow instance"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity to ServiceNow instance

        Returns:
            Result with status and data or error
        """
        # Retrieve credentials
        url = self.settings.get(SETTINGS_URL)
        if not url:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_URL,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        # Validate auth credentials
        has_basic_auth = username and password
        has_oauth = client_id and client_secret

        if not has_basic_auth and not has_oauth:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Normalize URL
            base_url = url.rstrip("/")
            if not base_url.startswith("http"):
                base_url = f"https://{base_url}"

            # Test endpoint - query incidents table with limit 1
            endpoint = f"{base_url}{API_BASE}{TABLE_ENDPOINT.format(table='incident')}"
            params = {SYSPARM_LIMIT: 1}

            # Use basic auth if available, otherwise OAuth would be needed
            auth = (username, password) if has_basic_auth else None

            response = await self.http_request(
                endpoint, params=params, auth=auth, timeout=timeout
            )

            data = response.json()

            if not isinstance(data, dict):
                return {
                    "healthy": False,
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_RESPONSE,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Successfully connected to ServiceNow instance",
                "data": {
                    "healthy": True,
                    "instance_url": base_url,
                    "auth_type": "basic_auth" if has_basic_auth else "oauth",
                },
            }

        except httpx.HTTPStatusError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"HTTP error occurred: {e.response.status_code} - {e!s}",
                "error_type": ERROR_TYPE_HTTP,
            }
        except httpx.RequestError as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_CONNECTION_ERROR.format(error=str(e)),
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class CreateTicketAction(IntegrationAction):
    """Create a ticket in ServiceNow"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create a ticket in ServiceNow

        Args:
            **kwargs: Must contain:
                - table (string): Table to create ticket in (default: incident)
                - short_description (string): Short description of the ticket
                - description (string): Detailed description
                - fields (string): JSON string of additional fields

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        table = kwargs.get("table", DEFAULT_TABLE)
        short_description = kwargs.get("short_description")
        description = kwargs.get("description")
        fields = kwargs.get("fields")

        # Validate required parameters
        if not short_description and not description and not fields:
            return {
                "status": STATUS_ERROR,
                "error": "Please specify at least one of: short_description, description, or fields",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Normalize URL
            base_url = url.rstrip("/")
            if not base_url.startswith("http"):
                base_url = f"https://{base_url}"

            # Build request body
            body = {}
            if short_description:
                body["short_description"] = short_description
            if description:
                body["description"] = description

            # Parse additional fields if provided
            if fields:
                try:
                    additional_fields = (
                        json.loads(fields) if isinstance(fields, str) else fields
                    )
                    if isinstance(additional_fields, dict):
                        body.update(additional_fields)
                except (json.JSONDecodeError, TypeError):
                    return {
                        "status": STATUS_ERROR,
                        "error": "Unable to parse the fields parameter into a dictionary",
                        "error_type": ERROR_TYPE_VALIDATION,
                    }

            # Create ticket
            endpoint = f"{base_url}{API_BASE}{TABLE_ENDPOINT.format(table=table)}"

            response = await self.http_request(
                endpoint,
                method="POST",
                json_data=body,
                auth=(username, password),
                timeout=timeout,
            )

            data = response.json()

            if not isinstance(data, dict):
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_RESPONSE,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            result = data.get("result", {})
            return {
                "status": STATUS_SUCCESS,
                "message": "Ticket created successfully",
                "data": {
                    "ticket_id": result.get("number"),
                    "sys_id": result.get("sys_id"),
                    "table": table,
                    "full_result": result,
                },
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP error occurred: {e.response.status_code} - {e!s}",
                "error_type": ERROR_TYPE_HTTP,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": MSG_CONNECTION_ERROR.format(error=str(e)),
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class GetTicketAction(IntegrationAction):
    """Get a ticket from ServiceNow"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get a ticket from ServiceNow

        Args:
            **kwargs: Must contain:
                - id (string): Ticket ID or sys_id
                - table (string): Table to query (default: incident)
                - is_sys_id (boolean): Whether ID is a sys_id

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        ticket_id = kwargs.get("id")
        table = kwargs.get("table", DEFAULT_TABLE)
        is_sys_id = kwargs.get("is_sys_id", False)

        # Validate required parameters
        if not ticket_id:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter: id",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Normalize URL
            base_url = url.rstrip("/")
            if not base_url.startswith("http"):
                base_url = f"https://{base_url}"

            # Build endpoint based on whether we have sys_id
            if is_sys_id:
                endpoint = f"{base_url}{API_BASE}{TICKET_ENDPOINT.format(table=table, id=ticket_id)}"
                params = {}
            else:
                # Query by ticket number
                endpoint = f"{base_url}{API_BASE}{TABLE_ENDPOINT.format(table=table)}"
                params = {SYSPARM_QUERY: f"number={ticket_id}"}

            response = await self.http_request(
                endpoint,
                params=params,
                auth=(username, password),
                timeout=timeout,
            )

            data = response.json()

            if not isinstance(data, dict):
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_RESPONSE,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            # Handle response based on query type
            if is_sys_id:
                result = data.get("result", {})
            else:
                results = data.get("result", [])
                if not results:
                    return {
                        "status": STATUS_ERROR,
                        "error": f"Ticket not found: {ticket_id}",
                        "error_type": ERROR_TYPE_VALIDATION,
                    }
                result = results[0]

            return {
                "status": STATUS_SUCCESS,
                "data": {
                    "ticket_id": result.get("number"),
                    "sys_id": result.get("sys_id"),
                    "table": table,
                    "state": result.get("state"),
                    "short_description": result.get("short_description"),
                    "description": result.get("description"),
                    "full_result": result,
                },
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP error occurred: {e.response.status_code} - {e!s}",
                "error_type": ERROR_TYPE_HTTP,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": MSG_CONNECTION_ERROR.format(error=str(e)),
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class UpdateTicketAction(IntegrationAction):
    """Update a ticket in ServiceNow"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update a ticket in ServiceNow

        Args:
            **kwargs: Must contain:
                - id (string): Ticket ID or sys_id
                - table (string): Table name (default: incident)
                - is_sys_id (boolean): Whether ID is a sys_id
                - fields (string): JSON string of fields to update

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        ticket_id = kwargs.get("id")
        table = kwargs.get("table", DEFAULT_TABLE)
        is_sys_id = kwargs.get("is_sys_id", False)
        fields = kwargs.get("fields")

        # Validate required parameters
        if not ticket_id:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter: id",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not fields:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter: fields",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Parse fields
            try:
                update_fields = (
                    json.loads(fields) if isinstance(fields, str) else fields
                )
                if not isinstance(update_fields, dict):
                    raise ValueError("Fields must be a dictionary")
            except (json.JSONDecodeError, TypeError, ValueError):
                return {
                    "status": STATUS_ERROR,
                    "error": "Unable to parse the fields parameter into a dictionary",
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            # Normalize URL
            base_url = url.rstrip("/")
            if not base_url.startswith("http"):
                base_url = f"https://{base_url}"

            # Get sys_id if not provided
            if not is_sys_id:
                # Query to get sys_id from ticket number
                endpoint_query = (
                    f"{base_url}{API_BASE}{TABLE_ENDPOINT.format(table=table)}"
                )
                params = {SYSPARM_QUERY: f"number={ticket_id}", SYSPARM_LIMIT: 1}

                response = await self.http_request(
                    endpoint_query,
                    params=params,
                    auth=(username, password),
                    timeout=timeout,
                )
                data = response.json()
                results = data.get("result", [])
                if not results:
                    return {
                        "status": STATUS_ERROR,
                        "error": f"Ticket not found: {ticket_id}",
                        "error_type": ERROR_TYPE_VALIDATION,
                    }
                sys_id = results[0].get("sys_id")
            else:
                sys_id = ticket_id

            # Update ticket
            endpoint = (
                f"{base_url}{API_BASE}{TICKET_ENDPOINT.format(table=table, id=sys_id)}"
            )

            response = await self.http_request(
                endpoint,
                method="PATCH",
                json_data=update_fields,
                auth=(username, password),
                timeout=timeout,
            )

            data = response.json()

            if not isinstance(data, dict):
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_RESPONSE,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            result = data.get("result", {})
            return {
                "status": STATUS_SUCCESS,
                "message": "Ticket updated successfully",
                "data": {
                    "ticket_id": result.get("number"),
                    "sys_id": result.get("sys_id"),
                    "table": table,
                    "full_result": result,
                },
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP error occurred: {e.response.status_code} - {e!s}",
                "error_type": ERROR_TYPE_HTTP,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": MSG_CONNECTION_ERROR.format(error=str(e)),
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class ListTicketsAction(IntegrationAction):
    """List tickets from ServiceNow"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List tickets from ServiceNow

        Args:
            **kwargs: May contain:
                - table (string): Table to query (default: incident)
                - query (string): ServiceNow query string
                - max_results (integer): Maximum number of results

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        table = kwargs.get("table", DEFAULT_TABLE)
        query = kwargs.get("query")
        max_results = kwargs.get("max_results")

        # Retrieve credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        default_max = self.settings.get(SETTINGS_MAX_RESULTS, DEFAULT_MAX_RESULTS)

        try:
            # Parse max_results
            try:
                limit = int(max_results) if max_results is not None else default_max
                if limit <= 0:
                    limit = default_max
            except (ValueError, TypeError):
                limit = default_max

            # Normalize URL
            base_url = url.rstrip("/")
            if not base_url.startswith("http"):
                base_url = f"https://{base_url}"

            # Build endpoint
            endpoint = f"{base_url}{API_BASE}{TABLE_ENDPOINT.format(table=table)}"
            params = {SYSPARM_LIMIT: limit}

            if query:
                params[SYSPARM_QUERY] = query

            response = await self.http_request(
                endpoint,
                params=params,
                auth=(username, password),
                timeout=timeout,
            )

            data = response.json()

            if not isinstance(data, dict):
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_RESPONSE,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            results = data.get("result", [])

            return {
                "status": STATUS_SUCCESS,
                "data": {
                    "total_tickets": len(results),
                    "table": table,
                    "tickets": results,
                },
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP error occurred: {e.response.status_code} - {e!s}",
                "error_type": ERROR_TYPE_HTTP,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": MSG_CONNECTION_ERROR.format(error=str(e)),
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class AddCommentAction(IntegrationAction):
    """Add a comment to a ServiceNow ticket"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add a comment to a ServiceNow ticket

        Args:
            **kwargs: Must contain:
                - id (string): Ticket ID or sys_id
                - table (string): Table name (default: incident)
                - is_sys_id (boolean): Whether ID is a sys_id
                - comment (string): Comment text to add

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        ticket_id = kwargs.get("id")
        table = kwargs.get("table", DEFAULT_TABLE)
        is_sys_id = kwargs.get("is_sys_id", False)
        comment = kwargs.get("comment")

        # Validate required parameters
        if not ticket_id:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter: id",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not comment:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter: comment",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Retrieve credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Normalize URL
            base_url = url.rstrip("/")
            if not base_url.startswith("http"):
                base_url = f"https://{base_url}"

            # Get sys_id if not provided
            if not is_sys_id:
                endpoint_query = (
                    f"{base_url}{API_BASE}{TABLE_ENDPOINT.format(table=table)}"
                )
                params = {SYSPARM_QUERY: f"number={ticket_id}", SYSPARM_LIMIT: 1}

                response = await self.http_request(
                    endpoint_query,
                    params=params,
                    auth=(username, password),
                    timeout=timeout,
                )
                data = response.json()
                results = data.get("result", [])
                if not results:
                    return {
                        "status": STATUS_ERROR,
                        "error": f"Ticket not found: {ticket_id}",
                        "error_type": ERROR_TYPE_VALIDATION,
                    }
                sys_id = results[0].get("sys_id")
            else:
                sys_id = ticket_id

            # Add comment to ticket
            endpoint = (
                f"{base_url}{API_BASE}{TICKET_ENDPOINT.format(table=table, id=sys_id)}"
            )
            body = {"comments": comment}

            response = await self.http_request(
                endpoint,
                method="PATCH",
                json_data=body,
                auth=(username, password),
                timeout=timeout,
            )

            data = response.json()

            if not isinstance(data, dict):
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_RESPONSE,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            result = data.get("result", {})
            return {
                "status": STATUS_SUCCESS,
                "message": "Comment added successfully",
                "data": {
                    "ticket_id": result.get("number"),
                    "sys_id": result.get("sys_id"),
                    "table": table,
                },
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP error occurred: {e.response.status_code} - {e!s}",
                "error_type": ERROR_TYPE_HTTP,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": MSG_CONNECTION_ERROR.format(error=str(e)),
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

class QueryUsersAction(IntegrationAction):
    """Query users in ServiceNow"""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Query users in ServiceNow

        Args:
            **kwargs: May contain:
                - query (string): Query string to filter users
                - max_results (integer): Maximum number of results

        Returns:
            Result with status and data or error
        """
        # Extract parameters
        query = kwargs.get("query")
        max_results = kwargs.get("max_results")

        # Retrieve credentials
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Retrieve settings
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        default_max = self.settings.get(SETTINGS_MAX_RESULTS, DEFAULT_MAX_RESULTS)

        try:
            # Parse max_results
            try:
                limit = int(max_results) if max_results is not None else default_max
                if limit <= 0:
                    limit = default_max
            except (ValueError, TypeError):
                limit = default_max

            # Normalize URL
            base_url = url.rstrip("/")
            if not base_url.startswith("http"):
                base_url = f"https://{base_url}"

            # Build endpoint
            endpoint = (
                f"{base_url}{API_BASE}{TABLE_ENDPOINT.format(table=TABLE_SYS_USER)}"
            )
            params = {SYSPARM_LIMIT: limit}

            if query:
                params[SYSPARM_QUERY] = query

            response = await self.http_request(
                endpoint,
                params=params,
                auth=(username, password),
                timeout=timeout,
            )

            data = response.json()

            if not isinstance(data, dict):
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_INVALID_RESPONSE,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            results = data.get("result", [])

            return {
                "status": STATUS_SUCCESS,
                "data": {
                    "total_users": len(results),
                    "users": results,
                },
            }

        except httpx.HTTPStatusError as e:
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP error occurred: {e.response.status_code} - {e!s}",
                "error_type": ERROR_TYPE_HTTP,
            }
        except httpx.RequestError as e:
            return {
                "status": STATUS_ERROR,
                "error": MSG_CONNECTION_ERROR.format(error=str(e)),
                "error_type": ERROR_TYPE_REQUEST,
            }
        except httpx.TimeoutException as e:
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out: {e!s}",
                "error_type": ERROR_TYPE_TIMEOUT,
            }

"""JIRA integration actions for ticket management."""

from typing import Any
from urllib.parse import urljoin

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_ISSUE,
    API_MYSELF,
    API_PROJECT,
    API_SEARCH,
    API_SERVER_INFO,
    API_USER_SEARCH,
    DEFAULT_MAX_RESULTS,
    DEFAULT_START_INDEX,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MSG_MISSING_AUTH,
    MSG_MISSING_COMMENT,
    MSG_MISSING_ISSUE_TYPE,
    MSG_MISSING_PROJECT_KEY,
    MSG_MISSING_STATUS,
    MSG_MISSING_SUMMARY,
    MSG_MISSING_TICKET_ID,
    MSG_MISSING_URL,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_jira_url(base_url: str, endpoint: str) -> str:
    """Construct JIRA API URL.

    Args:
        base_url: JIRA base URL
        endpoint: API endpoint

    Returns:
        Full API URL
    """
    # Ensure base_url ends with /
    if not base_url.endswith("/"):
        base_url = base_url + "/"
    return urljoin(base_url, endpoint)

async def _make_jira_request(
    action: IntegrationAction,
    base_url: str,
    endpoint: str,
    username: str,
    password: str,
    method: str = "GET",
    data: dict | None = None,
    params: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Make HTTP request to JIRA API.

    Uses ``action.http_request()`` for automatic retry via ``integration_retry_policy``.

    Args:
        action: The IntegrationAction instance (provides http_request with retry).
        base_url: JIRA base URL
        endpoint: API endpoint
        username: JIRA username
        password: JIRA password/API token
        method: HTTP method
        data: Request body data
        params: Query parameters
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates

    Returns:
        API response data

    Raises:
        Exception: On API errors
    """
    url = _get_jira_url(base_url, endpoint)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = await action.http_request(
            url,
            method=method,
            headers=headers,
            auth=(username, password),
            json_data=data,
            params=params,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        # Some DELETE requests return empty responses
        if response.status_code == 204 or not response.content:
            return {}

        return response.json()

    except httpx.TimeoutException as e:
        logger.error("jira_api_timeout_for", endpoint=endpoint, error=str(e))
        raise Exception(f"Request timed out after {timeout} seconds")
    except httpx.HTTPStatusError as e:
        logger.error(
            "jira_api_http_error_for",
            endpoint=endpoint,
            status_code=e.response.status_code,
        )
        if e.response.status_code == 401:
            raise Exception("Authentication failed - invalid credentials")
        if e.response.status_code == 403:
            raise Exception("Access forbidden - insufficient permissions")
        if e.response.status_code == 404:
            raise Exception("Resource not found")
        if e.response.status_code == 400:
            # Try to extract error message from response
            try:
                error_data = e.response.json()
                error_messages = error_data.get("errorMessages", [])
                errors = error_data.get("errors", {})
                if error_messages:
                    raise Exception(f"Bad request: {'; '.join(error_messages)}")
                if errors:
                    raise Exception(f"Bad request: {errors}")
            except Exception:
                pass
            raise Exception(f"Bad request: {e.response.text}")
        raise Exception(f"HTTP {e.response.status_code}: {e.response.text}")
    except Exception as e:
        logger.error("jira_api_error_for", endpoint=endpoint, error=str(e))
        raise

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for JIRA API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check JIRA API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        url = self.settings.get("url")
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        verify_ssl = self.settings.get("verify_ssl", True)

        if not url:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_URL,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        if not username or not password:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            # Get current user info as health check
            result = await _make_jira_request(
                self,
                url,
                API_MYSELF,
                username,
                password,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            # Also get server info
            server_info = await _make_jira_request(
                self,
                url,
                API_SERVER_INFO,
                username,
                password,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "JIRA API is accessible",
                "data": {
                    "healthy": True,
                    "user": result.get("displayName"),
                    "server_version": server_info.get("version"),
                    "server_title": server_info.get("serverTitle"),
                },
            }

        except Exception as e:
            logger.error("jira_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class CreateTicketAction(IntegrationAction):
    """Create a new JIRA ticket (issue)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create a new JIRA ticket.

        Args:
            **kwargs: Must contain 'summary', 'project_key', 'issue_type'
                     Optional: 'description', 'priority', 'assignee', 'labels', 'fields'

        Returns:
            Result with created ticket information or error
        """
        # Validate required parameters
        summary = kwargs.get("summary")
        if not summary:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_SUMMARY,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        project_key = kwargs.get("project_key")
        if not project_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PROJECT_KEY,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        issue_type = kwargs.get("issue_type")
        if not issue_type:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ISSUE_TYPE,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Get credentials
        url = self.settings.get("url")
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        verify_ssl = self.settings.get("verify_ssl", True)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        # Build issue fields
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }

        # Add optional fields
        if kwargs.get("description"):
            fields["description"] = kwargs["description"]

        if kwargs.get("priority"):
            fields["priority"] = {"name": kwargs["priority"]}

        if kwargs.get("assignee"):
            fields["assignee"] = {"name": kwargs["assignee"]}

        if kwargs.get("labels"):
            labels = kwargs["labels"]
            if isinstance(labels, str):
                labels = [label.strip() for label in labels.split(",")]
            fields["labels"] = labels

        # Add custom fields if provided
        if kwargs.get("fields"):
            custom_fields = kwargs["fields"]
            if isinstance(custom_fields, dict):
                fields.update(custom_fields)

        issue_data = {"fields": fields}

        try:
            result = await _make_jira_request(
                self,
                url,
                API_ISSUE,
                username,
                password,
                method="POST",
                data=issue_data,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            return {
                "status": STATUS_SUCCESS,
                "ticket_id": result.get("id"),
                "ticket_key": result.get("key"),
                "ticket_url": result.get("self"),
                "message": f"Created ticket {result.get('key')}",
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("jira_create_ticket_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                }
            logger.error("jira_create_ticket_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetTicketAction(IntegrationAction):
    """Get JIRA ticket (issue) information."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get ticket information.

        Args:
            **kwargs: Must contain 'ticket_id' (issue key or ID)

        Returns:
            Result with ticket information or error
        """
        ticket_id = kwargs.get("ticket_id") or kwargs.get("id")
        if not ticket_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_TICKET_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get("url")
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        verify_ssl = self.settings.get("verify_ssl", True)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            endpoint = f"{API_ISSUE}/{ticket_id}"
            result = await _make_jira_request(
                self,
                url,
                endpoint,
                username,
                password,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            fields = result.get("fields", {})

            return {
                "status": STATUS_SUCCESS,
                "ticket_id": result.get("id"),
                "ticket_key": result.get("key"),
                "summary": fields.get("summary"),
                "description": fields.get("description"),
                "ticket_status": fields.get("status", {}).get("name"),
                "priority": fields.get("priority", {}).get("name")
                if fields.get("priority")
                else None,
                "assignee": fields.get("assignee", {}).get("displayName")
                if fields.get("assignee")
                else None,
                "reporter": fields.get("reporter", {}).get("displayName")
                if fields.get("reporter")
                else None,
                "created": fields.get("created"),
                "updated": fields.get("updated"),
                "labels": fields.get("labels", []),
                "full_data": result,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("jira_ticket_not_found", ticket_id=ticket_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ticket_id": ticket_id,
                }
            logger.error(
                "jira_get_ticket_failed_for", ticket_id=ticket_id, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class UpdateTicketAction(IntegrationAction):
    """Update a JIRA ticket (issue)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update a JIRA ticket.

        Args:
            **kwargs: Must contain 'ticket_id'
                     Optional: 'summary', 'description', 'priority', 'assignee', 'labels', 'fields'

        Returns:
            Result with success message or error
        """
        ticket_id = kwargs.get("ticket_id") or kwargs.get("id")
        if not ticket_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_TICKET_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get("url")
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        verify_ssl = self.settings.get("verify_ssl", True)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        # Build update fields
        fields = {}

        if kwargs.get("summary"):
            fields["summary"] = kwargs["summary"]

        if kwargs.get("description"):
            fields["description"] = kwargs["description"]

        if kwargs.get("priority"):
            fields["priority"] = {"name": kwargs["priority"]}

        if kwargs.get("assignee"):
            fields["assignee"] = {"name": kwargs["assignee"]}

        if kwargs.get("labels"):
            labels = kwargs["labels"]
            if isinstance(labels, str):
                labels = [label.strip() for label in labels.split(",")]
            fields["labels"] = labels

        # Add custom fields if provided
        if kwargs.get("fields"):
            custom_fields = kwargs["fields"]
            if isinstance(custom_fields, dict):
                fields.update(custom_fields)

        if not fields:
            return {
                "status": STATUS_ERROR,
                "error": "No fields provided to update",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        update_data = {"fields": fields}

        try:
            endpoint = f"{API_ISSUE}/{ticket_id}"
            await _make_jira_request(
                self,
                url,
                endpoint,
                username,
                password,
                method="PUT",
                data=update_data,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            return {
                "status": STATUS_SUCCESS,
                "ticket_id": ticket_id,
                "message": f"Successfully updated ticket {ticket_id}",
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("jira_ticket_not_found", ticket_id=ticket_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ticket_id": ticket_id,
                }
            logger.error(
                "jira_update_ticket_failed_for", ticket_id=ticket_id, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class AddCommentAction(IntegrationAction):
    """Add a comment to a JIRA ticket."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add comment to a ticket.

        Args:
            **kwargs: Must contain 'ticket_id' and 'comment'

        Returns:
            Result with success message or error
        """
        ticket_id = kwargs.get("ticket_id") or kwargs.get("id")
        if not ticket_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_TICKET_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        comment = kwargs.get("comment") or kwargs.get("body")
        if not comment:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_COMMENT,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get("url")
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        verify_ssl = self.settings.get("verify_ssl", True)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        comment_data = {"body": comment}

        try:
            endpoint = f"{API_ISSUE}/{ticket_id}/comment"
            result = await _make_jira_request(
                self,
                url,
                endpoint,
                username,
                password,
                method="POST",
                data=comment_data,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            return {
                "status": STATUS_SUCCESS,
                "ticket_id": ticket_id,
                "comment_id": result.get("id"),
                "message": f"Successfully added comment to ticket {ticket_id}",
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("jira_ticket_not_found", ticket_id=ticket_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ticket_id": ticket_id,
                }
            logger.error(
                "jira_add_comment_failed_for", ticket_id=ticket_id, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class SetTicketStatusAction(IntegrationAction):
    """Set the status of a JIRA ticket."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Set ticket status via transition.

        Args:
            **kwargs: Must contain 'ticket_id' and 'status'
                     Optional: 'comment' to add with transition

        Returns:
            Result with success message or error
        """
        ticket_id = kwargs.get("ticket_id") or kwargs.get("id")
        if not ticket_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_TICKET_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        status = kwargs.get("status")
        if not status:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_STATUS,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get("url")
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        verify_ssl = self.settings.get("verify_ssl", True)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            # First, get available transitions
            endpoint = f"{API_ISSUE}/{ticket_id}/transitions"
            transitions_result = await _make_jira_request(
                self,
                url,
                endpoint,
                username,
                password,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            # Find the transition matching the desired status
            transitions = transitions_result.get("transitions", [])
            matching_transition = None
            for transition in transitions:
                if transition.get("to", {}).get("name", "").lower() == status.lower():
                    matching_transition = transition
                    break

            if not matching_transition:
                # Try matching by transition name instead
                for transition in transitions:
                    if transition.get("name", "").lower() == status.lower():
                        matching_transition = transition
                        break

            if not matching_transition:
                available = [t.get("to", {}).get("name") for t in transitions]
                return {
                    "status": STATUS_ERROR,
                    "error": f"Status '{status}' not found. Available transitions: {', '.join(available)}",
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            # Perform the transition
            transition_data = {"transition": {"id": matching_transition["id"]}}

            # Add comment if provided
            if kwargs.get("comment"):
                transition_data["update"] = {
                    "comment": [{"add": {"body": kwargs["comment"]}}]
                }

            await _make_jira_request(
                self,
                url,
                endpoint,
                username,
                password,
                method="POST",
                data=transition_data,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            return {
                "status": STATUS_SUCCESS,
                "ticket_id": ticket_id,
                "new_status": status,
                "message": f"Successfully set ticket {ticket_id} status to {status}",
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("jira_ticket_not_found", ticket_id=ticket_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ticket_id": ticket_id,
                }
            logger.error(
                "jira_set_status_failed_for", ticket_id=ticket_id, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class DeleteTicketAction(IntegrationAction):
    """Delete a JIRA ticket (issue)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Delete a JIRA ticket.

        Args:
            **kwargs: Must contain 'ticket_id'

        Returns:
            Result with success message or error
        """
        ticket_id = kwargs.get("ticket_id") or kwargs.get("id")
        if not ticket_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_TICKET_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get("url")
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        verify_ssl = self.settings.get("verify_ssl", True)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            endpoint = f"{API_ISSUE}/{ticket_id}"
            await _make_jira_request(
                self,
                url,
                endpoint,
                username,
                password,
                method="DELETE",
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            return {
                "status": STATUS_SUCCESS,
                "ticket_id": ticket_id,
                "message": f"Successfully deleted ticket {ticket_id}",
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("jira_ticket_not_found", ticket_id=ticket_id)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ticket_id": ticket_id,
                }
            logger.error(
                "jira_delete_ticket_failed_for", ticket_id=ticket_id, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ListProjectsAction(IntegrationAction):
    """List all JIRA projects."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all accessible JIRA projects.

        Returns:
            Result with list of projects or error
        """
        url = self.settings.get("url")
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        verify_ssl = self.settings.get("verify_ssl", True)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            result = await _make_jira_request(
                self,
                url,
                API_PROJECT,
                username,
                password,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            projects = []
            for project in result:
                projects.append(
                    {
                        "id": project.get("id"),
                        "key": project.get("key"),
                        "name": project.get("name"),
                        "project_type": project.get("projectTypeKey"),
                    }
                )

            return {
                "status": STATUS_SUCCESS,
                "total_projects": len(projects),
                "projects": projects,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("jira_projects_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "total_projects": 0,
                    "projects": [],
                }
            logger.error("jira_list_projects_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ListTicketsAction(IntegrationAction):
    """List JIRA tickets (issues) in a project."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List tickets in a project.

        Args:
            **kwargs: Optional: 'project_key', 'max_results', 'start_index', 'jql'

        Returns:
            Result with list of tickets or error
        """
        url = self.settings.get("url")
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        verify_ssl = self.settings.get("verify_ssl", True)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        # Build JQL query
        jql = kwargs.get("jql", "")
        if not jql and kwargs.get("project_key"):
            jql = f"project = {kwargs['project_key']}"
        elif not jql:
            jql = "ORDER BY created DESC"

        max_results = kwargs.get("max_results", DEFAULT_MAX_RESULTS)
        start_at = kwargs.get("start_index", DEFAULT_START_INDEX)

        params = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
        }

        try:
            result = await _make_jira_request(
                self,
                url,
                API_SEARCH,
                username,
                password,
                params=params,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            issues = []
            for issue in result.get("issues", []):
                fields = issue.get("fields", {})
                issues.append(
                    {
                        "id": issue.get("id"),
                        "key": issue.get("key"),
                        "summary": fields.get("summary"),
                        "status": fields.get("status", {}).get("name"),
                        "priority": fields.get("priority", {}).get("name")
                        if fields.get("priority")
                        else None,
                        "assignee": fields.get("assignee", {}).get("displayName")
                        if fields.get("assignee")
                        else None,
                        "created": fields.get("created"),
                        "updated": fields.get("updated"),
                    }
                )

            return {
                "status": STATUS_SUCCESS,
                "total_issues": result.get("total"),
                "start_at": result.get("startAt"),
                "max_results": result.get("maxResults"),
                "issues": issues,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("jira_tickets_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "total_issues": 0,
                    "issues": [],
                }
            logger.error("jira_list_tickets_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class SearchUsersAction(IntegrationAction):
    """Search for JIRA users."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search for users.

        Args:
            **kwargs: Must contain 'query' (username or display name)

        Returns:
            Result with list of users or error
        """
        query = (
            kwargs.get("query") or kwargs.get("username") or kwargs.get("display_name")
        )
        if not query:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'query'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        url = self.settings.get("url")
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        verify_ssl = self.settings.get("verify_ssl", True)

        if not url or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_AUTH,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        params = {"query": query}
        max_results = kwargs.get("max_results")
        if max_results:
            params["maxResults"] = max_results

        try:
            result = await _make_jira_request(
                self,
                url,
                API_USER_SEARCH,
                username,
                password,
                params=params,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            users = []
            for user in result:
                users.append(
                    {
                        "account_id": user.get("accountId"),
                        "name": user.get("name"),
                        "display_name": user.get("displayName"),
                        "email": user.get("emailAddress"),
                        "active": user.get("active"),
                    }
                )

            return {
                "status": STATUS_SUCCESS,
                "total_users": len(users),
                "users": users,
            }

        except Exception as e:
            if "Resource not found" in str(e):
                logger.info("jira_users_not_found")
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "total_users": 0,
                    "users": [],
                }
            logger.error("jira_search_users_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

"""
Wiz cloud security (CNAPP) integration actions.

Uses Wiz GraphQL API with OAuth2 client credentials flow for authentication.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.wiz.constants import (
    CREDENTIAL_CLIENT_ID,
    CREDENTIAL_CLIENT_SECRET,
    DEFAULT_API_URL,
    DEFAULT_AUTH_URL,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    GET_CONFIGURATION_FINDING_QUERY,
    GET_ISSUE_QUERY,
    GET_RESOURCE_QUERY,
    HEALTH_CHECK_QUERY,
    LIST_ISSUES_QUERY,
    LIST_PROJECTS_QUERY,
    LIST_VULNERABILITIES_QUERY,
    MAX_PAGE_SIZE,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_PARAMETER,
    OAUTH_AUDIENCE,
    OAUTH_GRANT_TYPE,
    SEARCH_RESOURCES_QUERY,
    SETTINGS_API_URL,
    SETTINGS_AUTH_URL,
    SETTINGS_TIMEOUT,
)

logger = get_logger(__name__)

class WizNotFoundError(Exception):
    """Raised when Wiz API indicates a resource was not found.

    This covers both HTTP 404 responses and GraphQL-level errors that
    indicate a missing resource (e.g., "Resource not found" in the errors array).
    """

# GraphQL error patterns that indicate a resource was not found.
# These are distinct from schema errors like "Field 'x' not found".
_NOT_FOUND_EXTENSIONS_CODES = {"NOT_FOUND", "RESOURCE_NOT_FOUND"}
_NOT_FOUND_MESSAGE_PREFIXES = (
    "could not find ",
    "resource not found",
    "issue not found",
    "entity not found",
    "finding not found",
)

def _is_graphql_not_found(errors: list[dict]) -> bool:
    """Check if GraphQL errors indicate a resource-not-found condition.

    Uses two signals:
    1. extensions.code contains a known not-found code (e.g., NOT_FOUND)
    2. Error message starts with a known resource-not-found prefix

    This avoids false positives on schema errors like "Field 'x' not found".
    """
    for err in errors:
        # Check extensions.code first (most reliable)
        ext_code = err.get("extensions", {}).get("code", "")
        if ext_code in _NOT_FOUND_EXTENSIONS_CODES:
            return True
        # Check message as fallback
        msg = err.get("message", "").lower().strip()
        if msg.startswith(_NOT_FOUND_MESSAGE_PREFIXES):
            return True
    return False

class WizOAuth2Mixin:
    """Mixin to handle OAuth2 token management for Wiz API."""

    async def _get_access_token(self) -> str:
        """Acquire a fresh OAuth2 access token.

        Uses client_credentials grant type with the Wiz auth endpoint.
        Always calls the OAuth2 endpoint (no caching) to avoid any risk
        of cross-tenant token leakage via class-level state.

        Returns:
            Access token string

        Raises:
            ValueError: If credentials are missing or token response is invalid
        """
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not client_id or not client_secret:
            raise ValueError(MSG_MISSING_CREDENTIALS)

        auth_url = self.settings.get(SETTINGS_AUTH_URL, DEFAULT_AUTH_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        response = await self.http_request(
            auth_url,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={
                "grant_type": OAUTH_GRANT_TYPE,
                "client_id": client_id,
                "client_secret": client_secret,
                "audience": OAUTH_AUDIENCE,
            },
            timeout=timeout,
        )
        token_data = response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            raise ValueError("No access token in authentication response")

        return access_token

    async def _graphql_request(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Execute a GraphQL request against the Wiz API.

        Handles OAuth2 token management and automatic retry on 401.

        Args:
            query: GraphQL query string
            variables: GraphQL variables
            retry_auth: Whether to retry with fresh token on 401

        Returns:
            The 'data' portion of the GraphQL response

        Raises:
            WizNotFoundError: On HTTP 404 or GraphQL "not found" errors
            httpx.HTTPStatusError: On non-retryable HTTP errors (except 404)
            ValueError: On GraphQL-level errors (except not-found patterns)
        """
        api_url = self.settings.get(SETTINGS_API_URL, DEFAULT_API_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = await self.http_request(
                api_url,
                method="POST",
                json_data=payload,
                headers=headers,
                timeout=timeout,
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401 and retry_auth:
                return await self._graphql_request(query, variables, retry_auth=False)
            if e.response.status_code == 404:
                raise WizNotFoundError("Wiz API returned 404 for request") from e
            raise

        result = response.json()

        # Check for GraphQL-level errors
        if result.get("errors"):
            errors = result["errors"]
            error_messages = "; ".join(
                err.get("message", "Unknown error") for err in errors
            )
            # Detect not-found GraphQL errors before raising generic ValueError.
            # Wiz returns NOT_FOUND in extensions.code, or resource-specific
            # messages like "Issue not found" / "Could not find resource".
            if _is_graphql_not_found(errors):
                raise WizNotFoundError(f"GraphQL not found: {error_messages}")
            raise ValueError(f"GraphQL errors: {error_messages}")

        return result.get("data", {})

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction, WizOAuth2Mixin):
    """Check connectivity to Wiz API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute health check by authenticating and running a minimal query.

        Returns:
            Health check result with connectivity status
        """
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)

        if not client_id or not client_secret:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
                healthy=False,
            )

        try:
            data = await self._graphql_request(HEALTH_CHECK_QUERY)

            return self.success_result(
                data={
                    "healthy": True,
                    "api_url": self.settings.get(SETTINGS_API_URL, DEFAULT_API_URL),
                    "issues_total_count": data.get("issues", {}).get("totalCount", 0),
                },
                healthy=True,
            )
        except ValueError as e:
            logger.error("wiz_health_check_auth_failed", error=str(e))
            return self.error_result(
                e, error_type=ERROR_TYPE_AUTHENTICATION, healthy=False
            )
        except Exception as e:
            logger.error("wiz_health_check_failed", error=str(e))
            return self.error_result(e, healthy=False)

class ListIssuesAction(IntegrationAction, WizOAuth2Mixin):
    """List security issues from Wiz."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List security issues with optional filters.

        Args:
            **kwargs:
                severity: Filter by severity (INFORMATIONAL, LOW, MEDIUM, HIGH, CRITICAL)
                status: Filter by status (OPEN, IN_PROGRESS, RESOLVED, REJECTED)
                resource_type: Filter by resource type
                first: Number of results to return (default: 50, max: 500)
                after: Pagination cursor

        Returns:
            List of issues with pagination info
        """
        first = min(kwargs.get("first", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        after = kwargs.get("after")

        filter_by: dict[str, Any] = {}
        if severity := kwargs.get("severity"):
            filter_by["severity"] = (
                [severity.upper()] if isinstance(severity, str) else severity
            )
        if status := kwargs.get("status"):
            filter_by["status"] = (
                [status.upper()] if isinstance(status, str) else status
            )
        if resource_type := kwargs.get("resource_type"):
            filter_by["relatedEntity"] = {"type": [resource_type]}

        variables: dict[str, Any] = {"first": first}
        if after:
            variables["after"] = after
        if filter_by:
            variables["filterBy"] = filter_by

        try:
            data = await self._graphql_request(LIST_ISSUES_QUERY, variables)
            issues_data = data.get("issues", {})

            return self.success_result(
                data={
                    "issues": issues_data.get("nodes", []),
                    "total_count": issues_data.get("totalCount", 0),
                    "page_info": issues_data.get("pageInfo", {}),
                },
            )
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_AUTHENTICATION)
        except Exception as e:
            logger.error("wiz_list_issues_failed", error=str(e))
            return self.error_result(e)

class GetIssueAction(IntegrationAction, WizOAuth2Mixin):
    """Get details of a specific Wiz issue."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get issue details by ID.

        Args:
            **kwargs:
                issue_id: The Wiz issue ID

        Returns:
            Issue details or not_found result
        """
        issue_id = kwargs.get("issue_id")
        if not issue_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("issue_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            data = await self._graphql_request(GET_ISSUE_QUERY, {"id": issue_id})
            issue = data.get("issue")

            if not issue:
                self.log_info("wiz_issue_not_found", issue_id=issue_id)
                return self.success_result(
                    not_found=True,
                    data={"issue_id": issue_id},
                )

            return self.success_result(data={"issue": issue})
        except WizNotFoundError:
            self.log_info("wiz_issue_not_found", issue_id=issue_id)
            return self.success_result(
                not_found=True,
                data={"issue_id": issue_id},
            )
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_AUTHENTICATION)
        except Exception as e:
            logger.error("wiz_get_issue_failed", issue_id=issue_id, error=str(e))
            return self.error_result(e)

class ListVulnerabilitiesAction(IntegrationAction, WizOAuth2Mixin):
    """List vulnerability findings from Wiz."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List vulnerability findings with optional filters.

        Args:
            **kwargs:
                severity: Filter by CVSS severity
                has_exploit: Filter for vulnerabilities with known exploits
                has_cisa_kev: Filter for CISA KEV vulnerabilities
                first: Number of results (default: 50, max: 500)
                after: Pagination cursor

        Returns:
            List of vulnerability findings with pagination
        """
        first = min(kwargs.get("first", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        after = kwargs.get("after")

        filter_by: dict[str, Any] = {}
        if severity := kwargs.get("severity"):
            filter_by["CVSSSeverity"] = (
                [severity.upper()] if isinstance(severity, str) else severity
            )
        if kwargs.get("has_exploit") is not None:
            filter_by["hasExploit"] = kwargs["has_exploit"]
        if kwargs.get("has_cisa_kev") is not None:
            filter_by["hasCisaKevExploit"] = kwargs["has_cisa_kev"]

        variables: dict[str, Any] = {"first": first}
        if after:
            variables["after"] = after
        if filter_by:
            variables["filterBy"] = filter_by

        try:
            data = await self._graphql_request(LIST_VULNERABILITIES_QUERY, variables)
            vuln_data = data.get("vulnerabilityFindings", {})

            return self.success_result(
                data={
                    "vulnerabilities": vuln_data.get("nodes", []),
                    "total_count": vuln_data.get("totalCount", 0),
                    "page_info": vuln_data.get("pageInfo", {}),
                },
            )
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_AUTHENTICATION)
        except Exception as e:
            logger.error("wiz_list_vulnerabilities_failed", error=str(e))
            return self.error_result(e)

class GetResourceAction(IntegrationAction, WizOAuth2Mixin):
    """Get details of a cloud resource from Wiz."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get cloud resource details by ID.

        Args:
            **kwargs:
                resource_id: The Wiz graph entity ID

        Returns:
            Resource details or not_found result
        """
        resource_id = kwargs.get("resource_id")
        if not resource_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("resource_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            data = await self._graphql_request(GET_RESOURCE_QUERY, {"id": resource_id})
            entity = data.get("graphEntity")

            if not entity:
                self.log_info("wiz_resource_not_found", resource_id=resource_id)
                return self.success_result(
                    not_found=True,
                    data={"resource_id": resource_id},
                )

            return self.success_result(data={"resource": entity})
        except WizNotFoundError:
            self.log_info("wiz_resource_not_found", resource_id=resource_id)
            return self.success_result(
                not_found=True,
                data={"resource_id": resource_id},
            )
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_AUTHENTICATION)
        except Exception as e:
            logger.error(
                "wiz_get_resource_failed", resource_id=resource_id, error=str(e)
            )
            return self.error_result(e)

class SearchResourcesAction(IntegrationAction, WizOAuth2Mixin):
    """Search cloud resources in Wiz graph."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search cloud resources using graph queries.

        Args:
            **kwargs:
                resource_type: Type of resource to search (e.g., VirtualMachine, Container)
                cloud_platform: Cloud platform filter (AWS, Azure, GCP)
                first: Number of results (default: 50, max: 500)
                after: Pagination cursor

        Returns:
            List of matching resources with pagination
        """
        resource_type = kwargs.get("resource_type")
        if not resource_type:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("resource_type"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        first = min(kwargs.get("first", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        after = kwargs.get("after")

        # Build graph query for searching entities of a specific type
        query_input: dict[str, Any] = {
            "type": [resource_type],
        }
        if cloud_platform := kwargs.get("cloud_platform"):
            query_input["where"] = {
                "cloudPlatform": {"EQUALS": [cloud_platform.upper()]}
            }

        variables: dict[str, Any] = {
            "first": first,
            "query": query_input,
        }
        if after:
            variables["after"] = after

        try:
            data = await self._graphql_request(SEARCH_RESOURCES_QUERY, variables)
            search_data = data.get("graphSearch", {})

            # Flatten entities from nested structure
            resources = []
            for node in search_data.get("nodes", []):
                resources.extend(node.get("entities", []))

            return self.success_result(
                data={
                    "resources": resources,
                    "total_count": search_data.get("totalCount", 0),
                    "page_info": search_data.get("pageInfo", {}),
                },
            )
        except WizNotFoundError:
            self.log_info(
                "wiz_search_resources_not_found",
                resource_type=resource_type,
            )
            return self.success_result(
                not_found=True,
                data={
                    "resources": [],
                    "total_count": 0,
                    "page_info": {},
                    "resource_type": resource_type,
                },
            )
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_AUTHENTICATION)
        except Exception as e:
            logger.error("wiz_search_resources_failed", error=str(e))
            return self.error_result(e)

class ListProjectsAction(IntegrationAction, WizOAuth2Mixin):
    """List Wiz projects."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List projects in the Wiz tenant.

        Args:
            **kwargs:
                first: Number of results (default: 50, max: 500)
                after: Pagination cursor

        Returns:
            List of projects with pagination
        """
        first = min(kwargs.get("first", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        after = kwargs.get("after")

        variables: dict[str, Any] = {"first": first}
        if after:
            variables["after"] = after

        try:
            data = await self._graphql_request(LIST_PROJECTS_QUERY, variables)
            projects_data = data.get("projects", {})

            return self.success_result(
                data={
                    "projects": projects_data.get("nodes", []),
                    "total_count": projects_data.get("totalCount", 0),
                    "page_info": projects_data.get("pageInfo", {}),
                },
            )
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_AUTHENTICATION)
        except Exception as e:
            logger.error("wiz_list_projects_failed", error=str(e))
            return self.error_result(e)

class GetConfigurationFindingAction(IntegrationAction, WizOAuth2Mixin):
    """Get a misconfiguration finding from Wiz."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get configuration finding details by ID.

        Args:
            **kwargs:
                finding_id: The Wiz configuration finding ID

        Returns:
            Configuration finding details or not_found result
        """
        finding_id = kwargs.get("finding_id")
        if not finding_id:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("finding_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            data = await self._graphql_request(
                GET_CONFIGURATION_FINDING_QUERY, {"id": finding_id}
            )
            finding = data.get("configurationFinding")

            if not finding:
                self.log_info(
                    "wiz_configuration_finding_not_found", finding_id=finding_id
                )
                return self.success_result(
                    not_found=True,
                    data={"finding_id": finding_id},
                )

            return self.success_result(data={"finding": finding})
        except WizNotFoundError:
            self.log_info("wiz_configuration_finding_not_found", finding_id=finding_id)
            return self.success_result(
                not_found=True,
                data={"finding_id": finding_id},
            )
        except ValueError as e:
            return self.error_result(e, error_type=ERROR_TYPE_AUTHENTICATION)
        except Exception as e:
            logger.error(
                "wiz_get_configuration_finding_failed",
                finding_id=finding_id,
                error=str(e),
            )
            return self.error_result(e)

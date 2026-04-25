"""Tanium REST integration actions.

Uses the Tanium REST API v2 with session-token authentication
(username/password login) or a direct API token.

Auth flow:
  1. If api_token is provided, use it directly as the session header.
  2. Otherwise POST username/password to /api/v2/session/login to get a
     session token, then pass it via the ``session`` header on all requests.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.tanium.constants import (
    EXECUTE_ACTION_URL,
    PACKAGES_URL,
    PARSE_QUESTION_URL,
    QUESTION_RESULTS_URL,
    QUESTIONS_URL,
    SAVED_QUESTIONS_URL,
    SERVER_INFO_URL,
    SESSION_HEADER,
    SESSION_LOGIN_URL,
)

logger = get_logger(__name__)

# ============================================================================
# AUTH HELPERS
# ============================================================================

async def _get_session_token(action: IntegrationAction) -> str:
    """Obtain a Tanium session token.

    If an ``api_token`` credential is provided it is returned directly.
    Otherwise a login request is made with username/password.

    Returns:
        Session token string.

    Raises:
        httpx.HTTPStatusError: On authentication failure.
    """
    api_token = action.credentials.get("api_token")
    if api_token:
        return api_token

    username = action.credentials.get("username")
    password = action.credentials.get("password")
    if not username or not password:
        raise ValueError(
            "Either api_token or both username and password must be provided"
        )

    base_url = action.settings.get("base_url", "").rstrip("/")
    response = await action.http_request(
        url=f"{base_url}{SESSION_LOGIN_URL}",
        method="POST",
        json_data={"username": username, "password": password},
    )
    data = response.json()
    token = data.get("data", {}).get("session")
    if not token:
        raise ValueError("Session token not returned from login endpoint")
    return token

async def _tanium_request(
    action: IntegrationAction,
    endpoint: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_data: Any | None = None,
    session_token: str | None = None,
) -> httpx.Response:
    """Make an authenticated Tanium REST API request.

    Obtains a session token (if not provided), then calls the endpoint
    with the ``session`` header set.
    """
    if session_token is None:
        session_token = await _get_session_token(action)

    base_url = action.settings.get("base_url", "").rstrip("/")
    url = f"{base_url}{endpoint}"

    return await action.http_request(
        url=url,
        method=method,
        headers={SESSION_HEADER: session_token, "Content-Type": "application/json"},
        params=params,
        json_data=json_data,
    )

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Verify connectivity to the Tanium REST API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity by authenticating and listing saved questions."""
        api_token = self.credentials.get("api_token")
        username = self.credentials.get("username")
        password = self.credentials.get("password")

        if not api_token and not (username and password):
            return self.error_result(
                "Either api_token or both username and password must be provided",
                error_type="ConfigurationError",
            )

        base_url = self.settings.get("base_url")
        if not base_url:
            return self.error_result(
                "Missing required setting: base_url",
                error_type="ConfigurationError",
            )

        try:
            token = await _get_session_token(self)
            # Verify connectivity by fetching saved questions (same as upstream)
            await _tanium_request(
                self,
                SAVED_QUESTIONS_URL,
                session_token=token,
            )

            return self.success_result(
                data={"healthy": True, "base_url": base_url},
                healthy=True,
            )
        except httpx.HTTPStatusError as e:
            self.log_error("tanium_health_check_failed", error=e)
            return self.error_result(e, healthy=False)
        except Exception as e:
            self.log_error("tanium_health_check_failed", error=e)
            return self.error_result(e, healthy=False)

class RunQueryAction(IntegrationAction):
    """Run a Tanium question/query and return the parsed question data.

    This action parses and posts a question to the Tanium server.
    To get the results, use the returned question_id with
    get_question_results.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Run a Tanium question.

        Args:
            query_text: The Tanium question text to run.
            group_name: Optional computer group to scope the query.
            timeout_seconds: Question expiry in seconds (default 600).
        """
        query_text = kwargs.get("query_text")
        if not query_text:
            return self.error_result(
                "Missing required parameter: query_text",
                error_type="ValidationError",
            )

        group_name = kwargs.get("group_name")
        timeout_seconds = kwargs.get("timeout_seconds", 600)

        try:
            timeout_seconds = int(timeout_seconds)
            if timeout_seconds <= 0:
                return self.error_result(
                    "timeout_seconds must be a positive integer",
                    error_type="ValidationError",
                )
        except (TypeError, ValueError):
            return self.error_result(
                "timeout_seconds must be a valid integer",
                error_type="ValidationError",
            )

        try:
            token = await _get_session_token(self)

            # Step 1: Parse the question to validate syntax
            parse_resp = await _tanium_request(
                self,
                PARSE_QUESTION_URL,
                method="POST",
                json_data={"text": query_text},
                session_token=token,
            )
            parsed = parse_resp.json()
            parsed_questions = parsed.get("data", [])

            if not parsed_questions:
                return self.error_result(
                    "Question could not be parsed by Tanium server",
                    error_type="ValidationError",
                )

            # Build question data from parsed output
            question_data = parsed_questions[0]
            question_data["expire_seconds"] = timeout_seconds

            # Step 2: Resolve group if specified
            if group_name:
                from analysi.integrations.framework.integrations.tanium.constants import (
                    GROUP_URL,
                )

                group_resp = await _tanium_request(
                    self,
                    GROUP_URL.format(group_name=group_name),
                    session_token=token,
                )
                group_data = group_resp.json().get("data")
                if not group_data:
                    return self.error_result(
                        f"Group '{group_name}' not found",
                        error_type="ValidationError",
                    )
                group_record = (
                    group_data[0] if isinstance(group_data, list) else group_data
                )
                question_data["context_group"] = {"id": group_record.get("id")}

            # Step 3: Post the question
            question_resp = await _tanium_request(
                self,
                QUESTIONS_URL,
                method="POST",
                json_data=question_data,
                session_token=token,
            )
            question_result = question_resp.json()
            question_id = question_result.get("data", {}).get("id")

            return self.success_result(
                data={
                    "question_id": question_id,
                    "query_text": query_text,
                    "timeout_seconds": timeout_seconds,
                    "group_name": group_name,
                    "parsed_question": parsed_questions[0],
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("tanium_run_query_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("tanium_run_query_failed", error=e)
            return self.error_result(e)

class GetQuestionResultsAction(IntegrationAction):
    """Get results for a Tanium question by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Fetch results for a previously asked question.

        Args:
            question_id: The numeric Tanium question ID.
        """
        question_id = kwargs.get("question_id")
        if question_id is None:
            return self.error_result(
                "Missing required parameter: question_id",
                error_type="ValidationError",
            )

        try:
            question_id = int(question_id)
        except (TypeError, ValueError):
            return self.error_result(
                "question_id must be a valid integer",
                error_type="ValidationError",
            )

        try:
            token = await _get_session_token(self)
            endpoint = QUESTION_RESULTS_URL.format(question_id=question_id)
            response = await _tanium_request(
                self,
                endpoint,
                session_token=token,
            )
            result = response.json()

            # Extract row count from result sets
            result_sets = result.get("data", {}).get("result_sets", [])
            row_count = result_sets[0].get("row_count", 0) if result_sets else 0

            return self.success_result(
                data={
                    "question_id": question_id,
                    "row_count": row_count,
                    "result_sets": result_sets,
                    "full_response": result.get("data", {}),
                },
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("tanium_question_not_found", question_id=question_id)
                return self.success_result(
                    not_found=True,
                    data={
                        "question_id": question_id,
                        "row_count": 0,
                        "result_sets": [],
                    },
                )
            self.log_error("tanium_get_question_results_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("tanium_get_question_results_failed", error=e)
            return self.error_result(e)

class ListSavedQuestionsAction(IntegrationAction):
    """List saved questions from the Tanium server."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all saved questions.

        Returns list of saved questions with their IDs and names.
        """
        try:
            token = await _get_session_token(self)
            response = await _tanium_request(
                self,
                SAVED_QUESTIONS_URL,
                session_token=token,
            )
            result = response.json()
            questions = result.get("data", [])

            return self.success_result(
                data={
                    "saved_questions": questions,
                    "count": len(questions) if isinstance(questions, list) else 0,
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("tanium_list_saved_questions_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("tanium_list_saved_questions_failed", error=e)
            return self.error_result(e)

class GetSystemStatusAction(IntegrationAction):
    """Get Tanium server system status/info."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve system status information from the Tanium server."""
        try:
            token = await _get_session_token(self)
            response = await _tanium_request(
                self,
                SERVER_INFO_URL,
                session_token=token,
            )
            result = response.json()

            return self.success_result(
                data=result.get("data", {}),
            )
        except httpx.HTTPStatusError as e:
            self.log_error("tanium_get_system_status_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("tanium_get_system_status_failed", error=e)
            return self.error_result(e)

class ExecuteActionAction(IntegrationAction):
    """Execute a Tanium action/package on target endpoints.

    This creates a saved action that distributes a package to endpoints
    in a specified action group.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute a Tanium action.

        Args:
            action_name: Name for the action.
            action_group: Target action group name.
            package_name: Package to deploy.
            package_parameters: Optional JSON object of package parameters.
            expire_seconds: Action expiry time in seconds.
            group_name: Optional target computer group.
            distribute_seconds: Optional distribution window in seconds.
            issue_seconds: Optional issue delay in seconds.
        """
        action_name = kwargs.get("action_name")
        if not action_name:
            return self.error_result(
                "Missing required parameter: action_name",
                error_type="ValidationError",
            )

        action_group = kwargs.get("action_group")
        if not action_group:
            return self.error_result(
                "Missing required parameter: action_group",
                error_type="ValidationError",
            )

        package_name = kwargs.get("package_name")
        if not package_name:
            return self.error_result(
                "Missing required parameter: package_name",
                error_type="ValidationError",
            )

        expire_seconds = kwargs.get("expire_seconds", 600)
        try:
            expire_seconds = int(expire_seconds)
            if expire_seconds <= 0:
                return self.error_result(
                    "expire_seconds must be a positive integer",
                    error_type="ValidationError",
                )
        except (TypeError, ValueError):
            return self.error_result(
                "expire_seconds must be a valid integer",
                error_type="ValidationError",
            )

        package_parameters = kwargs.get("package_parameters")
        group_name = kwargs.get("group_name")
        distribute_seconds = kwargs.get("distribute_seconds")
        issue_seconds = kwargs.get("issue_seconds")

        try:
            token = await _get_session_token(self)

            # Step 1: Resolve package by name
            from analysi.integrations.framework.integrations.tanium.constants import (
                PACKAGE_URL,
            )

            pkg_resp = await _tanium_request(
                self,
                PACKAGE_URL.format(package=package_name),
                session_token=token,
            )
            pkg_data = pkg_resp.json().get("data")
            if not pkg_data:
                return self.error_result(
                    f"Package '{package_name}' not found",
                    error_type="ValidationError",
                )
            pkg_record = pkg_data[0] if isinstance(pkg_data, list) else pkg_data
            package_id = pkg_record.get("id")

            # Step 2: Resolve action group
            from analysi.integrations.framework.integrations.tanium.constants import (
                ACTION_GROUP_URL,
            )

            ag_resp = await _tanium_request(
                self,
                ACTION_GROUP_URL.format(action_group=action_group),
                session_token=token,
            )
            ag_data = ag_resp.json().get("data")
            if not ag_data:
                return self.error_result(
                    f"Action group '{action_group}' not found",
                    error_type="ValidationError",
                )
            ag_record = ag_data[0] if isinstance(ag_data, list) else ag_data
            action_group_id = ag_record.get("id")

            # Step 3: Build action payload
            payload: dict[str, Any] = {
                "name": action_name,
                "action_group": {"id": action_group_id},
                "package_spec": {"source_id": package_id},
                "expire_seconds": expire_seconds,
            }

            if package_parameters and isinstance(package_parameters, dict):
                param_list = [
                    {"key": k, "value": v} for k, v in package_parameters.items()
                ]
                payload["package_spec"]["parameters"] = param_list

            if distribute_seconds is not None:
                payload["distribute_seconds"] = int(distribute_seconds)

            if issue_seconds is not None:
                payload["issue_seconds"] = int(issue_seconds)

            # Step 4: Resolve optional target group
            if group_name:
                from analysi.integrations.framework.integrations.tanium.constants import (
                    GROUP_URL,
                )

                grp_resp = await _tanium_request(
                    self,
                    GROUP_URL.format(group_name=group_name),
                    session_token=token,
                )
                grp_data = grp_resp.json().get("data")
                if not grp_data:
                    return self.error_result(
                        f"Group '{group_name}' not found",
                        error_type="ValidationError",
                    )
                grp_record = grp_data[0] if isinstance(grp_data, list) else grp_data
                payload["target_group"] = {
                    "source_id": grp_record.get("id"),
                    "name": str(grp_record.get("name")),
                }

            # Step 5: Execute the action
            resp = await _tanium_request(
                self,
                EXECUTE_ACTION_URL,
                method="POST",
                json_data=payload,
                session_token=token,
            )
            result = resp.json()

            return self.success_result(
                data=result.get("data", {}),
            )
        except httpx.HTTPStatusError as e:
            self.log_error("tanium_execute_action_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("tanium_execute_action_failed", error=e)
            return self.error_result(e)

class ListPackagesAction(IntegrationAction):
    """List available packages on the Tanium server."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all available packages."""
        try:
            token = await _get_session_token(self)
            response = await _tanium_request(
                self,
                PACKAGES_URL,
                session_token=token,
            )
            result = response.json()
            packages = result.get("data", [])

            return self.success_result(
                data={
                    "packages": packages,
                    "count": len(packages) if isinstance(packages, list) else 0,
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("tanium_list_packages_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("tanium_list_packages_failed", error=e)
            return self.error_result(e)

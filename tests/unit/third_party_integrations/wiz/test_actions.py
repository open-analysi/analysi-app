"""Unit tests for Wiz cloud security integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.wiz.actions import (
    GetConfigurationFindingAction,
    GetIssueAction,
    GetResourceAction,
    HealthCheckAction,
    ListIssuesAction,
    ListProjectsAction,
    ListVulnerabilitiesAction,
    SearchResourcesAction,
    WizNotFoundError,
    _is_graphql_not_found,
)


@pytest.fixture
def mock_credentials():
    """Mock Wiz OAuth2 credentials."""
    return {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
    }


@pytest.fixture
def mock_settings():
    """Mock integration settings."""
    return {
        "api_url": "https://api.us20.app.wiz.io/graphql",
        "auth_url": "https://auth.app.wiz.io/oauth/token",
        "timeout": 30,
    }


def create_action(
    action_class, action_id="test_action", credentials=None, settings=None
):
    """Helper to create action instances with required parameters."""
    return action_class(
        integration_id="wiz",
        action_id=action_id,
        credentials=credentials or {},
        settings=settings or {},
    )


# ============================================================================
# HealthCheckAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(mock_credentials, mock_settings):
    """Test successful health check with OAuth2 token + GraphQL query."""
    action = create_action(
        HealthCheckAction, "health_check", mock_credentials, mock_settings
    )

    # Mock token response
    token_response = MagicMock()
    token_response.json.return_value = {"access_token": "test_token"}

    # Mock GraphQL response
    graphql_response = MagicMock()
    graphql_response.json.return_value = {
        "data": {"issues": {"totalCount": 42}},
    }

    action.http_request = AsyncMock(side_effect=[token_response, graphql_response])

    result = await action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True
    assert result["data"]["healthy"] is True
    assert result["data"]["issues_total_count"] == 42
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials returns ConfigurationError."""
    action = create_action(HealthCheckAction, "health_check")

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert result["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_auth_failure(mock_credentials, mock_settings):
    """Test health check with authentication failure."""
    action = create_action(
        HealthCheckAction, "health_check", mock_credentials, mock_settings
    )

    # Token request returns no access_token
    token_response = MagicMock()
    token_response.json.return_value = {"error": "invalid_client"}

    action.http_request = AsyncMock(return_value=token_response)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"
    assert result["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_network_error(mock_credentials, mock_settings):
    """Test health check with network failure."""
    action = create_action(
        HealthCheckAction, "health_check", mock_credentials, mock_settings
    )

    action.http_request = AsyncMock(side_effect=ConnectionError("Connection refused"))

    result = await action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False


# ============================================================================
# ListIssuesAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_issues_success(mock_credentials, mock_settings):
    """Test successful issue listing."""
    action = create_action(
        ListIssuesAction, "list_issues", mock_credentials, mock_settings
    )

    mock_issues = [
        {
            "id": "issue-1",
            "severity": "HIGH",
            "status": "OPEN",
            "sourceRule": {"id": "rule-1", "name": "Public S3 Bucket"},
            "entitySnapshot": {
                "id": "entity-1",
                "type": "Bucket",
                "name": "my-bucket",
                "cloudPlatform": "AWS",
            },
        }
    ]

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={
                "issues": {
                    "totalCount": 1,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": mock_issues,
                }
            },
        ):
            result = await action.execute(severity="HIGH", status="OPEN")

    assert result["status"] == "success"
    assert result["data"]["total_count"] == 1
    assert len(result["data"]["issues"]) == 1
    assert result["data"]["issues"][0]["id"] == "issue-1"
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_list_issues_with_filters(mock_credentials, mock_settings):
    """Test issue listing with severity and status filters passed to GraphQL."""
    action = create_action(
        ListIssuesAction, "list_issues", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={
                "issues": {
                    "totalCount": 0,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [],
                }
            },
        ) as mock_gql:
            result = await action.execute(severity="CRITICAL", status="OPEN", first=10)

    assert result["status"] == "success"
    # Verify variables include filters
    call_args = mock_gql.call_args
    variables = call_args[1].get("variables") or call_args[0][1]
    assert variables["first"] == 10
    assert variables["filterBy"]["severity"] == ["CRITICAL"]
    assert variables["filterBy"]["status"] == ["OPEN"]


@pytest.mark.asyncio
async def test_list_issues_empty_result(mock_credentials, mock_settings):
    """Test issue listing with no results."""
    action = create_action(
        ListIssuesAction, "list_issues", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={
                "issues": {
                    "totalCount": 0,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [],
                }
            },
        ):
            result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["total_count"] == 0
    assert result["data"]["issues"] == []


@pytest.mark.asyncio
async def test_list_issues_auth_error(mock_credentials, mock_settings):
    """Test issue listing with authentication failure."""
    action = create_action(
        ListIssuesAction, "list_issues", mock_credentials, mock_settings
    )

    with patch.object(
        action,
        "_get_access_token",
        side_effect=ValueError("Missing required credentials"),
    ):
        # _graphql_request calls _get_access_token which raises ValueError
        result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"


# ============================================================================
# GetIssueAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_issue_success(mock_credentials, mock_settings):
    """Test successful single issue retrieval."""
    action = create_action(GetIssueAction, "get_issue", mock_credentials, mock_settings)

    mock_issue = {
        "id": "issue-123",
        "severity": "CRITICAL",
        "status": "OPEN",
        "sourceRule": {
            "id": "rule-1",
            "name": "Unrestricted SSH Access",
            "description": "Security group allows SSH from 0.0.0.0/0",
        },
        "entitySnapshot": {
            "id": "sg-abc123",
            "type": "SecurityGroup",
            "name": "my-sg",
            "cloudPlatform": "AWS",
        },
        "evidence": [
            {
                "currentValue": "0.0.0.0/0",
                "expectedValue": "restricted",
                "fieldName": "cidrBlock",
            }
        ],
    }

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={"issue": mock_issue},
        ):
            result = await action.execute(issue_id="issue-123")

    assert result["status"] == "success"
    assert result["data"]["issue"]["id"] == "issue-123"
    assert result["data"]["issue"]["severity"] == "CRITICAL"
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_get_issue_missing_id():
    """Test get issue without issue_id returns ValidationError."""
    action = create_action(GetIssueAction, "get_issue")

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "issue_id" in result["error"]


@pytest.mark.asyncio
async def test_get_issue_not_found(mock_credentials, mock_settings):
    """Test get issue that does not exist returns success with not_found."""
    action = create_action(GetIssueAction, "get_issue", mock_credentials, mock_settings)

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={"issue": None},
        ):
            result = await action.execute(issue_id="nonexistent-id")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["issue_id"] == "nonexistent-id"


# ============================================================================
# ListVulnerabilitiesAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_vulnerabilities_success(mock_credentials, mock_settings):
    """Test successful vulnerability listing."""
    action = create_action(
        ListVulnerabilitiesAction,
        "list_vulnerabilities",
        mock_credentials,
        mock_settings,
    )

    mock_vulns = [
        {
            "id": "vuln-1",
            "name": "CVE-2024-1234",
            "CVSSSeverity": "HIGH",
            "score": 8.5,
            "hasExploit": True,
            "hasCisaKevExploit": False,
            "vulnerableAsset": {
                "id": "vm-1",
                "type": "VirtualMachine",
                "name": "prod-server",
                "cloudPlatform": "AWS",
            },
        }
    ]

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={
                "vulnerabilityFindings": {
                    "totalCount": 1,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": mock_vulns,
                }
            },
        ):
            result = await action.execute(severity="HIGH", has_exploit=True)

    assert result["status"] == "success"
    assert result["data"]["total_count"] == 1
    assert len(result["data"]["vulnerabilities"]) == 1
    assert result["data"]["vulnerabilities"][0]["name"] == "CVE-2024-1234"


@pytest.mark.asyncio
async def test_list_vulnerabilities_with_cisa_kev_filter(
    mock_credentials, mock_settings
):
    """Test vulnerability listing with CISA KEV filter."""
    action = create_action(
        ListVulnerabilitiesAction,
        "list_vulnerabilities",
        mock_credentials,
        mock_settings,
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={
                "vulnerabilityFindings": {
                    "totalCount": 0,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [],
                }
            },
        ) as mock_gql:
            result = await action.execute(has_cisa_kev=True)

    assert result["status"] == "success"
    call_args = mock_gql.call_args
    variables = call_args[1].get("variables") or call_args[0][1]
    assert variables["filterBy"]["hasCisaKevExploit"] is True


# ============================================================================
# GetResourceAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_resource_success(mock_credentials, mock_settings):
    """Test successful resource retrieval."""
    action = create_action(
        GetResourceAction, "get_resource", mock_credentials, mock_settings
    )

    mock_resource = {
        "id": "res-abc123",
        "type": "VirtualMachine",
        "name": "prod-web-01",
        "properties": {
            "cloudPlatform": "AWS",
            "region": "us-east-1",
            "instanceType": "t3.large",
        },
    }

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={"graphEntity": mock_resource},
        ):
            result = await action.execute(resource_id="res-abc123")

    assert result["status"] == "success"
    assert result["data"]["resource"]["id"] == "res-abc123"
    assert result["data"]["resource"]["type"] == "VirtualMachine"
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_get_resource_missing_id():
    """Test get resource without resource_id returns ValidationError."""
    action = create_action(GetResourceAction, "get_resource")

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "resource_id" in result["error"]


@pytest.mark.asyncio
async def test_get_resource_not_found(mock_credentials, mock_settings):
    """Test get resource that does not exist returns success with not_found."""
    action = create_action(
        GetResourceAction, "get_resource", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={"graphEntity": None},
        ):
            result = await action.execute(resource_id="nonexistent-id")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["resource_id"] == "nonexistent-id"


# ============================================================================
# SearchResourcesAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_search_resources_success(mock_credentials, mock_settings):
    """Test successful resource search."""
    action = create_action(
        SearchResourcesAction, "search_resources", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={
                "graphSearch": {
                    "totalCount": 2,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "entities": [
                                {
                                    "id": "vm-1",
                                    "type": "VirtualMachine",
                                    "name": "web-01",
                                    "properties": {"region": "us-east-1"},
                                },
                                {
                                    "id": "vm-2",
                                    "type": "VirtualMachine",
                                    "name": "web-02",
                                    "properties": {"region": "us-west-2"},
                                },
                            ]
                        }
                    ],
                }
            },
        ):
            result = await action.execute(
                resource_type="VirtualMachine", cloud_platform="AWS"
            )

    assert result["status"] == "success"
    assert result["data"]["total_count"] == 2
    assert len(result["data"]["resources"]) == 2
    assert result["data"]["resources"][0]["name"] == "web-01"


@pytest.mark.asyncio
async def test_search_resources_missing_type():
    """Test search resources without resource_type returns ValidationError."""
    action = create_action(SearchResourcesAction, "search_resources")

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "resource_type" in result["error"]


@pytest.mark.asyncio
async def test_search_resources_empty_results(mock_credentials, mock_settings):
    """Test search resources with no results."""
    action = create_action(
        SearchResourcesAction, "search_resources", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={
                "graphSearch": {
                    "totalCount": 0,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [],
                }
            },
        ):
            result = await action.execute(resource_type="Container")

    assert result["status"] == "success"
    assert result["data"]["total_count"] == 0
    assert result["data"]["resources"] == []


# ============================================================================
# ListProjectsAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_projects_success(mock_credentials, mock_settings):
    """Test successful project listing."""
    action = create_action(
        ListProjectsAction, "list_projects", mock_credentials, mock_settings
    )

    mock_projects = [
        {
            "id": "proj-1",
            "name": "Production",
            "slug": "production",
            "description": "Production workloads",
            "businessUnit": "Engineering",
            "riskProfile": {"businessImpact": "MHBI"},
            "projectOwners": [{"name": "Jane Doe", "email": "jane@example.com"}],
        }
    ]

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={
                "projects": {
                    "totalCount": 1,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": mock_projects,
                }
            },
        ):
            result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["total_count"] == 1
    assert len(result["data"]["projects"]) == 1
    assert result["data"]["projects"][0]["name"] == "Production"
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_list_projects_pagination(mock_credentials, mock_settings):
    """Test project listing with pagination cursor."""
    action = create_action(
        ListProjectsAction, "list_projects", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={
                "projects": {
                    "totalCount": 100,
                    "pageInfo": {
                        "hasNextPage": True,
                        "endCursor": "cursor-abc123",
                    },
                    "nodes": [{"id": "proj-51", "name": "Project 51"}],
                }
            },
        ) as mock_gql:
            result = await action.execute(first=10, after="cursor-prev")

    assert result["status"] == "success"
    assert result["data"]["page_info"]["hasNextPage"] is True
    assert result["data"]["page_info"]["endCursor"] == "cursor-abc123"
    # Verify cursor was passed to GraphQL
    call_args = mock_gql.call_args
    variables = call_args[1].get("variables") or call_args[0][1]
    assert variables["after"] == "cursor-prev"
    assert variables["first"] == 10


# ============================================================================
# GetConfigurationFindingAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_configuration_finding_success(mock_credentials, mock_settings):
    """Test successful configuration finding retrieval."""
    action = create_action(
        GetConfigurationFindingAction,
        "get_configuration_finding",
        mock_credentials,
        mock_settings,
    )

    mock_finding = {
        "id": "finding-xyz",
        "result": "FAIL",
        "severity": "HIGH",
        "analyzedAt": "2025-01-15T10:30:00Z",
        "resource": {
            "id": "sg-abc123",
            "type": "SecurityGroup",
            "name": "my-sg",
            "cloudPlatform": "AWS",
            "region": "us-east-1",
        },
        "rule": {
            "id": "rule-1",
            "name": "Restrict SSH access",
            "description": "Ensure SSH is not open to the world",
            "remediationInstructions": "Restrict the CIDR range in the SG rule",
        },
    }

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={"configurationFinding": mock_finding},
        ):
            result = await action.execute(finding_id="finding-xyz")

    assert result["status"] == "success"
    assert result["data"]["finding"]["id"] == "finding-xyz"
    assert result["data"]["finding"]["result"] == "FAIL"
    assert result["data"]["finding"]["rule"]["name"] == "Restrict SSH access"
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_get_configuration_finding_missing_id():
    """Test get finding without finding_id returns ValidationError."""
    action = create_action(GetConfigurationFindingAction, "get_configuration_finding")

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "finding_id" in result["error"]


@pytest.mark.asyncio
async def test_get_configuration_finding_not_found(mock_credentials, mock_settings):
    """Test get finding that does not exist returns success with not_found."""
    action = create_action(
        GetConfigurationFindingAction,
        "get_configuration_finding",
        mock_credentials,
        mock_settings,
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={"configurationFinding": None},
        ):
            result = await action.execute(finding_id="nonexistent-id")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["finding_id"] == "nonexistent-id"


# ============================================================================
# WizOAuth2Mixin Tests
# ============================================================================


@pytest.mark.asyncio
async def test_oauth2_token_no_caching(mock_credentials, mock_settings):
    """Test that each call acquires a fresh OAuth2 token (no cross-tenant leak)."""
    action = create_action(
        ListIssuesAction, "list_issues", mock_credentials, mock_settings
    )

    # Mock token responses (one per execute call)
    token_response_1 = MagicMock()
    token_response_1.json.return_value = {"access_token": "token_1"}

    token_response_2 = MagicMock()
    token_response_2.json.return_value = {"access_token": "token_2"}

    # Mock GraphQL responses (2 calls)
    graphql_response = MagicMock()
    graphql_response.json.return_value = {
        "data": {
            "issues": {
                "totalCount": 0,
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [],
            }
        },
    }

    action.http_request = AsyncMock(
        side_effect=[
            token_response_1,
            graphql_response,
            token_response_2,
            graphql_response,
        ]
    )

    # Each call should acquire its own fresh token
    await action.execute()
    await action.execute()

    # Token request (2) + GraphQL (2) = 4 total HTTP calls
    assert action.http_request.call_count == 4


@pytest.mark.asyncio
async def test_oauth2_token_retry_on_401(mock_credentials, mock_settings):
    """Test that 401 response triggers token refresh and retry."""
    action = create_action(
        HealthCheckAction, "health_check", mock_credentials, mock_settings
    )

    import httpx

    # First token
    token_response_1 = MagicMock()
    token_response_1.json.return_value = {"access_token": "expired_token"}

    # 401 error on first GraphQL call
    error_response = MagicMock()
    error_response.status_code = 401
    error_response.headers = {}
    error_response.text = "Unauthorized"
    mock_request = MagicMock()
    http_401_error = httpx.HTTPStatusError(
        "Unauthorized", request=mock_request, response=error_response
    )

    # Refresh token
    token_response_2 = MagicMock()
    token_response_2.json.return_value = {"access_token": "fresh_token"}

    # Success on retry
    graphql_response = MagicMock()
    graphql_response.json.return_value = {
        "data": {"issues": {"totalCount": 5}},
    }

    action.http_request = AsyncMock(
        side_effect=[
            token_response_1,
            http_401_error,
            token_response_2,
            graphql_response,
        ]
    )

    result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["issues_total_count"] == 5


@pytest.mark.asyncio
async def test_graphql_error_handling(mock_credentials, mock_settings):
    """Test GraphQL-level error handling (valid HTTP, invalid GraphQL)."""
    action = create_action(
        ListIssuesAction, "list_issues", mock_credentials, mock_settings
    )

    # Token response
    token_response = MagicMock()
    token_response.json.return_value = {"access_token": "test_token"}

    # GraphQL response with errors
    error_graphql_response = MagicMock()
    error_graphql_response.json.return_value = {
        "errors": [
            {"message": "Field 'invalidField' not found"},
            {"message": "Syntax error in query"},
        ],
    }

    action.http_request = AsyncMock(
        side_effect=[token_response, error_graphql_response]
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert "GraphQL errors" in result["error"]
    assert "invalidField" in result["error"]


@pytest.mark.asyncio
async def test_page_size_capped_at_max(mock_credentials, mock_settings):
    """Test that page size is capped at MAX_PAGE_SIZE (500)."""
    action = create_action(
        ListIssuesAction, "list_issues", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_graphql_request",
            return_value={
                "issues": {
                    "totalCount": 0,
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [],
                }
            },
        ) as mock_gql:
            # Request 9999 but should be capped at 500
            await action.execute(first=9999)

    call_args = mock_gql.call_args
    variables = call_args[1].get("variables") or call_args[0][1]
    assert variables["first"] == 500


# ============================================================================
# _is_graphql_not_found Tests
# ============================================================================


def test_is_graphql_not_found_by_extensions_code():
    """Test detection of not-found via extensions.code."""
    errors = [{"message": "Some error", "extensions": {"code": "NOT_FOUND"}}]
    assert _is_graphql_not_found(errors) is True


def test_is_graphql_not_found_by_resource_not_found_code():
    """Test detection of not-found via RESOURCE_NOT_FOUND extensions code."""
    errors = [{"message": "Some error", "extensions": {"code": "RESOURCE_NOT_FOUND"}}]
    assert _is_graphql_not_found(errors) is True


def test_is_graphql_not_found_by_message_prefix():
    """Test detection of not-found via message prefix."""
    errors = [{"message": "Could not find issue with id 'abc-123'"}]
    assert _is_graphql_not_found(errors) is True


def test_is_graphql_not_found_entity_message():
    """Test detection of 'entity not found' message."""
    errors = [{"message": "Entity not found"}]
    assert _is_graphql_not_found(errors) is True


def test_is_graphql_not_found_schema_error_is_not_matched():
    """Schema errors like 'Field X not found' must NOT trigger not-found."""
    errors = [{"message": "Field 'invalidField' not found"}]
    assert _is_graphql_not_found(errors) is False


def test_is_graphql_not_found_syntax_error_is_not_matched():
    """Syntax errors must NOT trigger not-found."""
    errors = [{"message": "Syntax error in query"}]
    assert _is_graphql_not_found(errors) is False


def test_is_graphql_not_found_empty_errors():
    """Empty errors list returns False."""
    assert _is_graphql_not_found([]) is False


def test_is_graphql_not_found_no_extensions():
    """Errors without extensions and non-matching message returns False."""
    errors = [{"message": "Internal server error"}]
    assert _is_graphql_not_found(errors) is False


# ============================================================================
# _graphql_request HTTP 404 and GraphQL Not-Found Tests
# ============================================================================


def _make_http_404_error():
    """Create an httpx.HTTPStatusError with status 404."""
    response = MagicMock()
    response.status_code = 404
    response.headers = {}
    response.text = "Not Found"
    request = MagicMock()
    return httpx.HTTPStatusError("Not Found", request=request, response=response)


@pytest.mark.asyncio
async def test_graphql_request_http_404_raises_not_found(
    mock_credentials, mock_settings
):
    """Test that HTTP 404 from Wiz API raises WizNotFoundError."""
    action = create_action(GetIssueAction, "get_issue", mock_credentials, mock_settings)

    token_response = MagicMock()
    token_response.json.return_value = {"access_token": "test_token"}

    action.http_request = AsyncMock(
        side_effect=[token_response, _make_http_404_error()]
    )

    with pytest.raises(WizNotFoundError, match="Wiz API returned 404"):
        await action._graphql_request("query { issue(id: $id) { id } }", {"id": "x"})


@pytest.mark.asyncio
async def test_graphql_request_not_found_extensions_raises(
    mock_credentials, mock_settings
):
    """Test that GraphQL errors with NOT_FOUND code raise WizNotFoundError."""
    action = create_action(GetIssueAction, "get_issue", mock_credentials, mock_settings)

    token_response = MagicMock()
    token_response.json.return_value = {"access_token": "test_token"}

    graphql_response = MagicMock()
    graphql_response.json.return_value = {
        "errors": [
            {
                "message": "Issue with id 'bad-id' was not found",
                "extensions": {"code": "NOT_FOUND"},
            }
        ]
    }

    action.http_request = AsyncMock(side_effect=[token_response, graphql_response])

    with pytest.raises(WizNotFoundError, match="GraphQL not found"):
        await action._graphql_request("query { issue(id: $id) { id } }", {"id": "x"})


@pytest.mark.asyncio
async def test_graphql_request_not_found_message_prefix_raises(
    mock_credentials, mock_settings
):
    """Test that GraphQL errors with not-found message prefix raise WizNotFoundError."""
    action = create_action(GetIssueAction, "get_issue", mock_credentials, mock_settings)

    token_response = MagicMock()
    token_response.json.return_value = {"access_token": "test_token"}

    graphql_response = MagicMock()
    graphql_response.json.return_value = {
        "errors": [{"message": "Could not find resource with the given identifier"}]
    }

    action.http_request = AsyncMock(side_effect=[token_response, graphql_response])

    with pytest.raises(WizNotFoundError, match="GraphQL not found"):
        await action._graphql_request("query { issue(id: $id) { id } }", {"id": "x"})


@pytest.mark.asyncio
async def test_graphql_request_schema_error_raises_value_error(
    mock_credentials, mock_settings
):
    """Test that schema GraphQL errors still raise ValueError, not WizNotFoundError."""
    action = create_action(GetIssueAction, "get_issue", mock_credentials, mock_settings)

    token_response = MagicMock()
    token_response.json.return_value = {"access_token": "test_token"}

    graphql_response = MagicMock()
    graphql_response.json.return_value = {
        "errors": [
            {"message": "Field 'invalidField' not found"},
            {"message": "Syntax error in query"},
        ]
    }

    action.http_request = AsyncMock(side_effect=[token_response, graphql_response])

    with pytest.raises(ValueError, match="GraphQL errors"):
        await action._graphql_request("query { bad }", {})


# ============================================================================
# Action-level Not-Found Handling Tests (HTTP 404)
# ============================================================================


@pytest.mark.asyncio
async def test_get_issue_http_404_returns_not_found(mock_credentials, mock_settings):
    """Test GetIssueAction returns not_found on HTTP 404."""
    action = create_action(GetIssueAction, "get_issue", mock_credentials, mock_settings)

    with patch.object(action, "_graphql_request", side_effect=WizNotFoundError("404")):
        result = await action.execute(issue_id="missing-id")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["issue_id"] == "missing-id"


@pytest.mark.asyncio
async def test_get_resource_http_404_returns_not_found(mock_credentials, mock_settings):
    """Test GetResourceAction returns not_found on HTTP 404."""
    action = create_action(
        GetResourceAction, "get_resource", mock_credentials, mock_settings
    )

    with patch.object(action, "_graphql_request", side_effect=WizNotFoundError("404")):
        result = await action.execute(resource_id="missing-res")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["resource_id"] == "missing-res"


@pytest.mark.asyncio
async def test_get_configuration_finding_http_404_returns_not_found(
    mock_credentials, mock_settings
):
    """Test GetConfigurationFindingAction returns not_found on HTTP 404."""
    action = create_action(
        GetConfigurationFindingAction,
        "get_configuration_finding",
        mock_credentials,
        mock_settings,
    )

    with patch.object(action, "_graphql_request", side_effect=WizNotFoundError("404")):
        result = await action.execute(finding_id="missing-finding")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["finding_id"] == "missing-finding"


@pytest.mark.asyncio
async def test_search_resources_not_found_returns_empty(
    mock_credentials, mock_settings
):
    """Test SearchResourcesAction returns not_found with empty results."""
    action = create_action(
        SearchResourcesAction, "search_resources", mock_credentials, mock_settings
    )

    with patch.object(
        action, "_graphql_request", side_effect=WizNotFoundError("not found")
    ):
        result = await action.execute(resource_type="NonExistentType")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["resources"] == []
    assert result["data"]["total_count"] == 0
    assert result["data"]["resource_type"] == "NonExistentType"


# ============================================================================
# Action-level Not-Found Handling Tests (GraphQL not-found error)
# ============================================================================


@pytest.mark.asyncio
async def test_get_issue_graphql_not_found_returns_not_found(
    mock_credentials, mock_settings
):
    """Test GetIssueAction returns not_found on GraphQL not-found error."""
    action = create_action(GetIssueAction, "get_issue", mock_credentials, mock_settings)

    with patch.object(
        action,
        "_graphql_request",
        side_effect=WizNotFoundError("GraphQL not found: Issue not found"),
    ):
        result = await action.execute(issue_id="bad-issue-id")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["issue_id"] == "bad-issue-id"


@pytest.mark.asyncio
async def test_get_resource_graphql_not_found_returns_not_found(
    mock_credentials, mock_settings
):
    """Test GetResourceAction returns not_found on GraphQL not-found error."""
    action = create_action(
        GetResourceAction, "get_resource", mock_credentials, mock_settings
    )

    with patch.object(
        action,
        "_graphql_request",
        side_effect=WizNotFoundError("GraphQL not found: Entity not found"),
    ):
        result = await action.execute(resource_id="bad-resource-id")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["resource_id"] == "bad-resource-id"


@pytest.mark.asyncio
async def test_get_configuration_finding_graphql_not_found(
    mock_credentials, mock_settings
):
    """Test GetConfigurationFindingAction returns not_found on GraphQL not-found."""
    action = create_action(
        GetConfigurationFindingAction,
        "get_configuration_finding",
        mock_credentials,
        mock_settings,
    )

    with patch.object(
        action,
        "_graphql_request",
        side_effect=WizNotFoundError("GraphQL not found: Finding not found"),
    ):
        result = await action.execute(finding_id="bad-finding-id")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["finding_id"] == "bad-finding-id"

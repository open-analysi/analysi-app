"""
Wiz cloud security (CNAPP) integration constants.

Wiz uses a GraphQL API over HTTPS with OAuth2 client credentials authentication.
"""

# Timeout settings
DEFAULT_TIMEOUT = 30

# Default API URLs
DEFAULT_API_URL = "https://api.us20.app.wiz.io/graphql"
DEFAULT_AUTH_URL = "https://auth.app.wiz.io/oauth/token"

# OAuth2 settings
OAUTH_AUDIENCE = "wiz-api"
OAUTH_GRANT_TYPE = "client_credentials"

# Credential field names
CREDENTIAL_CLIENT_ID = "client_id"
CREDENTIAL_CLIENT_SECRET = "client_secret"

# Settings field names
SETTINGS_API_URL = "api_url"
SETTINGS_AUTH_URL = "auth_url"
SETTINGS_TIMEOUT = "timeout"

# Status values
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Error types
ERROR_TYPE_VALIDATION = "ValidationError"
ERROR_TYPE_CONFIGURATION = "ConfigurationError"
ERROR_TYPE_AUTHENTICATION = "AuthenticationError"

# Error messages
MSG_MISSING_CREDENTIALS = "Missing required credentials: client_id and client_secret"
MSG_MISSING_PARAMETER = "Missing required parameter: {}"
MSG_AUTHENTICATION_FAILED = "Failed to authenticate with Wiz API"

# Default pagination limits
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

# Issue severity levels
ISSUE_SEVERITIES = ["INFORMATIONAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Issue status values
ISSUE_STATUSES = ["OPEN", "IN_PROGRESS", "RESOLVED", "REJECTED"]

# GraphQL queries
HEALTH_CHECK_QUERY = """
query HealthCheck {
  issues(first: 1) {
    totalCount
  }
}
"""

LIST_ISSUES_QUERY = """
query ListIssues($first: Int, $after: String, $filterBy: IssueFilters) {
  issues(first: $first, after: $after, filterBy: $filterBy) {
    totalCount
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      sourceRule {
        id
        name
      }
      createdAt
      updatedAt
      status
      severity
      entitySnapshot {
        id
        type
        name
        cloudPlatform
        subscriptionExternalId
        region
        nativeType
      }
      notes {
        text
        createdAt
      }
    }
  }
}
"""

GET_ISSUE_QUERY = """
query GetIssue($id: ID!) {
  issue(id: $id) {
    id
    sourceRule {
      id
      name
      description
    }
    createdAt
    updatedAt
    status
    severity
    entitySnapshot {
      id
      type
      name
      cloudPlatform
      subscriptionExternalId
      region
      nativeType
      tags
    }
    notes {
      text
      createdAt
      updatedBy {
        name
        email
      }
    }
    evidence {
      currentValue
      expectedValue
      fieldName
    }
  }
}
"""

LIST_VULNERABILITIES_QUERY = """
query ListVulnerabilities($first: Int, $after: String, $filterBy: VulnerabilityFilters) {
  vulnerabilityFindings(first: $first, after: $after, filterBy: $filterBy) {
    totalCount
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      name
      CVEDescription
      CVSSSeverity
      score
      exploitabilityScore
      impactScore
      hasExploit
      hasCisaKevExploit
      fixedVersion
      version
      detailedName
      vendorSeverity
      vulnerableAsset {
        id
        type
        name
        cloudPlatform
        subscriptionExternalId
        region
      }
    }
  }
}
"""

GET_RESOURCE_QUERY = """
query GetResource($id: ID!) {
  graphEntity(id: $id) {
    id
    type
    name
    properties
  }
}
"""

SEARCH_RESOURCES_QUERY = """
query SearchResources($first: Int, $after: String, $query: GraphEntityQueryInput) {
  graphSearch(first: $first, after: $after, query: $query) {
    totalCount
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      entities {
        id
        type
        name
        properties
      }
    }
  }
}
"""

LIST_PROJECTS_QUERY = """
query ListProjects($first: Int, $after: String) {
  projects(first: $first, after: $after) {
    totalCount
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      name
      slug
      description
      businessUnit
      riskProfile {
        businessImpact
      }
      projectOwners {
        name
        email
      }
    }
  }
}
"""

GET_CONFIGURATION_FINDING_QUERY = """
query GetConfigurationFinding($id: ID!) {
  configurationFinding(id: $id) {
    id
    result
    severity
    analyzedAt
    resource {
      id
      type
      name
      cloudPlatform
      subscriptionExternalId
      region
      nativeType
    }
    rule {
      id
      name
      description
      remediationInstructions
    }
  }
}
"""

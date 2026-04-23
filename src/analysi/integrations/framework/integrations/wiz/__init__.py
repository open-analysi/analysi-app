"""Wiz cloud security (CNAPP) integration."""

from analysi.integrations.framework.integrations.wiz.actions import (
    GetConfigurationFindingAction,
    GetIssueAction,
    GetResourceAction,
    HealthCheckAction,
    ListIssuesAction,
    ListProjectsAction,
    ListVulnerabilitiesAction,
    SearchResourcesAction,
)

__all__ = [
    "GetConfigurationFindingAction",
    "GetIssueAction",
    "GetResourceAction",
    "HealthCheckAction",
    "ListIssuesAction",
    "ListProjectsAction",
    "ListVulnerabilitiesAction",
    "SearchResourcesAction",
]

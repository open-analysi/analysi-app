"""Google Cloud Security Command Center (SCC) integration actions.

Provides CloudProvider actions for managing GCP security findings,
sources, assets, and notification configs via the SCC REST API v1.

Authentication: Bearer token (access_token) provided in credentials.
Users generate tokens via `gcloud auth print-access-token` or workload identity.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    DEFAULT_PAGE_SIZE,
    GCP_SCC_BASE_URL,
    MAX_PAGE_SIZE,
    VALID_FINDING_STATES,
)

logger = get_logger(__name__)

# ============================================================================
# BASE CLASS — shared auth & request logic
# ============================================================================

class _GCPSCCBase(IntegrationAction):
    """Base class for all GCP SCC actions.

    Provides:
    - Bearer token auth via get_http_headers()
    - Organization parent path helper
    - Credential and settings validation helpers
    """

    def get_http_headers(self) -> dict[str, str]:
        """Return Bearer token auth header."""
        access_token = self.credentials.get("access_token", "")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers

    def _get_org_parent(self) -> str | None:
        """Return the organization parent path (e.g. 'organizations/123456')."""
        org_id = self.settings.get("organization_id")
        if not org_id:
            return None
        return f"organizations/{org_id}"

    def _validate_credentials(self) -> dict[str, Any] | None:
        """Validate access_token is present. Returns error dict or None."""
        if not self.credentials.get("access_token"):
            return self.error_result(
                "Missing required credential: access_token",
                error_type="ConfigurationError",
            )
        return None

    def _validate_org_id(self) -> dict[str, Any] | None:
        """Validate organization_id is present. Returns error dict or None."""
        if not self.settings.get("organization_id"):
            return self.error_result(
                "Missing required setting: organization_id",
                error_type="ConfigurationError",
            )
        return None

# ============================================================================
# ACTIONS
# ============================================================================

class HealthCheckAction(_GCPSCCBase):
    """Verify connectivity to GCP Security Command Center API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test API connectivity by listing sources (limited to 1).

        Returns:
            Success with API version info, or error on failure.
        """
        cred_error = self._validate_credentials()
        if cred_error:
            return cred_error

        org_error = self._validate_org_id()
        if org_error:
            return org_error

        parent = self._get_org_parent()

        try:
            response = await self.http_request(
                url=f"{GCP_SCC_BASE_URL}/{parent}/sources",
                params={"pageSize": 1},
            )
            data = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "api_version": "v1",
                    "organization_id": self.settings.get("organization_id"),
                    "sources_accessible": "sources" in data or isinstance(data, dict),
                },
                healthy=True,
            )
        except Exception as e:
            self.log_error("gcp_scc_health_check_failed", error=e)
            return self.error_result(e, healthy=False)

class ListFindingsAction(_GCPSCCBase):
    """List security findings with optional filters."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List security findings from GCP SCC.

        Args:
            **kwargs:
                source_id (str, optional): Source ID to filter findings.
                    Use '-' for all sources (default).
                filter (str, optional): SCC filter expression
                    (e.g. 'severity="HIGH" AND state="ACTIVE"').
                page_size (int, optional): Number of results per page (default: 100).
                page_token (str, optional): Token for pagination.
                order_by (str, optional): Sort order (e.g. 'eventTime desc').

        Returns:
            Success with list of findings, or error.
        """
        cred_error = self._validate_credentials()
        if cred_error:
            return cred_error

        org_error = self._validate_org_id()
        if org_error:
            return org_error

        parent = self._get_org_parent()
        source_id = kwargs.get("source_id", "-")

        page_size = kwargs.get("page_size", DEFAULT_PAGE_SIZE)
        if isinstance(page_size, str):
            try:
                page_size = int(page_size)
            except ValueError:
                return self.error_result(
                    f"Invalid page_size: {page_size}", error_type="ValidationError"
                )
        page_size = min(page_size, MAX_PAGE_SIZE)

        params: dict[str, Any] = {"pageSize": page_size}

        scc_filter = kwargs.get("filter")
        if scc_filter:
            params["filter"] = scc_filter

        page_token = kwargs.get("page_token")
        if page_token:
            params["pageToken"] = page_token

        order_by = kwargs.get("order_by")
        if order_by:
            params["orderBy"] = order_by

        try:
            response = await self.http_request(
                url=f"{GCP_SCC_BASE_URL}/{parent}/sources/{source_id}/findings",
                params=params,
            )
            data = response.json()

            findings = data.get("listFindingsResults", [])
            next_page_token = data.get("nextPageToken")

            return self.success_result(
                data={
                    "findings": findings,
                    "total_results": len(findings),
                    "next_page_token": next_page_token,
                    "read_time": data.get("readTime"),
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("gcp_scc_list_findings_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("gcp_scc_list_findings_failed", error=e)
            return self.error_result(e)

class GetFindingAction(_GCPSCCBase):
    """Get details of a specific security finding."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get a finding by its full resource name.

        Args:
            **kwargs:
                finding_name (str): Full resource name of the finding, e.g.
                    'organizations/123/sources/456/findings/789'.

        Returns:
            Success with finding details, or error.
        """
        cred_error = self._validate_credentials()
        if cred_error:
            return cred_error

        finding_name = kwargs.get("finding_name")
        if not finding_name:
            return self.error_result(
                "Missing required parameter: finding_name",
                error_type="ValidationError",
            )

        try:
            response = await self.http_request(
                url=f"{GCP_SCC_BASE_URL}/{finding_name}",
            )
            finding = response.json()

            return self.success_result(data=finding)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("gcp_scc_finding_not_found", finding_name=finding_name)
                return self.success_result(
                    not_found=True,
                    data={"finding_name": finding_name},
                )
            self.log_error("gcp_scc_get_finding_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("gcp_scc_get_finding_failed", error=e)
            return self.error_result(e)

class UpdateFindingStateAction(_GCPSCCBase):
    """Update the state of a security finding."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Set a finding's state (ACTIVE, INACTIVE, or MUTED).

        Args:
            **kwargs:
                finding_name (str): Full resource name of the finding.
                state (str): New state — one of ACTIVE, INACTIVE, MUTED.

        Returns:
            Success with updated finding, or error.
        """
        cred_error = self._validate_credentials()
        if cred_error:
            return cred_error

        finding_name = kwargs.get("finding_name")
        if not finding_name:
            return self.error_result(
                "Missing required parameter: finding_name",
                error_type="ValidationError",
            )

        state = kwargs.get("state")
        if not state:
            return self.error_result(
                "Missing required parameter: state",
                error_type="ValidationError",
            )

        state = state.upper()
        if state not in VALID_FINDING_STATES:
            return self.error_result(
                f"Invalid state: {state}. Must be one of: {', '.join(sorted(VALID_FINDING_STATES))}",
                error_type="ValidationError",
            )

        try:
            response = await self.http_request(
                url=f"{GCP_SCC_BASE_URL}/{finding_name}:setState",
                method="POST",
                json_data={"state": state},
            )
            updated_finding = response.json()

            return self.success_result(
                data={
                    "finding": updated_finding,
                    "new_state": state,
                },
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "gcp_scc_finding_not_found_for_update", finding_name=finding_name
                )
                return self.success_result(
                    not_found=True,
                    data={"finding_name": finding_name},
                )
            self.log_error("gcp_scc_update_finding_state_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("gcp_scc_update_finding_state_failed", error=e)
            return self.error_result(e)

class ListSourcesAction(_GCPSCCBase):
    """List security sources in the organization."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List SCC sources (Security Health Analytics, ETD, etc.).

        Args:
            **kwargs:
                page_size (int, optional): Number of results (default: 100).
                page_token (str, optional): Pagination token.

        Returns:
            Success with list of sources, or error.
        """
        cred_error = self._validate_credentials()
        if cred_error:
            return cred_error

        org_error = self._validate_org_id()
        if org_error:
            return org_error

        parent = self._get_org_parent()

        page_size = kwargs.get("page_size", DEFAULT_PAGE_SIZE)
        if isinstance(page_size, str):
            try:
                page_size = int(page_size)
            except ValueError:
                return self.error_result(
                    f"Invalid page_size: {page_size}", error_type="ValidationError"
                )
        page_size = min(page_size, MAX_PAGE_SIZE)

        params: dict[str, Any] = {"pageSize": page_size}

        page_token = kwargs.get("page_token")
        if page_token:
            params["pageToken"] = page_token

        try:
            response = await self.http_request(
                url=f"{GCP_SCC_BASE_URL}/{parent}/sources",
                params=params,
            )
            data = response.json()

            sources = data.get("sources", [])
            next_page_token = data.get("nextPageToken")

            return self.success_result(
                data={
                    "sources": sources,
                    "total_results": len(sources),
                    "next_page_token": next_page_token,
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("gcp_scc_list_sources_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("gcp_scc_list_sources_failed", error=e)
            return self.error_result(e)

class ListAssetsAction(_GCPSCCBase):
    """List cloud assets in the organization."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List GCP assets with optional filters.

        Args:
            **kwargs:
                filter (str, optional): SCC filter expression for assets.
                page_size (int, optional): Number of results (default: 100).
                page_token (str, optional): Pagination token.
                order_by (str, optional): Sort order.

        Returns:
            Success with list of assets, or error.
        """
        cred_error = self._validate_credentials()
        if cred_error:
            return cred_error

        org_error = self._validate_org_id()
        if org_error:
            return org_error

        parent = self._get_org_parent()

        page_size = kwargs.get("page_size", DEFAULT_PAGE_SIZE)
        if isinstance(page_size, str):
            try:
                page_size = int(page_size)
            except ValueError:
                return self.error_result(
                    f"Invalid page_size: {page_size}", error_type="ValidationError"
                )
        page_size = min(page_size, MAX_PAGE_SIZE)

        params: dict[str, Any] = {"pageSize": page_size}

        asset_filter = kwargs.get("filter")
        if asset_filter:
            params["filter"] = asset_filter

        page_token = kwargs.get("page_token")
        if page_token:
            params["pageToken"] = page_token

        order_by = kwargs.get("order_by")
        if order_by:
            params["orderBy"] = order_by

        try:
            response = await self.http_request(
                url=f"{GCP_SCC_BASE_URL}/{parent}/assets",
                params=params,
            )
            data = response.json()

            assets = data.get("listAssetsResults", [])
            next_page_token = data.get("nextPageToken")

            return self.success_result(
                data={
                    "assets": assets,
                    "total_results": len(assets),
                    "next_page_token": next_page_token,
                    "read_time": data.get("readTime"),
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("gcp_scc_list_assets_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("gcp_scc_list_assets_failed", error=e)
            return self.error_result(e)

class GetNotificationConfigAction(_GCPSCCBase):
    """Get a notification config by name."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get a SCC notification configuration.

        Args:
            **kwargs:
                config_name (str): Full resource name of the notification config,
                    e.g. 'organizations/123/notificationConfigs/my-config'.

        Returns:
            Success with notification config details, or error.
        """
        cred_error = self._validate_credentials()
        if cred_error:
            return cred_error

        config_name = kwargs.get("config_name")
        if not config_name:
            return self.error_result(
                "Missing required parameter: config_name",
                error_type="ValidationError",
            )

        try:
            response = await self.http_request(
                url=f"{GCP_SCC_BASE_URL}/{config_name}",
            )
            config = response.json()

            return self.success_result(data=config)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "gcp_scc_notification_config_not_found", config_name=config_name
                )
                return self.success_result(
                    not_found=True,
                    data={"config_name": config_name},
                )
            self.log_error("gcp_scc_get_notification_config_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("gcp_scc_get_notification_config_failed", error=e)
            return self.error_result(e)

class ListNotificationConfigsAction(_GCPSCCBase):
    """List notification configs for the organization."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List SCC notification configurations.

        Args:
            **kwargs:
                page_size (int, optional): Number of results (default: 100).
                page_token (str, optional): Pagination token.

        Returns:
            Success with list of notification configs, or error.
        """
        cred_error = self._validate_credentials()
        if cred_error:
            return cred_error

        org_error = self._validate_org_id()
        if org_error:
            return org_error

        parent = self._get_org_parent()

        page_size = kwargs.get("page_size", DEFAULT_PAGE_SIZE)
        if isinstance(page_size, str):
            try:
                page_size = int(page_size)
            except ValueError:
                return self.error_result(
                    f"Invalid page_size: {page_size}", error_type="ValidationError"
                )
        page_size = min(page_size, MAX_PAGE_SIZE)

        params: dict[str, Any] = {"pageSize": page_size}

        page_token = kwargs.get("page_token")
        if page_token:
            params["pageToken"] = page_token

        try:
            response = await self.http_request(
                url=f"{GCP_SCC_BASE_URL}/{parent}/notificationConfigs",
                params=params,
            )
            data = response.json()

            configs = data.get("notificationConfigs", [])
            next_page_token = data.get("nextPageToken")

            return self.success_result(
                data={
                    "notification_configs": configs,
                    "total_results": len(configs),
                    "next_page_token": next_page_token,
                },
            )
        except httpx.HTTPStatusError as e:
            self.log_error("gcp_scc_list_notification_configs_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("gcp_scc_list_notification_configs_failed", error=e)
            return self.error_result(e)

"""Microsoft Defender for Cloud integration actions for the Naxos framework.

Built from Azure Resource Manager REST API. Uses OAuth2 client credentials
flow (same pattern as Microsoft Sentinel and Defender for Endpoint).
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ALERTS_API_VERSION,
    ARM_BASE_URL,
    ASSESSMENTS_API_VERSION,
    CREDENTIAL_CLIENT_ID,
    CREDENTIAL_CLIENT_SECRET,
    DEFAULT_ALERT_LIMIT,
    DEFAULT_ASSESSMENT_LIMIT,
    DEFAULT_RECOMMENDATION_LIMIT,
    DEFAULT_TIMEOUT,
    ENDPOINT_ALERT_BY_NAME,
    ENDPOINT_ALERT_STATUS,
    ENDPOINT_ALERTS,
    ENDPOINT_ASSESSMENTS,
    ENDPOINT_RECOMMENDATION_BY_ID,
    ENDPOINT_RECOMMENDATIONS,
    ENDPOINT_SECURE_SCORES,
    ENDPOINT_SUBSCRIPTIONS,
    ERROR_INVALID_LIMIT,
    ERROR_INVALID_STATUS,
    ERROR_MISSING_ALERT_NAME,
    ERROR_MISSING_CREDENTIALS,
    ERROR_MISSING_LOCATION,
    ERROR_MISSING_RECOMMENDATION_ID,
    ERROR_MISSING_RESOURCE_ID,
    ERROR_MISSING_STATUS,
    ERROR_MISSING_SUBSCRIPTION_ID,
    ERROR_MISSING_TENANT_ID,
    ERROR_TOKEN_FAILED,
    ERROR_TYPE_VALIDATION,
    JSON_ACCESS_TOKEN,
    JSON_NEXT_LINK,
    JSON_VALUE,
    LOGIN_SCOPE,
    LOGIN_URL,
    SECURE_SCORES_API_VERSION,
    SECURITY_API_VERSION,
    SETTINGS_SUBSCRIPTION_ID,
    SETTINGS_TENANT_ID,
    SUBSCRIPTIONS_API_VERSION,
    VALID_ALERT_STATUSES,
)

logger = get_logger(__name__)

class _AzureDefenderBase(IntegrationAction):
    """Shared base class for Azure Defender for Cloud actions.

    Handles OAuth2 token acquisition (client credentials flow) and provides
    common helpers for ARM API calls. Follows the same pattern as the
    MS Sentinel and Defender for Endpoint integrations.
    """

    def _get_tenant_id(self) -> str:
        """Get tenant ID from settings."""
        tenant_id = self.settings.get(SETTINGS_TENANT_ID)
        if not tenant_id:
            raise ValueError(ERROR_MISSING_TENANT_ID)
        return tenant_id

    def _get_subscription_id(self) -> str:
        """Get subscription ID from settings."""
        subscription_id = self.settings.get(SETTINGS_SUBSCRIPTION_ID)
        if not subscription_id:
            raise ValueError(ERROR_MISSING_SUBSCRIPTION_ID)
        return subscription_id

    def _validate_credentials(self) -> tuple[str, str]:
        """Validate and return client_id and client_secret from credentials.

        Returns:
            Tuple of (client_id, client_secret)

        Raises:
            ValueError: If credentials are missing.
        """
        client_id = self.credentials.get(CREDENTIAL_CLIENT_ID)
        client_secret = self.credentials.get(CREDENTIAL_CLIENT_SECRET)
        if not client_id or not client_secret:
            raise ValueError(ERROR_MISSING_CREDENTIALS)
        return client_id, client_secret

    async def _get_access_token(self) -> str:
        """Acquire OAuth2 access token for Azure Resource Manager API.

        Uses the v2.0 token endpoint with client_credentials grant type.

        Returns:
            Bearer access token string.

        Raises:
            Exception: If token acquisition fails.
        """
        tenant_id = self._get_tenant_id()
        client_id, client_secret = self._validate_credentials()

        token_url = LOGIN_URL.format(tenant_id=tenant_id)

        login_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": LOGIN_SCOPE,
            "grant_type": "client_credentials",
        }

        try:
            response = await self.http_request(
                token_url,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=login_payload,
                timeout=DEFAULT_TIMEOUT,
            )
            token_data = response.json()
            return token_data[JSON_ACCESS_TOKEN]
        except httpx.HTTPStatusError as e:
            raise Exception(
                f"{ERROR_TOKEN_FAILED}: HTTP {e.response.status_code}"
            ) from e
        except KeyError as e:
            raise Exception(f"{ERROR_TOKEN_FAILED}: Invalid response format") from e

    async def _arm_request(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        api_version: str = SECURITY_API_VERSION,
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
    ) -> httpx.Response:
        """Make an authenticated ARM API request.

        Args:
            endpoint: API path (appended to ARM_BASE_URL).
            method: HTTP method.
            api_version: API version query parameter.
            params: Additional query parameters.
            json_data: JSON body for POST/PUT/PATCH.

        Returns:
            httpx.Response object.
        """
        access_token = await self._get_access_token()

        query_params = {"api-version": api_version}
        if params:
            query_params.update(params)

        url = f"{ARM_BASE_URL}{endpoint}"

        return await self.http_request(
            url,
            method=method,
            headers={"Authorization": f"Bearer {access_token}"},
            params=query_params,
            json_data=json_data,
            timeout=self.settings.get("timeout", DEFAULT_TIMEOUT),
        )

    async def _fetch_paginated(
        self,
        endpoint: str,
        *,
        api_version: str = SECURITY_API_VERSION,
        limit: int = 100,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch paginated results from an ARM API endpoint.

        Follows nextLink pagination until the limit is reached or
        there are no more pages.

        Args:
            endpoint: Initial API path.
            api_version: API version.
            limit: Maximum number of results to return.
            params: Additional query parameters for the first request.

        Returns:
            List of result items.
        """
        results: list[dict[str, Any]] = []
        access_token = await self._get_access_token()

        query_params: dict[str, Any] = {"api-version": api_version}
        if params:
            query_params.update(params)

        url = f"{ARM_BASE_URL}{endpoint}"

        while True:
            response = await self.http_request(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=query_params,
                timeout=self.settings.get("timeout", DEFAULT_TIMEOUT),
            )
            data = response.json()

            for item in data.get(JSON_VALUE, []):
                if len(results) >= limit:
                    return results
                results.append(item)

            next_link = data.get(JSON_NEXT_LINK)
            if not next_link or len(results) >= limit:
                break

            # nextLink is a full URL with api-version already included
            url = next_link
            query_params = {}

        return results

class HealthCheckAction(_AzureDefenderBase):
    """Verify API connectivity by listing subscriptions."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity to Azure Resource Manager.

        Lists subscriptions accessible by the service principal to verify
        that credentials and permissions are correctly configured.

        Returns:
            Success result with subscription count and names.
        """
        try:
            response = await self._arm_request(
                ENDPOINT_SUBSCRIPTIONS,
                api_version=SUBSCRIPTIONS_API_VERSION,
            )
            data = response.json()
            subscriptions = data.get(JSON_VALUE, [])

            subscription_names = [
                sub.get("displayName", sub.get("subscriptionId", "unknown"))
                for sub in subscriptions
            ]

            return self.success_result(
                data={
                    "healthy": True,
                    "subscription_count": len(subscriptions),
                    "subscriptions": subscription_names,
                }
            )
        except Exception as e:
            self.log_error("health_check_failed", error=e)
            return self.error_result(e)

class ListAlertsAction(_AzureDefenderBase):
    """List security alerts from Defender for Cloud."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List security alerts for the configured subscription.

        Args:
            limit: Maximum number of alerts to return (default: 100).

        Returns:
            Success result with alerts list and count.
        """
        limit = kwargs.get("limit", DEFAULT_ALERT_LIMIT)

        if not isinstance(limit, int) or limit <= 0:
            return self.error_result(
                ERROR_INVALID_LIMIT, error_type=ERROR_TYPE_VALIDATION
            )

        try:
            subscription_id = self._get_subscription_id()
            endpoint = ENDPOINT_ALERTS.format(subscription_id=subscription_id)

            alerts = await self._fetch_paginated(
                endpoint,
                api_version=ALERTS_API_VERSION,
                limit=limit,
            )

            return self.success_result(
                data={
                    "total_alerts": len(alerts),
                    "alerts": alerts,
                }
            )
        except Exception as e:
            self.log_error("list_alerts_failed", error=e)
            return self.error_result(e)

class GetAlertAction(_AzureDefenderBase):
    """Get details of a specific security alert."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get alert details by name.

        Args:
            alert_name: The alert name (GUID).
            location: Azure region where the alert was generated
                      (e.g. 'centralus').

        Returns:
            Success result with alert details.
        """
        alert_name = kwargs.get("alert_name")
        location = kwargs.get("location")

        if not alert_name:
            return self.error_result(
                ERROR_MISSING_ALERT_NAME, error_type=ERROR_TYPE_VALIDATION
            )
        if not location:
            return self.error_result(
                ERROR_MISSING_LOCATION, error_type=ERROR_TYPE_VALIDATION
            )

        try:
            subscription_id = self._get_subscription_id()
            endpoint = ENDPOINT_ALERT_BY_NAME.format(
                subscription_id=subscription_id,
                location=location,
                alert_name=alert_name,
            )

            response = await self._arm_request(endpoint, api_version=ALERTS_API_VERSION)
            alert = response.json()

            return self.success_result(data=alert)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "azure_defender_alert_not_found",
                    alert_name=alert_name,
                )
                return self.success_result(
                    not_found=True,
                    data={"alert_name": alert_name, "location": location},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("get_alert_failed", error=e)
            return self.error_result(e)

class UpdateAlertStatusAction(_AzureDefenderBase):
    """Update the status of a security alert."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update alert status (dismiss, activate, resolve, inProgress).

        The Defender for Cloud API uses a POST to a status-specific endpoint
        rather than a PATCH on the alert resource itself.

        Args:
            alert_name: The alert name (GUID).
            location: Azure region where the alert was generated.
            status: New status (dismiss, activate, resolve, inProgress).

        Returns:
            Success result confirming the status change.
        """
        alert_name = kwargs.get("alert_name")
        location = kwargs.get("location")
        status = kwargs.get("status")

        if not alert_name:
            return self.error_result(
                ERROR_MISSING_ALERT_NAME, error_type=ERROR_TYPE_VALIDATION
            )
        if not location:
            return self.error_result(
                ERROR_MISSING_LOCATION, error_type=ERROR_TYPE_VALIDATION
            )
        if not status:
            return self.error_result(
                ERROR_MISSING_STATUS, error_type=ERROR_TYPE_VALIDATION
            )
        if status not in VALID_ALERT_STATUSES:
            return self.error_result(
                ERROR_INVALID_STATUS, error_type=ERROR_TYPE_VALIDATION
            )

        try:
            subscription_id = self._get_subscription_id()
            endpoint = ENDPOINT_ALERT_STATUS.format(
                subscription_id=subscription_id,
                location=location,
                alert_name=alert_name,
                status=status,
            )

            await self._arm_request(
                endpoint,
                method="POST",
                api_version=ALERTS_API_VERSION,
            )

            return self.success_result(
                data={
                    "alert_name": alert_name,
                    "new_status": status,
                    "message": f"Alert status updated to '{status}'",
                }
            )
        except Exception as e:
            self.log_error("update_alert_status_failed", error=e)
            return self.error_result(e)

class ListSecureScoresAction(_AzureDefenderBase):
    """List secure scores for the subscription."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all secure scores for the configured subscription.

        Secure scores represent the overall security posture as a percentage.
        Each score corresponds to a security control group.

        Returns:
            Success result with secure scores.
        """
        try:
            subscription_id = self._get_subscription_id()
            endpoint = ENDPOINT_SECURE_SCORES.format(subscription_id=subscription_id)

            response = await self._arm_request(
                endpoint, api_version=SECURE_SCORES_API_VERSION
            )
            data = response.json()
            scores = data.get(JSON_VALUE, [])

            return self.success_result(
                data={
                    "total_scores": len(scores),
                    "scores": scores,
                }
            )
        except Exception as e:
            self.log_error("list_secure_scores_failed", error=e)
            return self.error_result(e)

class ListRecommendationsAction(_AzureDefenderBase):
    """List security recommendations."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List security recommendations for the configured subscription.

        Recommendations are actionable suggestions to improve security
        posture (e.g., enable MFA, encrypt storage, patch VMs).

        Args:
            limit: Maximum number of recommendations (default: 100).

        Returns:
            Success result with recommendations list.
        """
        limit = kwargs.get("limit", DEFAULT_RECOMMENDATION_LIMIT)

        if not isinstance(limit, int) or limit <= 0:
            return self.error_result(
                ERROR_INVALID_LIMIT, error_type=ERROR_TYPE_VALIDATION
            )

        try:
            subscription_id = self._get_subscription_id()
            endpoint = ENDPOINT_RECOMMENDATIONS.format(subscription_id=subscription_id)

            recommendations = await self._fetch_paginated(
                endpoint,
                api_version=SECURITY_API_VERSION,
                limit=limit,
            )

            return self.success_result(
                data={
                    "total_recommendations": len(recommendations),
                    "recommendations": recommendations,
                }
            )
        except Exception as e:
            self.log_error("list_recommendations_failed", error=e)
            return self.error_result(e)

class GetRecommendationAction(_AzureDefenderBase):
    """Get details of a specific security recommendation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get recommendation details by ID.

        Args:
            recommendation_id: The recommendation resource name (GUID).

        Returns:
            Success result with recommendation details.
        """
        recommendation_id = kwargs.get("recommendation_id")

        if not recommendation_id:
            return self.error_result(
                ERROR_MISSING_RECOMMENDATION_ID, error_type=ERROR_TYPE_VALIDATION
            )

        try:
            subscription_id = self._get_subscription_id()
            endpoint = ENDPOINT_RECOMMENDATION_BY_ID.format(
                subscription_id=subscription_id,
                recommendation_id=recommendation_id,
            )

            response = await self._arm_request(
                endpoint, api_version=SECURITY_API_VERSION
            )
            recommendation = response.json()

            return self.success_result(data=recommendation)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "azure_defender_recommendation_not_found",
                    recommendation_id=recommendation_id,
                )
                return self.success_result(
                    not_found=True,
                    data={"recommendation_id": recommendation_id},
                )
            return self.error_result(e)
        except Exception as e:
            self.log_error("get_recommendation_failed", error=e)
            return self.error_result(e)

class ListAssessmentsAction(_AzureDefenderBase):
    """List security assessments for a specific resource."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List security assessments for a given Azure resource.

        Assessments evaluate a resource against security recommendations
        and provide a status (healthy, unhealthy, notApplicable).

        Args:
            resource_id: Full ARM resource ID to assess (e.g.,
                /subscriptions/{sub}/resourceGroups/{rg}/providers/...).
            limit: Maximum number of assessments (default: 100).

        Returns:
            Success result with assessments list.
        """
        resource_id = kwargs.get("resource_id")
        limit = kwargs.get("limit", DEFAULT_ASSESSMENT_LIMIT)

        if not resource_id:
            return self.error_result(
                ERROR_MISSING_RESOURCE_ID, error_type=ERROR_TYPE_VALIDATION
            )
        if not isinstance(limit, int) or limit <= 0:
            return self.error_result(
                ERROR_INVALID_LIMIT, error_type=ERROR_TYPE_VALIDATION
            )

        try:
            # Assessments endpoint is scoped to a resource, not subscription
            endpoint = ENDPOINT_ASSESSMENTS.format(resource_id=resource_id)

            assessments = await self._fetch_paginated(
                endpoint,
                api_version=ASSESSMENTS_API_VERSION,
                limit=limit,
            )

            return self.success_result(
                data={
                    "resource_id": resource_id,
                    "total_assessments": len(assessments),
                    "assessments": assessments,
                }
            )
        except Exception as e:
            self.log_error("list_assessments_failed", error=e)
            return self.error_result(e)

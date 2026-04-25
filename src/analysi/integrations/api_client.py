"""Integration API Client for worker to REST API communication."""

from typing import Any
from uuid import UUID

import httpx

from analysi.common.internal_client import InternalAsyncClient
from analysi.common.retry_config import http_retry_policy
from analysi.config.logging import get_logger
from analysi.integrations.config import IntegrationConfig

logger = get_logger(__name__)


class IntegrationAPIClient:
    """Client for worker to communicate with backend REST API."""

    def __init__(self, base_url: str | None = None, timeout: int = 30):
        """
        Initialize API client.

        Args:
            base_url: Backend API base URL (defaults to config)
            timeout: Request timeout in seconds
        """
        if base_url is None:
            base_url = IntegrationConfig.API_BASE_URL
        self.base_url = base_url
        self.timeout = timeout
        headers = {}
        if IntegrationConfig.API_AUTH_TOKEN:
            headers["X-API-Key"] = IntegrationConfig.API_AUTH_TOKEN
        self.client = InternalAsyncClient(
            base_url=base_url, timeout=timeout, headers=headers
        )

    @http_retry_policy()
    async def get_credential(
        self, tenant_id: str, credential_id: UUID
    ) -> dict[str, Any]:
        """
        Fetch decrypted credential from API.

        Args:
            tenant_id: Tenant identifier
            credential_id: Credential UUID

        Returns:
            Decrypted credential data

        Raises:
            httpx.HTTPError: On API communication errors
        """
        url = f"/v1/{tenant_id}/credentials/{credential_id}"

        try:
            response = await self.client.get(url)
            response.raise_for_status()

            # Response includes decrypted secret
            data = response.json()
            logger.debug(
                "successfully_fetched_credential_for_tenant",
                credential_id=credential_id,
                tenant_id=tenant_id,
            )
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(
                    "credential_not_found_for_tenant",
                    credential_id=credential_id,
                    tenant_id=tenant_id,
                )
                raise
            logger.error("failed_to_fetch_credential", error=str(e))
            raise
        except Exception as e:
            logger.error("unexpected_error_fetching_credential", error=str(e))
            raise

    @http_retry_policy()
    async def update_health_status(
        self,
        tenant_id: str,
        integration_id: str,
        health_status: str,
        health_message: str | None = None,
    ) -> dict[str, Any]:
        """
        Update integration health status with retry logic.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier
            health_status: Health status (healthy/degraded/unhealthy)
            health_message: Optional status message

        Returns:
            Updated integration data
        """
        url = f"/v1/{tenant_id}/integrations/{integration_id}/health"

        payload = {"health_status": health_status}
        if health_message:
            payload["health_message"] = health_message

        try:
            response = await self.client.patch(url, json=payload)
            response.raise_for_status()

            data = response.json()
            logger.info(
                "updated_health_status",
                integration_id=integration_id,
                health_status=health_status,
            )
            return data

        except httpx.HTTPStatusError as e:
            logger.error("failed_to_update_health_status", error=str(e))
            raise
        except Exception as e:
            logger.error("unexpected_error_updating_health_status", error=str(e))
            raise

    @http_retry_policy()
    async def get_integration(
        self, tenant_id: str, integration_id: str
    ) -> dict[str, Any] | None:
        """
        Get integration configuration from API.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier

        Returns:
            Integration data or None if not found
        """
        url = f"/v1/{tenant_id}/integrations/{integration_id}"

        try:
            response = await self.client.get(url)
            response.raise_for_status()

            data = response.json()
            logger.debug(
                "successfully_fetched_integration_for_tenant",
                integration_id=integration_id,
                tenant_id=tenant_id,
            )
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(
                    "integration_not_found_for_tenant",
                    integration_id=integration_id,
                    tenant_id=tenant_id,
                )
                return None
            logger.error("failed_to_fetch_integration", error=str(e))
            raise
        except Exception as e:
            logger.error("unexpected_error_fetching_integration", error=str(e))
            raise

    async def list_integration_credentials(
        self, tenant_id: str, integration_id: str
    ) -> list[dict[str, Any]]:
        """
        List credentials associated with an integration.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier

        Returns:
            List of credential information
        """
        url = f"/v1/{tenant_id}/credentials/integrations/{integration_id}"

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            logger.error("failed_to_list_credentials", error=str(e))
            raise
        except Exception as e:
            logger.error("unexpected_error_listing_credentials", error=str(e))
            raise

    @http_retry_policy()
    async def upsert_knowledge_unit_table(
        self,
        tenant_id: str,
        table_name: str,
        content: dict[str, Any],
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create or update a Table Knowledge Unit (upsert pattern).

        Searches for existing table by name, updates if found, creates if not.

        Args:
            tenant_id: Tenant identifier
            table_name: Name of the table
            content: Table content with schema and rows
            description: Optional table description
            tags: Optional list of tags/categories

        Returns:
            Created or updated table KU data
        """
        # First, list all tables to find one matching the name
        list_url = f"/v1/{tenant_id}/knowledge-units/tables"

        try:
            # Search for existing table by name
            params = {"limit": 100}  # Reasonable limit for search
            response = await self.client.get(list_url, params=params)
            response.raise_for_status()

            tables_data = response.json()
            existing_table = None

            # After InternalAsyncClient unwrap, tables_data is a list
            for table in tables_data or []:
                if table.get("name") == table_name:
                    existing_table = table
                    break

            # Prepare payload
            payload = {
                "name": table_name,
                "content": content,
            }
            if description:
                payload["description"] = description
            if tags:
                payload["categories"] = tags

            # Update or create
            if existing_table:
                # Update existing table
                table_id = existing_table["id"]
                update_url = f"/v1/{tenant_id}/knowledge-units/tables/{table_id}"
                response = await self.client.put(update_url, json=payload)
                response.raise_for_status()
                logger.info(
                    "updated_existing_table_ku_id",
                    table_name=table_name,
                    table_id=table_id,
                )
            else:
                # Create new table
                response = await self.client.post(list_url, json=payload)
                response.raise_for_status()
                logger.info("created_new_table_ku", table_name=table_name)

            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(
                "failed_to_upsert_table_ku", table_name=table_name, error=str(e)
            )
            raise
        except Exception as e:
            logger.error(
                "unexpected_error_upserting_table_ku",
                table_name=table_name,
                error=str(e),
            )
            raise

    @http_retry_policy()
    async def trigger_alert_analysis(
        self, tenant_id: str, alert_id: str
    ) -> dict[str, Any]:
        """
        Trigger alert analysis workflow.

        Args:
            tenant_id: Tenant identifier
            alert_id: Alert identifier

        Returns:
            Analysis trigger response
        """
        url = f"/v1/{tenant_id}/alerts/{alert_id}/analyze"

        try:
            response = await self.client.post(url)
            response.raise_for_status()

            data = response.json()
            logger.debug("triggered_analysis_for_alert", alert_id=alert_id)
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(
                    "alert_not_found_for_tenant", alert_id=alert_id, tenant_id=tenant_id
                )
                raise
            logger.error("failed_to_trigger_alert_analysis", error=str(e))
            raise
        except Exception as e:
            logger.error("unexpected_error_triggering_alert_analysis", error=str(e))
            raise

    async def close(self):
        """Close HTTP client connections."""
        await self.client.aclose()

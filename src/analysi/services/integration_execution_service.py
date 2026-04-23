"""Service for executing integration tools and capturing results."""

import asyncio
import time
from typing import Any

from genson import SchemaBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.integrations.framework.loader import IntegrationLoader
from analysi.integrations.framework.registry import (
    get_registry,
)
from analysi.models.integration import Integration

logger = get_logger(__name__)


class IntegrationExecutionService:
    """
    Service for executing integration tools dynamically.

    Enables testing integration tools before writing Cy scripts.
    Supports schema capture for understanding tool outputs.
    """

    def __init__(self, session: AsyncSession):
        """Initialize service with database session."""
        self.session = session
        self.framework = get_registry()
        self.loader = IntegrationLoader()

    async def execute_tool(
        self,
        tenant_id: str,
        integration_id: str,
        action_id: str,
        arguments: dict[str, Any],
        timeout_seconds: int = 30,
        capture_schema: bool = False,
    ) -> dict[str, Any]:
        """
        Execute an integration tool and return results.

        IMPORTANT: This method requires the integration INSTANCE ID (e.g., "splunk-prod",
        "virustotal-main"), NOT the integration type (e.g., "splunk", "virustotal").

        Args:
            tenant_id: Tenant ID for integration configuration
            integration_id: Integration INSTANCE ID (e.g., "splunk-prod", "virustotal-main", "echo-edr-1")
                           This is the configured instance name from the database,
                           NOT the integration type.
            action_id: Action identifier (e.g., "ip_reputation", "health_check")
            arguments: Tool-specific arguments
            timeout_seconds: Execution timeout in seconds
            capture_schema: If True, generate JSON schema from output

        Returns:
            {
                "status": "success" | "error" | "timeout",
                "output": Any | None,
                "output_schema": dict | None,  # If capture_schema=True
                "error": str | None,
                "execution_time_ms": int | None
            }

        Raises:
            ValueError: If integration or action not found

        Example:
            # Execute health check on Splunk production instance
            result = await service.execute_tool(
                tenant_id="my-tenant",
                integration_id="splunk-prod",  # Instance ID, not type!
                action_id="health_check",
                arguments={}
            )

            # Execute IP reputation on VirusTotal main instance
            result = await service.execute_tool(
                tenant_id="my-tenant",
                integration_id="virustotal-main",  # Instance ID, not type!
                action_id="ip_reputation",
                arguments={"ip": "8.8.8.8"},
                capture_schema=True
            )
        """
        start_time = time.time()

        try:
            # Validate integration exists and is configured
            integration = await self._validate_integration_exists(
                integration_id, tenant_id
            )

            # Get integration type from database record
            integration_type = integration.integration_type

            # Validate action exists in manifest
            await self._validate_action_exists(integration_type, action_id)

            # Get integration settings
            settings = integration.settings or {}

            # Load credentials for the integration
            credentials = await self._load_integration_credentials(
                tenant_id, integration_id
            )

            # Build execution context
            ctx = {
                "tenant_id": tenant_id,
                "integration_id": integration_id,
                "job_id": None,
                "run_id": None,
                "session": self.session,
            }

            # Load action
            action = await self.loader.load_action(
                integration_id=integration_type,
                action_id=action_id,
                action_metadata={"type": "tool"},  # Assume tool type for execute_tool
                settings=settings,
                credentials=credentials,
                ctx=ctx,
            )

            # Execute with timeout
            try:
                result = await asyncio.wait_for(
                    action.execute(**arguments), timeout=timeout_seconds
                )
                execution_time_ms = int((time.time() - start_time) * 1000)

                # Check if result has standard format
                if isinstance(result, dict) and "status" in result:
                    status = "success" if result["status"] == "success" else "error"
                    output = result.get("data", result)
                    error = result.get("error") if status == "error" else None
                else:
                    # Non-standard result - treat as success
                    status = "success"
                    output = result
                    error = None

                # Generate schema if requested
                output_schema = None
                if capture_schema and output is not None:
                    output_schema = self._generate_schema_from_output(output)

                return {
                    "status": status,
                    "output": output,
                    "output_schema": output_schema,
                    "error": error,
                    "execution_time_ms": execution_time_ms,
                }

            except TimeoutError:
                execution_time_ms = int((time.time() - start_time) * 1000)
                logger.warning(
                    "tool_execution_timed_out",
                    integration_id=integration_id,
                    action_id=action_id,
                    timeout_seconds=timeout_seconds,
                )
                return {
                    "status": "timeout",
                    "output": None,
                    "output_schema": None,
                    "error": f"Execution timed out after {timeout_seconds} seconds",
                    "execution_time_ms": execution_time_ms,
                }

        except ValueError as e:
            # Validation errors (integration not found, action not found, etc.)
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error("tool_execution_validation_failed", error=str(e))
            return {
                "status": "error",
                "output": None,
                "output_schema": None,
                "error": str(e),
                "execution_time_ms": execution_time_ms,
            }

        except Exception as e:
            # Unexpected errors
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.exception(
                "tool_execution_failed_with_unexpected_error", error=str(e)
            )
            return {
                "status": "error",
                "output": None,
                "output_schema": None,
                "error": f"Unexpected error: {e!s}",
                "execution_time_ms": execution_time_ms,
            }

    async def _validate_integration_exists(
        self, integration_id: str, tenant_id: str
    ) -> Integration:
        """
        Validate that integration exists and is configured for tenant.

        Args:
            integration_id: Integration identifier
            tenant_id: Tenant ID

        Returns:
            Integration model if found

        Raises:
            ValueError: If integration not found or not configured
        """
        # Query database for integration
        stmt = (
            select(Integration)
            .where(Integration.tenant_id == tenant_id)
            .where(Integration.integration_id == integration_id)
        )
        result = await self.session.execute(stmt)
        integration = result.scalar_one_or_none()

        if not integration:
            raise ValueError(
                f"Integration '{integration_id}' not found for tenant '{tenant_id}'"
            )

        if not integration.enabled:
            raise ValueError(
                f"Integration '{integration_id}' is disabled. Enable it to use this tool."
            )

        return integration

    async def _validate_action_exists(
        self, integration_type: str, action_id: str
    ) -> bool:
        """
        Validate that action exists for integration.

        Args:
            integration_type: Integration type from manifest
            action_id: Action identifier

        Returns:
            True if action exists

        Raises:
            ValueError: If action not found
        """
        # Get manifest
        manifest = self.framework.get_integration(integration_type)
        if not manifest:
            raise ValueError(
                f"Integration type '{integration_type}' not found in framework"
            )

        # Find action in manifest
        action_found = False
        for action in manifest.actions:
            if action.id == action_id:
                action_found = True
                break

        if not action_found:
            available_actions = [action.id for action in manifest.actions]
            raise ValueError(
                f"Action '{action_id}' not found in integration '{integration_type}'. "
                f"Available actions: {', '.join(available_actions)}"
            )

        return True

    async def _load_integration_credentials(
        self, tenant_id: str, integration_id: str
    ) -> dict[str, Any]:
        """
        Load decrypted credentials for an integration.

        Finds the primary credential associated with the integration and decrypts it.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration instance ID (e.g., "splunk-local")

        Returns:
            Decrypted credentials dict, or empty dict if no credentials configured
        """
        from uuid import UUID

        from analysi.services.credential_service import CredentialService

        credential_service = CredentialService(self.session)

        try:
            # Get all credentials associated with this integration
            integration_creds = await credential_service.get_integration_credentials(
                tenant_id, integration_id
            )

            if not integration_creds:
                logger.debug(
                    "no_credentials_configured",
                    integration_id=integration_id,
                )
                return {}

            # Find primary credential, or use first available
            primary_cred = None
            for cred in integration_creds:
                if cred.get("is_primary", False):
                    primary_cred = cred
                    break

            if not primary_cred:
                # Use first credential if no primary
                primary_cred = integration_creds[0]

            # Decrypt the credential
            credential_id = UUID(primary_cred["id"])
            decrypted = await credential_service.get_credential(
                tenant_id, credential_id
            )

            if decrypted:
                logger.debug("loaded_credentials", integration_id=integration_id)
                return decrypted

            logger.warning(
                "credential_decryption_failed",
                credential_id=str(credential_id),
                integration_id=integration_id,
            )
            return {}

        except Exception as e:
            logger.warning(
                "failed_to_load_credentials",
                integration_id=integration_id,
                error=str(e),
            )
            return {}

    def _generate_schema_from_output(self, output: Any) -> dict[str, Any]:
        """
        Generate JSON schema from tool output using genson.

        Args:
            output: Tool output (dict, list, or primitive)

        Returns:
            JSON Schema representation of output
        """
        try:
            builder = SchemaBuilder()
            builder.add_object(output)
            schema = builder.to_schema()
            return schema
        except Exception as e:
            logger.warning("failed_to_generate_schema_from_output", error=str(e))
            # Return a basic schema as fallback
            return {
                "type": type(output).__name__,
                "error": f"Schema generation failed: {e!s}",
            }

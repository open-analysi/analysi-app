"""
Cy Native Functions for Artifacts Store Integration.

Native functions that can be called from within Cy scripts to store artifacts.
"""

from typing import Any

from analysi.common.retry_config import RetryableHTTPError, http_retry_policy
from analysi.config.logging import get_logger
from analysi.services.artifact_service import ArtifactService

logger = get_logger(__name__)


class CyArtifactFunctions:
    """Native functions for artifact management in Cy scripts."""

    def __init__(
        self, artifact_service: ArtifactService, execution_context: dict[str, Any]
    ):
        """
        Initialize Cy artifact functions with service and execution context.

        Args:
            artifact_service: ArtifactService instance
            execution_context: Current task/workflow execution context
        """
        self.artifact_service = artifact_service
        self.execution_context = execution_context

    async def store_artifact(
        self,
        name: str,
        artifact: str | bytes | dict[str, Any],
        tags: dict[str, Any] = None,
        artifact_type: str | None = None,
    ) -> str:
        """
        Store artifact from Cy script execution using internal service.

        This is the main native function that will be available in Cy scripts.
        Creates artifacts immediately using the internal ArtifactService and returns the real database ID.

        Args:
            name: Human-readable artifact name
            artifact: Content to store (string, bytes, or structured data)
            tags: Dictionary of tags (will be converted to list)
            artifact_type: Semantic type (timeline, activity_graph, etc.)

        Returns:
            Real artifact ID from database (not a mock ID)

        Raises:
            ValueError: If invalid parameters
            RuntimeError: If storage fails
        """
        try:
            # Get execution context
            context = self._get_execution_context()
            tenant_id = context.get("tenant_id", "default")

            # Prepare content - convert dict to JSON string if needed
            processed_content = self._prepare_content_for_storage(artifact)

            # Prepare tags - handle None and convert dict format if needed
            processed_tags = self._convert_tags_to_list(tags)

            # Parse context UUIDs properly - handle string UUIDs and None values
            def safe_uuid(value):
                """Safely convert to UUID, return None if invalid."""
                if not value:
                    return None
                try:
                    from uuid import UUID

                    if isinstance(value, UUID):
                        return value
                    return UUID(str(value))
                except (ValueError, TypeError):
                    return None

            # Create ArtifactCreate schema object
            from analysi.schemas.artifact import ArtifactCreate

            artifact_data = ArtifactCreate(
                name=name,
                content=processed_content,
                tags=processed_tags,
                artifact_type=artifact_type,
                task_run_id=safe_uuid(context.get("task_run_id")),
                workflow_run_id=safe_uuid(context.get("workflow_run_id")),
                workflow_node_instance_id=safe_uuid(
                    context.get("workflow_node_instance_id")
                ),
                analysis_id=safe_uuid(context.get("analysis_id")),
                source="cy_script",  # Artifacts from store_artifact() are cy_script provenance
            )

            # Database constraint requires at least one relationship field to be non-null
            # If all relationship fields are missing, we need to provide at least one
            if not any(
                [
                    artifact_data.task_run_id,
                    artifact_data.workflow_run_id,
                    artifact_data.workflow_node_instance_id,
                    artifact_data.analysis_id,
                ]
            ):
                if context.get("task_run_id"):
                    artifact_data.task_run_id = safe_uuid(context.get("task_run_id"))
                else:
                    # Create a temporary analysis_id for orphaned artifacts
                    import uuid

                    artifact_data.analysis_id = uuid.uuid4()

            # Debug logging
            logger.info("storeartifact_execution_context", context=context)
            logger.info(
                "store_artifact_creating",
                name=name,
                artifact_type=artifact_type,
            )

            # Always use REST API - pytest-httpx will handle mocking in tests
            artifact_id = await self._create_artifact_via_async_api(
                tenant_id, artifact_data
            )

            logger.info(
                "created_artifact_with_real_id", name=name, artifact_id=artifact_id
            )
            return str(artifact_id)

        except Exception as e:
            logger.error("failed_to_store_artifact", name=name, error=str(e))
            raise RuntimeError(f"Failed to store artifact: {e}")

    @http_retry_policy()
    async def _create_artifact_via_async_api(
        self, tenant_id: str, artifact_data
    ) -> str:
        """
        Create artifact via REST API using async HTTP client.

        Args:
            tenant_id: Tenant identifier
            artifact_data: ArtifactCreate schema instance

        Returns:
            Real artifact ID from database
        """
        import os

        # Get API base URL from environment variables
        backend_api_host = os.getenv("BACKEND_API_HOST", "localhost")
        backend_api_port = int(os.getenv("BACKEND_API_PORT", 8001))
        api_base_url = f"http://{backend_api_host}:{backend_api_port}"
        api_url = f"{api_base_url}/v1/{tenant_id}/artifacts"

        # Convert Pydantic model to dict for JSON serialization
        api_data = artifact_data.model_dump()

        # Convert UUID objects to strings for JSON serialization
        for key, value in api_data.items():
            if hasattr(value, "hex"):  # UUID objects have a hex attribute
                api_data[key] = str(value)

        # Remove None values
        api_data = {k: v for k, v in api_data.items() if v is not None}

        logger.debug(
            "store_artifact_request", tenant_id=tenant_id, keys=list(api_data.keys())
        )

        # Use InternalAsyncClient to auto-unwrap Sifnos {data, meta} envelope
        from analysi.common.internal_auth import internal_auth_headers
        from analysi.common.internal_client import InternalAsyncClient

        async with InternalAsyncClient(
            timeout=30.0, headers=internal_auth_headers()
        ) as client:
            response = await client.post(api_url, json=api_data)

            if response.status_code == 201:
                response_data = response.json()
                artifact_id = response_data["id"]
                logger.info(
                    "successfully_created_artifact_with_id", artifact_id=artifact_id
                )
                return artifact_id
            # Handle API errors - use RetryableHTTPError for tenacity
            error_detail = response.text
            logger.error("api_error_response", error_detail=error_detail)
            raise RetryableHTTPError(
                f"API call failed with status {response.status_code}: {error_detail}",
                response.status_code,
            )

    async def _async_create_artifact(self, tenant_id: str, artifact_data) -> str:
        """
        Async helper to create artifact using internal service.

        Args:
            tenant_id: Tenant identifier
            artifact_data: ArtifactCreate schema instance

        Returns:
            Artifact ID
        """
        from analysi.db.session import AsyncSessionLocal
        from analysi.services.artifact_service import ArtifactService

        logger.info("store_artifact: Creating database session")

        async with AsyncSessionLocal() as session:
            try:
                logger.info("store_artifact: Initializing ArtifactService")
                service = ArtifactService(session)

                logger.info("store_artifact: Calling service.create_artifact")
                artifact = await service.create_artifact(tenant_id, artifact_data)

                logger.info("store_artifact: Committing transaction")
                await session.commit()

                logger.info(
                    "store_artifact_created",
                    artifact_id=str(artifact.id),
                )
                return str(artifact.id)
            except Exception:
                logger.error("store_artifact: Error occurred, rolling back transaction")
                await session.rollback()
                raise
            finally:
                await session.close()

    def _get_execution_context(self) -> dict[str, Any]:
        """
        Extract relevant context from current execution.

        Returns:
            Dictionary with context fields (tenant_id, task_run_id, etc.)
        """
        return self.execution_context.copy()

    def _determine_mime_type(self, artifact: str | bytes | dict[str, Any]) -> str:
        """
        Determine MIME type based on artifact content.

        Args:
            artifact: Artifact content

        Returns:
            Appropriate MIME type
        """
        raise NotImplementedError("TODO: Implement _determine_mime_type")

    def _prepare_content_for_storage(
        self, artifact: str | bytes | dict[str, Any]
    ) -> str | bytes:
        """
        Prepare content for storage (serialize dicts to JSON, etc.).

        Args:
            artifact: Raw artifact content

        Returns:
            Content ready for storage
        """
        if isinstance(artifact, dict):
            # Convert dict to JSON string
            import json

            return json.dumps(artifact)
        if isinstance(artifact, str | bytes):
            # Already in correct format
            return artifact
        # Convert other types to string representation
        return str(artifact)

    def _convert_tags_to_list(
        self, tags: dict[str, Any] | list[str] | None
    ) -> list[str]:
        """
        Convert Cy script tags dictionary to list format.

        Args:
            tags: Tags from Cy script (can be dict, list, or None)

        Returns:
            List of tag strings
        """
        if tags is None:
            return []
        if isinstance(tags, dict):
            # Convert dict to list format: {"key": "value"} -> ["key:value"]
            return [f"{k}:{v}" for k, v in tags.items()]
        if isinstance(tags, list):
            # Convert all items to strings
            return [str(tag) for tag in tags]
        # Single tag, convert to list
        return [str(tags)]


def create_cy_artifact_functions(
    artifact_service: ArtifactService, execution_context: dict[str, Any]
) -> dict[str, Any]:
    """
    Create dictionary of native functions to pass to Cy interpreter.

    Args:
        artifact_service: ArtifactService instance (unused but kept for compatibility)
        execution_context: Current execution context

    Returns:
        Dictionary of functions for Cy interpreter
    """
    cy_functions = CyArtifactFunctions(artifact_service, execution_context)

    functions_dict = {"store_artifact": cy_functions.store_artifact}

    return functions_dict


# Future work: Load artifact functions (deferred to later phases)
def load_artifact_by_name(name: str) -> Any:
    """Load artifact by name - FUTURE WORK."""
    raise NotImplementedError(
        "TODO: Future work - load_artifact_by_name in later phase"
    )


def load_artifact_by_id(artifact_id: str) -> Any:
    """Load artifact by ID - FUTURE WORK."""
    raise NotImplementedError("TODO: Future work - load_artifact_by_id in later phase")

"""
Artifact Service.

Business logic layer for artifact management.
"""

import base64
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from analysi.config.logging import get_logger

if TYPE_CHECKING:
    from analysi.schemas.task_execution import LLMUsage

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.artifact import Artifact
from analysi.repositories.artifact_repository import ArtifactRepository
from analysi.schemas.artifact import ArtifactCreate, ArtifactResponse
from analysi.services.artifact_storage import ArtifactStorageService

logger = get_logger(__name__)


class ArtifactService:
    """Service for artifact business logic following task service patterns."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service with database session."""
        self.session = session
        self.repository = ArtifactRepository(session)
        self.storage_service = ArtifactStorageService()

    async def create_artifact(
        self, tenant_id: str, artifact_data: ArtifactCreate
    ) -> ArtifactResponse:
        """
        Create a new artifact with storage handling.

        Args:
            tenant_id: Tenant identifier
            artifact_data: Artifact creation data

        Returns:
            Created artifact

        Raises:
            ValueError: If validation fails
            RuntimeError: If storage fails
        """
        logger.debug("create_artifact", tenant_id=tenant_id)

        # Convert Pydantic model to dict and add tenant_id
        artifact_dict = artifact_data.model_dump()
        artifact_dict["tenant_id"] = tenant_id

        # Process content for storage
        raw_content = artifact_dict["content"]

        # Handle content_encoding for hex data
        if artifact_dict.get("content_encoding") == "hex" and isinstance(
            raw_content, str
        ):
            try:
                raw_content = bytes.fromhex(raw_content)
                artifact_dict["content"] = raw_content
            except ValueError:
                raise ValueError("Invalid hex content")

        # Determine MIME type if not provided
        if not artifact_dict.get("mime_type"):
            artifact_dict["mime_type"] = self.storage_service.determine_mime_type(
                raw_content, artifact_dict.get("name")
            )

        # Determine storage strategy
        storage_class = self.storage_service.determine_storage_class(
            raw_content, artifact_dict["mime_type"]
        )
        logger.debug(
            "storage_class_determined",
            storage_class=storage_class,
            mime_type=artifact_dict["mime_type"],
        )

        # Encode content for storage
        encoded_content = self.storage_service.encode_content_for_storage(
            raw_content, artifact_dict["mime_type"]
        )

        # Compute hashes
        sha256_hash, md5_hash = self.storage_service.compute_hashes(encoded_content)

        # Prepare final artifact data for repository
        artifact_dict.update(
            {
                "sha256": sha256_hash,
                "md5": md5_hash,
                "size_bytes": len(encoded_content),
                "storage_class": storage_class,
                "deleted_at": None,
            }
        )

        # Handle storage based on strategy
        if storage_class == ArtifactStorageService.STORAGE_INLINE:
            # Compress text content for inline storage (saves 60-80% for JSON/text)
            stored_content, content_encoding = self.storage_service.compress_for_inline(
                encoded_content, artifact_dict["mime_type"]
            )
            artifact_dict.update(
                {
                    "inline_content": stored_content,
                    "content_encoding": content_encoding,
                    "bucket": None,
                    "object_key": None,
                }
            )
        else:  # object storage with content-addressable dedup (AD-2)
            sha256_hex = sha256_hash.hex()
            bucket, object_key = await self.storage_service.store_object(
                encoded_content, tenant_id, sha256_hex, artifact_dict["mime_type"]
            )
            logger.info("object_stored", bucket=bucket, key=object_key)
            artifact_dict.update(
                {
                    "inline_content": None,
                    "content_encoding": None,
                    "bucket": bucket,
                    "object_key": object_key,
                }
            )

        # Remove fields that aren't database columns
        del artifact_dict["content"]

        # Create artifact in database
        try:
            result = await self.repository.create(artifact_dict)
            logger.info(
                "artifact_created", artifact_id=str(result.id), name=result.name
            )
            return await self._convert_to_response(result)
        except Exception as e:
            logger.error("artifact_db_error", error_type=type(e).__name__, error=str(e))
            # Handle constraint violations gracefully
            if "CheckViolationError" in str(
                type(e)
            ) or "artifacts_relationship_check" in str(e):
                raise ValueError(
                    "At least one relationship field (alert_id, task_run_id, workflow_run_id, workflow_node_instance_id, or analysis_id) must be provided"
                )
            if "artifacts_source_check" in str(e):
                raise ValueError(
                    "Invalid source value. Must be one of: auto_capture, cy_script, rest_api, mcp, unknown"
                )
            raise

    async def get_artifact(
        self, tenant_id: str, artifact_id: UUID
    ) -> ArtifactResponse | None:
        """
        Get artifact by ID with decoded content.

        Args:
            tenant_id: Tenant identifier
            artifact_id: Artifact UUID

        Returns:
            ArtifactResponse with decoded content, or None if not found
        """
        artifact = await self.repository.get_by_id(tenant_id, artifact_id)
        if not artifact:
            return None
        return await self._convert_to_response(artifact, include_content=True)

    async def list_artifacts(
        self,
        tenant_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[ArtifactResponse], int]:
        """
        List artifacts with filtering and pagination.

        Args:
            tenant_id: Tenant identifier
            filters: Optional filtering criteria
            limit: Page size
            offset: Pagination offset
            sort_by: Sort field
            sort_order: Sort direction

        Returns:
            Tuple of (ArtifactResponse list without content, total_count)
        """
        artifacts, total = await self.repository.list(
            tenant_id, filters, limit, offset, sort_by, sort_order
        )
        # List endpoints never include content or presigned URLs (AD-3),
        # so _convert_to_response won't make any async calls here
        items = [
            await self._convert_to_response(artifact, include_content=False)
            for artifact in artifacts
        ]
        return items, total

    async def get_artifact_content(
        self, tenant_id: str, artifact_id: UUID
    ) -> tuple[bytes, str, str, str] | None:
        """
        Get raw artifact content for download endpoint.

        Args:
            tenant_id: Tenant identifier
            artifact_id: Artifact UUID

        Returns:
            Tuple of (content_bytes, mime_type, filename, sha256_hex) or None
        """
        artifact = await self.repository.get_by_id(tenant_id, artifact_id)
        if not artifact:
            return None

        # Retrieve content based on storage class (decompress inline if needed)
        if (
            artifact.storage_class == ArtifactStorageService.STORAGE_INLINE
            and artifact.inline_content
        ):
            content = self.storage_service.decompress_inline(
                artifact.inline_content, artifact.content_encoding
            )
        elif (
            artifact.storage_class == ArtifactStorageService.STORAGE_OBJECT
            and artifact.bucket
            and artifact.object_key
        ):
            content = await self.storage_service.retrieve_object(
                artifact.bucket, artifact.object_key
            )
        else:
            return None

        # Generate filename from artifact name and MIME type
        filename = artifact.name
        if not filename.endswith(
            self.storage_service.get_file_extension(artifact.mime_type)
        ):
            filename += self.storage_service.get_file_extension(artifact.mime_type)

        sha256_hex = artifact.sha256.hex() if artifact.sha256 else ""

        return content, artifact.mime_type, filename, sha256_hex

    async def delete_artifact(self, tenant_id: str, artifact_id: UUID) -> bool:
        """
        Soft delete artifact (mark as deleted, preserve data).

        Args:
            tenant_id: Tenant identifier
            artifact_id: Artifact UUID

        Returns:
            True if deleted, False if not found
        """
        return await self.repository.soft_delete(tenant_id, artifact_id)

    async def get_download_info(self, tenant_id: str, artifact_id: UUID) -> dict | None:
        """
        Get download information for an artifact (used by tests).

        Args:
            tenant_id: Tenant identifier
            artifact_id: Artifact UUID

        Returns:
            Dictionary with download info or None if not found
        """
        artifact = await self.repository.get_by_id(tenant_id, artifact_id)
        if not artifact:
            return None

        result = {
            "id": artifact_id,
            "name": artifact.name,
            "mime_type": artifact.mime_type,
            "size_bytes": artifact.size_bytes,
            "storage_class": artifact.storage_class,
        }

        if artifact.storage_class == ArtifactStorageService.STORAGE_INLINE:
            result["has_inline_content"] = artifact.inline_content is not None
            if artifact.inline_content:
                result["content"] = self.storage_service.decompress_inline(
                    artifact.inline_content, artifact.content_encoding
                )
        else:
            result["bucket"] = artifact.bucket
            result["object_key"] = artifact.object_key
            result["has_object_reference"] = (
                artifact.bucket is not None and artifact.object_key is not None
            )

        return result

    async def get_artifacts_by_task_run(
        self, tenant_id: str, task_run_id: UUID
    ) -> list[ArtifactResponse]:
        """
        Get all artifacts created by a task run.

        Args:
            tenant_id: Tenant identifier
            task_run_id: Task run UUID

        Returns:
            List of artifact responses (without content)
        """
        artifacts = await self.repository.get_by_task_run(tenant_id, task_run_id)
        return [
            await self._convert_to_response(a, include_content=False) for a in artifacts
        ]

    async def get_artifacts_by_workflow_run(
        self, tenant_id: str, workflow_run_id: UUID
    ) -> list[ArtifactResponse]:
        """
        Get all artifacts created by a workflow run.

        Args:
            tenant_id: Tenant identifier
            workflow_run_id: Workflow run UUID

        Returns:
            List of artifact responses (without content)
        """
        artifacts = await self.repository.get_by_workflow_run(
            tenant_id, workflow_run_id
        )
        return [
            await self._convert_to_response(a, include_content=False) for a in artifacts
        ]

    async def get_artifacts_by_analysis(
        self, tenant_id: str, analysis_id: UUID
    ) -> dict[str, list[ArtifactResponse]]:
        """
        Get artifacts grouped by type for analysis (UI dashboard use case).

        Args:
            tenant_id: Tenant identifier
            analysis_id: Analysis UUID

        Returns:
            Dictionary keyed by artifact_type with lists of artifacts
        """
        artifacts = await self.repository.get_by_analysis(tenant_id, analysis_id)
        grouped: dict[str, list[ArtifactResponse]] = {}
        for artifact in artifacts:
            response = await self._convert_to_response(artifact, include_content=False)
            key = artifact.artifact_type or "unknown"
            grouped.setdefault(key, []).append(response)
        return grouped

    async def _convert_to_response(
        self, artifact: Artifact, include_content: bool = True
    ) -> ArtifactResponse:
        """
        Convert Artifact model to response schema.

        Handles content decoding for inline artifacts and presigned URLs
        for object-stored artifacts.

        Args:
            artifact: Artifact model instance
            include_content: Whether to include decoded content / presigned URL
                             (False for list endpoints per AD-3)

        Returns:
            Artifact response schema
        """
        response_data = {
            "id": artifact.id,
            "tenant_id": artifact.tenant_id,
            "name": artifact.name,
            "artifact_type": artifact.artifact_type,
            "mime_type": artifact.mime_type,
            "tags": artifact.tags,
            "sha256": artifact.sha256.hex() if artifact.sha256 else None,
            "size_bytes": artifact.size_bytes,
            "storage_class": artifact.storage_class,
            "alert_id": artifact.alert_id,
            "task_run_id": artifact.task_run_id,
            "workflow_run_id": artifact.workflow_run_id,
            "workflow_node_instance_id": artifact.workflow_node_instance_id,
            "analysis_id": artifact.analysis_id,
            "integration_id": artifact.integration_id,
            "source": artifact.source,
            "created_at": artifact.created_at,
        }

        # Add storage-specific fields
        if (
            artifact.storage_class == ArtifactStorageService.STORAGE_OBJECT
            and include_content
        ):
            download_url = await self._generate_presigned_url_safe(artifact)
            response_data.update(
                {
                    "bucket": artifact.bucket,
                    "object_key": artifact.object_key,
                    "download_url": download_url,
                }
            )
        elif artifact.storage_class == ArtifactStorageService.STORAGE_OBJECT:
            # List endpoint: no presigned URL
            response_data.update(
                {
                    "bucket": artifact.bucket,
                    "object_key": artifact.object_key,
                }
            )
        elif (
            artifact.storage_class == ArtifactStorageService.STORAGE_INLINE
            and include_content
        ):
            response_data["content"] = self._decode_inline_content(artifact)

        return ArtifactResponse(**response_data)

    async def _generate_presigned_url_safe(self, artifact: Artifact) -> str | None:
        """Generate a presigned URL, returning None on failure instead of raising."""
        if not artifact.bucket or not artifact.object_key:
            return None
        try:
            return await self.storage_service.generate_presigned_url(
                artifact.bucket, artifact.object_key
            )
        except Exception:
            logger.warning(
                "Failed to generate presigned URL for artifact %s", artifact.id
            )
            return None

    def _decode_inline_content(self, artifact: Artifact) -> str | dict | None:
        """
        Decode inline content based on MIME type.

        Transparently decompresses zlib-compressed content before decoding.

        Returns:
            Parsed JSON dict, decoded text string, or base64 string for binary.
            None if no inline content.
        """
        if not artifact.inline_content:
            return None

        # Decompress if stored compressed
        raw = self.storage_service.decompress_inline(
            artifact.inline_content, artifact.content_encoding
        )

        try:
            if artifact.mime_type == "application/json":
                return json.loads(raw.decode("utf-8"))
            if artifact.mime_type.startswith("text/"):
                return raw.decode("utf-8")
            return base64.b64encode(raw).decode("ascii")
        except Exception:
            # If decoding fails, fall back to base64
            return base64.b64encode(raw).decode("ascii")

    async def create_tool_execution_artifact(
        self,
        tenant_id: str,
        tool_fqn: str,
        integration_id: str,
        input_params: dict[str, Any],
        output: Any,
        duration_ms: int,
        analysis_id: UUID | None = None,
        task_run_id: UUID | None = None,
        workflow_run_id: UUID | None = None,
        workflow_node_instance_id: UUID | None = None,
    ) -> ArtifactResponse:
        """
        Create an artifact for an integration tool execution.

        This is a fire-and-forget helper for auto-capturing tool I/O during
        Cy script execution.

        Args:
            tenant_id: Tenant identifier
            tool_fqn: Tool fully qualified name (e.g., "app::virustotal::ip_reputation")
            integration_id: Integration instance ID (e.g., "virustotal-prod")
            input_params: Input parameters passed to the tool
            output: Output from the tool execution
            duration_ms: Execution duration in milliseconds
            analysis_id: Associated analysis ID (for alert processing)
            task_run_id: Associated task run ID
            workflow_run_id: Associated workflow run ID
            workflow_node_instance_id: Associated workflow node instance ID

        Returns:
            Created Artifact
        """
        # Build content with input, output, timing
        content = {
            "input": input_params,
            "output": output,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        artifact_data = ArtifactCreate(
            name=tool_fqn,
            content=json.dumps(content, default=str),
            artifact_type="tool_execution",
            task_run_id=task_run_id,
            workflow_run_id=workflow_run_id,
            workflow_node_instance_id=workflow_node_instance_id,
            analysis_id=analysis_id,
            integration_id=integration_id,
            source="auto_capture",
        )

        return await self.create_artifact(tenant_id, artifact_data)

    async def create_llm_execution_artifact(
        self,
        tenant_id: str,
        function_name: str,
        integration_id: str,
        prompt: str,
        completion: str,
        model: str | None,
        duration_ms: int,
        llm_usage: "LLMUsage | None" = None,
        analysis_id: UUID | None = None,
        task_run_id: UUID | None = None,
        workflow_run_id: UUID | None = None,
        workflow_node_instance_id: UUID | None = None,
    ) -> ArtifactResponse:
        """
        Create an artifact for an LLM execution.

        This is a fire-and-forget helper for auto-capturing LLM I/O during
        Cy script execution.

        Args:
            tenant_id: Tenant identifier
            function_name: LLM function name (e.g., "llm_run", "llm_summarize")
            integration_id: LLM integration instance ID
            prompt: The prompt sent to the LLM
            completion: The completion received from the LLM
            model: Model name used (e.g., "gpt-4")
            duration_ms: Execution duration in milliseconds
            llm_usage: Token counts and estimated cost. None when not available.
            analysis_id: Associated analysis ID (for alert processing)
            task_run_id: Associated task run ID
            workflow_run_id: Associated workflow run ID
            workflow_node_instance_id: Associated workflow node instance ID

        Returns:
            Created Artifact
        """
        # Build content with prompt, completion, model, timing, and token usage
        content = {
            "prompt": prompt,
            "completion": completion,
            "model": model,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(UTC).isoformat(),
            # Token counts and cost; None when provider didn't return usage
            "input_tokens": llm_usage.input_tokens if llm_usage else None,
            "output_tokens": llm_usage.output_tokens if llm_usage else None,
            "total_tokens": llm_usage.total_tokens if llm_usage else None,
            "cost_usd": llm_usage.cost_usd if llm_usage else None,
        }

        artifact_data = ArtifactCreate(
            name=function_name,
            content=json.dumps(content, default=str),
            artifact_type="llm_execution",
            task_run_id=task_run_id,
            workflow_run_id=workflow_run_id,
            workflow_node_instance_id=workflow_node_instance_id,
            analysis_id=analysis_id,
            integration_id=integration_id,
            source="auto_capture",
        )

        return await self.create_artifact(tenant_id, artifact_data)

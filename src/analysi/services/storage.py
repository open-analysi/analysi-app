"""
Storage Strategy Implementation

Handles inline and MinIO S3-compatible storage for task inputs/outputs.
"""

import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import aioboto3

from analysi.config.logging import get_logger
from analysi.config.object_storage import ObjectStorageConfig

logger = get_logger(__name__)

# Maximum size for S3 object reads (50 MB). Objects larger than this are
# rejected to prevent DoS from oversized payloads consuming memory when
# parsed into workflow run responses.
_MAX_S3_OBJECT_BYTES = 50 * 1024 * 1024


class StorageStrategy(ABC):
    """Abstract base class for storage strategies."""

    @abstractmethod
    async def store(
        self,
        content: str,
        content_type: str,
        tenant_id: str,
        task_run_id: str,
        storage_purpose: str,
    ) -> dict[str, Any]:
        """Store content and return storage information."""
        pass

    @abstractmethod
    async def retrieve(self, location: str, content_type: str) -> str:
        """Retrieve content from storage location."""
        pass


class InlineStorageStrategy(StorageStrategy):
    """Storage strategy for small content (< 512KB) stored inline in database."""

    async def store(
        self,
        content: str,
        content_type: str,
        tenant_id: str,
        task_run_id: str,
        storage_purpose: str,
    ) -> dict[str, Any]:
        """
        Store content inline in database.

        Args:
            content: Content to store
            content_type: MIME type of content
            tenant_id: Tenant identifier
            task_run_id: Task run identifier
            storage_purpose: 'input' or 'output'

        Returns:
            Storage information dictionary
        """
        return {
            "storage_type": "inline",
            "location": content,  # Content stored directly
            "content_type": content_type,
        }

    async def retrieve(self, location: str, content_type: str) -> str:
        """Retrieve inline content (location is the content itself)."""
        return location


class MinIOStorageStrategy(StorageStrategy):
    """Storage strategy for large content (≥ 512KB) using MinIO S3-compatible storage."""

    def __init__(self) -> None:
        self.config = ObjectStorageConfig.get_settings()
        self._session = None

    def _get_session(self) -> aioboto3.Session:
        """Get or create aioboto3 session."""
        if self._session is None:
            self._session = aioboto3.Session()
        return self._session

    async def store(
        self,
        content: str,
        content_type: str,
        tenant_id: str,
        task_run_id: str,
        storage_purpose: str,
    ) -> dict[str, Any]:
        """
        Store content in MinIO S3-compatible storage.

        Args:
            content: Content to store
            content_type: MIME type of content
            tenant_id: Tenant identifier
            task_run_id: Task run identifier
            storage_purpose: 'input' or 'output'

        Returns:
            Storage information dictionary
        """
        # Generate storage path
        detector = ContentTypeDetector()
        file_extension = detector.get_file_extension(content_type)
        storage_path = self.generate_storage_path(
            tenant_id, task_run_id, storage_purpose, file_extension
        )

        # Convert content to bytes
        content_bytes = content.encode("utf-8")

        # Store in MinIO using aioboto3
        session = self._get_session()

        # Handle endpoint with or without protocol prefix
        endpoint = self.config["endpoint"]
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"http://{endpoint}"

        async with session.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=self.config["access_key"],
            aws_secret_access_key=self.config["secret_key"],
        ) as s3_client:
            # Upload to MinIO
            await s3_client.put_object(
                Bucket=self.config["bucket"],
                Key=storage_path,
                Body=content_bytes,
                ContentType=content_type,
            )

        return {
            "storage_type": "s3",
            "location": storage_path,
            "content_type": content_type,
            "bucket": self.config["bucket"],
        }

    async def retrieve(self, location: str, content_type: str) -> str:
        """Retrieve content from MinIO storage."""
        session = self._get_session()

        # Handle endpoint with or without protocol prefix
        endpoint = self.config["endpoint"]
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"http://{endpoint}"

        async with session.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=self.config["access_key"],
            aws_secret_access_key=self.config["secret_key"],
        ) as s3_client:
            # Download from MinIO
            response = await s3_client.get_object(
                Bucket=self.config["bucket"], Key=location
            )
            # Read all content from the streaming body in chunks to handle
            # aioboto3's async streaming which may return partial reads.
            body = response["Body"]
            chunks = []
            total = 0
            async for chunk in body:
                total += len(chunk)
                if total > _MAX_S3_OBJECT_BYTES:
                    raise ValueError(
                        f"S3 object exceeds {_MAX_S3_OBJECT_BYTES} byte limit"
                    )
                chunks.append(chunk)

            content_bytes = b"".join(chunks)
            return content_bytes.decode("utf-8")

    def generate_storage_path(
        self,
        tenant_id: str,
        task_run_id: str,
        storage_purpose: str,
        file_extension: str,
    ) -> str:
        """
        Generate S3 storage path following spec format.

        Format: {tenant}/task-runs/{YYYY-MM-DD}/{task_run_id}/{purpose}.{ext}
        """
        today = datetime.now(tz=UTC).date().strftime("%Y-%m-%d")
        return f"{tenant_id}/task-runs/{today}/{task_run_id}/{storage_purpose}{file_extension}"


class StorageManager:
    """Manages storage strategy selection and operations."""

    def __init__(self) -> None:
        self.inline_strategy = InlineStorageStrategy()
        self.s3_strategy = MinIOStorageStrategy()
        self.size_threshold = 512 * 1024  # 512KB

    def select_storage_type(self, content: str) -> str:
        """
        Select storage type based on content size.

        Args:
            content: Content to be stored

        Returns:
            'inline' for small content, 's3' for large content
        """
        content_size = len(content.encode("utf-8"))
        return "inline" if content_size < self.size_threshold else "s3"

    async def store(
        self,
        content: str,
        content_type: str,
        tenant_id: str,
        task_run_id: str,
        storage_purpose: str,
    ) -> dict[str, Any]:
        """Store content using appropriate strategy."""
        storage_type = self.select_storage_type(content)

        if storage_type == "inline":
            return await self.inline_strategy.store(
                content, content_type, tenant_id, task_run_id, storage_purpose
            )
        return await self.s3_strategy.store(
            content, content_type, tenant_id, task_run_id, storage_purpose
        )

    async def retrieve(
        self, storage_type: str, location: str, content_type: str
    ) -> str:
        """Retrieve content using appropriate strategy."""
        if storage_type == "inline":
            return await self.inline_strategy.retrieve(location, content_type)
        if storage_type == "s3":
            return await self.s3_strategy.retrieve(location, content_type)
        raise ValueError(f"Unknown storage type: {storage_type}")


class ContentTypeDetector:
    """Detects content types and maps them to file extensions."""

    EXTENSION_MAPPING = {  # noqa: RUF012
        "application/json": ".json",
        "text/plain": ".txt",
        "text/csv": ".csv",
        "text/markdown": ".md",
        "application/octet-stream": ".bin",
    }

    def detect_content_type(self, content: str | bytes) -> str:
        """
        Detect content type from content.

        Args:
            content: Content to analyze (string or bytes)

        Returns:
            MIME type string
        """
        if isinstance(content, bytes):
            return "application/octet-stream"

        if isinstance(content, str):
            # Try to parse as JSON
            try:
                json.loads(content)
                return "application/json"
            except (json.JSONDecodeError, ValueError):
                pass

            # Check for CSV pattern
            lines = content.strip().split("\n")
            if len(lines) >= 2 and "," in lines[0]:
                return "text/csv"

            # Default to plain text
            return "text/plain"

        return "application/octet-stream"

    def get_file_extension(self, content_type: str) -> str:
        """Get file extension for content type."""
        return self.EXTENSION_MAPPING.get(content_type, ".bin")


# File storage strategy (future work - stub only)
class FileStorageStrategy(StorageStrategy):
    """File system storage strategy (future work)."""

    async def store(
        self,
        content: str,
        content_type: str,
        tenant_id: str,
        task_run_id: str,
        storage_purpose: str,
    ) -> dict[str, Any]:
        """Store content in file system (not implemented)."""
        raise NotImplementedError("File storage is future work")

    async def retrieve(self, location: str, content_type: str) -> str:
        """Retrieve content from file system (not implemented)."""
        raise NotImplementedError("File storage is future work")

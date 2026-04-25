"""
Artifact Storage Service.

Handles storage strategy decisions, inline storage, and MinIO object storage.
"""

import hashlib
import json
import mimetypes
import zlib
from typing import Any

import aioboto3

from analysi.common.retry_config import storage_retry_policy
from analysi.config.logging import get_logger
from analysi.config.object_storage import ObjectStorageConfig

logger = get_logger(__name__)


class ArtifactStorageService:
    """
    Artifact storage service with 8KB inline threshold (AD-4).

    Storage Strategy:
    - ≤8KB: inline storage (PostgreSQL BYTEA)
    - >8KB: object storage (MinIO) with content-addressable dedup (AD-2)
    """

    INLINE_THRESHOLD = 8 * 1024  # 8KB in bytes (AD-4)
    # Minimum size worth compressing — below this the zlib header overhead isn't worth it
    COMPRESSION_MIN_BYTES = 64
    # MIME types that benefit from compression (text-based content)
    COMPRESSIBLE_MIME_PREFIXES = ("text/", "application/json", "application/xml")

    # Storage class constants — use these instead of raw strings
    STORAGE_INLINE = "inline"
    STORAGE_OBJECT = "object"

    TEXT_MIME_TYPES = [  # noqa: RUF012
        "application/json",
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/html",
        "text/xml",
        "application/xml",
    ]

    def __init__(self) -> None:
        """Initialize storage service with MinIO client."""
        self._session: aioboto3.Session | None = None
        # Cache config once — it reads from env vars which don't change at runtime
        config = ObjectStorageConfig.get_settings()
        self._bucket = config["artifacts_bucket"]
        endpoint = config["endpoint"]
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"http://{endpoint}"
        self._endpoint = endpoint
        self._access_key = config["access_key"]
        self._secret_key = config["secret_key"]

    def determine_storage_class(self, content: str | bytes, mime_type: str) -> str:
        """
        Determine storage strategy based on size and content type.

        Args:
            content: Content to store (string or bytes)
            mime_type: MIME type of content

        Returns:
            'inline' or 'object'
        """
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content

        size_bytes = len(content_bytes)

        if size_bytes <= self.INLINE_THRESHOLD:
            return self.STORAGE_INLINE
        return self.STORAGE_OBJECT

    def is_text_mime_type(self, mime_type: str) -> bool:
        """
        Check if MIME type is text-based.

        Args:
            mime_type: MIME type to check

        Returns:
            True if text-based
        """
        return mime_type in self.TEXT_MIME_TYPES or mime_type.startswith("text/")

    def determine_mime_type(
        self, content: str | bytes | dict, filename: str | None = None
    ) -> str:
        """
        Determine MIME type from content using Python's mimetypes module with fallback to content analysis.

        Args:
            content: Content to analyze
            filename: Optional filename for extension-based detection

        Returns:
            MIME type string
        """
        # First try filename-based detection if provided
        if filename:
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type:
                return mime_type

        # Content-based detection
        if isinstance(content, dict):
            return "application/json"
        if isinstance(content, str):
            # Try to parse as JSON first
            try:
                json.loads(content)
                return "application/json"
            except (json.JSONDecodeError, ValueError):
                # Check for CSV pattern
                lines = content.strip().split("\n")
                if len(lines) >= 2:
                    # Check if all lines have same number of commas (CSV pattern)
                    first_line_commas = lines[0].count(",")
                    if first_line_commas > 0 and all(
                        line.count(",") == first_line_commas
                        for line in lines[: min(5, len(lines))]
                    ):
                        return "text/csv"
                return "text/plain"
        elif isinstance(content, bytes):
            # Check for common binary format magic bytes as fallback
            if content.startswith(b"\x89PNG"):
                return "image/png"
            if content.startswith(b"\xff\xd8\xff"):
                return "image/jpeg"
            if content.startswith(b"%PDF"):
                return "application/pdf"
            if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
                return "image/gif"
            if content.startswith(b"\x00\x00\x00\x18ftypmp4") or content.startswith(
                b"\x00\x00\x00\x20ftypisom"
            ):
                return "video/mp4"
            if content.startswith(b"PK\x03\x04"):
                return "application/zip"
            return "application/octet-stream"
        else:
            return "text/plain"

    def compute_hashes(self, content: str | bytes) -> tuple[bytes, bytes]:
        """
        Compute SHA256 and MD5 hashes of content.

        Args:
            content: Content to hash

        Returns:
            Tuple of (sha256_bytes, md5_bytes)
        """
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content

        sha256_hash = hashlib.sha256(content_bytes).digest()
        md5_hash = hashlib.md5(content_bytes).digest()  # nosec B324

        return sha256_hash, md5_hash

    def encode_content_for_storage(self, content: str | bytes, mime_type: str) -> bytes:
        """
        Encode content for storage (UTF-8 for text, as-is for binary).

        Args:
            content: Content to encode
            mime_type: MIME type

        Returns:
            Bytes ready for storage
        """
        if isinstance(content, bytes):
            return content
        if isinstance(content, str):
            return content.encode("utf-8")
        if isinstance(content, dict):
            # Handle JSON/dict content
            json_str = json.dumps(content, separators=(",", ":"))
            return json_str.encode("utf-8")
        # Convert to string and encode
        return str(content).encode("utf-8")

    def decode_content_from_storage(
        self, content_bytes: bytes, mime_type: str
    ) -> str | bytes:
        """
        Decode content from storage based on MIME type.

        Args:
            content_bytes: Stored content bytes
            mime_type: Original MIME type

        Returns:
            Decoded content (string for text MIME types, raw bytes for binary)
        """
        if self.is_text_mime_type(mime_type):
            return content_bytes.decode("utf-8")
        return content_bytes

    def compress_for_inline(
        self, content_bytes: bytes, mime_type: str
    ) -> tuple[bytes, str | None]:
        """
        Compress content for inline (PostgreSQL BYTEA) storage.

        Only compresses text-based content above a minimum size threshold.
        Binary content (images, PDFs) is already compressed and won't benefit.

        Args:
            content_bytes: Raw content bytes
            mime_type: MIME type of content

        Returns:
            Tuple of (stored_bytes, content_encoding).
            content_encoding is 'zlib' when compressed, None otherwise.
        """
        if len(content_bytes) < self.COMPRESSION_MIN_BYTES:
            return content_bytes, None

        if not any(mime_type.startswith(p) for p in self.COMPRESSIBLE_MIME_PREFIXES):
            return content_bytes, None

        compressed = zlib.compress(content_bytes, level=6)
        # Only use compressed version if it's actually smaller
        if len(compressed) < len(content_bytes):
            logger.debug(
                "Inline compression: %d → %d bytes (%.0f%% saved)",
                len(content_bytes),
                len(compressed),
                (1 - len(compressed) / len(content_bytes)) * 100,
            )
            return compressed, "zlib"
        return content_bytes, None

    @staticmethod
    def decompress_inline(
        stored_bytes: bytes, content_encoding: str | None = None
    ) -> bytes:
        """
        Decompress inline content based on the content_encoding field.

        Args:
            stored_bytes: Bytes from PostgreSQL BYTEA column
            content_encoding: Value of the content_encoding column ('zlib' or None)

        Returns:
            Decompressed content bytes
        """
        if content_encoding == "zlib":
            return zlib.decompress(stored_bytes)
        return stored_bytes

    def _s3_client(self):
        """Async context manager for an S3 client with cached config."""
        if self._session is None:
            self._session = aioboto3.Session()
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        )

    @storage_retry_policy()
    async def object_exists(self, bucket: str, object_key: str) -> bool:
        """
        Check if an object already exists in storage (HEAD request).

        Args:
            bucket: Bucket name
            object_key: Object key

        Returns:
            True if object exists
        """
        try:
            async with self._s3_client() as s3:
                await s3.head_object(Bucket=bucket, Key=object_key)
                return True
        except Exception:
            return False

    @storage_retry_policy()
    async def store_object(
        self,
        content: str | bytes,
        tenant_id: str,
        sha256_hex: str,
        mime_type: str,
    ) -> tuple[str, str]:
        """
        Store content in MinIO with content-addressable dedup (AD-2).

        PUT is idempotent for content-addressable keys — same SHA256 = same
        content, so overwriting is safe and avoids a TOCTOU race from a
        separate HEAD check.

        Args:
            content: Content to store
            tenant_id: Tenant identifier
            sha256_hex: SHA256 hex digest of content
            mime_type: MIME type

        Returns:
            Tuple of (bucket_name, object_key)
        """
        bucket_name = self._bucket
        object_key = self.generate_object_key(tenant_id, sha256_hex)

        # Convert content to bytes if needed
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content

        async with self._s3_client() as s3:
            await s3.put_object(
                Bucket=bucket_name,
                Key=object_key,
                Body=content_bytes,
                ContentType=mime_type,
            )

        return bucket_name, object_key

    @storage_retry_policy()
    async def retrieve_object(self, bucket: str, object_key: str) -> bytes:
        """
        Retrieve content from MinIO object storage.

        Args:
            bucket: Bucket name
            object_key: Object key

        Returns:
            Raw content bytes
        """
        async with self._s3_client() as s3:
            response = await s3.get_object(Bucket=bucket, Key=object_key)
            body = response["Body"]
            chunks = []
            async for chunk in body:
                chunks.append(chunk)
            return b"".join(chunks)

    def generate_object_key(self, tenant_id: str, sha256_hex: str) -> str:
        """
        Generate content-addressable object key for MinIO storage (AD-2).

        Pattern: artifacts/{tenant_id}/{sha256hex}

        Args:
            tenant_id: Tenant identifier
            sha256_hex: SHA256 hex digest of the content

        Returns:
            Object key string
        """
        return f"artifacts/{tenant_id}/{sha256_hex}"

    @storage_retry_policy()
    async def generate_presigned_url(
        self, bucket: str, object_key: str, expires_hours: int = 1
    ) -> str:
        """
        Generate presigned download URL for object.

        Args:
            bucket: Bucket name
            object_key: Object key
            expires_hours: URL expiration time

        Returns:
            Presigned download URL
        """
        async with self._s3_client() as s3:
            presigned_url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": object_key},
                ExpiresIn=expires_hours * 3600,
            )
            return str(presigned_url)

    @storage_retry_policy()
    async def delete_object(self, bucket: str, object_key: str) -> bool:
        """
        Delete object from MinIO storage (for cleanup).

        Args:
            bucket: Bucket name
            object_key: Object key

        Returns:
            True if deleted successfully
        """
        async with self._s3_client() as s3:
            await s3.delete_object(Bucket=bucket, Key=object_key)
            return True

    def get_file_extension(self, mime_type: str) -> str:
        """
        Get appropriate file extension for MIME type.

        Args:
            mime_type: MIME type

        Returns:
            File extension (including dot)
        """
        # Common MIME type to extension mapping
        mime_to_ext = {
            "application/json": ".json",
            "text/plain": ".txt",
            "text/markdown": ".md",
            "text/csv": ".csv",
            "text/html": ".html",
            "text/xml": ".xml",
            "application/xml": ".xml",
            "application/pdf": ".pdf",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "application/octet-stream": ".bin",
        }

        return mime_to_ext.get(mime_type, ".txt")

    async def get_storage_info(self) -> dict[str, Any]:
        """
        Get storage service information and health status.

        Returns:
            Dictionary with storage service status including bucket accessibility
        """
        try:
            async with self._s3_client() as s3:
                await s3.head_bucket(Bucket=self._bucket)
                return {
                    "status": "healthy",
                    "bucket": self._bucket,
                    "endpoint": self._endpoint,
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "bucket": self._bucket,
                "endpoint": self._endpoint,
                "error": str(e),
            }

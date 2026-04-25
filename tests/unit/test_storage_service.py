"""
Storage Strategy Tests

Tests for inline and MinIO storage strategies.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from analysi.config.object_storage import ObjectStorageConfig
from analysi.services.storage import (
    ContentTypeDetector,
    InlineStorageStrategy,
    MinIOStorageStrategy,
    StorageManager,
)


class TestInlineStorage:
    """Test inline storage for small inputs/outputs (< 512KB)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_store_small_content_inline(self):
        """Test that small content is stored inline."""
        storage = InlineStorageStrategy()

        # Small JSON content
        content = {"message": "Hello World", "data": [1, 2, 3]}
        content_str = json.dumps(content)

        # Should be stored inline since it's small
        result = await storage.store(
            content=content_str,
            content_type="application/json",
            tenant_id="test_tenant",
            task_run_id="test-trid",
            storage_purpose="input",
        )

        assert result["storage_type"] == "inline"
        assert result["location"] == content_str  # Content stored directly
        assert result["content_type"] == "application/json"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_store_text_content_inline(self):
        """Test inline storage of text content."""
        storage = InlineStorageStrategy()

        content = "This is a test message for inline storage."

        result = await storage.store(
            content=content,
            content_type="text/plain",
            tenant_id="test_tenant",
            task_run_id="test-trid",
            storage_purpose="output",
        )

        assert result["storage_type"] == "inline"
        assert result["location"] == content
        assert result["content_type"] == "text/plain"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieve_inline_content(self):
        """Test retrieval of inline content."""
        storage = InlineStorageStrategy()

        # Content should be returned as-is
        stored_content = '{"result": "success"}'

        retrieved = await storage.retrieve(
            location=stored_content, content_type="application/json"
        )

        assert retrieved == stored_content


class TestMinIOStorage:
    """Test MinIO S3-compatible storage for large inputs/outputs (≥ 512KB)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_store_large_content_in_minio(self):
        """Test that large content is stored in MinIO."""
        storage = MinIOStorageStrategy()

        # Large content (> 512KB)
        large_content = "x" * (600 * 1024)  # 600KB

        # Mock aioboto3 session and client
        mock_s3_client = AsyncMock()
        mock_s3_client.put_object = AsyncMock()

        # Create a proper async context manager mock
        mock_client_context = AsyncMock()
        mock_client_context.__aenter__ = AsyncMock(return_value=mock_s3_client)
        mock_client_context.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.client = Mock(return_value=mock_client_context)

        with patch.object(storage, "_get_session", return_value=mock_session):
            result = await storage.store(
                content=large_content,
                content_type="text/plain",
                tenant_id="test_tenant",
                task_run_id="test-trid",
                storage_purpose="input",
            )

            assert result["storage_type"] == "s3"
            assert "test_tenant/task-runs/" in result["location"]
            assert "test-trid" in result["location"]
            assert result["content_type"] == "text/plain"

            # Verify MinIO client was called
            mock_s3_client.put_object.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_minio_bucket_path_generation(self):
        """Test MinIO bucket path generation follows spec."""
        storage = MinIOStorageStrategy()

        # Mock the path generation
        path = storage.generate_storage_path(
            tenant_id="tenant1",
            task_run_id="trid-123",
            storage_purpose="input",
            file_extension=".json",
        )

        # Should follow: {tenant}/task-runs/{YYYY-MM-DD}/{task_run_id}/{purpose}.{ext}
        assert "tenant1/task-runs/" in path
        assert "trid-123" in path
        assert path.endswith("input.json")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieve_minio_content(self):
        """Test retrieval of content from MinIO."""
        storage = MinIOStorageStrategy()

        # Mock aioboto3 session and client
        # retrieve() uses `async for chunk in body` (chunked streaming)
        content = b'{"result": "from minio"}'

        mock_body = AsyncMock()

        async def async_iter():
            yield content

        mock_body.__aiter__ = lambda self: async_iter()

        mock_s3_client = AsyncMock()
        mock_s3_client.get_object = AsyncMock(return_value={"Body": mock_body})

        # Create a proper async context manager mock
        mock_client_context = AsyncMock()
        mock_client_context.__aenter__ = AsyncMock(return_value=mock_s3_client)
        mock_client_context.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.client = Mock(return_value=mock_client_context)

        with patch.object(storage, "_get_session", return_value=mock_session):
            retrieved = await storage.retrieve(
                location="tenant1/task-runs/2026-04-26/trid-123/input.json",
                content_type="application/json",
            )

            assert retrieved == '{"result": "from minio"}'
            mock_s3_client.get_object.assert_called_once()


class TestStorageStrategySelection:
    """Test automatic storage type selection based on 512KB threshold."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_storage_manager_selects_inline_for_small_content(self):
        """Test that StorageManager selects inline storage for small content."""
        manager = StorageManager()

        small_content = "Small content"  # < 512KB

        storage_type = manager.select_storage_type(small_content)

        assert storage_type == "inline"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_storage_manager_selects_s3_for_large_content(self):
        """Test that StorageManager selects S3 storage for large content."""
        manager = StorageManager()

        large_content = "x" * (600 * 1024)  # 600KB > 512KB

        storage_type = manager.select_storage_type(large_content)

        assert storage_type == "s3"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_storage_manager_boundary_condition(self):
        """Test storage selection at 512KB boundary."""
        manager = StorageManager()

        # Exactly 512KB should use S3
        boundary_content = "x" * (512 * 1024)  # Exactly 512KB

        storage_type = manager.select_storage_type(boundary_content)

        assert storage_type == "s3"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_storage_manager_stores_content(self):
        """Test that StorageManager delegates to appropriate strategy."""
        manager = StorageManager()

        # Mock strategies
        mock_inline = AsyncMock()
        mock_s3 = AsyncMock()

        with (
            patch.object(manager, "inline_strategy", mock_inline),
            patch.object(manager, "s3_strategy", mock_s3),
        ):
            # Small content should use inline
            small_content = "small"
            await manager.store(
                content=small_content,
                content_type="text/plain",
                tenant_id="test",
                task_run_id="trid",
                storage_purpose="input",
            )

            mock_inline.store.assert_called_once()
            mock_s3.store.assert_not_called()


class TestContentTypeDetection:
    """Test content-type detection and file extension mapping."""

    @pytest.mark.unit
    def test_detect_json_content_type(self):
        """Test JSON content type detection."""
        detector = ContentTypeDetector()

        json_content = '{"key": "value"}'

        content_type = detector.detect_content_type(json_content)
        assert content_type == "application/json"

        extension = detector.get_file_extension(content_type)
        assert extension == ".json"

    @pytest.mark.unit
    def test_detect_text_content_type(self):
        """Test plain text content type detection."""
        detector = ContentTypeDetector()

        text_content = "This is plain text content."

        content_type = detector.detect_content_type(text_content)
        assert content_type == "text/plain"

        extension = detector.get_file_extension(content_type)
        assert extension == ".txt"

    @pytest.mark.unit
    def test_detect_csv_content_type(self):
        """Test CSV content type detection."""
        detector = ContentTypeDetector()

        csv_content = "name,age,city\nAlice,30,NYC\nBob,25,LA"

        content_type = detector.detect_content_type(csv_content)
        assert content_type == "text/csv"

        extension = detector.get_file_extension(content_type)
        assert extension == ".csv"

    @pytest.mark.unit
    def test_content_type_extension_mapping(self):
        """Test content-type to extension mapping per spec."""
        detector = ContentTypeDetector()

        mappings = {
            "application/json": ".json",
            "text/plain": ".txt",
            "text/csv": ".csv",
            "text/markdown": ".md",
            "application/octet-stream": ".bin",
        }

        for content_type, expected_ext in mappings.items():
            extension = detector.get_file_extension(content_type)
            assert extension == expected_ext

    @pytest.mark.unit
    def test_unknown_content_type_fallback(self):
        """Test fallback for unknown content types."""
        detector = ContentTypeDetector()

        # Unknown content type should fallback to binary
        unknown_content = b"\x00\x01\x02\x03"  # Binary data

        content_type = detector.detect_content_type(unknown_content)
        assert content_type == "application/octet-stream"

        extension = detector.get_file_extension(content_type)
        assert extension == ".bin"


class TestMinIOConfiguration:
    """Test MinIO configuration from environment variables (via ObjectStorageConfig)."""

    @pytest.mark.unit
    def test_load_minio_config_from_environment(self):
        """Test MinIO configuration loading from environment."""
        env_vars = {
            "MINIO_ENDPOINT": "localhost:9000",
            "MINIO_ACCESS_KEY": "test-key",
            "MINIO_SECRET_KEY": "test-secret",
            "MINIO_BUCKET": "analysi-storage",
        }

        with patch.dict("os.environ", env_vars, clear=True):
            config = ObjectStorageConfig.get_settings()

            assert config["endpoint"] == "localhost:9000"
            assert config["access_key"] == "test-key"
            assert config["secret_key"] == "test-secret"
            assert config["bucket"] == "analysi-storage"

    @pytest.mark.unit
    def test_minio_config_defaults(self):
        """Test MinIO configuration defaults."""
        with patch.dict("os.environ", {}, clear=True):
            config = ObjectStorageConfig.get_settings()

            assert config["endpoint"] is not None
            assert config["bucket"] is not None
            # Credentials are None when unset (no hardcoded minioadmin)
            assert config["access_key"] is None
            assert config["secret_key"] is None

    @pytest.mark.unit
    def test_minio_config_validation(self):
        """Test MinIO configuration validation."""
        with patch.dict("os.environ", {"MINIO_ENDPOINT": "localhost:9000"}, clear=True):
            config = ObjectStorageConfig.get_settings()
            with pytest.raises(
                ValueError, match="Object storage configuration incomplete"
            ):
                ObjectStorageConfig.validate(config)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_minio_endpoint_with_http_protocol_not_duplicated(self):
        """
        Test that when MINIO_ENDPOINT includes http:// prefix, it's not duplicated.

        Bug: If .env has MINIO_ENDPOINT=http://minio:9000,
        the code was constructing http://http://minio:9000
        """
        # Arrange - env with http:// prefix (as in production .env)
        env_with_http = {
            "MINIO_ENDPOINT": "http://minio:9000",
            "MINIO_ACCESS_KEY": "test-access-key",
            "MINIO_SECRET_KEY": "test-secret-key",
            "MINIO_BUCKET": "test-bucket",
        }

        with patch.dict("os.environ", env_with_http, clear=True):
            storage = MinIOStorageStrategy()

            # Mock aioboto3 session and client
            mock_client = AsyncMock()
            mock_session = Mock()
            mock_session.client = Mock(return_value=mock_client)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.put_object = AsyncMock()

            with patch.object(storage, "_get_session", return_value=mock_session):
                # Act - store something
                await storage.store(
                    content='{"test": "data"}',
                    content_type="application/json",
                    tenant_id="test-tenant",
                    task_run_id="test-run-id",
                    storage_purpose="output",
                )

            # Assert - check endpoint_url doesn't have double http://
            mock_session.client.assert_called_once()
            call_kwargs = mock_session.client.call_args[1]
            endpoint_url = call_kwargs["endpoint_url"]

            # Should be http://minio:9000, not http://http://...
            assert endpoint_url == "http://minio:9000", (
                f"Expected 'http://minio:9000', "
                f"got '{endpoint_url}' (double http:// prefix bug)"
            )
            assert "http://http://" not in endpoint_url, (
                "Endpoint URL should not have double http:// prefix"
            )

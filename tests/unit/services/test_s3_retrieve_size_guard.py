"""Regression tests for S3 object size guard in MinIOStorageStrategy.

Without a size cap, a large stored object (malicious or accidental) can
force high memory usage when retrieved via streaming body. This is a DoS
vector since workflow run endpoints parse the content into memory.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_async_body(data: bytes, chunk_size: int = 8192):
    """Create a mock S3 streaming body that yields chunks via async iteration."""
    mock_body = AsyncMock()

    async def async_iter():
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    mock_body.__aiter__ = lambda self: async_iter()
    return mock_body


class TestMinIORetrieveSizeGuard:
    """Verify MinIOStorageStrategy.retrieve() enforces a size limit."""

    @pytest.mark.asyncio
    async def test_retrieve_rejects_oversized_object(self):
        """retrieve() must raise ValueError for objects exceeding the size limit."""
        from analysi.services.storage import (
            _MAX_S3_OBJECT_BYTES,
            MinIOStorageStrategy,
        )

        strategy = MinIOStorageStrategy.__new__(MinIOStorageStrategy)
        strategy.config = {
            "endpoint": "http://localhost:9000",
            "access_key": "test",
            "secret_key": "test",
            "bucket": "test-bucket",
        }

        # Create oversized content
        oversized = b"x" * (_MAX_S3_OBJECT_BYTES + 1)
        mock_body = _make_async_body(oversized)

        mock_s3 = AsyncMock()
        mock_s3.get_object = AsyncMock(return_value={"Body": mock_body})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)
        strategy._session = mock_session

        with pytest.raises(ValueError, match="byte limit"):
            await strategy.retrieve("test/path.json", "application/json")

    @pytest.mark.asyncio
    async def test_retrieve_accepts_normal_sized_object(self):
        """Normal-sized objects should be returned successfully."""
        from analysi.services.storage import MinIOStorageStrategy

        strategy = MinIOStorageStrategy.__new__(MinIOStorageStrategy)
        strategy.config = {
            "endpoint": "http://localhost:9000",
            "access_key": "test",
            "secret_key": "test",
            "bucket": "test-bucket",
        }

        normal_content = b'{"result": "ok"}'
        mock_body = _make_async_body(normal_content)

        mock_s3 = AsyncMock()
        mock_s3.get_object = AsyncMock(return_value={"Body": mock_body})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)
        strategy._session = mock_session

        result = await strategy.retrieve("test/path.json", "application/json")
        assert result == '{"result": "ok"}'


class TestSizeGuardChunkedRead:
    """Verify body is read via async iteration with size tracking."""

    @pytest.mark.asyncio
    async def test_size_tracked_during_iteration(self):
        """Total bytes should be tracked across chunks and rejected if over limit."""
        from analysi.services.storage import (
            _MAX_S3_OBJECT_BYTES,
            MinIOStorageStrategy,
        )

        strategy = MinIOStorageStrategy.__new__(MinIOStorageStrategy)
        strategy.config = {
            "endpoint": "http://localhost:9000",
            "access_key": "test",
            "secret_key": "test",
            "bucket": "test-bucket",
        }

        # Create content just over the limit, in small chunks
        oversized = b"x" * (_MAX_S3_OBJECT_BYTES + 1)
        mock_body = _make_async_body(oversized, chunk_size=1024 * 1024)

        mock_s3 = AsyncMock()
        mock_s3.get_object = AsyncMock(return_value={"Body": mock_body})
        mock_s3.__aenter__ = AsyncMock(return_value=mock_s3)
        mock_s3.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.client = MagicMock(return_value=mock_s3)
        strategy._session = mock_session

        with pytest.raises(ValueError, match="byte limit"):
            await strategy.retrieve("test/path.json", "application/json")


class TestSizeGuardConstant:
    """Verify the S3 size guard constant exists and is reasonable."""

    def test_s3_limit_is_50mb(self):
        """S3 object read limit should be 50 MB."""
        from analysi.services.storage import _MAX_S3_OBJECT_BYTES

        assert _MAX_S3_OBJECT_BYTES == 50 * 1024 * 1024

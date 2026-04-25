"""
Unit tests for ArtifactStorageService.

Tests storage decision logic and content processing.
"""

import hashlib

import pytest

from analysi.services.artifact_storage import ArtifactStorageService


@pytest.fixture
def storage_service():
    """Create ArtifactStorageService instance for testing."""
    return ArtifactStorageService()


@pytest.mark.unit
class TestArtifactStorageService:
    """Test suite for ArtifactStorageService functionality."""

    def test_determine_storage_class_inline_small_text(self, storage_service):
        """Test storage decision for small text content."""
        content = "Small text content for testing"
        mime_type = "text/plain"

        result = storage_service.determine_storage_class(content, mime_type)

        assert result == "inline"

    def test_determine_storage_class_object_large_content(self, storage_service):
        """Test storage decision for content larger than 8KB threshold."""
        large_content = "x" * (10 * 1024)  # 10KB > 8KB
        mime_type = "text/plain"

        result = storage_service.determine_storage_class(large_content, mime_type)

        assert result == "object"

    def test_determine_storage_class_boundary_exactly_8kb(self, storage_service):
        """Test storage decision at exactly 8KB boundary (AD-4)."""
        content = "x" * (8 * 1024)
        mime_type = "text/plain"

        result = storage_service.determine_storage_class(content, mime_type)

        assert result == "inline"  # ≤ threshold is inline

    def test_determine_mime_type_text_content(self, storage_service):
        """Test MIME type detection for text content."""
        text_content = "This is plain text"

        result = storage_service.determine_mime_type(text_content)

        assert result == "text/plain"

    def test_determine_mime_type_json_content(self, storage_service):
        """Test MIME type detection for JSON content."""
        json_content = '{"key": "value", "number": 42}'

        result = storage_service.determine_mime_type(json_content)

        assert result == "application/json"

    def test_determine_mime_type_binary_content(self, storage_service):
        """Test MIME type detection for binary content."""
        binary_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

        result = storage_service.determine_mime_type(binary_content)

        # Our implementation detects PNG signature, which is correct
        assert result == "image/png"

    def test_encode_content_for_storage_text(self, storage_service):
        """Test content encoding for text content."""
        text_content = "Test text content"
        mime_type = "text/plain"

        result = storage_service.encode_content_for_storage(text_content, mime_type)

        assert isinstance(result, bytes)
        assert result == text_content.encode("utf-8")

    def test_encode_content_for_storage_json(self, storage_service):
        """Test content encoding for JSON content."""
        json_data = {"key": "value", "number": 42}
        mime_type = "application/json"

        result = storage_service.encode_content_for_storage(json_data, mime_type)

        assert isinstance(result, bytes)
        # Should be JSON encoded (compact format without spaces)
        expected = b'{"key":"value","number":42}'
        assert result == expected

    def test_encode_content_for_storage_bytes(self, storage_service):
        """Test content encoding for binary content."""
        binary_content = b"binary data"
        mime_type = "application/octet-stream"

        result = storage_service.encode_content_for_storage(binary_content, mime_type)

        assert isinstance(result, bytes)
        assert result == binary_content

    def test_compute_hashes(self, storage_service):
        """Test hash computation for content."""
        content = b"test content for hashing"

        sha256_hash, md5_hash = storage_service.compute_hashes(content)

        # Verify hash types and lengths
        assert isinstance(sha256_hash, bytes)
        assert isinstance(md5_hash, bytes)
        assert len(sha256_hash) == 32  # SHA256 is 32 bytes
        assert len(md5_hash) == 16  # MD5 is 16 bytes

        # Verify actual hash values
        expected_sha256 = hashlib.sha256(content).digest()
        expected_md5 = hashlib.md5(content).digest()
        assert sha256_hash == expected_sha256
        assert md5_hash == expected_md5

    def test_inline_threshold_constant(self, storage_service):
        """Test that inline threshold is 8KB (AD-4)."""
        assert storage_service.INLINE_THRESHOLD == 8 * 1024

    def test_text_mime_types_list(self, storage_service):
        """Test that text MIME types are properly defined."""
        expected_types = [
            "application/json",
            "text/plain",
            "text/markdown",
            "text/csv",
            "text/html",
            "text/xml",
            "application/xml",
        ]

        for mime_type in expected_types:
            assert mime_type in storage_service.TEXT_MIME_TYPES

    def test_decode_content_from_storage_text(self, storage_service):
        """Text MIME types return decoded string."""
        content = b"Hello, world!"
        result = storage_service.decode_content_from_storage(content, "text/plain")
        assert result == "Hello, world!"
        assert isinstance(result, str)

    def test_decode_content_from_storage_json(self, storage_service):
        """JSON MIME type returns decoded string (caller parses if needed)."""
        content = b'{"key":"value"}'
        result = storage_service.decode_content_from_storage(
            content, "application/json"
        )
        assert result == '{"key":"value"}'
        assert isinstance(result, str)

    def test_decode_content_from_storage_binary(self, storage_service):
        """Binary MIME type returns raw bytes."""
        content = b"\x89PNG\r\n"
        result = storage_service.decode_content_from_storage(content, "image/png")
        assert result == content
        assert isinstance(result, bytes)

    def test_generate_object_key_content_addressable(self, storage_service):
        """Object key uses SHA256 hex digest (AD-2)."""
        sha256_hex = "a" * 64
        key = storage_service.generate_object_key("tenant-1", sha256_hex)
        assert key == f"artifacts/tenant-1/{'a' * 64}"

    def test_generate_object_key_deterministic(self, storage_service):
        """Same inputs always produce same key (content-addressable)."""
        key1 = storage_service.generate_object_key("t", "abc123")
        key2 = storage_service.generate_object_key("t", "abc123")
        assert key1 == key2 == "artifacts/t/abc123"


@pytest.mark.unit
class TestArtifactStorageCompression:
    """Tests for inline content compression/decompression."""

    def test_compress_json_content(self, storage_service):
        """JSON content above threshold gets compressed with encoding='zlib'."""
        content = b'{"events":' + b'[{"type":"login","ip":"192.168.1.1"}]' * 5 + b"}"
        result, encoding = storage_service.compress_for_inline(
            content, "application/json"
        )
        assert len(result) < len(content)
        assert encoding == "zlib"

    def test_compress_text_content(self, storage_service):
        """Text content above threshold gets compressed with encoding='zlib'."""
        content = b"The quick brown fox jumps over the lazy dog. " * 5
        result, encoding = storage_service.compress_for_inline(content, "text/plain")
        assert len(result) < len(content)
        assert encoding == "zlib"

    def test_compress_skips_small_content(self, storage_service):
        """Content below minimum threshold returns None encoding."""
        content = b'{"small": true}'
        result, encoding = storage_service.compress_for_inline(
            content, "application/json"
        )
        assert result == content  # unchanged
        assert encoding is None

    def test_compress_skips_binary_mime(self, storage_service):
        """Binary MIME types return None encoding."""
        content = b"\x89PNG" + b"\x00" * 200
        result, encoding = storage_service.compress_for_inline(content, "image/png")
        assert result == content  # unchanged
        assert encoding is None

    def test_decompress_with_zlib_encoding(self, storage_service):
        """Decompress correctly round-trips using content_encoding field."""
        original = b'{"events":' + b'[{"type":"login"}]' * 10 + b"}"
        compressed, encoding = storage_service.compress_for_inline(
            original, "application/json"
        )
        assert compressed != original  # was actually compressed
        assert encoding == "zlib"
        decompressed = storage_service.decompress_inline(
            compressed, content_encoding=encoding
        )
        assert decompressed == original

    def test_decompress_with_none_encoding(self, storage_service):
        """Uncompressed content passes through when encoding is None."""
        content = b'{"key": "value"}'
        result = storage_service.decompress_inline(content, content_encoding=None)
        assert result == content

    def test_decompress_binary_with_none_encoding(self, storage_service):
        """Binary content starting with 0x78 is NOT decompressed when encoding is None."""
        content = b"\x78\xff\x00\x01\x02"
        result = storage_service.decompress_inline(content, content_encoding=None)
        assert result == content  # no magic-byte sniffing

    def test_compress_returns_none_encoding_when_not_smaller(self, storage_service):
        """If compression doesn't reduce size, encoding is None."""
        import os

        content = os.urandom(100)
        result, encoding = storage_service.compress_for_inline(content, "text/plain")
        # Either compressed (smaller) or original (same size)
        assert len(result) <= len(content)
        if len(result) < len(content):
            assert encoding == "zlib"
        else:
            assert encoding is None

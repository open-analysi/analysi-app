"""
Unit tests for Artifact SQLAlchemy model.

Tests model structure and basic initialization without database.
"""

from uuid import uuid4

import pytest

from analysi.models.artifact import Artifact


@pytest.mark.unit
class TestArtifactModel:
    """Test suite for Artifact model creation and methods."""

    def test_artifact_model_attributes(self):
        """Test that Artifact model has expected attributes."""
        # Test required attributes exist
        assert hasattr(Artifact, "id")
        assert hasattr(Artifact, "tenant_id")
        assert hasattr(Artifact, "name")
        assert hasattr(Artifact, "artifact_type")
        assert hasattr(Artifact, "mime_type")
        assert hasattr(Artifact, "tags")
        assert hasattr(Artifact, "sha256")
        assert hasattr(Artifact, "md5")
        assert hasattr(Artifact, "size_bytes")
        assert hasattr(Artifact, "storage_class")
        assert hasattr(Artifact, "inline_content")
        assert hasattr(Artifact, "content_encoding")
        assert hasattr(Artifact, "bucket")
        assert hasattr(Artifact, "object_key")
        assert hasattr(Artifact, "created_at")

        # Test relationship attributes exist (task_id and workflow_id removed in V070)
        assert hasattr(Artifact, "alert_id")
        assert hasattr(Artifact, "task_run_id")
        assert hasattr(Artifact, "workflow_run_id")
        assert hasattr(Artifact, "workflow_node_instance_id")
        assert hasattr(Artifact, "analysis_id")
        assert hasattr(Artifact, "integration_id")
        assert hasattr(Artifact, "source")
        assert hasattr(Artifact, "deleted_at")

    def test_artifact_model_initialization(self):
        """Test Artifact model initialization with minimal fields."""
        artifact_data = {
            "tenant_id": "test-tenant",
            "name": "Test Timeline Analysis",
            "artifact_type": "timeline",
            "mime_type": "application/json",
            "tags": ["analysis", "timeline", "security"],
            "sha256": b"mock_sha256_hash_32_bytes____",  # Exactly 32 bytes
            "md5": b"mock_md5_hash_16",  # Exactly 16 bytes
            "size_bytes": 1024,
            "storage_class": "inline",
            "inline_content": b'{"events": [{"time": "10:00", "action": "login"}]}',
            "bucket": None,
            "object_key": None,
            "task_run_id": uuid4(),
            "workflow_run_id": None,
            "workflow_node_instance_id": None,
            "analysis_id": None,
            "integration_id": "virustotal-prod",
            "source": "auto_capture",
            "deleted_at": None,
        }

        artifact = Artifact(**artifact_data)

        # Verify basic attributes are set
        assert artifact.tenant_id == "test-tenant"
        assert artifact.name == "Test Timeline Analysis"
        assert artifact.artifact_type == "timeline"
        assert artifact.storage_class == "inline"
        assert artifact.size_bytes == 1024
        assert artifact.integration_id == "virustotal-prod"
        assert artifact.source == "auto_capture"

    def test_artifact_is_inline_storage_property(self):
        """Test is_inline_storage property for storage strategy detection."""
        inline_artifact = Artifact(
            tenant_id="test-tenant",
            name="Inline Artifact",
            mime_type="text/plain",
            sha256=b"hash123hash123hash123hash123h",  # 32 bytes
            md5=b"hash123hash123h_",  # 16 bytes
            size_bytes=100,
            storage_class="inline",
            inline_content=b"small content",
            task_run_id=uuid4(),
            source="auto_capture",
        )

        object_artifact = Artifact(
            tenant_id="test-tenant",
            name="Object Artifact",
            mime_type="application/octet-stream",
            sha256=b"hash456hash456hash456hash456h",  # 32 bytes
            md5=b"hash456hash456h_",  # 16 bytes
            size_bytes=500000,
            storage_class="object",
            bucket="artifacts_test",
            object_key="test/large_file.bin",
            workflow_run_id=uuid4(),
            source="auto_capture",
        )

        # Test the property works
        assert inline_artifact.is_inline_storage is True
        assert object_artifact.is_inline_storage is False

    def test_artifact_repr_method(self):
        """Test Artifact __repr__ string representation."""
        artifact = Artifact(
            tenant_id="test-tenant",
            name="Repr Test",
            artifact_type="activity_graph",
            mime_type="application/json",
            sha256=b"test_hash_32_bytes_test_hash_32_",  # 32 bytes
            size_bytes=200,
            storage_class="inline",
            task_run_id=uuid4(),
        )

        # Test string representation includes key identifiers
        repr_str = repr(artifact)
        assert "Artifact(" in repr_str
        assert "test-tenant" in repr_str
        assert "Repr Test" in repr_str
        assert "activity_graph" in repr_str

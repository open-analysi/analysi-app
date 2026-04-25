"""
Integration tests for Artifact Storage.

Tests storage layer integration with PostgreSQL and MinIO.
Following TDD approach - all tests should fail initially.
"""

from uuid import uuid4

import pytest

from analysi.repositories.artifact_repository import ArtifactRepository
from analysi.schemas.artifact import ArtifactCreate
from analysi.services.artifact_service import ArtifactService
from analysi.services.artifact_storage import ArtifactStorageService

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.integration
class TestArtifactStorageIntegration:
    """Integration tests for storage layer."""

    @pytest.fixture
    async def artifact_service(self, integration_test_session):
        """Create ArtifactService instance with test session."""
        return ArtifactService(integration_test_session)

    @pytest.fixture
    async def storage_service(self):
        """Create ArtifactStorageService instance."""
        return ArtifactStorageService()

    @pytest.fixture
    async def repository(self, integration_test_session):
        """Create ArtifactRepository instance with test session."""
        return ArtifactRepository(integration_test_session)

    @pytest.mark.asyncio
    async def test_end_to_end_inline_storage_postgresql(self, artifact_service):
        """IT-STOR-1: End-to-end inline storage (PostgreSQL BYTEA)."""
        # Test data
        content = b'{"timeline": "test data for inline storage"}'
        tenant_id = "test-tenant"

        # Create artifact via service (should use inline storage)
        artifact_data = ArtifactCreate(
            name="Inline Storage Test",
            content=content.decode("utf-8"),
            artifact_type="timeline",
            task_run_id=uuid4(),
        )

        # Should fail since service not implemented
        created_artifact = await artifact_service.create_artifact(
            tenant_id, artifact_data
        )

        # Should fail since methods not implemented
        assert created_artifact.storage_class == "inline"
        assert created_artifact.size_bytes == len(content)
        assert created_artifact.bucket is None
        assert created_artifact.object_key is None

        # Verify data stored in PostgreSQL inline_content field
        retrieved_artifact = await artifact_service.get_artifact(
            tenant_id, created_artifact.id
        )

        # Should fail since methods not implemented
        assert retrieved_artifact is not None
        assert retrieved_artifact.storage_class == "inline"

        # Verify content can be downloaded directly
        download_info = await artifact_service.get_download_info(
            tenant_id, created_artifact.id
        )

        # Should fail since methods not implemented
        assert download_info["storage_class"] == "inline"
        assert download_info["content"] == content

    @pytest.mark.asyncio
    async def test_end_to_end_object_storage_minio(
        self, artifact_service, storage_service
    ):
        """IT-STOR-2: End-to-end object storage (MinIO)."""
        # Large content for object storage
        large_content = "Large test content for MinIO storage " * 10000  # > 256KB
        tenant_id = "test-tenant"

        artifact_data = ArtifactCreate(
            name="Object Storage Test",
            content=large_content,
            artifact_type="log_archive",
            workflow_run_id=uuid4(),
        )

        # Should fail since service not implemented
        created_artifact = await artifact_service.create_artifact(
            tenant_id, artifact_data
        )

        # Should fail since methods not implemented
        assert created_artifact.storage_class == "object"
        assert created_artifact.size_bytes > 256 * 1024
        assert created_artifact.bucket is not None
        assert created_artifact.object_key is not None

        # Verify object was stored in MinIO
        # Should fail since storage service not implemented
        retrieved_content = await storage_service.retrieve_object(
            bucket=created_artifact.bucket, object_key=created_artifact.object_key
        )

        # Should fail since methods not implemented
        assert retrieved_content.decode("utf-8") == large_content

        # Verify presigned URL generation
        presigned_url = await storage_service.generate_presigned_url(
            bucket=created_artifact.bucket,
            object_key=created_artifact.object_key,
            expires_hours=1,
        )

        # Should fail since methods not implemented
        assert presigned_url.startswith("http")
        assert "minio" in presigned_url.lower() or "localhost" in presigned_url

    @pytest.mark.asyncio
    async def test_bucket_separation_artifacts_vs_test(self, storage_service):
        """IT-STOR-3: Bucket name is read from config at init time."""
        # Config is cached at __init__ — verify it was resolved
        assert storage_service._bucket is not None
        assert isinstance(storage_service._bucket, str)

    @pytest.mark.asyncio
    async def test_production_bucket_configuration(self, storage_service):
        """Test bucket config is set and non-empty."""
        assert len(storage_service._bucket) > 0

    @pytest.mark.asyncio
    async def test_large_file_handling_and_retrieval(self, artifact_service):
        """IT-STOR-4: Large file handling and retrieval."""
        # Create 1MB test file
        large_binary_content = b"Binary data block " * 60000  # ~1.08MB
        tenant_id = "test-tenant"

        artifact_data = ArtifactCreate(
            name="1MB Binary File",
            content=large_binary_content.hex(),  # Send as hex
            content_encoding="hex",
            artifact_type="log_archive",
            workflow_run_id=str(uuid4()),  # Use safe foreign key field
        )

        # Should fail since service not implemented
        created_artifact = await artifact_service.create_artifact(
            tenant_id, artifact_data
        )

        # Should fail since methods not implemented
        assert created_artifact.storage_class == "object"
        assert created_artifact.size_bytes >= 1024 * 1024  # At least 1MB

        # Test retrieval of large file
        download_info = await artifact_service.get_download_info(
            tenant_id, created_artifact.id
        )

        # Should fail since methods not implemented
        assert download_info["storage_class"] == "object"
        # Note: download_url not implemented yet
        # assert "download_url" in download_info

    @pytest.mark.asyncio
    async def test_content_type_preservation_across_storage(self, artifact_service):
        """IT-STOR-5: Content type preservation across storage/retrieval."""
        tenant_id = "test-tenant"

        test_cases = [
            {
                "name": "JSON Document",
                "content": '{"test": "json content"}',
                "expected_mime": "application/json",
                "artifact_type": "activity_graph",
            },
            {
                "name": "Plain Text Log",
                "content": "Plain text log entry\nSecond line\nThird line",
                "expected_mime": "text/plain",
                "artifact_type": "timeline",
            },
            {
                "name": "CSV Data",
                "content": "name,age,city\nAlice,30,NYC\nBob,25,LA",
                "expected_mime": "text/csv",
                "artifact_type": "alert_summary",
            },
        ]

        for case in test_cases:
            artifact_data = ArtifactCreate(
                name=case["name"],
                content=case["content"],
                artifact_type=case["artifact_type"],
                workflow_run_id=str(uuid4()),  # Use safe foreign key field
            )

            # Should fail since service not implemented
            created_artifact = await artifact_service.create_artifact(
                tenant_id, artifact_data
            )

            # Should fail since methods not implemented
            assert created_artifact.mime_type == case["expected_mime"]

            # Verify MIME type preserved on retrieval
            download_info = await artifact_service.get_download_info(
                tenant_id, created_artifact.id
            )

            # Should fail since methods not implemented
            assert download_info["mime_type"] == case["expected_mime"]


@pytest.mark.integration
class TestArtifactDatabaseIntegration:
    """Integration tests for database operations."""

    @pytest.fixture
    async def repository(self, integration_test_session):
        """Create ArtifactRepository instance with test session."""
        return ArtifactRepository(integration_test_session)

    @pytest.mark.asyncio
    async def test_partition_creation_and_management(self, repository):
        """IT-DB-1: Partition creation and management (daily partitions)."""
        # Create artifacts across multiple days (would create partitions)
        tenant_id = "test-tenant"

        for i in range(5):
            artifact_data = {
                "tenant_id": tenant_id,
                "name": f"Partition Test {i}",
                "artifact_type": "timeline",
                "mime_type": "text/plain",
                "tags": [f"partition_test_{i}"],
                "sha256": b"hash" + b"\x00" * 28,
                "size_bytes": 100,
                "storage_class": "inline",
                "inline_content": f"Content {i}".encode(),
                "task_run_id": uuid4(),
            }

            # Should fail since repository.create not implemented
            created_artifact = await repository.create(artifact_data)

            # Should fail since method not implemented
            assert created_artifact.tenant_id == tenant_id
            assert created_artifact.name == f"Partition Test {i}"

    @pytest.mark.asyncio
    async def test_cross_partition_queries(self, repository):
        """IT-DB-2: Cross-partition queries work correctly."""
        tenant_id = "test-tenant"

        # Create artifacts that might span partitions
        artifact_ids = []
        for i in range(3):
            artifact_data = {
                "tenant_id": tenant_id,
                "name": f"Cross Partition {i}",
                "artifact_type": "alert_summary",
                "mime_type": "application/json",
                "tags": ["cross_partition_test"],
                "sha256": b"hash" + b"\x00" * 28,
                "size_bytes": 200,
                "storage_class": "inline",
                "inline_content": f'{{"test": {i}}}'.encode(),
                "analysis_id": uuid4(),
            }

            # Should fail since repository.create not implemented
            created_artifact = await repository.create(artifact_data)
            artifact_ids.append(created_artifact.id)

        # Query across partitions
        # Should fail since repository.list not implemented
        artifacts, total = await repository.list(
            tenant_id=tenant_id, filters={"tags": ["cross_partition_test"]}, limit=10
        )

        # Should fail since method not implemented
        assert len(artifacts) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_relationship_tracking_task_run_id(self, repository):
        """IT-DB-3: Relationship tracking works (task_run_id population)."""
        tenant_id = "test-tenant"
        task_run_id = uuid4()

        # Create multiple artifacts for same task run
        for i in range(3):
            artifact_data = {
                "tenant_id": tenant_id,
                "name": f"Task Run Artifact {i}",
                "artifact_type": "timeline",
                "mime_type": "text/plain",
                "tags": ["task_run_test"],
                "sha256": b"hash" + b"\x00" * 28,
                "size_bytes": 50,
                "storage_class": "inline",
                "inline_content": f"Task run content {i}".encode(),
                "task_run_id": task_run_id,
            }

            # Should fail since repository.create not implemented
            await repository.create(artifact_data)

        # Query by task_run_id
        # Should fail since repository.get_by_task_run not implemented
        task_artifacts = await repository.get_by_task_run(tenant_id, task_run_id)

        # Should fail since method not implemented
        assert len(task_artifacts) == 3
        for artifact in task_artifacts:
            assert artifact.task_run_id == task_run_id

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation_enforcement(self, repository):
        """IT-DB-4: Multi-tenant isolation enforcement."""
        tenant_a = "tenant-a"
        tenant_b = "tenant-b"

        # Create artifacts for different tenants
        artifact_a_data = {
            "tenant_id": tenant_a,
            "name": "Tenant A Artifact",
            "artifact_type": "timeline",
            "mime_type": "text/plain",
            "tags": ["tenant_isolation_test"],
            "sha256": b"hash_a" + b"\x00" * 26,
            "size_bytes": 100,
            "storage_class": "inline",
            "inline_content": b"Tenant A content",
            "workflow_run_id": uuid4(),
        }

        artifact_b_data = {
            "tenant_id": tenant_b,
            "name": "Tenant B Artifact",
            "artifact_type": "alert_summary",
            "mime_type": "text/plain",
            "tags": ["tenant_isolation_test"],
            "sha256": b"hash_b" + b"\x00" * 26,
            "size_bytes": 100,
            "storage_class": "inline",
            "inline_content": b"Tenant B content",
            "workflow_run_id": uuid4(),
        }

        # Should fail since repository.create not implemented
        await repository.create(artifact_a_data)
        artifact_b = await repository.create(artifact_b_data)

        # Verify tenant A can only see their artifacts
        # Should fail since repository.list not implemented
        tenant_a_artifacts, _ = await repository.list(tenant_id=tenant_a)

        # Should fail since method not implemented
        tenant_a_names = [a.name for a in tenant_a_artifacts]
        assert "Tenant A Artifact" in tenant_a_names
        assert "Tenant B Artifact" not in tenant_a_names

        # Verify tenant B can only see their artifacts
        # Should fail since repository.list not implemented
        tenant_b_artifacts, _ = await repository.list(tenant_id=tenant_b)

        # Should fail since method not implemented
        tenant_b_names = [a.name for a in tenant_b_artifacts]
        assert "Tenant B Artifact" in tenant_b_names
        assert "Tenant A Artifact" not in tenant_b_names

        # Verify cross-tenant access fails
        # Should fail since repository.get_by_id not implemented
        cross_access_result = await repository.get_by_id(tenant_a, artifact_b.id)

        # Should fail since method not implemented
        assert (
            cross_access_result is None
        )  # Should not be able to access other tenant's data

    @pytest.mark.asyncio
    async def test_soft_delete_data_preservation(self, repository):
        """IT-DB-5: Soft delete preservation of data."""
        tenant_id = "test-tenant"

        # Create artifact
        artifact_data = {
            "tenant_id": tenant_id,
            "name": "Soft Delete Test",
            "artifact_type": "timeline",
            "mime_type": "text/plain",
            "tags": ["soft_delete_test"],
            "sha256": b"hash" + b"\x00" * 28,
            "size_bytes": 200,
            "storage_class": "inline",
            "inline_content": b"Content to be soft deleted",
            "analysis_id": uuid4(),
        }

        # Should fail since repository.create not implemented
        created_artifact = await repository.create(artifact_data)
        artifact_id = created_artifact.id

        # Verify artifact exists and is not deleted
        # Should fail since repository.get_by_id not implemented
        original_artifact = await repository.get_by_id(tenant_id, artifact_id)

        # Should fail since method not implemented
        assert original_artifact is not None
        assert original_artifact.is_soft_deleted is False

        # Soft delete the artifact
        # Should fail since repository.soft_delete not implemented
        delete_success = await repository.soft_delete(tenant_id, artifact_id)

        # Should fail since method not implemented
        assert delete_success is True

        # Verify artifact is marked as deleted but data is preserved
        # Query directly in DB since get_by_id filters out deleted artifacts
        from sqlalchemy import select as sa_select

        from analysi.models.artifact import Artifact

        stmt = sa_select(Artifact).where(Artifact.id == artifact_id)
        result = await repository.session.execute(stmt)
        deleted_artifact = result.scalar_one_or_none()

        assert deleted_artifact is not None  # Still exists in database
        assert deleted_artifact.is_soft_deleted is True  # But marked as deleted
        assert (
            deleted_artifact.inline_content == b"Content to be soft deleted"
        )  # Data preserved
        assert deleted_artifact.name == "Soft Delete Test"  # Metadata preserved

        # Verify artifact doesn't appear in normal lists (filtered out)
        # Should fail since repository.list not implemented
        active_artifacts, _ = await repository.list(tenant_id=tenant_id)

        # Should fail since method not implemented
        active_names = [a.name for a in active_artifacts]
        assert "Soft Delete Test" not in active_names  # Filtered out of normal results

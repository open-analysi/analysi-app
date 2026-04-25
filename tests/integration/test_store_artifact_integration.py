"""
Simple integration test for store_artifact function

Tests direct integration between store_artifact Cy function and database
"""

import json
import zlib
from uuid import uuid4

import pytest

from analysi.repositories.artifact_repository import ArtifactRepository
from analysi.services.artifact_service import ArtifactService
from analysi.services.cy_functions import CyArtifactFunctions


@pytest.mark.integration
class TestStoreArtifactIntegration:
    """Test store_artifact function direct database integration."""

    @pytest.mark.asyncio
    async def test_artifact_repository_direct_integration(
        self, integration_test_session
    ):
        """Test artifact repository creates artifacts in database directly."""

        tenant_id = "test-artifact-tenant"
        workflow_run_id = str(uuid4())

        # Create artifact data directly (bypassing service layer)
        artifact_data = {
            "tenant_id": tenant_id,
            "name": "Test Integration Artifact",
            "artifact_type": "test_type",
            "mime_type": "application/json",
            "tags": {"category": "test", "priority": "low"},
            "sha256": b"test_hash_bytes_here_32_chars_xx",  # 32 bytes
            "size_bytes": 100,
            "storage_class": "inline",
            "inline_content": b'{"message": "Hello from integration test"}',
            "workflow_run_id": workflow_run_id,
        }

        # Use repository directly with integration test session
        artifact_repo = ArtifactRepository(integration_test_session)

        # Create artifact
        await artifact_repo.create(artifact_data)

        # Query it back
        artifacts_list, total_count = await artifact_repo.list(tenant_id)

        # Verify artifact was persisted
        assert len(artifacts_list) == 1
        artifact = artifacts_list[0]

        assert artifact.name == "Test Integration Artifact"
        assert artifact.tenant_id == tenant_id
        assert str(artifact.workflow_run_id) == workflow_run_id
        assert artifact.artifact_type == "test_type"
        assert artifact.storage_class == "inline"

        # Verify content
        raw = artifact.inline_content
        if raw and len(raw) >= 2 and raw[0] == 0x78:
            raw = zlib.decompress(raw)
        content = json.loads(raw.decode("utf-8"))
        assert content["message"] == "Hello from integration test"

    @pytest.mark.asyncio
    async def test_store_artifact_function_integration(
        self, integration_test_session, httpx_mock
    ):
        """Test store_artifact function integration with mocked HTTP API."""

        tenant_id = "test-artifact-tenant"
        workflow_run_id = str(uuid4())
        mock_artifact_id = str(uuid4())

        # Mock the HTTP POST to artifacts API
        httpx_mock.add_response(
            url=f"http://localhost:8001/v1/{tenant_id}/artifacts",
            method="POST",
            status_code=201,
            json={"id": mock_artifact_id},
        )

        execution_context = {"workflow_run_id": workflow_run_id, "tenant_id": tenant_id}

        artifact_service = ArtifactService(integration_test_session)
        cy_functions = CyArtifactFunctions(artifact_service, execution_context)

        test_data = {"message": "Hello from integration test"}
        test_tags = {"category": "test", "priority": "low"}

        # Call store_artifact function
        artifact_id = await cy_functions.store_artifact(
            name="Test Integration Artifact",
            artifact=test_data,
            tags=test_tags,
            artifact_type="test_type",
        )

        # Verify function integration works
        assert artifact_id == mock_artifact_id

    @pytest.mark.asyncio
    async def test_store_artifact_function_mock_behavior(
        self, integration_test_session, httpx_mock
    ):
        """Test that store_artifact function returns valid artifact IDs."""

        tenant_id = "mock-test-tenant"
        mock_artifact_id = str(uuid4())

        # Mock the HTTP POST to artifacts API
        httpx_mock.add_response(
            url=f"http://localhost:8001/v1/{tenant_id}/artifacts",
            method="POST",
            status_code=201,
            json={"id": mock_artifact_id},
        )

        execution_context = {"tenant_id": tenant_id}

        artifact_service = ArtifactService(integration_test_session)
        cy_functions = CyArtifactFunctions(artifact_service, execution_context)

        artifact_id = await cy_functions.store_artifact(
            name="Mock Test Artifact",
            artifact={"data": "test"},
            tags={},
            artifact_type="test",
        )

        # Verify function returns a valid UUID format
        assert artifact_id is not None
        assert isinstance(artifact_id, str)
        from uuid import UUID

        UUID(artifact_id)  # This will raise ValueError if not valid UUID

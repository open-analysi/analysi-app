"""
Critical integration tests for Artifacts Store - User Requirements.

These are the specific tests requested by the user:
- IT-REQ-A1: Store/retrieve inline binary payload via POST/GET API
- IT-REQ-A2: Store/retrieve inline JSON payload via POST/GET API
- IT-REQ-B1: Send large payload (>256KB), verify stored in MinIO object storage
- IT-REQ-C1: Create task that uses store_artifact() Cy function, verify artifact exists

Following TDD approach - all tests should fail initially.
"""

import json
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.integration
class TestCriticalArtifactRequirements:
    """Critical user requirement tests."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        # Clean up the override
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_store_retrieve_inline_binary_payload_api(self, client: AsyncClient):
        """IT-REQ-A1: Store/retrieve inline binary payload via POST/GET API."""

        tenant_id = "test-tenant"

        # Binary payload (PNG header + some data)
        binary_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x00\x00\x00\x01\x00\x08\x02\x00\x00\x00\x90wS\xde"

        artifact_data = {
            "name": "Test Binary Image",
            "content": binary_content.hex(),  # Send as hex string
            "content_encoding": "hex",
            "artifact_type": "log_archive",
            "tags": {"format": "png", "source": "test"},
            "workflow_run_id": str(uuid4()),  # Satisfy relationship constraint
        }

        # POST: Create artifact
        response = await client.post(f"/v1/{tenant_id}/artifacts", json=artifact_data)
        assert response.status_code == 201
        created_artifact = response.json()["data"]

        assert created_artifact["name"] == "Test Binary Image"
        assert (
            created_artifact["storage_class"] == "inline"
        )  # Should be inline (< 256KB)
        assert (
            created_artifact["mime_type"] == "image/png"
        )  # Correctly detected from PNG magic bytes

        artifact_id = created_artifact["id"]

        # GET: Retrieve artifact metadata
        get_response = await client.get(f"/v1/{tenant_id}/artifacts/{artifact_id}")
        assert get_response.status_code == 200
        retrieved_artifact = get_response.json()["data"]

        assert retrieved_artifact["id"] == artifact_id
        assert retrieved_artifact["name"] == "Test Binary Image"
        assert retrieved_artifact["storage_class"] == "inline"

        # GET: Download raw binary content
        download_response = await client.get(
            f"/v1/{tenant_id}/artifacts/{artifact_id}/download"
        )
        assert download_response.status_code == 200
        assert download_response.headers["content-type"] == "image/png"
        assert download_response.content == binary_content

    @pytest.mark.asyncio
    async def test_store_retrieve_inline_json_payload_api(self, client: AsyncClient):
        """IT-REQ-A2: Store/retrieve inline JSON payload via POST/GET API."""

        tenant_id = "test-tenant"

        # JSON payload
        json_content = {
            "timeline": {
                "events": [
                    {
                        "time": "10:00",
                        "event": "login",
                        "user": "alice",
                        "ip": "192.168.1.100",
                    },
                    {
                        "time": "10:15",
                        "event": "file_access",
                        "file": "/secrets/data.txt",
                    },
                    {"time": "10:30", "event": "logout"},
                ]
            },
            "analysis": {
                "risk_score": 8.5,
                "suspicious_indicators": ["unusual_ip", "sensitive_file_access"],
            },
        }

        artifact_data = {
            "name": "Security Timeline Analysis",
            "content": json.dumps(json_content),
            "content_encoding": "utf-8",
            "artifact_type": "timeline",
            "tags": {"category": "security", "priority": "high"},
            "workflow_run_id": str(uuid4()),  # Satisfy relationship constraint
        }

        # POST: Create artifact
        response = await client.post(f"/v1/{tenant_id}/artifacts", json=artifact_data)
        assert response.status_code == 201
        created_artifact = response.json()["data"]

        assert created_artifact["name"] == "Security Timeline Analysis"
        assert created_artifact["artifact_type"] == "timeline"
        assert created_artifact["storage_class"] == "inline"  # JSON should be inline
        assert created_artifact["mime_type"] == "application/json"

        artifact_id = created_artifact["id"]

        # GET: Retrieve and verify JSON content
        download_response = await client.get(
            f"/v1/{tenant_id}/artifacts/{artifact_id}/download"
        )
        assert download_response.status_code == 200
        assert download_response.headers["content-type"] == "application/json"

        # Verify JSON content is preserved
        retrieved_json = download_response.json()
        assert retrieved_json == json_content
        assert retrieved_json["timeline"]["events"][0]["user"] == "alice"
        assert retrieved_json["analysis"]["risk_score"] == 8.5

    @pytest.mark.asyncio
    async def test_large_payload_minio_object_storage(
        self, client: AsyncClient, minio_test_bucket
    ):
        """IT-REQ-B1: Send large payload (>256KB), verify stored in MinIO object storage."""

        tenant_id = "test-tenant"

        # Create large payload > 256KB
        large_content = "Large log entry " * 20000  # ~340KB

        artifact_data = {
            "name": "Large System Log",
            "content": large_content,
            "content_encoding": "utf-8",
            "artifact_type": "log_archive",
            "tags": {"size": "large", "system": "auth_server"},
            "workflow_run_id": str(uuid4()),  # Satisfy relationship constraint
        }

        # POST: Create large artifact
        response = await client.post(f"/v1/{tenant_id}/artifacts", json=artifact_data)
        assert response.status_code == 201
        created_artifact = response.json()["data"]

        assert created_artifact["name"] == "Large System Log"
        assert created_artifact["storage_class"] == "object"  # Should be object storage
        assert created_artifact["size_bytes"] > 256 * 1024  # Verify size > 256KB

        # Verify MinIO storage fields are populated
        assert created_artifact["bucket"] is not None
        assert created_artifact["object_key"] is not None
        assert created_artifact["bucket"] == minio_test_bucket

        artifact_id = created_artifact["id"]

        # GET: Retrieve metadata (should include download URL)
        get_response = await client.get(f"/v1/{tenant_id}/artifacts/{artifact_id}")
        assert get_response.status_code == 200
        retrieved_artifact = get_response.json()["data"]

        assert retrieved_artifact["storage_class"] == "object"
        # Note: Presigned download URL generation not implemented yet
        # assert "download_url" in retrieved_artifact
        # assert retrieved_artifact["download_url"].startswith("http")

    @pytest.mark.asyncio
    async def test_artifact_api_list_with_filtering(self, client: AsyncClient):
        """Test artifact list API with filtering by type and tags."""

        tenant_id = "test-tenant"

        # Create several test artifacts first
        wf_run_id = str(uuid4())  # Use same workflow_run_id for all test artifacts
        test_artifacts = [
            {
                "name": "Timeline 1",
                "content": '{"events": ["event1"]}',
                "artifact_type": "timeline",
                "tags": {"category": "security"},
                "workflow_run_id": wf_run_id,
            },
            {
                "name": "Analysis 1",
                "content": '{"analysis": "result"}',
                "artifact_type": "alert_summary",
                "tags": {"category": "analysis"},
                "workflow_run_id": wf_run_id,
            },
            {
                "name": "Timeline 2",
                "content": '{"events": ["event2"]}',
                "artifact_type": "timeline",
                "tags": {"category": "security"},
                "workflow_run_id": wf_run_id,
            },
        ]

        created_ids = []

        # Create test artifacts
        for artifact_data in test_artifacts:
            response = await client.post(
                f"/v1/{tenant_id}/artifacts", json=artifact_data
            )
            assert response.status_code == 201
            created_ids.append(response.json()["data"]["id"])

        # Test: List all artifacts
        response = await client.get(f"/v1/{tenant_id}/artifacts")
        assert response.status_code == 200
        all_artifacts = response.json()
        assert len(all_artifacts["data"]) >= 3

        # Test: Filter by artifact_type
        response = await client.get(f"/v1/{tenant_id}/artifacts?artifact_type=timeline")
        assert response.status_code == 200
        timeline_artifacts = response.json()
        assert len(timeline_artifacts["data"]) == 2  # Should find 2 timeline artifacts

        # Test: Pagination
        response = await client.get(f"/v1/{tenant_id}/artifacts?limit=2&offset=0")
        assert response.status_code == 200
        page_body = response.json()
        assert len(page_body["data"]) <= 2
        assert page_body["meta"]["limit"] == 2
        assert page_body["meta"]["offset"] == 0

    @pytest.mark.asyncio
    async def test_artifact_soft_delete_api(self, client: AsyncClient):
        """Test artifact soft delete via API."""

        tenant_id = "test-tenant"

        # Create artifact to delete
        artifact_data = {
            "name": "To Be Deleted",
            "content": "temporary content",
            "workflow_run_id": str(uuid4()),  # Satisfy relationship constraint
        }

        # Create artifact
        create_response = await client.post(
            f"/v1/{tenant_id}/artifacts", json=artifact_data
        )
        assert create_response.status_code == 201
        artifact_id = create_response.json()["data"]["id"]

        # Verify artifact exists
        get_response = await client.get(f"/v1/{tenant_id}/artifacts/{artifact_id}")
        assert get_response.status_code == 200
        assert get_response.json()["data"]["name"] == "To Be Deleted"

        # Delete artifact (soft delete)
        delete_response = await client.delete(
            f"/v1/{tenant_id}/artifacts/{artifact_id}"
        )
        assert delete_response.status_code == 204  # No Content

        # Verify artifact is soft deleted (should not appear in normal lists)
        list_response = await client.get(f"/v1/{tenant_id}/artifacts")
        assert list_response.status_code == 200

        artifact_names = [a["name"] for a in list_response.json()["data"]]
        assert "To Be Deleted" not in artifact_names  # Should be filtered out

        # Direct GET on soft-deleted artifact returns 404 (artifact is gone from public API)
        get_deleted_response = await client.get(
            f"/v1/{tenant_id}/artifacts/{artifact_id}"
        )
        assert get_deleted_response.status_code == 404

    @pytest.mark.asyncio
    async def test_task_cy_function_artifact_creation(self, client: AsyncClient):
        """IT-REQ-C1: Create task that uses store_artifact() Cy function, verify artifact exists."""

        tenant_id = "test-tenant"

        # Create a task that uses store_artifact in Cy script
        cy_script = """
        #!cy 2.1

        # Analyze alert data and create timeline artifact
        alert_data = {
            "alert_id": "ALERT-2024-001",
            "events": [
                {"time": "14:25", "event": "failed_login", "ip": "192.168.1.100"},
                {"time": "14:30", "event": "successful_login", "ip": "192.168.1.100"}
            ]
        }

        # Store timeline artifact using Cy native function
        timeline_id = store_artifact(
            "Alert Timeline Analysis",
            alert_data,
            {"category": "security", "alert_id": "ALERT-2024-001"},
            "timeline"
        )

        # Create analysis summary that references the timeline
        summary = {
            "summary": "Suspicious login activity detected",
            "risk_level": "HIGH",
            "timeline_artifact_id": timeline_id,
            "recommendations": ["Block IP", "Force password reset"]
        }

        # Store summary artifact
        summary_id = store_artifact(
            "Alert Analysis Summary",
            summary,
            {"category": "analysis", "alert_id": "ALERT-2024-001"},
            "alert_summary"
        )

        # Output both artifact IDs for verification
        {
            "timeline_artifact_id": timeline_id,
            "summary_artifact_id": summary_id,
            "status": "completed"
        }
        """

        task_data = {
            "name": "Cy Artifact Test Task",
            "description": "Test task that creates artifacts using store_artifact function",
            "cy_script": cy_script,
            "workflow_run_id": str(uuid4()),  # Satisfy relationship constraint
        }

        # NOTE: This test will be skipped until task execution and Cy integration is implemented
        pytest.skip("Task execution and store_artifact Cy function not yet implemented")

        # Create task
        task_response = await client.post(f"/v1/{tenant_id}/tasks", json=task_data)
        assert task_response.status_code == 201
        task = task_response.json()["data"]
        task_id = task["id"]

        # Execute task (this should create artifacts via Cy store_artifact function)
        execution_response = await client.post(
            f"/v1/{tenant_id}/tasks/{task_id}/execute"
        )
        assert execution_response.status_code == 200
        execution_result = execution_response.json()["data"]

        # Verify artifacts were created
        assert "timeline_artifact_id" in execution_result
        assert "summary_artifact_id" in execution_result

        # Check that artifacts exist in database
        timeline_artifact_id = execution_result["timeline_artifact_id"]
        summary_artifact_id = execution_result["summary_artifact_id"]

        # Verify timeline artifact
        timeline_response = await client.get(
            f"/v1/{tenant_id}/artifacts/{timeline_artifact_id}"
        )
        assert timeline_response.status_code == 200
        timeline_artifact = timeline_response.json()
        assert timeline_artifact["name"] == "Alert Timeline Analysis"
        assert timeline_artifact["artifact_type"] == "timeline"

        # Verify summary artifact
        summary_response = await client.get(
            f"/v1/{tenant_id}/artifacts/{summary_artifact_id}"
        )
        assert summary_response.status_code == 200
        summary_artifact = summary_response.json()
        assert summary_artifact["name"] == "Alert Analysis Summary"
        assert summary_artifact["artifact_type"] == "alert_summary"

        # Verify artifacts can be found by filtering
        filter_response = await client.get(
            f"/v1/{tenant_id}/artifacts?artifact_type=timeline"
        )
        assert filter_response.status_code == 200
        filtered_artifacts = filter_response.json()
        timeline_names = [a["name"] for a in filtered_artifacts["artifacts"]]
        assert "Alert Timeline Analysis" in timeline_names

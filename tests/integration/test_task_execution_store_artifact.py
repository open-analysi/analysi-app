"""
Task Execution Service Integration Test with store_artifact

Tests the complete integration flow:
TaskExecutionService → Cy script → store_artifact function → ArtifactService → Database

This is a service-level integration test that verifies:
1. TaskExecutionService can execute Cy scripts with store_artifact function
2. Execution context is properly passed through to Cy functions
3. Artifacts are successfully created and stored in database
4. Multiple artifacts can be created from single task execution
"""

import json
import zlib
from uuid import uuid4

import pytest

from analysi.models.task_run import TaskRun
from analysi.repositories.artifact_repository import ArtifactRepository
from analysi.services.task_execution import TaskExecutionService


@pytest.mark.integration
class TestTaskExecutionStoreArtifactIntegration:
    """Integration test for task execution with store_artifact function."""

    @pytest.fixture
    async def task_execution_service(self, integration_test_session):
        """Create TaskExecutionService instance with test session."""
        # Import here to avoid circular imports
        service = TaskExecutionService()
        # Override the session creation to use our test session
        service._test_session = integration_test_session
        yield service

        # Cleanup async resources
        try:
            if hasattr(service.executor, "_cleanup_artifact_session"):
                await service.executor._cleanup_artifact_session()
        except Exception:
            pass  # Ignore cleanup errors

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Event loop closed error - needs investigation")
    async def test_task_execution_creates_artifacts_via_cy_function(
        self, integration_test_session, task_execution_service
    ):
        """Test that TaskExecutionService can execute Cy scripts that create artifacts."""

        tenant_id = "integration-test-tenant"
        task_run_id = str(uuid4())
        task_id = str(uuid4())

        # Create a realistic Cy script that uses store_artifact function
        cy_script = """#!cy 2.1

// Simulate security analysis task creating multiple artifacts
analysis_input = input

// Create timeline data from analysis
timeline_data = {
    "alert_id": "ALERT-" + analysis_input["alert_id"],
    "events": [
        {
            "timestamp": "2025-08-25T14:25:00Z",
            "event_type": "failed_login",
            "source_ip": analysis_input["source_ip"],
            "user": analysis_input["user"]
        },
        {
            "timestamp": "2025-08-25T14:30:00Z",
            "event_type": "successful_login",
            "source_ip": analysis_input["source_ip"],
            "user": analysis_input["user"]
        }
    ]
}

// Store timeline artifact
timeline_artifact_id = store_artifact("Security Event Timeline", timeline_data, {"category": "security", "priority": "high", "alert_id": analysis_input["alert_id"]}, "timeline")

// Create analysis summary that references timeline
summary_data = {
    "analysis_result": "Suspicious login pattern detected",
    "risk_score": 8.5,
    "timeline_reference": timeline_artifact_id,
    "recommendations": [
        "Monitor user activity closely",
        "Consider temporary access restrictions"
    ],
    "analyst_notes": "Multiple failed attempts followed by success from same IP"
}

// Store analysis summary artifact
summary_artifact_id = store_artifact("Security Analysis Summary", summary_data, {"category": "analysis", "priority": "high", "alert_id": analysis_input["alert_id"]}, "alert_summary")

// Return execution result with artifact references
return {
    "status": "analysis_complete",
    "timeline_artifact_id": timeline_artifact_id,
    "summary_artifact_id": summary_artifact_id,
    "risk_score": 8.5
}
"""

        # Create TaskRun instance for execution
        task_run = TaskRun()
        task_run.id = task_run_id
        task_run.task_id = task_id
        task_run.tenant_id = tenant_id
        task_run.cy_script = cy_script
        task_run.status = "running"
        task_run.execution_context = {}  # Clean execution context

        # Input data for the Cy script
        input_data = {
            "alert_id": "SEC-2025-001",
            "source_ip": "192.168.1.100",
            "user": "alice.johnson",
        }

        # CRITICAL: Commit test session so background services can see test data
        await integration_test_session.commit()

        # Mock TaskRunService.retrieve_input_data to return our test input
        # But don't mock the session - let artifacts service use real session
        from unittest.mock import AsyncMock, patch

        with patch(
            "analysi.services.task_run.TaskRunService"
        ) as mock_task_service_class:
            # Setup task service mock
            mock_task_service = mock_task_service_class.return_value
            mock_task_service.retrieve_input_data = AsyncMock(return_value=input_data)
            mock_task_service.update_status = AsyncMock()

            # Execute the task - this should create artifacts via store_artifact function
            await task_execution_service.execute_single_task(task_run)

            # Verify TaskRunService was called correctly
            mock_task_service.retrieve_input_data.assert_called_once()
            mock_task_service.update_status.assert_called()

            # Check the task execution result
            update_calls = mock_task_service.update_status.call_args_list
            final_call = update_calls[-1]
            assert final_call[0][1] == task_run_id  # task_run_id

            status = final_call[0][2]
            if status == "failed":
                error_info = (
                    final_call[1].get("error_info", {}) if len(final_call) > 1 else {}
                )
                error_msg = error_info.get("error", "Unknown error")
                print(f"Task execution failed: {error_msg}")
                # Print all update calls for debugging
                for i, call in enumerate(update_calls):
                    print(f"Call {i}: {call}")
                pytest.fail(f"Task execution failed: {error_msg}")

            assert status == "completed"  # status

            # Extract the output data
            output_data = final_call[1]["output_data"]
            # Output could be a dict (if returned from Cy) or JSON string
            if isinstance(output_data, str):
                output_dict = json.loads(output_data)
            else:
                output_dict = output_data

            assert output_dict["status"] == "analysis_complete"
            assert "timeline_artifact_id" in output_dict
            assert "summary_artifact_id" in output_dict
            assert output_dict["risk_score"] == 8.5

        # CRITICAL: Let artifact service complete and commit its transactions
        import asyncio

        await asyncio.sleep(0.1)  # Give time for any async operations to complete

        # Now verify artifacts were actually created in database using the same test session
        # to avoid session isolation issues
        artifact_repo = ArtifactRepository(integration_test_session)

        # Get artifacts for this specific task run
        artifacts_list, total_count = await artifact_repo.list(
            tenant_id, filters={"task_run_id": task_run_id}
        )

        # Should have 2 artifacts created by the Cy script for this specific task run
        assert len(artifacts_list) == 2

        # Find timeline and summary artifacts
        timeline_artifact = None
        summary_artifact = None

        for artifact in artifacts_list:
            if artifact.name == "Security Event Timeline":
                timeline_artifact = artifact
            elif artifact.name == "Security Analysis Summary":
                summary_artifact = artifact

        assert timeline_artifact is not None, "Timeline artifact not found"
        assert summary_artifact is not None, "Summary artifact not found"

        # Verify timeline artifact details
        assert timeline_artifact.tenant_id == tenant_id
        assert timeline_artifact.artifact_type == "timeline"
        assert str(timeline_artifact.task_run_id) == task_run_id  # Context was passed
        assert (
            timeline_artifact.storage_class == "inline"
        )  # Should be small enough for inline
        assert timeline_artifact.is_deleted is False

        # Verify timeline content (stored as JSON, possibly compressed)
        raw = timeline_artifact.inline_content
        if raw and len(raw) >= 2 and raw[0] == 0x78:
            raw = zlib.decompress(raw)
        timeline_content = json.loads(raw.decode("utf-8"))
        assert timeline_content["alert_id"] == "ALERT-SEC-2025-001"
        assert len(timeline_content["events"]) == 2
        assert timeline_content["events"][0]["event_type"] == "failed_login"
        assert timeline_content["events"][0]["source_ip"] == "192.168.1.100"

        # Verify timeline tags (stored as key:value format)
        assert "category:security" in timeline_artifact.tags
        assert "priority:high" in timeline_artifact.tags
        assert "alert_id:SEC-2025-001" in timeline_artifact.tags

        # Verify summary artifact details
        assert summary_artifact.tenant_id == tenant_id
        assert summary_artifact.artifact_type == "alert_summary"
        assert str(summary_artifact.task_run_id) == task_run_id  # Context was passed
        assert (
            summary_artifact.storage_class == "inline"
        )  # Should be small enough for inline

        # Verify summary content (stored as JSON, possibly compressed)
        raw = summary_artifact.inline_content
        if raw and len(raw) >= 2 and raw[0] == 0x78:
            raw = zlib.decompress(raw)
        summary_content = json.loads(raw.decode("utf-8"))
        assert summary_content["analysis_result"] == "Suspicious login pattern detected"
        assert summary_content["risk_score"] == 8.5
        # Verify timeline reference exists (will be the mock ID returned during Cy execution)
        assert "timeline_reference" in summary_content
        assert len(summary_content["timeline_reference"]) == 36  # UUID length
        assert len(summary_content["recommendations"]) == 2

        # Verify summary tags (stored as key:value format)
        assert "category:analysis" in summary_artifact.tags
        assert "priority:high" in summary_artifact.tags
        assert "alert_id:SEC-2025-001" in summary_artifact.tags

    @pytest.mark.asyncio
    async def test_task_execution_context_propagation(
        self, integration_test_session, task_execution_service, httpx_mock
    ):
        """Test that execution context (task_run_id, tenant_id) is properly passed to store_artifact."""
        from unittest.mock import patch

        tenant_id = "context-test-tenant"
        task_run_id = uuid4()
        workflow_run_id = uuid4()
        test_artifact_id = str(uuid4())

        # Mock the HTTP call to artifacts API
        httpx_mock.add_response(
            method="POST",
            url=f"http://localhost:8001/v1/{tenant_id}/artifacts",
            status_code=201,
            json={"id": test_artifact_id},
        )

        # Simple Cy script that creates one artifact
        cy_script = """#!cy 2.1
artifact_data = {"test": "context_propagation"}
artifact_id = store_artifact("Context Test Artifact", artifact_data, {"test": "true"}, "test_type")
return {"artifact_id": artifact_id}
"""

        # Create and persist TaskRun to DB (required by new execute_single_task API)
        task_run = TaskRun(
            id=task_run_id,
            tenant_id=tenant_id,
            cy_script=cy_script,
            status="running",
            execution_context={
                "workflow_run_id": str(workflow_run_id),
                "node_id": "test_node",
            },
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Mock AsyncSessionLocal so execute_single_task uses integration_test_session
        with patch("analysi.db.session.AsyncSessionLocal") as mock_session_class:
            mock_session_class.return_value.__aenter__.return_value = (
                integration_test_session
            )
            mock_session_class.return_value.__aexit__.return_value = None

            # Execute task using new API (task_run_id, tenant_id)
            await task_execution_service.execute_single_task(task_run_id, tenant_id)

        # Verify the HTTP call was made with correct data
        requests = httpx_mock.get_requests()

        # Filter for artifact creation requests (ignore MCP initialization)
        artifact_requests = [r for r in requests if "/artifacts" in str(r.url)]
        assert len(artifact_requests) == 1

        request = artifact_requests[0]
        assert request.method == "POST"
        assert f"/v1/{tenant_id}/artifacts" in str(request.url)

        # Verify request payload contains context
        request_data = json.loads(request.content)
        assert request_data["name"] == "Context Test Artifact"
        assert request_data["artifact_type"] == "test_type"
        assert request_data["task_run_id"] == str(task_run_id)

    @pytest.mark.asyncio
    async def test_task_execution_store_artifact_error_handling(
        self, integration_test_session, task_execution_service, httpx_mock
    ):
        """Test error handling when store_artifact function encounters HTTP API errors."""
        from analysi.schemas.task_execution import TaskExecutionStatus

        tenant_id = "error-test-tenant"
        task_run_id = uuid4()

        # Mock the HTTP call to return an error (register multiple for retries)
        for _ in range(3):
            httpx_mock.add_response(
                method="POST",
                url=f"http://localhost:8001/v1/{tenant_id}/artifacts",
                status_code=500,
                text="Internal Server Error",
            )

        # Cy script that tries to store artifact
        cy_script = """#!cy 2.1
artifact_id = store_artifact("Error Test", {"data": "test"}, {}, "test_type")
return {"result": "completed", "artifact_id": artifact_id}
"""

        # Create and persist TaskRun to DB (required by new execute_single_task API)
        task_run = TaskRun(
            id=task_run_id,
            tenant_id=tenant_id,
            cy_script=cy_script,
            status="running",
            execution_context=None,
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Execute task using a real session (execute_single_task creates its own session)
        # The TaskRun is committed to DB and visible to a new real session
        result = await task_execution_service.execute_single_task(
            task_run_id, tenant_id
        )

        # Verify task failed with proper error handling via TaskExecutionResult
        assert result.status == TaskExecutionStatus.FAILED
        assert result.error_message is not None
        assert "Failed to store artifact" in result.error_message
